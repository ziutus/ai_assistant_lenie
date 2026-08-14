"""Best-effort audit trail for real non-LLM external service requests."""

import logging
import time

from library.db.engine import get_session
from library.db.models import ExternalServiceEvent

logger = logging.getLogger(__name__)


def record_external_service_event(*, service: str, operation: str, success: bool,
                                  status_code: int | None = None, error_code: str | None = None,
                                  latency_ms: int | None = None) -> None:
    session = None
    try:
        session = get_session()
        session.add(ExternalServiceEvent(
            service=service, operation=operation, success=success,
            status_code=status_code, error_code=error_code, latency_ms=latency_ms,
        ))
        session.commit()
    except (SystemExit, Exception):
        logger.exception("Could not record external service event: %s/%s", service, operation)
        if session is not None:
            session.rollback()
    finally:
        if session is not None:
            session.close()


def observed_request(*, service: str, operation: str, request_fn, success_fn=None):
    """Run one HTTP request and persist its outcome without altering callers."""
    started = time.monotonic()
    try:
        response = request_fn()
    except Exception as exc:
        record_external_service_event(
            service=service, operation=operation, success=False,
            error_code=type(exc).__name__, latency_ms=int((time.monotonic() - started) * 1000),
        )
        raise
    success = bool(success_fn(response) if success_fn else response.ok)
    record_external_service_event(
        service=service, operation=operation, success=success, status_code=response.status_code,
        error_code=None if success else f"HTTP_{response.status_code}",
        latency_ms=int((time.monotonic() - started) * 1000),
    )
    return response
