"""REST API for feed configuration, curation and explicit jobs."""

import datetime as dt
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from flask import Blueprint, abort, g, jsonify, request
from sqlalchemy import select, case, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from library.db.engine import get_scoped_session
from library.db.models import (
    ContentGroup, Document, DocumentAnalysisRun, DocumentChunk, DocumentChunkGroupMembership,
    FeedItemGroupMembership, FeedSource, FeedItem, FeedReviewDecision, Job, ScheduledTask,
)
from library.content_group_service import (
    archive_group,
    create_group,
    group_to_dict,
    replace_chunk_groups,
    replace_document_groups,
    replace_feed_item_groups,
    update_group,
)
from library.content_group_suggestion_service import decide_suggestion, request_suggestions
from library.db.models import ContentGroupSuggestionRun
from library.feed_source_service import list_feeds, feed_to_dict, resolve_references
from library.feed_monitor_service import transition_item, save_review_note, import_feed_item, ignore_feed_item, record_review_decision, new_review_batch_id
from library.job_queue import JOB_TYPES, enqueue, retry, cancel

bp = Blueprint("feeds", __name__)


def _user():
    if getattr(g, "auth", None) is None or g.auth.kind != "user":
        abort(403, "user API key required")
    return g.auth.user_id


def _service():
    if getattr(g, "auth", None) is None or g.auth.kind != "service":
        abort(403, "service API key required")


def _job_viewer() -> bool:
    if getattr(g, "auth", None) is None or g.auth.kind not in {"user", "service"}:
        abort(403, "user or service API key required")
    return g.auth.kind == "service"


def _job_capabilities() -> dict[str, bool]:
    """Return permitted job actions for the authenticated principal."""
    can_manage = _job_viewer()
    return {
        "manage_jobs": can_manage,
        "run_legacy_aws_pull": can_manage or g.auth.kind == "user",
        "run_feed_daily": can_manage or g.auth.kind == "user",
    }


def _timestamp(value):
    return value.isoformat() if value else None


def _job_dict(job: Job):
    result = job.result or {}
    return {
        "id": job.id,
        "type": job.type,
        "status": job.status,
        "parameters": job.parameters,
        "progress": job.progress,
        "result": job.result,
        "error": job.error,
        "attempt": job.attempt,
        "max_attempts": job.max_attempts,
        "created_at": _timestamp(job.created_at),
        "started_at": _timestamp(job.started_at),
        "finished_at": _timestamp(job.finished_at),
        "watermark": result.get("watermark") if isinstance(result, dict) else None,
    }


def _next_task_run(now: dt.datetime, timezone: ZoneInfo, times: list[str]) -> dt.datetime:
    """Return the next local scheduler tick from a task's configured times."""
    local_now = now.astimezone(timezone)
    candidates = []
    for time_text in times:
        hour, minute = map(int, time_text.split(":", 1))
        scheduled = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if scheduled <= local_now:
            scheduled += dt.timedelta(days=1)
        candidates.append(scheduled)
    return min(candidates)


def _validate_schedule(timezone_name: str, times: list) -> list[str]:
    try:
        ZoneInfo(timezone_name)
        normalized = sorted({f"{int(value.split(':', 1)[0]):02d}:{int(value.split(':', 1)[1]):02d}" for value in times})
        if not normalized or any(not 0 <= int(value[:2]) <= 23 or not 0 <= int(value[3:]) <= 59 for value in normalized):
            raise ValueError
    except (AttributeError, TypeError, ValueError, ZoneInfoNotFoundError) as exc:
        raise ValueError("timezone must be valid and times must contain HH:MM values") from exc
    return normalized


def _item_dict(item):
    groups = sorted(
        [
            {
                "id": membership.group.id,
                "name": membership.group.name,
                "kind": membership.group.kind,
                "priority_rank": membership.group.priority_rank,
                "source": membership.source,
            }
            for membership in item.group_memberships
        ],
        key=lambda group: (group["kind"] != "priority", group["priority_rank"] if group["priority_rank"] is not None else 10**9, group["name"].casefold()),
    )
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
        "groups": groups,
    }


