"""Observed health of external dependencies.

This deliberately reports outcomes of real requests rather than issuing
synthetic LLM prompts. A status page must not consume LLM quota or turn a
provider's transient probe failure into a customer-visible outage.
"""

from datetime import UTC, datetime, timedelta

from flask import Blueprint, jsonify, request
from sqlalchemy import func, select

from library.db.engine import get_scoped_session
from library.db.models import ExternalServiceEvent, LlmUsageLog

bp = Blueprint("service_status", __name__)

DEFAULT_WINDOW_MINUTES = 15
MAX_WINDOW_MINUTES = 24 * 60


def _window_minutes() -> int:
    value = request.args.get("window_minutes", default=DEFAULT_WINDOW_MINUTES, type=int)
    return max(1, min(value or DEFAULT_WINDOW_MINUTES, MAX_WINDOW_MINUTES))


def _status(successes: int, failures: int) -> str:
    if failures and not successes:
        return "down"
    if failures:
        return "warning"
    if successes:
        return "ok"
    return "unknown"


def _utc_iso(value: datetime | None) -> str | None:
    """Serialize database timestamps explicitly as UTC for browser clients."""
    if value is None:
        return None
    return value.replace(tzinfo=UTC).isoformat().replace("+00:00", "Z")


def _llm_service(session, since, *, provider: str, service_id: str, name: str) -> dict:
    totals = session.execute(
        select(
            func.count().filter(LlmUsageLog.success.is_(True)).label("successes"),
            func.count().filter(LlmUsageLog.success.is_(False)).label("failures"),
            func.max(LlmUsageLog.called_at).filter(LlmUsageLog.success.is_(True)).label("last_success_at"),
            func.max(LlmUsageLog.called_at).filter(LlmUsageLog.success.is_(False)).label("last_failure_at"),
        ).where(LlmUsageLog.provider == provider, LlmUsageLog.called_at >= since)
    ).one()
    last = session.execute(
        select(LlmUsageLog.operation, LlmUsageLog.error_code)
        .where(LlmUsageLog.provider == provider, LlmUsageLog.called_at >= since)
        .order_by(LlmUsageLog.called_at.desc()).limit(1)
    ).one_or_none()
    successes, failures = int(totals.successes or 0), int(totals.failures or 0)
    return {
        "id": service_id, "name": name, "status": _status(successes, failures), "observed_only": True,
        "successes": successes, "failures": failures,
        "last_success_at": _utc_iso(totals.last_success_at),
        "last_failure_at": _utc_iso(totals.last_failure_at),
        "last_error_code": last.error_code if last else None,
        "last_operation": last.operation if last else None,
    }


def _external_service(session, since, *, service: str, name: str) -> dict:
    totals = session.execute(
        select(
            func.count().filter(ExternalServiceEvent.success.is_(True)).label("successes"),
            func.count().filter(ExternalServiceEvent.success.is_(False)).label("failures"),
            func.max(ExternalServiceEvent.occurred_at).filter(ExternalServiceEvent.success.is_(True)).label("last_success_at"),
            func.max(ExternalServiceEvent.occurred_at).filter(ExternalServiceEvent.success.is_(False)).label("last_failure_at"),
        ).where(ExternalServiceEvent.service == service, ExternalServiceEvent.occurred_at >= since)
    ).one()
    last = session.execute(
        select(ExternalServiceEvent.operation, ExternalServiceEvent.error_code)
        .where(ExternalServiceEvent.service == service, ExternalServiceEvent.occurred_at >= since)
        .order_by(ExternalServiceEvent.occurred_at.desc()).limit(1)
    ).one_or_none()
    successes, failures = int(totals.successes or 0), int(totals.failures or 0)
    return {
        "id": service, "name": name, "status": _status(successes, failures), "observed_only": True,
        "successes": successes, "failures": failures,
        "last_success_at": _utc_iso(totals.last_success_at),
        "last_failure_at": _utc_iso(totals.last_failure_at),
        "last_error_code": last.error_code if last else None,
        "last_operation": last.operation if last else None,
    }


@bp.get("/service_status")
def service_status():
    """Return observed CloudFerro LLM and embedding health from production calls.

    ``unknown`` means no call was made in the requested period; it never means
    that a synthetic check failed. ``down`` means every observed recent call
    failed, while ``warning`` means failures occurred but the provider also
    served at least one successful request.
    """
    window_minutes = _window_minutes()
    # ``called_at`` is a PostgreSQL timestamp without timezone, so normalize
    # the UTC clock to the same representation for the query boundary.
    now = datetime.now(UTC).replace(tzinfo=None)
    since = now - timedelta(minutes=window_minutes)
    session = get_scoped_session()

    return jsonify({
        "status": "success",
        "observed_at": _utc_iso(now),
        "window_minutes": window_minutes,
        "services": [
            _llm_service(session, since, provider="cloudferro", service_id="cloudferro", name="CloudFerro Sherlock (LLM i embeddingi)"),
            _llm_service(session, since, provider="arklabs", service_id="arklabs", name="ARK Labs (LLM)"),
            _llm_service(session, since, provider="openai", service_id="openai", name="OpenAI (LLM)"),
            _llm_service(session, since, provider="aws-bedrock", service_id="aws_bedrock", name="AWS Bedrock (LLM)"),
            _llm_service(session, since, provider="google-vertexai", service_id="google_vertexai", name="Google Vertex AI (LLM)"),
            _external_service(session, since, service="webshare", name="Webshare proxy API"),
            _external_service(session, since, service="locationiq", name="LocationIQ geocoding"),
            _external_service(session, since, service="wikidata", name="Wikidata API"),
            _external_service(session, since, service="overpass", name="Overpass / OpenStreetMap"),
        ],
    })
