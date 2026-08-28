"""Database-backed feed checks and curation operations."""

import datetime as dt
import logging
import re
import uuid
import regex as safe_regex
from sqlalchemy import select, update, text
from library.db.models import FeedSource, FeedItem, ContentGroup, Document, DocumentGroupMembership, FeedItemGroupMembership, FeedReviewDecision
from library.db.engine import get_session
from library.document_service import DocumentService
from library.feed_parser import fetch_entries, apply_skip_filters, parse_published
from library.url_normalization import canonicalize_url
from library.content_group_service import replace_feed_item_groups

logger = logging.getLogger(__name__)
REVIEW_REASONS = {"not_interested", "duplicate", "already_known", "too_long", "other"}
ACTIVE_TRANSITIONS = {
    "new": {"llm_analysis_requested", "saved_for_later", "imported", "skipped", "ignored", "error"},
    "llm_analysis_requested": {"saved_for_later", "imported", "skipped", "ignored", "error"},
    "saved_for_later": {"new", "imported", "skipped", "ignored"},
    "error": {"saved_for_later", "imported", "skipped", "ignored"},
}


def _feed_config(feed: FeedSource) -> dict:
    return {
        "type": feed.type,
        "url": feed.url,
        "channel_id": feed.channel_id,
        "field_mapping": feed.field_mapping or {},
        "skip_url_patterns": feed.skip_url_patterns or [],
        "skip_title_patterns": feed.skip_title_patterns or [],
    }


def new_review_batch_id() -> str:
    return uuid.uuid4().hex


def record_review_decision(
    session, item: FeedItem, *, action: str, previous_status: str, previous_document_id: int | None,
    previous_saved_at, previous_review_reason: str | None, previous_ignored_pattern: str | None,
    previous_group_ids: list[int], user_id: int | None = None, batch_id: str | None = None,
    job_id: str | None = None, metadata: dict | None = None,
) -> FeedReviewDecision:
    session.add(FeedReviewDecision(
        batch_id=batch_id or new_review_batch_id(), job_id=job_id, feed_item_id=item.id, user_id=user_id,
        action=action, previous_status=previous_status, new_status=item.status,
        previous_document_id=previous_document_id, new_document_id=item.document_id,
        previous_saved_at=previous_saved_at, previous_review_reason=previous_review_reason,
        previous_ignored_pattern=previous_ignored_pattern, previous_group_ids=previous_group_ids,
        new_group_ids=[membership.group_id for membership in item.group_memberships], metadata_json=metadata or {},
    ))


def _upsert(session, feed: FeedSource, entry: dict, status: str = "new") -> FeedItem:
    url = entry.get("url", "").strip()
    if not url:
        raise ValueError("feed entry has no URL")
    canonical = canonicalize_url(url)
    item = session.scalars(
        select(FeedItem).where(FeedItem.feed_source_id == feed.id, FeedItem.canonical_url == canonical)
    ).one_or_none()
    now = dt.datetime.now(dt.timezone.utc)
    if item is None:
        item = FeedItem(
            feed_source_id=feed.id,
            url=url,
            canonical_url=canonical,
            title=entry.get("title", ""),
            summary=entry.get("summary"),
            published_at=parse_published(entry.get("published")),
            raw_payload=entry.get("raw_payload") or {},
            status=status,
            ignored_pattern=entry.get("ignored_pattern"),
        )
        session.add(item)
    else:
        item.url, item.title, item.summary, item.published_at, item.raw_payload, item.last_seen_at, item.updated_at = (
            url,
            entry.get("title", ""),
            entry.get("summary"),
            parse_published(entry.get("published")),
            entry.get("raw_payload") or {},
            now,
            now,
        )
    return item


def run_check(feed_source_id: int | None = None, session=None) -> dict:
    own = session is None
    session = session or get_session()
    result = {"checked": 0, "items": 0, "errors": []}
    try:
        query = select(FeedSource).where(FeedSource.disabled.is_(False))
        if feed_source_id is not None:
            query = query.where(FeedSource.id == feed_source_id)
        for feed in session.scalars(query.order_by(FeedSource.id)).all():
            try:
                entries = fetch_entries(_feed_config(feed))
                kept, ignored = apply_skip_filters(entries, _feed_config(feed))
                for entry in kept:
                    _upsert(session, feed, entry)
                for entry in ignored:
                    _upsert(session, feed, entry, "ignored")
                feed.last_checked_at, feed.last_error = dt.datetime.now(dt.timezone.utc), None
                result["items"] += len(entries)
                result["checked"] += 1
            except Exception as exc:
                feed.last_checked_at, feed.last_error_at, feed.last_error = (
                    dt.datetime.now(dt.timezone.utc),
                    dt.datetime.now(dt.timezone.utc),
                    str(exc)[:2000],
                )
                result["errors"].append(
                    {
                        "feed_source_id": feed.id,
                        "feed_name": feed.name,
                        "feed_url": feed.url,
                        "feed_type": feed.type,
                        "error": str(exc),
                    }
                )
            session.commit()
        return result
    finally:
        if own:
            session.close()