@bp.get("/content_groups")
def get_content_groups():
    _user()
    session = get_scoped_session()
    query = select(ContentGroup).order_by(ContentGroup.kind, ContentGroup.name)
    if request.args.get("include_archived") != "1":
        query = query.where(ContentGroup.archived_at.is_(None))
    return jsonify({"content_groups": [group_to_dict(group, session) for group in session.scalars(query).all()]})


@bp.post("/content_groups")
def post_content_group():
    _user()
    body = request.get_json(silent=True) or {}
    try:
        row = create_group(get_scoped_session(), body.get("name"), body.get("kind"), body.get("priority_rank"))
        get_scoped_session().commit()
    except ValueError as exc:
        get_scoped_session().rollback()
        abort(400, str(exc))
    except IntegrityError:
        get_scoped_session().rollback()
        abort(409, "active group name already exists")
    return jsonify(group_to_dict(row)), 201


@bp.patch("/content_groups/<int:group_id>")
def patch_content_group(group_id):
    _user()
    session = get_scoped_session()
    row = session.get(ContentGroup, group_id)
    if row is None:
        abort(404)
    body = request.get_json(silent=True) or {}
    try:
        row = update_group(session, row, **{key: body[key] for key in {"name", "kind", "priority_rank"} if key in body})
        session.commit()
    except ValueError as exc:
        session.rollback()
        abort(400, str(exc))
    except IntegrityError:
        session.rollback()
        abort(409, "active group name already exists")
    return jsonify(group_to_dict(row, session))


@bp.delete("/content_groups/<int:group_id>")
def delete_content_group(group_id):
    _user()
    session = get_scoped_session()
    row = session.get(ContentGroup, group_id)
    if row is None:
        abort(404)
    try:
        archive_group(session, row)
    except RuntimeError as exc:
        session.rollback()
        return jsonify({"error": str(exc), **getattr(exc, "counts", {})}), 409
    return jsonify(group_to_dict(row, session))


@bp.patch("/feed_items/<int:item_id>/groups")
def patch_feed_item_groups(item_id):
    _user()
    session = get_scoped_session()
    item = session.get(FeedItem, item_id)
    if item is None:
        abort(404)
    if item.status != "saved_for_later":
        abort(409, "only saved feed items can be edited")
    previous_group_ids = [membership.group_id for membership in item.group_memberships]
    previous_status = item.status
    previous_document_id = item.document_id
    previous_saved_at = item.saved_at
    previous_review_reason = item.review_reason
    previous_ignored_pattern = item.ignored_pattern
    try:
        body = request.get_json(silent=True) or {}
        replace_feed_item_groups(session, item, body.get("group_ids"))
        record_review_decision(
            session, item, action="groups", previous_status=previous_status,
            previous_document_id=previous_document_id, previous_saved_at=previous_saved_at,
            previous_review_reason=previous_review_reason, previous_ignored_pattern=previous_ignored_pattern,
            previous_group_ids=previous_group_ids, user_id=g.auth.user_id,
            batch_id=body.get("batch_id") or new_review_batch_id(), job_id=body.get("job_id"),
        )
        session.commit()
    except ValueError as exc:
        session.rollback()
        abort(400, str(exc))
    return jsonify(_item_dict(session.get(FeedItem, item_id)))


@bp.get("/feed_items/<int:item_id>/groups")
def get_feed_item_groups(item_id):
    _user()
    session = get_scoped_session()
    item = session.get(FeedItem, item_id)
    if item is None:
        abort(404)
    return jsonify({"feed_item_id": item_id, "groups": [
        {"id": membership.group.id, "name": membership.group.name, "kind": membership.group.kind, "priority_rank": membership.group.priority_rank, "source": membership.source}
        for membership in sorted(item.group_memberships, key=lambda row: row.group.name.casefold())
    ]})


@bp.get("/document/<int:document_id>/groups")
def get_document_groups(document_id):
    _user()
    session = get_scoped_session()
    document = session.get(Document, document_id)
    if document is None:
        abort(404)
    groups = sorted(document.group_memberships, key=lambda membership: (membership.group.kind != "priority", membership.group.priority_rank or 10**9, membership.group.name.casefold()))
    return jsonify({"document_id": document_id, "groups": [{**group_to_dict(membership.group), "source": membership.source} for membership in groups if membership.group.archived_at is None]})


