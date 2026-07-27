"""Database-backed feed checks and curation operations."""

import datetime as dt
import logging
import re
import regex as safe_regex
from sqlalchemy import select, update, text
from library.db.models import FeedSource, FeedItem, Document
from library.db.engine import get_session
from library.document_service import DocumentService
from library.feed_parser import fetch_entries, apply_skip_filters, parse_published
from library.url_normalization import canonicalize_url

logger = logging.getLogger(__name__)
ACTIVE_TRANSITIONS = {
    "new": {"llm_analysis_requested", "imported", "skipped", "ignored", "error"},
    "llm_analysis_requested": {"imported", "skipped", "ignored", "error"},
    "error": {"imported", "skipped", "ignored"},
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


def import_feed_item(item_id: int, session=None) -> tuple[FeedItem, Document]:
    own = session is None
    session = session or get_session()
    try:
        item = session.get(FeedItem, item_id)
        if item is None:
            raise ValueError("feed item not found")
        if item.status not in {"new", "llm_analysis_requested", "error"}:
            raise ValueError("feed item cannot be imported from its current state")
        session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 119954089))"), {"key": item.canonical_url}
        )
        existing = Document.get_by_url(session, item.canonical_url)
        if existing is None:
            feed = session.get(FeedSource, item.feed_source_id)
            doc, _ = DocumentService(session).import_document(
                item.canonical_url,
                "youtube" if "youtube" in feed.type else "link",
                processing_status=feed.default_state,
                title=item.title,
                summary=item.summary or "",
                published_on=item.published_at.date() if item.published_at else None,
                language=feed.language,
                tags=",".join(feed.tags or []),
                source=feed.name,
                collection_id=feed.collection_id,
            )
        else:
            doc = existing
        item.status, item.document_id, item.last_error, item.updated_at = (
            "imported",
            doc.id,
            None,
            dt.datetime.now(dt.timezone.utc),
        )
        session.commit()
        return item, doc
    except Exception:
        session.rollback()
        raise
    finally:
        if own:
            session.close()


def transition_item(session, item_id: int, target: str, user_id: int | None = None) -> FeedItem:
    item = session.get(FeedItem, item_id)
    if item is None:
        raise ValueError("feed item not found")
    if target not in ACTIVE_TRANSITIONS.get(item.status, set()):
        raise RuntimeError("invalid feed item state transition")
    result = session.execute(
        update(FeedItem)
        .where(FeedItem.id == item_id, FeedItem.status == item.status)
        .values(
            status=target,
            reviewed_at=dt.datetime.now(dt.timezone.utc),
            reviewed_by_user_id=user_id,
            updated_at=dt.datetime.now(dt.timezone.utc),
        )
    )
    if result.rowcount != 1:
        raise RuntimeError("feed item was changed concurrently")
    session.commit()
    return session.get(FeedItem, item_id)


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
    for candidate in session.scalars(
        select(FeedItem).where(FeedItem.feed_source_id == feed.id, FeedItem.status == "new")
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
            (
                candidate.status,
                candidate.ignored_pattern,
                candidate.reviewed_at,
                candidate.reviewed_by_user_id,
                candidate.updated_at,
            ) = "ignored", pattern, now, user_id, now
    session.commit()
    return session.get(FeedItem, item_id)