def run_auto_import(feed_source_id: int | None = None, session=None) -> dict:
    own = session is None
    session = session or get_session()
    result = {"imported": 0, "errors": []}
    try:
        now = dt.datetime.now(dt.timezone.utc)
        query = (
            select(FeedItem, FeedSource)
            .join(FeedSource, FeedSource.id == FeedItem.feed_source_id)
            .where(
                FeedItem.status.in_(["new", "error"]),
                FeedSource.auto_import.is_(True),
                FeedSource.disabled.is_(False),
                FeedSource.auto_import_after.is_not(None),
                FeedItem.published_at.is_not(None),
                FeedItem.published_at >= FeedSource.auto_import_after,
            )
        )
        if feed_source_id is not None:
            query = query.where(FeedSource.id == feed_source_id)
        for item, feed in session.execute(query).all():
            try:
                import_feed_item(item.id, session=session)
                result["imported"] += 1
                feed.last_successful_import_at = now
                session.commit()
            except Exception as exc:
                session.rollback()
                item = session.get(FeedItem, item.id)
                item.status, item.last_error = "error", str(exc)[:2000]
                session.commit()
                result["errors"].append({"feed_item_id": item.id, "error": str(exc)})
        return result
    finally:
        if own:
            session.close()


def import_feed_item(
    item_id: int, session=None, document_type: str | None = None, user_id: int | None = None,
    keep_for_review: bool = False,
) -> tuple[FeedItem, Document]:
    own = session is None
    session = session or get_session()
    try:
        item = session.get(FeedItem, item_id)
        if item is None:
            raise ValueError("feed item not found")
        if item.status not in {"new", "llm_analysis_requested", "saved_for_later", "error"}:
            raise ValueError("feed item cannot be imported from its current state")
        if document_type is not None and document_type not in {"link", "webpage", "youtube"}:
            raise ValueError("document_type must be link, webpage or youtube")
        previous_status = item.status
        previous_document_id = item.document_id
        previous_saved_at = item.saved_at
        previous_review_reason = item.review_reason
        previous_ignored_pattern = item.ignored_pattern
        previous_group_ids = [membership.group_id for membership in item.group_memberships]
        session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 119954089))"), {"key": item.canonical_url}
        )
        existing = Document.get_by_url(session, item.canonical_url)
        if existing is None:
            feed = session.get(FeedSource, item.feed_source_id)
            mapped_author = (feed.author_name or "").strip()
            doc, _ = DocumentService(session).import_document(
                item.canonical_url,
                document_type or ("youtube" if "youtube" in feed.type else "link"),
                processing_status=feed.default_state,
                title=item.title,
                summary=item.summary or "",
                published_on=item.published_at.date() if item.published_at else None,
                language=feed.language,
                tags=",".join(feed.tags or []),
                source=feed.name,
                collection_id=feed.collection_id,
                byline=mapped_author or None,
            )
            # A configured YouTube-channel author is a deliberate publisher/
            # creator mapping, not a claim that a named individual made the
            # video.  Still use the shared author service so the display
            # byline and the structured author relation cannot diverge.
            if feed.type == "youtube_channel" and mapped_author:
                from library.author_service import set_document_authors

                set_document_authors(session, doc, [mapped_author], method="manual")
            promoted = False
        else:
            doc = existing
            promoted = False
            # "Zaimportuj jako webpage" on a URL already stored as a link:
            # upgrade it in place instead of silently ignoring the request.
            if (
                document_type == "webpage"
                and doc.document_type == "link"
                and not doc.paywall
                and not doc.requires_login
            ):
                from library.document_promotion import promote_link_to_webpage

                promote_link_to_webpage(
                    session, DocumentService(session)._get_storage(), doc,
                    run_feed_linking=False,
                )
                promoted = True
        copy_feed_groups_to_document(session, [item], doc, "feed_import")
        item.status, item.document_id, item.last_error, item.updated_at = (
            "saved_for_later" if keep_for_review else "imported",
            doc.id,
            None,
            dt.datetime.now(dt.timezone.utc),
        )
        if keep_for_review:
            item.saved_at = dt.datetime.now(dt.timezone.utc)
            item.saved_by_user_id = user_id
        record_review_decision(
            session, item, action="import", previous_status=previous_status,
            previous_document_id=previous_document_id, previous_saved_at=previous_saved_at,
            previous_review_reason=previous_review_reason, previous_ignored_pattern=previous_ignored_pattern,
            previous_group_ids=previous_group_ids, user_id=user_id,
            metadata={
                "document_type": document_type or "default",
                "keep_for_review": keep_for_review,
                "promoted": promoted,
            },
        )
        session.commit()
        if promoted:
            from library.document_processing_service import ensure_document_prepare_job

            ensure_document_prepare_job(session, doc)
        return item, doc
    except Exception:
        session.rollback()
        raise
    finally:
        if own:
            session.close()