@bp.patch("/document/<int:document_id>/groups")
def patch_document_groups(document_id):
    _user()
    session = get_scoped_session()
    document = session.get(Document, document_id)
    if document is None:
        abort(404)
    try:
        replace_document_groups(session, document, (request.get_json(silent=True) or {}).get("group_ids"))
    except ValueError as exc:
        session.rollback()
        abort(400, str(exc))
    return get_document_groups(document_id)


def _reader_chunk(session, document_id: int, position: int) -> DocumentChunk:
    """Resolve a reader position to its TEMAT chunk, or explain why it cannot.

    Markdown-header chapters are slices of document text and do not have a
    stable chunk row. The feature is deliberately scoped to the chunk fallback
    used by newsletters and transcripts, where a saved item is exact.
    """
    from library.chunk_review_routes import _chunk_based_chapters, _latest_run_for_document

    run = _latest_run_for_document(session, document_id)
    chapter = next(
        (item for item in _chunk_based_chapters(run) if item["position"] == position),
        None,
    ) if run else None
    if chapter is None:
        abort(409, "this reader chapter is not backed by an analysis chunk")
    chunk = session.get(DocumentChunk, chapter["chunk_id"])
    if chunk is None:
        abort(404, "reader chunk not found")
    return chunk


@bp.get("/document/<int:document_id>/chapter/<int:position>/groups")
def get_reader_chapter_groups(document_id, position):
    _user()
    session = get_scoped_session()
    if session.get(Document, document_id) is None:
        abort(404)
    chunk = _reader_chunk(session, document_id, position)
    groups = sorted(
        (membership.group for membership in chunk.group_memberships if membership.group.archived_at is None),
        key=lambda group: group.name.casefold(),
    )
    return jsonify({
        "document_id": document_id,
        "position": position,
        "chunk_id": chunk.id,
        "groups": [group_to_dict(group) for group in groups],
    })


@bp.patch("/document/<int:document_id>/chapter/<int:position>/groups")
def patch_reader_chapter_groups(document_id, position):
    _user()
    session = get_scoped_session()
    if session.get(Document, document_id) is None:
        abort(404)
    chunk = _reader_chunk(session, document_id, position)
    try:
        replace_chunk_groups(session, chunk, (request.get_json(silent=True) or {}).get("group_ids"))
    except ValueError as exc:
        session.rollback()
        abort(400, str(exc))
    return get_reader_chapter_groups(document_id, position)


@bp.get("/chapter_group_entries")
def get_chapter_group_entries():
    _user()
    from library.chunk_review_routes import _chunk_based_chapters

    group_id = request.args.get("group_id", type=int)
    if group_id is None:
        abort(400, "group_id is required")
    session = get_scoped_session()
    group = session.get(ContentGroup, group_id)
    if group is None or group.archived_at is not None:
        abort(404, "active group not found")
    if group.kind != "topic":
        abort(400, "only topic groups can contain reader chapters")
    rows = session.execute(
        select(DocumentChunk, Document)
        .join(DocumentChunkGroupMembership, DocumentChunkGroupMembership.chunk_id == DocumentChunk.id)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(DocumentChunkGroupMembership.group_id == group_id)
        .order_by(DocumentChunk.created_at.desc(), DocumentChunk.id.desc())
    ).all()
    positions_by_chunk_id: dict[int, int] = {}
    for run_id in {chunk.run_id for chunk, _document in rows}:
        run = session.get(DocumentAnalysisRun, run_id)
        if run is not None:
            positions_by_chunk_id.update({
                item["chunk_id"]: item["position"]
                for item in _chunk_based_chapters(run)
            })
    return jsonify({
        "group": group_to_dict(group, session),
        "entries": [
            {
                "document_id": document.id,
                "chapter_position": positions_by_chunk_id.get(chunk.id),
                "title": chunk.topic or document.title or f"Dokument #{document.id}",
                "document_title": document.title,
                "summary": chunk.summary,
            }
            for chunk, document in rows
        ],
    })


