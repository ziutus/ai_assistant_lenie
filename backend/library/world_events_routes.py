"""Flask blueprint: the world-events registry views and named-event mention decisions (ADR-034).

Endpoints (x-api-key required via the global before_request; writes are blocked for read_only keys there):
  GET  /geo_event_kinds, /geo_event_roles            — dictionaries with Polish labels
  GET  /world_events?q=&kind=&status=&country=&with_countries=&limit=&offset=
                                                     — canonical events with the documents that mention them
  GET  /world_events/unlinked?q=&limit=&offset=      — named-event mentions not linked to any event, with suggestions
  GET  /world_events/candidates?name=                — events a name may mean (alias first, then similar)
  POST /world_events/mentions/link                   — {name, event_id, document_ids?}
  POST /world_events/mentions/reject                 — {name, event_id}: do not suggest this event for this name
  POST /world_events/mentions/unlink                 — {name, event_id, document_id?}
  POST /world_events/from_mention                    — {name, kind?, event_date?, description?}: create + link
  POST /document_events/<id>/to_world_event          — {event_id?, title?, kind?}: timeline entry -> event / source
"""

import logging

from flask import Blueprint, g, jsonify, request

from library.db.engine import get_scoped_session
from library.geopolitics_service import GeopoliticsError, event_to_dict, resolve_country
from library.world_events_service import (
    KIND_LABELS,
    ROLE_LABELS,
    create_event_from_mention,
    find_events_by_name,
    link_mentions,
    promote_document_event,
    reject_suggestion,
    unlink_mentions,
    unlinked_mentions,
    world_events_index,
)

logger = logging.getLogger(__name__)

bp = Blueprint("world_events", __name__)


@bp.errorhandler(Exception)
def _unexpected_error(exc):
    """JSON for an unexpected failure (class name only, details in the log), so the browser shows a reason."""
    from werkzeug.exceptions import HTTPException

    if isinstance(exc, HTTPException):
        return exc
    logger.exception("world events request failed")
    return jsonify(
        {"status": "error", "message": f"Błąd serwera ({type(exc).__name__}); szczegóły w logu backendu"}
    ), 500


def _user_id() -> int | None:
    return getattr(getattr(g, "auth", None), "user_id", None)


def _error(exc: GeopoliticsError):
    return jsonify({"status": "error", "message": exc.message}), exc.status


def _int_arg(name: str, default: int, maximum: int) -> int:
    try:
        return max(0, min(int(request.args.get(name, default)), maximum))
    except (TypeError, ValueError):
        return default


def _flag(name: str) -> bool | None:
    value = request.args.get(name)
    if value in ("1", "true", "yes"):
        return True
    if value in ("0", "false", "no"):
        return False
    return None


@bp.route("/geo_event_kinds", methods=["GET"])
def get_event_kinds():
    return jsonify({"status": "success", "kinds": [{"code": c, "label": label} for c, label in KIND_LABELS.items()]})


@bp.route("/geo_event_roles", methods=["GET"])
def get_event_roles():
    return jsonify({"status": "success", "roles": [{"code": c, "label": label} for c, label in ROLE_LABELS.items()]})


@bp.route("/world_events", methods=["GET"])
def get_world_events():
    session = get_scoped_session()
    try:
        country_id = None
        if request.args.get("country"):
            ref = request.args["country"]
            country_id = resolve_country(session, int(ref) if ref.isdigit() else ref).id
        items, total = world_events_index(
            session,
            q=request.args.get("q") or None,
            kind=request.args.get("kind") or None,
            status=request.args.get("status") or None,
            with_countries=_flag("with_countries"),
            country_id=country_id,
            limit=_int_arg("limit", 50, 200) or 50,
            offset=_int_arg("offset", 0, 1_000_000),
        )
    except GeopoliticsError as exc:
        return _error(exc)
    return jsonify({"status": "success", "total": total, "events": items})


