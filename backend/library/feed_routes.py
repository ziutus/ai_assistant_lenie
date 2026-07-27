"""REST API for feed configuration, curation and explicit jobs."""

import datetime as dt
from zoneinfo import ZoneInfo
from flask import Blueprint, abort, g, jsonify, request
from sqlalchemy import select, case
from library.db.engine import get_scoped_session
from library.db.models import FeedSource, FeedItem, Job
from library.feed_source_service import list_feeds, feed_to_dict, resolve_references
from library.feed_monitor_service import transition_item, save_review_note, import_feed_item, ignore_feed_item
from library.job_queue import enqueue, retry, cancel

bp = Blueprint("feeds", __name__)


def _user():
    if getattr(g, "auth", None) is None or g.auth.kind != "user":
        abort(403, "user API key required")
    return g.auth.user_id


def _service():
    if getattr(g, "auth", None) is None or g.auth.kind != "service":
        abort(403, "service API key required")


def _item_dict(item):
    return {
        "id": item.id,
        "feed_source_id": item.feed_source_id,
        "url": item.url,
        "canonical_url": item.canonical_url,
        "title": item.title,
        "summary": item.summary,
        "published_at": item.published_at.isoformat() if item.published_at else None,
        "status": item.status,
        "saved_at": item.saved_at.isoformat() if item.saved_at else None,
        "saved_by_user_id": item.saved_by_user_id,
        "document_id": item.document_id,
        "review_note": item.review_note,
        "review_reason": item.review_reason,
        "ignored_pattern": item.ignored_pattern,
        "first_seen_at": item.first_seen_at.isoformat() if item.first_seen_at else None,
    }


@bp.get("/feed_sources")
def get_feeds():
    _user()
    session = get_scoped_session()
    return jsonify({"feed_sources": [feed_to_dict(f) for f in list_feeds(session)]})


@bp.get("/feed_sources/<int:feed_id>")
def get_feed(feed_id):
    _user()
    feed = get_scoped_session().get(FeedSource, feed_id)
    if feed is None:
        abort(404)
    return jsonify(feed_to_dict(feed))


@bp.post("/feed_sources")
def create_feed():
    _service()
    session = get_scoped_session()
    values = resolve_references(session, request.get_json(silent=True) or {})
    if "name" not in values:
        abort(400, "name is required")
    row = FeedSource(**values)
    session.add(row)
    session.commit()
    return jsonify(feed_to_dict(row)), 201


@bp.patch("/feed_sources/<int:feed_id>")
def update_feed(feed_id):
    # Feed configuration is edited from the authenticated personal web panel.
    _user()
    session = get_scoped_session()
    row = session.get(FeedSource, feed_id)
    if row is None:
        abort(404)
    body = request.get_json(silent=True) or {}
    allowed = {"type", "url", "channel_id", "language", "tags", "auto_import", "disabled", "auto_import_after", "default_state", "field_mapping", "skip_url_patterns", "skip_title_patterns"}
    if not isinstance(body, dict) or any(key not in allowed for key in body):
        abort(400, "unsupported feed field")
    merged = {key: getattr(row, key) for key in allowed if hasattr(row, key)}
    merged.update(body)
    if isinstance(merged.get("auto_import_after"), str):
        try:
            merged["auto_import_after"] = dt.datetime.fromisoformat(merged["auto_import_after"].replace("Z", "+00:00")) if merged["auto_import_after"] else None
        except ValueError:
            abort(400, "auto_import_after must be an ISO timestamp")
    values = resolve_references(session, merged)
    values.pop("name", None)
    for key, value in values.items():
        setattr(row, key, value)
    row.updated_at = dt.datetime.now(dt.timezone.utc)
    session.commit()
    return jsonify(feed_to_dict(row))


@bp.post("/feed_sources/<int:feed_id>/check")
def check_feed(feed_id):
    user_id = _user()
    session = get_scoped_session()
    if session.get(FeedSource, feed_id) is None:
        abort(404)
    active = session.scalars(
        select(Job).where(
            Job.type == "feed_check",
            Job.status.in_(["queued", "running"]),
            Job.parameters["feed_source_id"].as_integer() == feed_id,
        )
    ).first()
    job = active or enqueue(session, "feed_check", {"feed_source_id": feed_id}, user_id=user_id)
    return jsonify({"job": {"id": job.id, "type": job.type, "status": job.status}}), 202


@bp.get("/feed_items")
def get_items():
    _user()
    session = get_scoped_session()
    status = request.args.get("status")
    order = [FeedItem.published_at.desc().nulls_last(), FeedItem.first_seen_at.desc()]
    if status == "saved_for_later":
        order = [
            case((FeedItem.saved_at.is_(None), 1), else_=0),
            FeedItem.saved_at.desc(),
            FeedItem.first_seen_at.desc(),
        ]
    query = select(FeedItem).order_by(*order)
    if status:
        query = query.where(FeedItem.status == status)
    if request.args.get("feed_source_id"):
        query = query.where(FeedItem.feed_source_id == int(request.args["feed_source_id"]))
    limit = min(max(int(request.args.get("limit", 50)), 1), 200)
    offset = max(int(request.args.get("offset", 0)), 0)
    return jsonify(
        {
            "feed_items": [_item_dict(x) for x in session.scalars(query.offset(offset).limit(limit)).all()],
            "limit": limit,
            "offset": offset,
        }
    )


