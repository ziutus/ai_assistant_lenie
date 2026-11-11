"""Flask blueprint: the world-events registry views and named-event mention decisions (ADR-034).

Endpoints (x-api-key required via the global before_request; writes are blocked for read_only keys there):
  GET  /geo_event_kinds, /geo_event_roles            — dictionaries with Polish labels (kinds: DB table only)
  POST /geo_event_kinds                              — {code, label, sort_order?}: add a kind, service key
  GET  /world_events?q=&kind=&status=&country=&with_countries=&limit=&offset=
                                                     — canonical events with the documents that mention them
  GET  /world_events/unlinked?q=&limit=&offset=      — named-event mentions not linked to any event, with suggestions
  GET  /world_events/candidates?name=                — events a name may mean (alias first, then similar)
  POST /world_events/mentions/link                   — {name, event_id, document_ids?}
  POST /world_events/mentions/reject                 — {name, event_id}: do not suggest this event for this name
  POST /world_events/mentions/unlink                 — {name, event_id, document_id?}
  POST /world_events/from_mention                    — {name, kind?, event_date?, description?}: create + link
  POST /document_events/<id>/to_world_event          — {event_id?, title?, kind?}: timeline entry -> event / source
  POST /document_events/<id>/ignore                  — {ignored?: true}: dismiss a proposal that is no event (false
                                                       restores it); a re-detection keeps it hidden
  POST /document_events/<id>/to_information_source   — {name?, source_type?, role?}: the entry is a publication
                                                       (study, report, book), so it becomes an approved information
                                                       source of the document and leaves the timeline
"""

import logging

from flask import Blueprint, g, jsonify, request