@bp.route("/world_events/unlinked", methods=["GET"])
def get_unlinked_mentions():
    session = get_scoped_session()
    items, total = unlinked_mentions(
        session,
        q=request.args.get("q") or None,
        limit=_int_arg("limit", 50, 200) or 50,
        offset=_int_arg("offset", 0, 1_000_000),
    )
    return jsonify({"status": "success", "total": total, "mentions": items})


@bp.route("/world_events/candidates", methods=["GET"])
def get_event_candidates():
    name = (request.args.get("name") or "").strip()
    if not name:
        return jsonify({"status": "error", "message": "name is required"}), 400
    return jsonify({"status": "success", "candidates": find_events_by_name(get_scoped_session(), name)})


def _body_name_and_event():
    data = request.get_json(silent=True) or {}
    name, event_id = data.get("name"), data.get("event_id")
    if not isinstance(name, str) or not name.strip():
        raise GeopoliticsError("name is required")
    if not isinstance(event_id, int) or isinstance(event_id, bool):
        raise GeopoliticsError("event_id must be an integer")
    return data, name, event_id


@bp.route("/world_events/mentions/link", methods=["POST"])
def link_event_mentions():
    session = get_scoped_session()
    try:
        data, name, event_id = _body_name_and_event()
        document_ids = data.get("document_ids")
        if document_ids is not None and not (
            isinstance(document_ids, list) and all(isinstance(i, int) for i in document_ids)
        ):
            raise GeopoliticsError("document_ids must be a list of integers")
        linked = link_mentions(session, name, event_id, document_ids=document_ids, user_id=_user_id())
        session.commit()
    except GeopoliticsError as exc:
        session.rollback()
        return _error(exc)
    return jsonify({"status": "success", "linked_documents": linked})


@bp.route("/world_events/mentions/reject", methods=["POST"])
def reject_event_suggestion():
    session = get_scoped_session()
    try:
        _data, name, event_id = _body_name_and_event()
        changed = reject_suggestion(session, name, event_id, user_id=_user_id())
        session.commit()
    except GeopoliticsError as exc:
        session.rollback()
        return _error(exc)
    return jsonify({"status": "success", "rejected_documents": changed})


@bp.route("/world_events/mentions/unlink", methods=["POST"])
def unlink_event_mentions():
    session = get_scoped_session()
    try:
        data, name, event_id = _body_name_and_event()
        removed = unlink_mentions(session, name, event_id, document_id=data.get("document_id"))
        session.commit()
    except GeopoliticsError as exc:
        session.rollback()
        return _error(exc)
    return jsonify({"status": "success", "removed": removed})


@bp.route("/world_events/from_mention", methods=["POST"])
def event_from_mention():
    session = get_scoped_session()
    data = request.get_json(silent=True) or {}
    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        return jsonify({"status": "error", "message": "name is required"}), 400
    try:
        event, created, linked = create_event_from_mention(
            session,
            name,
            kind=data.get("kind") or "other",
            event_date=data.get("event_date"),
            description=data.get("description"),
            user_id=_user_id(),
        )
        session.commit()
    except GeopoliticsError as exc:
        session.rollback()
        return _error(exc)
    session.refresh(event)
    body = {"status": "success", "created": created, "linked_documents": linked, "event": event_to_dict(event)}
    return jsonify(body), 201 if created else 200


@bp.route("/document_events/<int:document_event_id>/to_world_event", methods=["POST"])
def timeline_entry_to_event(document_event_id: int):
    session = get_scoped_session()
    data = request.get_json(silent=True) or {}
    try:
        event, created = promote_document_event(
            session,
            document_event_id,
            event_id=data.get("event_id"),
            title=data.get("title"),
            kind=data.get("kind") or "other",
            user_id=_user_id(),
        )
        session.commit()
    except GeopoliticsError as exc:
        session.rollback()
        return _error(exc)
    session.refresh(event)
    return jsonify({"status": "success", "created": created, "event": event_to_dict(event)}), 201 if created else 200
