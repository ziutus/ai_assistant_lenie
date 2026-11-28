"""Entity relation REST API; global authentication accepts user and service keys."""

import logging

from flask import Blueprint, g, jsonify, request
from werkzeug.exceptions import HTTPException

from library.db.engine import get_scoped_session
from library.db.models import Document, EntityRelation, Organization, Person
from library import entity_relations_service as service
from library.entity_relation_vocabulary import VOCABULARY, SYMMETRIC

bp = Blueprint("entity_relations", __name__)
logger = logging.getLogger(__name__)


def error(message, status):
    return jsonify(status="error", message=message), status


@bp.errorhandler(Exception)
def failure(exc):
    get_scoped_session().rollback()
    if isinstance(exc, HTTPException):
        return error("Invalid request", exc.code)
    if isinstance(exc, service.RelationError):
        return error("Invalid relation data", 400)
    if isinstance(exc, LookupError):
        return error("Entity not found", 404)
    from library.wikidata_relations import WikidataError
    if isinstance(exc, WikidataError):
        return error("Wikidata request failed", 503)
    logger.exception("Entity relation request failed")
    return error("Relation request failed", 500)


def body():
    value = request.get_json(silent=True)
    if not isinstance(value, dict):
        raise service.RelationError("JSON object required")
    return value


def user_id():
    return getattr(getattr(g, "auth", None), "user_id", None)


def require(model, identifier):
    row = get_scoped_session().get(model, identifier)
    if row is None:
        raise LookupError("Not found")
    return row


@bp.get("/entity_relations/vocabulary")
def vocabulary():
    return jsonify(status="success", vocabulary=[
        {"value": code, "label": data[0], "inverse_label": data[1],
         "pairs": [{"subject": a, "object": b} for a, b in data[2]], "symmetric": code in SYMMETRIC}
        for code, data in VOCABULARY.items()])


@bp.get("/persons/<int:identifier>/relations")
def person_relations(identifier):
    require(Person, identifier)
    return jsonify(status="success", relations=service.relations_for_person(
        get_scoped_session(), identifier, request.args.get("include_rejected") == "1"))


@bp.get("/organizations/<int:identifier>/relations")
def organization_relations(identifier):
    require(Organization, identifier)
    return jsonify(status="success", relations=service.relations_for_organization(
        get_scoped_session(), identifier, request.args.get("include_rejected") == "1"))


@bp.get("/document/<int:identifier>/relations")
def document_relations(identifier):
    require(Document, identifier)
    return jsonify(status="success", relations=service.relations_for_document(
        get_scoped_session(), identifier, request.args.get("include_rejected") == "1"))


@bp.post("/entity_relations")
def create():
    data = body()
    if set(data) - {"subject", "relation", "object", "title", "valid_from", "valid_to"}:
        raise service.RelationError("Invalid fields")
    session = get_scoped_session()
    row, created = service.manual_create(
        session, data.get("subject"), data.get("relation"), data.get("object"), user_id=user_id(),
        **{k: data[k] for k in ("title", "valid_from", "valid_to") if k in data})
    session.commit()
    return jsonify(status="success", created=created, relation=service.relation_dict(session, row)), 201 if created else 200


@bp.patch("/entity_relations/<int:identifier>")
def patch(identifier):
    row = require(EntityRelation, identifier)
    data = body()
    if not data or set(data) - {"status", "title", "valid_from", "valid_to"}:
        raise service.RelationError("Invalid fields")
    session = get_scoped_session()
    service.edit_relation(session, row, **{k: v for k, v in data.items() if k != "status"})
    if "status" in data:
        service.decide_relation(session, row, data["status"], user_id())
    session.commit()
    return jsonify(status="success", relation=service.relation_dict(session, row))


@bp.delete("/entity_relations/<int:identifier>")
def delete(identifier):
    row = require(EntityRelation, identifier)
    session = get_scoped_session()
    service.delete_relation(session, row)
    session.commit()
    return jsonify(status="success", deleted_id=identifier)


@bp.route("/relation_extraction/model", methods=["GET", "PUT"])
def model_setting():
    from library import app_settings
    from library.entity_relations_detect import SETTING_KEY, TASK, default_model
    from library.llm_model_registry import is_selectable, selectable_models
    session = get_scoped_session()
    if request.method == "PUT":
        data = body()
        model = data.get("model")
        if set(data) != {"model"} or model is not None and (
                not isinstance(model, str) or not is_selectable(model, TASK)):
            return error("Model is not available", 400)
        app_settings.set_setting(session, SETTING_KEY, model)
        return jsonify(status="success", default_model=default_model(session), saved=model is not None)
    return jsonify(status="success", default_model=default_model(session),
                   saved=isinstance(app_settings.get_setting(session, SETTING_KEY), str), models=selectable_models(TASK))


@bp.post("/document/<int:identifier>/relations/detect")
def detect(identifier):
    from library.document_busy import DocumentBusy, busy_response, claim_document
    from library.entity_relations_detect import TASK, detect_for_document
    from library.llm_model_registry import is_selectable
    require(Document, identifier)
    data = body()
    model = data.get("model")
    if set(data) - {"model"} or model is not None and (
            not isinstance(model, str) or not is_selectable(model, TASK)):
        return error("Model is not available", 400)
    session = get_scoped_session()
    try:
        with claim_document(identifier, "ekstrakcja relacji"):
            result = detect_for_document(session, identifier, model=model)
            session.commit()
    except DocumentBusy as busy:
        response, status = busy_response(busy)
        response["message"] = "Document is busy; retry when the current operation finishes"
        return jsonify(response), status
    return jsonify(status="success", **result)


@bp.post("/persons/<int:identifier>/relations/wikidata")
def wikidata(identifier):
    from library.wikidata_relations import propose_for_person
    require(Person, identifier)
    session = get_scoped_session()
    result = propose_for_person(session, identifier)
    session.commit()
    return jsonify(status="success", **result)