@bp.get("/document/<int:document_id>/origin-feed-groups")
def get_origin_feed_groups(document_id):
    _user()
    session = get_scoped_session()
    if session.get(Document, document_id) is None:
        abort(404)
    items = session.scalars(
        select(FeedItem).where(FeedItem.document_id == document_id).options(
            selectinload(FeedItem.group_memberships).selectinload(FeedItemGroupMembership.group)
        ).order_by(FeedItem.id)
    ).all()
    return jsonify({"document_id": document_id, "feed_items": [
        {"id": item.id, "canonical_url": item.canonical_url, "title": item.title, "groups": [
            {"id": membership.group.id, "name": membership.group.name, "kind": membership.group.kind, "priority_rank": membership.group.priority_rank}
            for membership in sorted(item.group_memberships, key=lambda row: row.group.name.casefold())
        ]} for item in items
    ]})


def _suggestion_dict(suggestion):
    return {
        "id": suggestion.id,
        "run_id": suggestion.run_id,
        "group_id": suggestion.group_id,
        "confidence": float(suggestion.confidence),
        "reason": suggestion.reason,
        "status": suggestion.status,
        "membership_created": suggestion.membership_created,
        "decided_by_user_id": suggestion.decided_by_user_id,
        "decided_at": suggestion.decided_at.isoformat() if suggestion.decided_at else None,
    }


def _suggestions_response(session, target_type, target_id):
    target_column = ContentGroupSuggestionRun.feed_item_id if target_type == "feed_item" else ContentGroupSuggestionRun.document_id
    run = session.scalar(select(ContentGroupSuggestionRun).where(target_column == target_id).order_by(ContentGroupSuggestionRun.id.desc()))
    if run is None:
        return {"run": None, "suggestions": []}
    return {"run": {"id": run.id, "status": run.status, "job_id": run.job_id, "error": run.error, "created_at": run.created_at.isoformat() if run.created_at else None}, "suggestions": [_suggestion_dict(item) for item in run.suggestions]}


@bp.get("/feed_items/<int:item_id>/group-suggestions")
def get_feed_suggestions(item_id):
    _user()
    session = get_scoped_session()
    if session.get(FeedItem, item_id) is None:
        abort(404)
    return jsonify(_suggestions_response(session, "feed_item", item_id))


@bp.get("/document/<int:document_id>/group-suggestions")
def get_document_suggestions(document_id):
    _user()
    session = get_scoped_session()
    if session.get(Document, document_id) is None:
        abort(404)
    return jsonify(_suggestions_response(session, "document", document_id))


def _request_suggestions(target_type, target_id):
    user_id = _user()
    session = get_scoped_session()
    try:
        job, run = request_suggestions(session, target_type, target_id, user_id=user_id, force=bool((request.get_json(silent=True) or {}).get("force")))
    except LookupError as exc:
        abort(404, str(exc))
    except ValueError as exc:
        abort(400, str(exc))
    return jsonify({"run": {"id": run.id, "status": run.status, "job_id": job.id if job else run.job_id}, "job": {"id": job.id, "type": job.type, "status": job.status} if job else None}), 202


@bp.post("/feed_items/<int:item_id>/group-suggestions")
def request_feed_suggestions(item_id):
    return _request_suggestions("feed_item", item_id)


@bp.post("/document/<int:document_id>/group-suggestions")
def request_document_suggestions(document_id):
    return _request_suggestions("document", document_id)


