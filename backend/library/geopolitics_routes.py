"""Flask blueprint: geopolitical events and directed country relations (ADR-033).

Endpoints (x-api-key required via the global before_request; writes are blocked for
read_only keys there):
  GET  /countries                              — country dictionary
  GET  /geopolitics/axes                       — axes with their score scales
  GET  /geo_events?status=&country=&limit=&offset=
  POST /geo_events                             — manual event {title, event_date, participants[], source?}
  PATCH /geo_events/<id>                       — {status: confirmed|rejected}
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
    resolve_country,
    set_event_status,
)

logger = logging.getLogger(__name__)

bp = Blueprint("geopolitics", __name__)


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
            limit=_int_arg("limit", 50, 200) or 50,
            offset=_int_arg("offset", 0, 1_000_000),
        )
    except GeopoliticsError as exc:
        return _error(exc)
    return jsonify({"status": "success", "total": total, "events": [event_to_dict(e) for e in events]})


@bp.route("/geo_events", methods=["POST"])
def add_geo_event():
    session = get_scoped_session()
    data = request.get_json(silent=True) or {}
    participants = []
    for entry in data.get("participants") or []:
        if not isinstance(entry, dict):
            return jsonify({"status": "error", "message": "participants must be objects"}), 400
        participants.append((entry.get("country"), entry.get("role")))
    try:
        event, created = create_event(
            session,
            title=data.get("title"),
            description=data.get("description"),
            event_date=data.get("event_date"),
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


@bp.route("/geo_events/<int:event_id>", methods=["PATCH"])
def patch_geo_event(event_id: int):
    session = get_scoped_session()
    event = session.get(GeoEvent, event_id)
    if event is None:
        return jsonify({"status": "error", "message": "Event not found"}), 404
    data = request.get_json(silent=True) or {}
    try:
        set_event_status(session, event, data.get("status"), _user_id())
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


@bp.route("/document/<int:doc_id>/geopolitics/detect", methods=["POST"])
def detect_document_geopolitics(doc_id: int):
    from library.geopolitics_detect import detect_for_document
    from library.llm_model_registry import is_selectable

    session = get_scoped_session()
    data = request.get_json(silent=True) or {}
    model = data.get("model")
    if model is not None and (not isinstance(model, str) or not is_selectable(model)):
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
