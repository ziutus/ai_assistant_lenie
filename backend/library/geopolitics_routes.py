"""Flask blueprint: world events and directed country relations (ADR-033, ADR-034).

Endpoints (x-api-key required via the global before_request; writes are blocked for
read_only keys there):
  GET  /countries                              — country dictionary
  GET  /geopolitics/axes                       — axes with their score scales
  GET  /geo_events?status=&country=&kind=&q=&with_countries=&undated=&limit=&offset=
  POST /geo_events                             — event {title, event_date?, kind?, participants[]?, aliases[]?, ...}
  GET  /geo_events/<id>
  PATCH /geo_events/<id>                       — {status} and/or {title, description, kind, event_date,
                                                 event_date_end, is_ongoing, expected_version}
  POST /geo_events/<id>/aliases, DELETE /geo_events/<id>/aliases/<alias_id>
  POST /geo_events/<id>/participants, DELETE /geo_events/<id>/participants   — {type, ref, role}
  GET  /country_relations?country=&at=&axis=&direction=from|to
  POST /country_relations                      — {from, to, axis, score, valid_from, ...}
  GET  /country_relations/<id>/history
  GET  /geopolitics/proposals                  — pending assessments with the one they replace
  POST /geopolitics/proposals/<id>/decision    — {decision: approve|reject, expected_version?}
  POST /document/<id>/geopolitics/detect       — LLM proposes events/relations; stores proposals only
"""

import datetime
import logging

from flask import Blueprint, g, jsonify, request

from library.db.engine import get_scoped_session
from library.db.models import GeoEvent
from library.geopolitics_service import (
    AXES,
    GeopoliticsError,
    add_alias,
    add_participant,
    assessment_history,
    assessment_to_dict,
    create_assessment,
    create_event,
    decide_assessment,
    event_to_dict,
    list_countries,
    list_events,
    list_proposals,
    relations_at,
    remove_alias,
    remove_participant,
    resolve_country,
    set_event_status,
    update_event,
)

logger = logging.getLogger(__name__)

bp = Blueprint("geopolitics", __name__)


@bp.errorhandler(Exception)
def _unexpected_error(exc):
    """Answer an unexpected failure with JSON the UI can show.

    Without this Flask's default 500 page carries no CORS headers, which a browser reports as a bare
    "Network Error". The exception class goes to the reader, the details only to the log.
    """
    from werkzeug.exceptions import HTTPException

    if isinstance(exc, HTTPException):
        return exc
    logger.exception("geopolitics request failed")
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


@bp.route("/countries", methods=["GET"])
def get_countries():
    return jsonify({"status": "success", "countries": list_countries(get_scoped_session())})


@bp.route("/geopolitics/axes", methods=["GET"])
def get_axes():
    return jsonify(
        {
            "status": "success",
            "axes": [
                {"value": key, "label": data["label"], "scale": {str(s): text for s, text in data["scale"].items()}}
                for key, data in AXES.items()
            ],
        }
    )


def _flag(name: str) -> bool | None:
    value = request.args.get(name)
    if value in ("1", "true", "yes"):
        return True
    if value in ("0", "false", "no"):
        return False
    return None


@bp.route("/geo_events", methods=["GET"])
def get_geo_events():
    session = get_scoped_session()
    try:
        country_id = None
        if request.args.get("country"):
            ref = request.args["country"]
            country_id = resolve_country(session, int(ref) if ref.isdigit() else ref).id
        events, total = list_events(
            session,
            status=request.args.get("status") or None,
            country_id=country_id,
            kind=request.args.get("kind") or None,
            q=request.args.get("q") or None,
            with_countries=_flag("with_countries"),
            undated=_flag("undated"),
            limit=_int_arg("limit", 50, 200) or 50,
            offset=_int_arg("offset", 0, 1_000_000),
        )
    except GeopoliticsError as exc:
        return _error(exc)
    return jsonify({"status": "success", "total": total, "events": [event_to_dict(e) for e in events]})


@bp.route("/geo_events/<int:event_id>", methods=["GET"])
def get_geo_event(event_id: int):
    event = get_scoped_session().get(GeoEvent, event_id)
    if event is None:
        return jsonify({"status": "error", "message": "Event not found"}), 404
    return jsonify({"status": "success", "event": event_to_dict(event)})


