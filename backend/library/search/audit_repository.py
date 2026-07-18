"""Audit persistence for search interpretations (search-rebuild, stage 2B).

Every write opens its own short-lived session, so audit rows commit
independently of the search transaction: a failed audit write is logged and
swallowed, never raised into the search path (plan rule: awaria zapisu logów
nie może wywalić wyszukiwania). The one exception is
``delete_expired_interpretations()`` — a maintenance operation run from a
job/CLI, where a failure must surface to the operator.

The audit columns are TEXT; length caps live here in the write layer:
``raw_query`` reuses MAX_QUERY_LENGTH from the domain types, raw responses
and error messages use module-level caps. Truncation is visible in the
stored value via TRUNCATION_SUFFIX.
"""

import logging
from dataclasses import fields
from datetime import date, datetime
from enum import Enum

from sqlalchemy import delete, func

from library.db.engine import get_session
from library.db.models import SearchInterpretationLog
from library.search.types import (
    MAX_COMMENT_LENGTH,
    MAX_QUERY_LENGTH,
    InterpretationStatus,
    ParsedSearchQuery,
    SearchFeedback,
)

logger = logging.getLogger(__name__)

TRUNCATION_SUFFIX = "… [truncated]"
MAX_RAW_RESPONSE_LENGTH = 20_000
MAX_ERROR_MESSAGE_LENGTH = 500


def _truncate(value: str | None, limit: int) -> str | None:
    if value is None or len(value) <= limit:
        return value
    return value[: limit - len(TRUNCATION_SUFFIX)] + TRUNCATION_SUFFIX


def parsed_query_to_dict(parsed: ParsedSearchQuery) -> dict:
    """JSON-safe dict for the parsed_query/corrected_query JSONB columns."""

    def convert(value):
        if isinstance(value, Enum):
            return value.value
        # datetime is a subclass of date — check it first.
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, date):
            return value.isoformat()
        if isinstance(value, tuple):
            return [convert(item) for item in value]
        return value

    return {f.name: convert(getattr(parsed, f.name)) for f in fields(parsed)}


def _as_json_dict(value: ParsedSearchQuery | dict | None) -> dict | None:
    if value is None or isinstance(value, dict):
        return value
    return parsed_query_to_dict(value)


def record_interpretation(
    *,
    raw_query: str,
    status: InterpretationStatus | str,
    model: str | None = None,
    parser_version: str | None = None,
    prompt_version: str | None = None,
    raw_response: str | None = None,
    parsed_query: ParsedSearchQuery | dict | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
    fallback_used: bool = False,
    llm_latency_ms: int | None = None,
    search_latency_ms: int | None = None,
    result_count: int | None = None,
    session_factory=get_session,
) -> int | None:
    """Persist one interpretation attempt; return the row id, or None.

    An invalid ``status`` raises ValueError eagerly (programmer error — the
    parser only produces InterpretationStatus values). Database failures are
    swallowed and yield None: the search request keeps working without its
    audit row.
    """
    status_value = InterpretationStatus(status)
    session = None
    try:
        session = session_factory()
        log = SearchInterpretationLog(
            raw_query=_truncate(raw_query, MAX_QUERY_LENGTH),
            model=model,
            parser_version=parser_version,
            prompt_version=prompt_version,
            raw_response=_truncate(raw_response, MAX_RAW_RESPONSE_LENGTH),
            parsed_query=_as_json_dict(parsed_query),
            status=status_value.value,
            error_code=error_code,
            error_message=_truncate(error_message, MAX_ERROR_MESSAGE_LENGTH),
            fallback_used=fallback_used or status_value is InterpretationStatus.FALLBACK,
            llm_latency_ms=llm_latency_ms,
            search_latency_ms=search_latency_ms,
            result_count=result_count,
        )
        session.add(log)
        session.commit()
        return log.id
    except (SystemExit, Exception):
        # SystemExit included: config_loader's require() exits when DB config
        # is missing — an audit write must never kill the search process.
        logger.exception("Failed to record search interpretation (status=%s)", status_value.value)
        if session is not None:
            try:
                session.rollback()
            except Exception:
                logger.exception("Rollback after failed interpretation write also failed")
        return None
    finally:
        if session is not None:
            try:
                session.close()
            except Exception:
                logger.exception("Closing audit session failed")


def record_feedback(
    interpretation_log_id: int,
    feedback: SearchFeedback,
    *,
    session_factory=get_session,
) -> bool:
    """Attach (or update) user feedback on an interpretation row.

    Repeated calls overwrite the previous verdict/comment/correction —
    the user may change their mind. Returns False when the row does not
    exist (e.g. already expired) or the write failed.
    """
    session = None
    try:
        session = session_factory()
        log = session.get(SearchInterpretationLog, interpretation_log_id)
        if log is None:
            logger.warning("Feedback for unknown interpretation log id=%s", interpretation_log_id)
            return False
        log.feedback_verdict = feedback.verdict.value
        log.feedback_comment = _truncate(feedback.comment, MAX_COMMENT_LENGTH)
        log.corrected_query = _as_json_dict(feedback.corrected_query)
        log.feedback_at = func.now()
        session.commit()
        return True
    except (SystemExit, Exception):
        logger.exception("Failed to record search feedback (log id=%s)", interpretation_log_id)
        if session is not None:
            try:
                session.rollback()
            except Exception:
                logger.exception("Rollback after failed feedback write also failed")
        return False
    finally:
        if session is not None:
            try:
                session.close()
            except Exception:
                logger.exception("Closing audit session failed")


def delete_expired_interpretations(*, session_factory=get_session) -> int:
    """Retention sweep (ADR-017: 90 days): delete rows past expires_at.

    Linked llm_usage_logs rows survive with search_interpretation_log_id
    set to NULL (ON DELETE SET NULL) — cost history is never lost.
    Maintenance path: database errors propagate to the caller.
    """
    session = session_factory()
    try:
        result = session.execute(
            delete(SearchInterpretationLog).where(SearchInterpretationLog.expires_at < func.now())
        )
        session.commit()
        deleted = result.rowcount or 0
        if deleted:
            logger.info("Deleted %d expired search interpretation logs", deleted)
        return deleted
    finally:
        session.close()