@bp.get("/feed_items/<int:item_id>")
def get_item(item_id):
    _user()
    item = get_scoped_session().get(FeedItem, item_id)
    if item is None:
        abort(404)
    return jsonify(_item_dict(item))


@bp.post("/feed_items/<int:item_id>/import")
def import_item(item_id):
    _user()
    session = get_scoped_session()
    try:
        item, doc = import_feed_item(item_id, session)
        item.reviewed_by_user_id = g.auth.user_id
        item.reviewed_at = dt.datetime.now(dt.timezone.utc)
        session.commit()
        item = session.get(FeedItem, item_id)
        return jsonify({"feed_item": _item_dict(item), "document_id": doc.id})
    except ValueError as exc:
        abort(400, str(exc))
    except RuntimeError as exc:
        abort(409, str(exc))


@bp.post("/feed_items/<int:item_id>/skip")
def skip_item(item_id):
    body = request.get_json(silent=True) or {}
    try:
        item = transition_item(get_scoped_session(), item_id, "skipped", _user(), body.get("reason"))
    except ValueError as exc:
        abort(400 if str(exc) == "invalid review reason" else 404, str(exc))
    except RuntimeError as exc:
        abort(409, str(exc))
    return jsonify(_item_dict(item))


@bp.post("/feed_items/<int:item_id>/save-for-later")
def save_for_later(item_id):
    try:
        item = transition_item(get_scoped_session(), item_id, "saved_for_later", _user())
    except ValueError as exc:
        abort(404, str(exc))
    except RuntimeError as exc:
        abort(409, str(exc))
    return jsonify(_item_dict(item))


@bp.post("/feed_items/<int:item_id>/restore")
def restore_item(item_id):
    try:
        item = transition_item(get_scoped_session(), item_id, "new", _user())
    except ValueError as exc:
        abort(404, str(exc))
    except RuntimeError as exc:
        abort(409, str(exc))
    return jsonify(_item_dict(item))


@bp.post("/feed_items/<int:item_id>/ignore")
def ignore_item(item_id):
    body = request.get_json(silent=True) or {}
    try:
        item = ignore_feed_item(
            get_scoped_session(), item_id, body.get("field", "title"), body.get("pattern", ""), _user()
        )
    except ValueError as exc:
        abort(400, str(exc))
    return jsonify(_item_dict(item))


@bp.patch("/feed_items/<int:item_id>/note")
def note_item(item_id):
    _user()
    return jsonify(
        _item_dict(
            save_review_note(get_scoped_session(), item_id, (request.get_json(silent=True) or {}).get("note", ""))
        )
    )


@bp.get("/jobs")
def get_jobs():
    _user()
    session = get_scoped_session()
    return jsonify(
        {
            "jobs": [
                {
                    "id": x.id,
                    "type": x.type,
                    "status": x.status,
                    "parameters": x.parameters,
                    "progress": x.progress,
                    "result": x.result,
                    "error": x.error,
                    "attempt": x.attempt,
                }
                for x in session.scalars(select(Job).order_by(Job.created_at.desc()).limit(200)).all()
            ]
        }
    )


@bp.get("/jobs/<job_id>")
def get_job(job_id):
    _user()
    job = get_scoped_session().get(Job, job_id)
    if job is None:
        abort(404)
    return jsonify(
        {
            "id": job.id,
            "type": job.type,
            "status": job.status,
            "parameters": job.parameters,
            "progress": job.progress,
            "result": job.result,
            "error": job.error,
            "attempt": job.attempt,
            "max_attempts": job.max_attempts,
        }
    )


@bp.post("/jobs")
def create_job():
    _service()
    session = get_scoped_session()
    body = request.get_json(silent=True) or {}
    typ = body.get("type")
    parameters = body.get("parameters") or {}
    if not isinstance(parameters, dict):
        abort(400, "parameters must be an object")
    if typ in {"feed_check", "feed_auto_import"}:
        if set(parameters) != {"feed_source_id"} or not isinstance(parameters.get("feed_source_id"), int):
            abort(400, "this job requires only integer feed_source_id")
    elif typ in {"feed_check_all", "feed_daily"} and parameters:
        abort(400, "this job type does not accept parameters")
    if typ == "feed_daily":
        key = f"feed_daily:{dt.datetime.now(dt.timezone.utc).astimezone(ZoneInfo('Europe/Warsaw')).date().isoformat()}"
    else:
        key = None
    try:
        job = enqueue(session, typ, parameters, idempotency_key=key)
    except ValueError as exc:
        abort(400, str(exc))
    return jsonify({"id": job.id, "status": job.status}), 202


@bp.post("/jobs/<job_id>/retry")
def retry_job(job_id):
    _service()
    session = get_scoped_session()
    job = session.get(Job, job_id)
    if job is None:
        abort(404)
    try:
        retry(session, job)
    except RuntimeError as exc:
        abort(409, str(exc))
    return jsonify({"id": job.id, "status": job.status})


@bp.post("/jobs/<job_id>/cancel")
def cancel_job(job_id):
    _service()
    session = get_scoped_session()
    job = session.get(Job, job_id)
    if job is None:
        abort(404)
    try:
        cancel(session, job)
    except RuntimeError as exc:
        abort(409, str(exc))
    return jsonify({"id": job.id, "status": job.status})