@bp.route("/geo_events", methods=["POST"])
def add_geo_event():
    session = get_scoped_session()
    data = request.get_json(silent=True) or {}
    participants = data.get("participants") or []
    if not isinstance(participants, list) or not all(isinstance(entry, dict) for entry in participants):
        return jsonify({"status": "error", "message": "participants must be a list of objects"}), 400
    aliases = data.get("aliases") or []
    if not isinstance(aliases, list) or not all(isinstance(alias, str) for alias in aliases):
        return jsonify({"status": "error", "message": "aliases must be a list of strings"}), 400
    try:
        event, created = create_event(
            session,
            title=data.get("title"),
            description=data.get("description"),
            event_date=data.get("event_date"),
            date_precision=data.get("date_precision"),
            event_date_end=data.get("event_date_end"),
            end_date_precision=data.get("end_date_precision"),
            is_ongoing=bool(data.get("is_ongoing")),
            kind=data.get("kind") or "other",
            aliases=aliases,
            participants=participants,
            source=data.get("source"),
            status="confirmed" if data.get("status") == "confirmed" else "proposed",
            user_id=_user_id(),
        )
        session.commit()
    except GeopoliticsError as exc:
        session.rollback()
        return _error(exc)
    session.refresh(event)
    return jsonify({"status": "success", "created": created, "event": event_to_dict(event)}), 201 if created else 200


_EDITABLE = ("title", "description", "kind", "event_date", "event_date_end", "is_ongoing")


@bp.route("/geo_events/<int:event_id>", methods=["PATCH"])
def patch_geo_event(event_id: int):
    session = get_scoped_session()
    event = session.get(GeoEvent, event_id)
    if event is None:
        return jsonify({"status": "error", "message": "Event not found"}), 404
    data = request.get_json(silent=True) or {}
    changes = {key: data[key] for key in _EDITABLE if key in data}
    try:
        if "status" in data:
            set_event_status(session, event, data.get("status"), _user_id())
        if changes:
            update_event(session, event, expected_version=data.get("expected_version"), **changes)
        elif "status" not in data:
            raise GeopoliticsError("nothing to change")
        session.commit()
    except GeopoliticsError as exc:
        session.rollback()
        return _error(exc)
    return jsonify({"status": "success", "event": event_to_dict(event)})


@bp.route("/geo_events/<int:event_id>/aliases", methods=["POST"])
def add_event_alias(event_id: int):
    session = get_scoped_session()
    event = session.get(GeoEvent, event_id)
    if event is None:
        return jsonify({"status": "error", "message": "Event not found"}), 404
    data = request.get_json(silent=True) or {}
    try:
        add_alias(session, event, data.get("alias") or "")
        session.commit()
    except GeopoliticsError as exc:
        session.rollback()
        return _error(exc)
    session.refresh(event)
    return jsonify({"status": "success", "event": event_to_dict(event)}), 201


@bp.route("/geo_events/<int:event_id>/aliases/<int:alias_id>", methods=["DELETE"])
def delete_event_alias(event_id: int, alias_id: int):
    session = get_scoped_session()
    event = session.get(GeoEvent, event_id)
    if event is None:
        return jsonify({"status": "error", "message": "Event not found"}), 404
    try:
        remove_alias(session, event, alias_id)
        session.commit()
    except GeopoliticsError as exc:
        session.rollback()
        return _error(exc)
    return jsonify({"status": "success", "event": event_to_dict(event)})


@bp.route("/geo_events/<int:event_id>/participants", methods=["POST"])
def add_event_participant(event_id: int):
    session = get_scoped_session()
    event = session.get(GeoEvent, event_id)
    if event is None:
        return jsonify({"status": "error", "message": "Event not found"}), 404
    try:
        add_participant(session, event, request.get_json(silent=True) or {})
        session.commit()
    except GeopoliticsError as exc:
        session.rollback()
        return _error(exc)
    return jsonify({"status": "success", "event": event_to_dict(event)}), 201


@bp.route("/geo_events/<int:event_id>/participants", methods=["DELETE"])
def delete_event_participant(event_id: int):
    session = get_scoped_session()
    event = session.get(GeoEvent, event_id)
    if event is None:
        return jsonify({"status": "error", "message": "Event not found"}), 404
    data = request.get_json(silent=True) or {}
    try:
        participant_id = data.get("id", data.get("ref"))
        if not isinstance(participant_id, int) or isinstance(participant_id, bool):
            raise GeopoliticsError("id must be the integer id of the participant")
        remove_participant(session, event, data.get("type") or "country", participant_id, data.get("role"))
        session.commit()
    except GeopoliticsError as exc:
        session.rollback()
        return _error(exc)
    return jsonify({"status": "success", "event": event_to_dict(event)})


@bp.route("/country_relations", methods=["GET"])
def get_country_relations():
    session = get_scoped_session()
    ref = request.args.get("country")
    if not ref:
        return jsonify({"status": "error", "message": "country is required"}), 400
    try:
        at = datetime.date.fromisoformat(request.args["at"]) if request.args.get("at") else datetime.date.today()
        country = resolve_country(session, int(ref) if ref.isdigit() else ref)
        relations = relations_at(
            session,
            country=country,
            at=at,
            axis=request.args.get("axis") or "political",
            direction=request.args.get("direction") or "from",
        )
    except ValueError:
        return jsonify({"status": "error", "message": "at must be YYYY-MM-DD"}), 400
    except GeopoliticsError as exc:
        return _error(exc)
    return jsonify(
        {
            "status": "success",
            "at": at.isoformat(),
            "country": {
                "id": country.id,
                "slug": country.slug,
                "name_pl": country.name_pl,
                "map_code": country.map_code,
            },
            "relations": relations,
        }
    )