@bp.post("/content_group_suggestions/<int:suggestion_id>/<action>")
def decide_content_group_suggestion(suggestion_id, action):
    user_id = _user()
    if action not in {"accept", "dismiss", "revert"}:
        abort(404)
    try:
        suggestion, target = decide_suggestion(get_scoped_session(), suggestion_id, action, user_id)
    except LookupError as exc:
        abort(404, str(exc))
    except (RuntimeError, ValueError) as exc:
        abort(409 if isinstance(exc, RuntimeError) else 400, str(exc))
    return jsonify({"suggestion": _suggestion_dict(suggestion), "target_id": target.id})


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
    allowed = {"type", "url", "channel_id", "author_name", "language", "tags", "default_topic_group_ids", "auto_import", "disabled", "auto_import_after", "default_state", "field_mapping", "skip_url_patterns", "skip_title_patterns"}
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
    query = select(FeedItem).options(selectinload(FeedItem.group_memberships).selectinload(FeedItemGroupMembership.group)).order_by(*order)
    if status:
        query = query.where(FeedItem.status == status)
    if request.args.get("feed_source_id"):
        query = query.where(FeedItem.feed_source_id == int(request.args["feed_source_id"]))
    try:
        topic_ids = _parse_group_ids(request.args.get("topic_group_ids"))
        priority_id = int(request.args["priority_group_id"]) if request.args.get("priority_group_id") else None
        if topic_ids and request.args.get("without_topics") == "1":
            abort(400, "topic_group_ids and without_topics are mutually exclusive")
        if priority_id and request.args.get("without_priority") == "1":
            abort(400, "priority_group_id and without_priority are mutually exclusive")
        _validate_filter_groups(session, topic_ids, priority_id)
        if topic_ids:
            topic_exists = select(1).select_from(FeedItemGroupMembership).where(
                FeedItemGroupMembership.feed_item_id == FeedItem.id,
                FeedItemGroupMembership.group_id.in_(topic_ids),
            )
            if request.args.get("topic_match", "any") == "all":
                for topic_id in topic_ids:
                    query = query.where(select(1).select_from(FeedItemGroupMembership).where(
                        FeedItemGroupMembership.feed_item_id == FeedItem.id,
                        FeedItemGroupMembership.group_id == topic_id,
                    ).exists())
            elif request.args.get("topic_match", "any") == "any":
                query = query.where(topic_exists.exists())
            else:
                abort(400, "topic_match must be any or all")
        elif request.args.get("topic_match") not in {None, "any", "all"}:
            abort(400, "topic_match must be any or all")
        if priority_id:
            query = query.where(select(1).select_from(FeedItemGroupMembership).where(FeedItemGroupMembership.feed_item_id == FeedItem.id, FeedItemGroupMembership.group_id == priority_id).exists())
        if request.args.get("without_topics") == "1":
            query = query.where(~select(1).select_from(FeedItemGroupMembership).where(FeedItemGroupMembership.feed_item_id == FeedItem.id, FeedItemGroupMembership.group.has(ContentGroup.kind == "topic")).exists())
        if request.args.get("without_priority") == "1":
            query = query.where(~select(1).select_from(FeedItemGroupMembership).where(FeedItemGroupMembership.feed_item_id == FeedItem.id, FeedItemGroupMembership.group.has(ContentGroup.kind == "priority")).exists())
    except (TypeError, ValueError):
        abort(400, "invalid group filter")
    limit = min(max(int(request.args.get("limit", 50)), 1), 200)
    offset = max(int(request.args.get("offset", 0)), 0)
    return jsonify(
        {
            "feed_items": [_item_dict(x) for x in session.scalars(query.offset(offset).limit(limit)).all()],
            "limit": limit,
            "offset": offset,
        }
    )


def _decision_dict(row):
    return {
        "id": row.id, "batch_id": row.batch_id, "job_id": row.job_id,
        "feed_item_id": row.feed_item_id, "feed_source_id": row.feed_item.feed_source_id,
        "title": row.feed_item.title, "url": row.feed_item.url, "action": row.action,
        "previous_status": row.previous_status, "new_status": row.new_status,
        "previous_document_id": row.previous_document_id, "new_document_id": row.new_document_id,
        "previous_group_ids": row.previous_group_ids or [], "new_group_ids": row.new_group_ids or [],
        "metadata": row.metadata_json or {}, "created_at": row.created_at.isoformat(),
        "undone_at": row.undone_at.isoformat() if row.undone_at else None,
    }


@bp.get("/feed_review_decisions")
def get_review_decisions():
    _user()
    session = get_scoped_session()
    query = select(FeedReviewDecision).join(FeedItem).order_by(FeedReviewDecision.created_at.desc(), FeedReviewDecision.id.desc())
    if request.args.get("feed_source_id"):
        query = query.where(FeedItem.feed_source_id == int(request.args["feed_source_id"]))
    if request.args.get("batch_id"):
        query = query.where(FeedReviewDecision.batch_id == request.args["batch_id"])
    if request.args.get("job_id"):
        query = query.where(FeedReviewDecision.job_id == request.args["job_id"])
    if request.args.get("include_undone") != "1":
        query = query.where(FeedReviewDecision.undone_at.is_(None))
    limit = min(max(int(request.args.get("limit", 100)), 1), 500)
    rows = session.scalars(query.limit(limit)).all()
    return jsonify({"decisions": [_decision_dict(row) for row in rows]})