def transition_item(
    session, item_id: int, target: str, user_id: int | None = None, review_reason: str | None = None,
    group_ids: list[int] | None = None,
) -> FeedItem:
    item = session.get(FeedItem, item_id)
    if item is None:
        raise ValueError("feed item not found")
    if target not in ACTIVE_TRANSITIONS.get(item.status, set()):
        raise RuntimeError("invalid feed item state transition")
    if review_reason is not None and review_reason not in REVIEW_REASONS:
        raise ValueError("invalid review reason")
    previous_status = item.status
    previous_document_id = item.document_id
    previous_saved_at = item.saved_at
    previous_review_reason = item.review_reason
    previous_ignored_pattern = item.ignored_pattern
    previous_group_ids = [membership.group_id for membership in item.group_memberships]
    now = dt.datetime.now(dt.timezone.utc)
    values = {"status": target, "updated_at": now}
    if target == "saved_for_later":
        values.update(saved_at=now, saved_by_user_id=user_id)
    elif item.status == "saved_for_later" and target == "new":
        values.update(saved_at=None, saved_by_user_id=None)
    if target in {"skipped", "ignored"}:
        values.update(reviewed_at=now, reviewed_by_user_id=user_id)
    if target == "skipped":
        values["review_reason"] = review_reason or "other"
    result = session.execute(
        update(FeedItem)
        .where(FeedItem.id == item_id, FeedItem.status == item.status)
        .values(**values)
    )
    if result.rowcount != 1:
        raise RuntimeError("feed item was changed concurrently")
    if group_ids is not None:
        replace_feed_item_groups(session, item, group_ids, commit=False)
    record_review_decision(
        session, item, action=target, previous_status=previous_status,
        previous_document_id=previous_document_id, previous_saved_at=previous_saved_at,
        previous_review_reason=previous_review_reason, previous_ignored_pattern=previous_ignored_pattern,
        previous_group_ids=previous_group_ids, user_id=user_id,
    )
    session.commit()
    return session.get(FeedItem, item_id)


def copy_feed_groups_to_document(session, feed_items, document: Document, source: str) -> None:
    """Copy active feed memberships into a document without changing provenance."""
    if source not in {"feed_import", "chrome_link"}:
        raise ValueError("invalid feed group copy source")
    item_ids = [item.id if isinstance(item, FeedItem) else item for item in feed_items]
    if not item_ids:
        return
    rows = session.execute(
        select(FeedItemGroupMembership, ContentGroup)
        .join(ContentGroup, ContentGroup.id == FeedItemGroupMembership.group_id)
        .where(
            FeedItemGroupMembership.feed_item_id.in_(item_ids),
            ContentGroup.archived_at.is_(None),
        )
    ).all()
    current = {
        membership.group_id: membership
        for membership in session.scalars(
            select(DocumentGroupMembership).where(DocumentGroupMembership.document_id == document.id)
        ).all()
    }
    topic_groups = {group.id: group for _, group in rows if group.kind == "topic"}
    feed_ids = {item.feed_source_id for item in feed_items if isinstance(item, FeedItem)}
    if feed_ids:
        configured_topic_ids = {
            group_id
            for configured_ids, in session.execute(
                select(FeedSource.default_topic_group_ids).where(FeedSource.id.in_(feed_ids))
            ).all()
            for group_id in (configured_ids or [])
        }
        if configured_topic_ids:
            configured_groups = session.scalars(
                select(ContentGroup).where(
                    ContentGroup.id.in_(configured_topic_ids),
                    ContentGroup.kind == "topic",
                    ContentGroup.archived_at.is_(None),
                )
            ).all()
            topic_groups.update({group.id: group for group in configured_groups})
    for group in topic_groups.values():
        if group.id not in current:
            session.add(DocumentGroupMembership(document_id=document.id, group_id=group.id, source=source))
    if not any(membership.group.kind == "priority" for membership in current.values() if membership.group is not None):
        priorities = [group for _, group in rows if group.kind == "priority"]
        if priorities:
            chosen = min(priorities, key=lambda group: (group.priority_rank, group.id))
            if chosen.id not in current:
                session.add(DocumentGroupMembership(document_id=document.id, group_id=chosen.id, source=source))
    session.flush()


