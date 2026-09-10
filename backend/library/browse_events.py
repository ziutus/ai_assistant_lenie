"""Best-effort UI telemetry. Retention is a maintenance operation and raises errors."""

import json
import logging
from threading import Lock
from uuid import UUID

from sqlalchemy import create_engine, delete, func, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.pool import NullPool

from library.db.engine import get_session
from library.db.models import DocumentBrowseEvent
from library.search.audit_repository import _truncate
from library.search.types import MAX_QUERY_LENGTH

logger = logging.getLogger(__name__)
_write_engine = None
_write_engine_lock = Lock()
TEXT_FIELDS = {
    "document_type",
    "processing_status",
    "topic_match",
    "author_name",
    "publisher_name",
    "publisher_domain",
    "discovery_source_name",
    "collection_name",
    "published_on_from",
    "published_on_to",
    "ingested_at_from",
    "ingested_at_to",
    "source_layer",
}
BOOL_FIELDS = {
    "only_missing_obsidian_notes",
    "only_has_obsidian_notes",
    "without_embedding",
    "without_topics",
    "topic_filter_active",
    "include_without_topics",
    "without_priority",
}
INT_FIELDS = {"priority_group_id", "subject_period_start_year", "subject_period_end_year"}
LIST_FIELDS = {"topic_group_ids", "document_types", "languages"}
FILTER_FIELDS = TEXT_FIELDS | BOOL_FIELDS | INT_FIELDS | LIST_FIELDS
CONTEXT_FIELDS = FILTER_FIELDS | {"query", "sort", "page_size", "requested_mode"}
ORIGINS = {"default", "remembered", "url", "manual", "ai"}
ACTIONS = {
    "initial_load",
    "submit",
    "filter_change",
    "sort_change",
    "page_change",
    "page_size_change",
    "clear",
    "refresh",
    "correction",
}


def validate_criteria(filters, changed_fields, criteria_origin):
    """Reject malformed telemetry instead of silently changing its statistical meaning."""
    if not isinstance(filters, dict) or set(filters) - FILTER_FIELDS:
        raise ValueError("invalid filter fields")
    for key, value in filters.items():
        if value is None and key in TEXT_FIELDS | INT_FIELDS:
            continue
        valid = False
        if key in TEXT_FIELDS:
            valid = isinstance(value, str) and len(value) <= 300
        elif key in BOOL_FIELDS:
            valid = type(value) is bool
        elif key in INT_FIELDS:
            valid = type(value) is int and -10000 <= value <= 2147483647
        elif key in LIST_FIELDS:
            valid = (
                isinstance(value, list)
                and len(value) <= 100
                and all(
                    (type(item) is int and 0 < item <= 2147483647)
                    if key == "topic_group_ids"
                    else (isinstance(item, str) and len(item) <= 300)
                    for item in value
                )
            )
        if not valid:
            raise ValueError("invalid filter value")
    if (
        not isinstance(changed_fields, list)
        or len(changed_fields) > len(CONTEXT_FIELDS)
        or any(not isinstance(key, str) or key not in CONTEXT_FIELDS for key in changed_fields)
    ):
        raise ValueError("invalid changed fields")
    if (
        not isinstance(criteria_origin, dict)
        or set(criteria_origin) - CONTEXT_FIELDS
        or any(not isinstance(value, str) or value not in ORIGINS for value in criteria_origin.values())
    ):
        raise ValueError("invalid criteria origin")
    return filters, list(dict.fromkeys(changed_fields)), criteria_origin


def telemetry_context(value):
    """Parse bounded transport data; malformed optional telemetry never rejects a request."""
    try:
        if not isinstance(value, dict):
            return None
        result = {key: str(UUID(value[key])) for key in ("event_id", "session_id", "browse_id")}
        if value.get("action") not in ACTIONS:
            return None
        mode = value.get("requested_mode")
        if mode not in {"strict", "similar", "natural", "explicit"}:
            return None
        result.update(action=value["action"], requested_mode=mode)
        for key, default in (("changed_fields", []), ("criteria_origin", {})):
            item = value.get(key, default)
            if isinstance(item, str):
                if len(item) > 8192:
                    return None
                item = json.loads(item)
            result[key] = item
        validate_criteria({}, result["changed_fields"], result["criteria_origin"])
        return result
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
        return None


def _write_session():
    """Use get_session, but don't wait behind the request's checked-out pool connection.

    A telemetry-only engine has no pool queue and a two-second connection
    timeout. SQL/lock waits are further limited within the transaction below.
    The request engine and its pool configuration remain untouched.
    """
    global _write_engine
    session = get_session()
    try:
        with _write_engine_lock:
            if _write_engine is None:
                from library.config_loader import load_config

                connect_args = {"connect_timeout": 2}
                sslmode = load_config().get("POSTGRESQL_SSLMODE")
                if sslmode:
                    connect_args["sslmode"] = sslmode
                _write_engine = create_engine(session.get_bind().url, poolclass=NullPool, connect_args=connect_args)
        session.bind = _write_engine
        return session
    except (SystemExit, Exception):
        session.close()
        raise


def record_browse_event(*, session_factory=None, **values):
    """Own transaction, bounded SQL waits, event-id dedup; never break the caller."""
    session = None
    try:
        for key in ("event_id", "session_id", "browse_id"):
            values[key] = UUID(str(values[key]))
        values["filters"], values["changed_fields"], values["criteria_origin"] = validate_criteria(
            values["filters"], values["changed_fields"], values["criteria_origin"]
        )
        for key in ("query_text", "effective_query"):
            values[key] = _truncate(values.get(key), MAX_QUERY_LENGTH)
        for key in ("requested_mode", "execution_mode", "sort"):
            if not isinstance(values.get(key), str) or len(values[key]) > 50:
                raise ValueError("invalid event label")
        session = (session_factory or _write_session)()
        session.execute(text("SET LOCAL statement_timeout = '500ms'"))
        session.execute(text("SET LOCAL lock_timeout = '100ms'"))
        result = session.execute(
            insert(DocumentBrowseEvent)
            .values(**values)
            .on_conflict_do_nothing(
                index_elements=[DocumentBrowseEvent.event_id],
            )
            .returning(DocumentBrowseEvent.id)
        )
        event_id = result.scalar_one_or_none()
        session.commit()
        return event_id
    except (SystemExit, Exception):
        # Do not log query text, API keys or SQL parameters on telemetry failure.
        logger.warning("Browse telemetry write failed")
        if session is not None:
            try:
                session.rollback()
            except (SystemExit, Exception):
                logger.warning("Browse telemetry rollback failed")
        return None
    finally:
        if session is not None:
            try:
                session.close()
            except (SystemExit, Exception):
                logger.warning("Browse telemetry close failed")


def delete_expired_browse_events(*, session_factory=get_session):
    session = session_factory()
    try:
        result = session.execute(delete(DocumentBrowseEvent).where(DocumentBrowseEvent.expires_at < func.now()))
        session.commit()
        return result.rowcount or 0
    finally:
        session.close()