@bp.post("/feed_review_decisions/<int:decision_id>/undo")
def undo_review_decision(decision_id):
    user_id = _user()
    session = get_scoped_session()
    row = session.get(FeedReviewDecision, decision_id)
    if row is None:
        abort(404)
    if row.undone_at is not None:
        abort(409, "decision already undone")
    item = session.get(FeedItem, row.feed_item_id)
    if item is None:
        abort(404)
    if item.status != row.new_status or item.document_id != row.new_document_id:
        abort(409, "feed item changed after this decision; manual review required")
    item.status = row.previous_status
    item.document_id = row.previous_document_id
    item.saved_at = row.previous_saved_at
    item.review_reason = row.previous_review_reason
    item.ignored_pattern = row.previous_ignored_pattern
    item.updated_at = dt.datetime.now(dt.timezone.utc)
    replace_feed_item_groups(session, item, row.previous_group_ids, commit=False)
    row.undone_at = dt.datetime.now(dt.timezone.utc)
    row.undone_by_user_id = user_id
    session.commit()
    return jsonify({"decision": _decision_dict(row), "feed_item": _item_dict(session.get(FeedItem, item.id))})


def _parse_group_ids(raw):
    if raw is None or raw == "":
        return []
    values = [int(value) for value in raw.split(",")]
    if len(values) != len(set(values)) or any(value <= 0 for value in values):
        raise ValueError("invalid group IDs")
    return values


def _validate_filter_groups(session, topic_ids, priority_id):
    ids = topic_ids + ([priority_id] if priority_id else [])
    if not ids:
        return
    groups = {group.id: group for group in session.scalars(select(ContentGroup).where(ContentGroup.id.in_(ids), ContentGroup.archived_at.is_(None))).all()}
    if len(groups) != len(ids) or any(groups[group_id].kind != "topic" for group_id in topic_ids) or (priority_id and groups[priority_id].kind != "priority"):
        raise ValueError("group filter has wrong kind or inactive group")


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
        body = request.get_json(silent=True) or {}
        item, doc = import_feed_item(
            item_id, session, body.get("document_type"), g.auth.user_id,
            keep_for_review=bool(body.get("keep_for_review", False)),
        )
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
    body = request.get_json(silent=True) or {}
    try:
        item = transition_item(get_scoped_session(), item_id, "saved_for_later", _user(), group_ids=body.get("group_ids"))
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
    capabilities = _job_capabilities()
    session = get_scoped_session()
    try:
        limit = min(max(int(request.args.get("limit", 50)), 1), 200)
        offset = max(int(request.args.get("offset", 0)), 0)
    except ValueError:
        abort(400, "limit and offset must be integers")
    job_type = request.args.get("type") or None
    status = request.args.get("status") or None
    if job_type is not None and job_type not in JOB_TYPES:
        abort(400, "unsupported job type")
    allowed_statuses = {"queued", "running", "done", "failed", "needs_intervention", "cancel_requested", "cancelled"}
    if status is not None and status not in allowed_statuses:
        abort(400, "unsupported job status")
    query = select(Job)
    if job_type is not None:
        query = query.where(Job.type == job_type)
    if status is not None:
        query = query.where(Job.status == status)
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    rows = session.scalars(query.order_by(Job.created_at.desc()).offset(offset).limit(limit)).all()
    return jsonify(
        {
            "jobs": [_job_dict(x) for x in rows],
            "capabilities": capabilities,
            "limit": limit,
            "offset": offset,
            "total": total,
            "filters": {"type": job_type, "status": status},
        }
    )