def link_matching_feed_items_to_document(session, document: Document) -> int:
    """Attach all feed entries for a canonical URL to a document idempotently."""
    items = session.scalars(
        select(FeedItem).where(FeedItem.canonical_url == document.canonical_url)
    ).all()
    linked = 0
    for item in items:
        if item.document_id != document.id:
            item.document_id = document.id
            linked += 1
        if item.status in {"new", "llm_analysis_requested", "saved_for_later", "error"}:
            item.status = "imported"
        item.updated_at = dt.datetime.now(dt.timezone.utc)
    if items:
        copy_feed_groups_to_document(session, items, document, "chrome_link")
    session.flush()
    return linked


def save_review_note(session, item_id: int, note: str) -> FeedItem:
    item = session.get(FeedItem, item_id)
    if item is None:
        raise ValueError("feed item not found")
    item.review_note = note
    item.updated_at = dt.datetime.now(dt.timezone.utc)
    session.commit()
    return item


def ignore_feed_item(session, item_id: int, field: str, pattern: str, user_id: int | None = None) -> FeedItem:
    if field not in {"url", "title"} or not pattern or len(pattern) > 256:
        raise ValueError("ignore pattern requires field=url|title and a pattern up to 256 characters")
    if field == "title":
        try:
            re.compile(pattern)
        except re.error as exc:
            raise ValueError(f"invalid title regex: {exc}") from exc
    item = session.get(FeedItem, item_id)
    if item is None:
        raise ValueError("feed item not found")
    feed = session.get(FeedSource, item.feed_source_id)
    values = list(feed.skip_url_patterns or []) if field == "url" else list(feed.skip_title_patterns or [])
    if pattern not in values:
        if len(values) >= 100:
            raise ValueError("maximum of 100 ignore patterns reached")
        values.append(pattern)
        if field == "url":
            feed.skip_url_patterns = values
        else:
            feed.skip_title_patterns = values
    now = dt.datetime.now(dt.timezone.utc)
    batch_id = new_review_batch_id()
    for candidate in session.scalars(
        select(FeedItem).where(FeedItem.feed_source_id == feed.id, FeedItem.status.in_(["new", "saved_for_later"]))
    ).all():
        try:
            matches = (
                candidate.url.startswith(pattern)
                if field == "url"
                else bool(safe_regex.search(pattern, candidate.title, safe_regex.I, timeout=0.05))
            )
        except (safe_regex.error, TimeoutError):
            matches = False
        if matches:
            previous_status = candidate.status
            previous_document_id = candidate.document_id
            previous_saved_at = candidate.saved_at
            previous_review_reason = candidate.review_reason
            previous_ignored_pattern = candidate.ignored_pattern
            previous_group_ids = [membership.group_id for membership in candidate.group_memberships]
            (
                candidate.status,
                candidate.ignored_pattern,
                candidate.reviewed_at,
                candidate.reviewed_by_user_id,
                candidate.updated_at,
            ) = "ignored", pattern, now, user_id, now
            record_review_decision(
                session, candidate, action="ignore", previous_status=previous_status,
                previous_document_id=previous_document_id, previous_saved_at=previous_saved_at,
                previous_review_reason=previous_review_reason, previous_ignored_pattern=previous_ignored_pattern,
                previous_group_ids=previous_group_ids, user_id=user_id, batch_id=batch_id,
                metadata={"field": field, "pattern": pattern},
            )
    session.commit()
    return session.get(FeedItem, item_id)
