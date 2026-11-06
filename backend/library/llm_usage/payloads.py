"""Bounded, best-effort LLM request/response audit, independent of cost retention."""

import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete

from library.config_loader import load_config
from library.db.engine import get_session
from library.db.models import LlmCallPayload

logger = logging.getLogger(__name__)
MAX_FIELD_CHARS = 200_000


def _config():
    try:
        return load_config()
    except (Exception, SystemExit):
        logger.warning("LLM payload configuration unavailable; using defaults")
        return {}


def payload_enabled() -> bool:
    return str(_config().get("LLM_PAYLOAD_STORE", True)).strip().casefold() not in {
        "false", "0", "no", "off", "none", "",
    }


def retention_days() -> int:
    try:
        days = int(_config().get("LLM_PAYLOAD_RETENTION_DAYS", 30))
        return days if days > 0 else 30
    except (TypeError, ValueError, OverflowError):
        return 30


def build_payload(*, system_prompt, request_text, response_text, error, request_extra) -> dict:
    values = {"system_prompt": system_prompt, "request_text": request_text,
              "response_text": response_text, "error": error}
    values = {key: str(value) if value is not None else None for key, value in values.items()}
    request_truncated = any(len(values[key] or "") > MAX_FIELD_CHARS for key in ("system_prompt", "request_text"))
    response_truncated = any(len(values[key] or "") > MAX_FIELD_CHARS for key in ("response_text", "error"))
    try:
        extra = json.loads(json.dumps(request_extra, ensure_ascii=False, allow_nan=False))
    except (TypeError, ValueError, OverflowError, RecursionError):
        logger.warning("Non-JSON LLM request metadata omitted")
        extra = None
    return {**{key: value[:MAX_FIELD_CHARS] if value is not None else None for key, value in values.items()},
            "request_extra": extra, "request_truncated": request_truncated, "response_truncated": response_truncated}


def store_payload(session, *, usage_log_id, document_id, operation, provider, model, payload) -> int | None:
    try:
        with session.begin_nested():
            row = LlmCallPayload(usage_log_id=usage_log_id, document_id=document_id, operation=operation,
                                 provider=provider, model=model, **payload)
            session.add(row)
            session.flush()
            return row.id
    except (Exception, SystemExit):
        # Do not log payload contents (including SQL parameters on an integrity error).
        logger.warning("LLM payload write failed (operation=%s)", operation)
        return None


def store_payload_standalone(**fields) -> int | None:
    session = None
    try:
        if not payload_enabled():
            return None
        from library.llm_usage.context import current_usage_context

        fields.setdefault("usage_log_id", None)
        fields.setdefault("document_id", current_usage_context()[0])
        session = get_session()
        row_id = store_payload(session, **fields)
        session.commit()
        return row_id
    except (Exception, SystemExit):
        logger.warning("Standalone LLM payload write failed")
        return None
    finally:
        if session is not None:
            try:
                session.close()
            except (Exception, SystemExit):
                logger.warning("Closing LLM payload session failed")


def delete_expired_llm_payloads() -> int:
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=retention_days())
    with get_session() as session:
        result = session.execute(delete(LlmCallPayload).where(LlmCallPayload.created_at < cutoff))
        session.commit()
        return result.rowcount