@bp.route("/country_relations", methods=["POST"])
def add_country_relation():
    session = get_scoped_session()
    data = request.get_json(silent=True) or {}
    try:
        row = create_assessment(
            session,
            from_country=data.get("from"),
            to_country=data.get("to"),
            axis=data.get("axis"),
            score=data.get("score"),
            confidence=data.get("confidence"),
            valid_from=data.get("valid_from"),
            rationale=data.get("rationale"),
            event_ids=data.get("event_ids") or [],
            context_event_ids=data.get("context_event_ids") or [],
            status="confirmed" if data.get("status") == "confirmed" else "proposed",
            user_id=_user_id(),
        )
        session.commit()
    except GeopoliticsError as exc:
        session.rollback()
        return _error(exc)
    session.refresh(row)
    return jsonify({"status": "success", "assessment": assessment_to_dict(row, with_evidence=True)}), 201


@bp.route("/country_relations/<int:assessment_id>/history", methods=["GET"])
def get_relation_history(assessment_id: int):
    try:
        history = assessment_history(get_scoped_session(), assessment_id)
    except GeopoliticsError as exc:
        return _error(exc)
    return jsonify({"status": "success", "history": history})


@bp.route("/geopolitics/proposals", methods=["GET"])
def get_proposals():
    return jsonify({"status": "success", "proposals": list_proposals(get_scoped_session())})


@bp.route("/geopolitics/proposals/<int:assessment_id>/decision", methods=["POST"])
def decide_proposal(assessment_id: int):
    session = get_scoped_session()
    data = request.get_json(silent=True) or {}
    try:
        row = decide_assessment(
            session,
            assessment_id,
            decision=data.get("decision"),
            expected_version=data.get("expected_version"),
            user_id=_user_id(),
            approve_events=data.get("approve_events", True) is not False,
        )
        session.commit()
    except GeopoliticsError as exc:
        session.rollback()
        return _error(exc)
    session.refresh(row)
    return jsonify({"status": "success", "assessment": assessment_to_dict(row, with_evidence=True)})


@bp.route("/geopolitics/model", methods=["GET"])
def get_geopolitics_model():
    """Models offered for the analysis (with prices), the one in effect and whether it was chosen."""
    from library import app_settings
    from library.geopolitics_detect import SETTING_KEY, TASK, default_model
    from library.llm_model_registry import selectable_models

    session = get_scoped_session()
    return jsonify(
        {
            "status": "success",
            "default_model": default_model(session),
            "saved": isinstance(app_settings.get_setting(session, SETTING_KEY), str),
            "models": selectable_models(TASK),
        }
    )


@bp.route("/geopolitics/model", methods=["PUT"])
def put_geopolitics_model():
    """Set the default analysis model (``{"model": id}``); ``{"model": null}`` restores the built-in default."""
    from library import app_settings
    from library.geopolitics_detect import SETTING_KEY, TASK, default_model
    from library.llm_model_registry import is_selectable

    body = request.get_json(silent=True) or {}
    if "model" not in body:
        return jsonify({"status": "error", "message": "model is required"}), 400
    model = body["model"]
    if model is not None and (not isinstance(model, str) or not is_selectable(model, TASK)):
        return jsonify({"status": "error", "message": "Model is not available"}), 400
    session = get_scoped_session()
    app_settings.set_setting(session, SETTING_KEY, model)
    return jsonify({"status": "success", "default_model": default_model(session), "saved": model is not None})


@bp.route("/document/<int:doc_id>/geopolitics/detect", methods=["POST"])
def detect_document_geopolitics(doc_id: int):
    from library.geopolitics_detect import TASK, detect_for_document
    from library.llm_model_registry import is_selectable

    session = get_scoped_session()
    data = request.get_json(silent=True) or {}
    model = data.get("model")
    if model is not None and (not isinstance(model, str) or not is_selectable(model, TASK)):
        return jsonify({"status": "error", "message": "Model is not available"}), 400
    try:
        summary = detect_for_document(session, doc_id, model=model, user_id=_user_id())
        session.commit()
    except GeopoliticsError as exc:
        session.rollback()
        return _error(exc)
    except Exception:  # noqa: BLE001 - provider failures must not leak details
        session.rollback()
        logger.exception("geopolitics detection failed for document %s", doc_id)
        return jsonify({"status": "error", "message": "Detection failed"}), 503
    return jsonify({"status": "success", **summary})