@bp.get("/scheduler")
def get_scheduler():
    """Expose database-owned scheduler configuration and recent executions."""
    capabilities = _job_capabilities()
    now = dt.datetime.now(dt.timezone.utc)
    session = get_scoped_session()
    tasks = {task.id: task for task in session.scalars(select(ScheduledTask)).all()}
    schedules = []
    for task_id, job_type, description in (
        ("feed_daily", "feed_daily", "Codzienne sprawdzenie i automatyczny import feedów"),
        ("legacy_aws_pull", "legacy_aws_pull", "Tymczasowa synchronizacja z legacy AWS"),
    ):
        task = tasks.get(task_id)
        if task is None:
            continue
        try:
            times = _validate_schedule(task.timezone, task.times)
            next_run = _next_task_run(now, ZoneInfo(task.timezone), times) if task.enabled else None
        except ValueError:
            abort(500, f"invalid schedule for {task_id}")
        last_job = session.scalars(select(Job).where(Job.type == job_type).order_by(Job.created_at.desc()).limit(1)).first()
        schedules.append({
            "id": task.id, "job_type": job_type, "enabled": task.enabled, "description": description,
            "timezone": task.timezone, "times": times, "schedule": ", ".join(times),
            "next_run_at": next_run.isoformat() if next_run else None,
            "last_job": _job_dict(last_job) if last_job else None,
        })
    return jsonify({
        "generated_at": now.isoformat(),
        "schedules": schedules,
        "capabilities": capabilities,
    })


@bp.patch("/scheduler/<task_id>")
def update_scheduler(task_id):
    _job_viewer()
    task = get_scoped_session().get(ScheduledTask, task_id)
    if task is None:
        abort(404)
    body = request.get_json(silent=True) or {}
    if set(body) - {"enabled", "timezone", "times"}:
        abort(400, "unsupported scheduler fields")
    enabled = body.get("enabled", task.enabled)
    timezone_name = body.get("timezone", task.timezone)
    times = body.get("times", task.times)
    if not isinstance(enabled, bool) or not isinstance(timezone_name, str) or not isinstance(times, list):
        abort(400, "invalid scheduler fields")
    try:
        task.times = _validate_schedule(timezone_name, times)
    except ValueError as exc:
        abort(400, str(exc))
    task.enabled = enabled
    task.timezone = timezone_name
    get_scoped_session().commit()
    return jsonify({"id": task.id, "enabled": task.enabled, "timezone": task.timezone, "times": task.times})


@bp.get("/jobs/<job_id>")
def get_job(job_id):
    _job_viewer()
    job = get_scoped_session().get(Job, job_id)
    if job is None:
        abort(404)
    return jsonify(_job_dict(job))


@bp.post("/jobs")
def create_job():
    _job_viewer()
    session = get_scoped_session()
    body = request.get_json(silent=True) or {}
    typ = body.get("type")
    parameters = body.get("parameters") or {}
    if not isinstance(parameters, dict):
        abort(400, "parameters must be an object")
    if g.auth.kind == "user" and typ not in {"legacy_aws_pull", "feed_daily"}:
        abort(403, "user API keys may create only legacy_aws_pull or feed_daily jobs")
    if typ in {"feed_check", "feed_auto_import"}:
        if set(parameters) != {"feed_source_id"} or not isinstance(parameters.get("feed_source_id"), int):
            abort(400, "this job requires only integer feed_source_id")
    elif typ in {"feed_check_all", "feed_daily"} and parameters:
        abort(400, "this job type does not accept parameters")
    elif typ == "legacy_aws_pull":
        allowed = {"since", "dry_run", "limit"}
        if set(parameters) - allowed:
            abort(400, "unsupported legacy_aws_pull parameter")
        if "since" in parameters and parameters["since"] is not None and not isinstance(parameters["since"], str):
            abort(400, "since must be null or an ISO-8601 timestamp")
        if "dry_run" in parameters and not isinstance(parameters["dry_run"], bool):
            abort(400, "dry_run must be boolean")
        if "limit" in parameters and (not isinstance(parameters["limit"], int) or isinstance(parameters["limit"], bool) or not 0 <= parameters["limit"] <= 1000):
            abort(400, "limit must be an integer from 0 to 1000")
    if typ == "feed_daily":
        key = f"feed_daily:{dt.datetime.now(dt.timezone.utc).astimezone(ZoneInfo('Europe/Warsaw')).date().isoformat()}"
    else:
        key = None
    try:
        job = enqueue(
            session,
            typ,
            parameters,
            idempotency_key=key,
            user_id=g.auth.user_id if g.auth.kind == "user" else None,
        )
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