from library.db.engine import get_scoped_session
from library.db.models import GeoEventKind
from library.geo_event_kind_store import bust_cache, check_kind, list_kinds
from library.document_event_sources import convert_document_event_to_source, set_document_event_ignored
from library.geopolitics_service import GeopoliticsError, event_to_dict, resolve_country
from library.world_events_service import (
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


@bp.route("/web_search/credits", methods=["GET"])
def web_search_credits():
    from library import web_search_client as client

    result = {}
    for name, call, empty in (
        ("serper", client.serper_account, {"credits_left": None}),
        ("firecrawl", client.firecrawl_credits, {"remaining": None, "plan": None}),
    ):
        try:
            result[name] = call()
        except Exception:
            result[name] = {**empty, "error": "Nie można odczytać pozostałych kredytów"}
    return jsonify(result)


@bp.route("/geo_events/web_enrich/model", methods=["GET", "PUT"])
def web_enrich_model():
    from library import app_settings, world_event_web_enrich as service
    from library.llm_model_registry import is_selectable, selectable_models

    session = get_scoped_session()
    if request.method == "PUT":
        body = request.get_json(silent=True)
        if not isinstance(body, dict) or "model" not in body:
            return _error(GeopoliticsError("Podaj model"))
        model = body["model"]
        if model is not None and (not isinstance(model, str) or not is_selectable(model, service.TASK)):
            return _error(GeopoliticsError("Niedostępny model"))
        app_settings.set_setting(session, service.SETTING_KEY, model)
    return jsonify(
        {
            "default_model": service.default_model(session),
            "saved": app_settings.get_setting(session, service.SETTING_KEY) is not None,
            "models": selectable_models(service.TASK),
        }
    )


def _web_enrich(event_id, *, estimate_only):
    from library import world_event_web_enrich as service
    from library.llm_model_registry import is_selectable
    from library.web_search_client import WebSearchUnavailable

    session = get_scoped_session()
    try:
        body = request.get_json(silent=True)
        if body is None:
            body = {}
        if not isinstance(body, dict):
            raise GeopoliticsError("Oczekiwano obiektu JSON")
        step = body.get("step", "wikipedia")
        service._check_step(step)
        with_wikipedia = body.get("with_wikipedia", False)
        if not isinstance(with_wikipedia, bool):
            raise GeopoliticsError("with_wikipedia musi być wartością logiczną")
        pages = body.get("scrape_pages", 2)
        if type(pages) is not int or not 0 <= pages <= 4:
            raise GeopoliticsError("Liczba stron musi być liczbą całkowitą od 0 do 4")
        model = body.get("model")
        if model is None:
            model = service.default_model(session)
        if not isinstance(model, str) or not is_selectable(model, service.TASK):
            raise GeopoliticsError("Niedostępny model")
        if estimate_only:
            result = service.estimate(session, event_id, model=model, scrape_pages=pages, step=step)
        else:
            result = service.enrich(
                session,
                event_id,
                model=model,
                scrape_pages=pages,
                user_id=_user_id(),
                step=step,
                with_wikipedia=with_wikipedia,
            )
        return jsonify(result)
    except GeopoliticsError as exc:
        return _error(exc)
    except WebSearchUnavailable:
        logger.warning("web search provider unavailable")
        return jsonify({"status": "error", "message": "Wyszukiwarka internetowa jest niedostępna (brak klucza lub błąd dostawcy)"}), 503


@bp.route("/geo_events/<int:event_id>/web_enrich/estimate", methods=["POST"])
def estimate_web_enrich(event_id):
    return _web_enrich(event_id, estimate_only=True)


@bp.route("/geo_events/<int:event_id>/web_enrich", methods=["POST"])
def run_web_enrich(event_id):
    return _web_enrich(event_id, estimate_only=False)


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
    """The kinds come only from the ``geo_event_kinds`` table (offline seed when it cannot be read)."""
    kinds = list_kinds(get_scoped_session())
    return jsonify(
        {"status": "success", "kinds": [{"code": k.code, "label": k.label, "sort_order": k.sort_order} for k in kinds]}
    )


@bp.route("/geo_event_kinds", methods=["POST"])
def add_event_kind():
    """Add a kind without a deploy (service key): ``{code, label, sort_order?}``."""
    if getattr(getattr(g, "auth", None), "kind", None) != "service":
        return jsonify({"status": "error", "message": "Dodanie typu wydarzenia wymaga klucza service"}), 403
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"status": "error", "message": "Wymagany obiekt JSON"}), 400
    values, problem = check_kind(
        code=data.get("code"), label=data.get("label"), sort_order=data.get("sort_order", 100)
    )
    if problem:
        return jsonify({"status": "error", "message": problem}), 400
    session = get_scoped_session()
    if session.get(GeoEventKind, values["code"]) is not None:
        return jsonify({"status": "error", "message": "Typ o tym kodzie już istnieje"}), 409
    try:
        session.add(GeoEventKind(**values))
        session.commit()
    except Exception:
        session.rollback()
        raise
    bust_cache()
    return jsonify({"status": "success", "kind": values}), 201


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


@bp.route("/document_events/<int:document_event_id>/ignore", methods=["POST"])
def timeline_entry_ignore(document_event_id: int):
    """Dismiss a timeline proposal that is no event (or bring it back with ``{"ignored": false}``)."""
    session = get_scoped_session()
    data = request.get_json(silent=True) or {}
    try:
        result = set_document_event_ignored(session, document_event_id, bool(data.get("ignored", True)))
        session.commit()
    except GeopoliticsError as exc:
        session.rollback()
        return _error(exc)
    return jsonify({"status": "success", **result}), 200


@bp.route("/document_events/<int:document_event_id>/to_information_source", methods=["POST"])
def timeline_entry_to_information_source(document_event_id: int):
    """The entry only reports a publication (a study, report, book): it is a source, not a world event."""
    session = get_scoped_session()
    data = request.get_json(silent=True) or {}
    try:
        result = convert_document_event_to_source(
            session,
            document_event_id,
            name=data.get("name"),
            source_type=data.get("source_type"),
            role=data.get("role"),
        )
        session.commit()
    except GeopoliticsError as exc:
        session.rollback()
        return _error(exc)
    return jsonify({"status": "success", **result}), 201 if result["created"] else 200
