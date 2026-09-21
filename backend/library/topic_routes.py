"""Topics API; x-api-key authentication is enforced by server.before_request."""

from flask import Blueprint, jsonify, request
from sqlalchemy import func, select

from library.db.engine import get_scoped_session
from library.db.models import Topic
from library import topic_service as svc

bp = Blueprint("topics", __name__)


@bp.errorhandler(ValueError)
def invalid_request(exc):
    get_scoped_session().rollback()
    return jsonify(status="error", message=str(exc)), 400


def _body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValueError("Request body must be a JSON object")
    return data


def _missing():
    return jsonify(status="error", message="Topic not found"), 404


@bp.get("/topics")
def topics_list():
    session = get_scoped_session()
    include_archived = request.args.get("include_archived") in {"1", "true", "yes"}
    limit = int(request.args.get("limit", "50"))
    offset = int(request.args.get("offset", "0"))
    if not 1 <= limit <= 100 or offset < 0:
        raise ValueError("limit must be between 1 and 100; offset must be non-negative")
    stmt = select(Topic)
    if not include_archived:
        stmt = stmt.where(Topic.archived_at.is_(None))
    total = session.scalar(select(func.count()).select_from(stmt.subquery()))
    topics = session.scalars(stmt.order_by(func.lower(Topic.name), Topic.id).limit(limit).offset(offset)).all()
    return jsonify(status="success", topics=[svc.topic_to_dict(topic) for topic in topics], total=total)


@bp.post("/topics")
def topics_create():
    data = _body()
    topic = svc.create_topic(get_scoped_session(), data.get("name"), data.get("description"))
    return jsonify(status="success", topic=svc.topic_to_dict(topic)), 201


@bp.get("/topics/<int:topic_id>")
def topics_detail(topic_id):
    topic = svc.get_topic_detail(get_scoped_session(), topic_id)
    return jsonify(status="success", topic=topic) if topic else _missing()


@bp.patch("/topics/<int:topic_id>")
def topics_update(topic_id):
    topic = svc.update_topic(get_scoped_session(), topic_id, _body())
    return jsonify(status="success", topic=svc.topic_to_dict(topic)) if topic else _missing()


@bp.post("/topics/<int:topic_id>/items")
def topics_add_item(topic_id):
    session = get_scoped_session()
    if svc.get_topic(session, topic_id) is None:
        return _missing()
    data = _body()
    item = svc.add_item(session, topic_id, data.get("entity_type"), data.get("entity_id"), data.get("note"))
    return jsonify(status="success", item=svc.item_to_dict(item)), 201


@bp.delete("/topic_items/<int:item_id>")
def topics_remove_item(item_id):
    if not svc.remove_item(get_scoped_session(), item_id):
        return jsonify(status="error", message="Topic item not found"), 404
    return jsonify(status="success")
