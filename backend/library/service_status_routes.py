"""Observed health of external dependencies without synthetic paid probes."""
from datetime import UTC, datetime, timedelta
from flask import Blueprint, jsonify, request
from sqlalchemy import func, select
from library.db.engine import get_scoped_session
from library.db.models import ExternalServiceEvent, LlmUsageLog

bp = Blueprint("service_status", __name__)

def _status(ok, failed): return "down" if failed and not ok else "warning" if failed else "ok" if ok else "unknown"

def _utc_iso(value):
    return value.replace(tzinfo=UTC).isoformat().replace("+00:00", "Z") if value else None

def _observed(session, since, model, service, time_col, label, source):
    totals = session.execute(select(func.count().filter(model.success.is_(True)).label("ok"), func.count().filter(model.success.is_(False)).label("failed"), func.max(time_col).filter(model.success.is_(True)).label("last_ok"), func.max(time_col).filter(model.success.is_(False)).label("last_failed")).where(source, time_col >= since)).one()
    last = session.execute(select(model.operation, model.error_code).where(source, time_col >= since).order_by(time_col.desc()).limit(1)).one_or_none()
    ok, failed = int(totals.ok or 0), int(totals.failed or 0)
    return {"id": service, "name": label, "status": _status(ok, failed), "observed_only": True, "successes": ok, "failures": failed, "last_success_at": _utc_iso(totals.last_ok), "last_failure_at": _utc_iso(totals.last_failed), "last_error_code": last.error_code if last else None, "last_operation": last.operation if last else None}

@bp.get("/service_status")
def service_status():
    minutes = max(1, min(request.args.get("window_minutes", default=15, type=int) or 15, 1440))
    now = datetime.now(UTC).replace(tzinfo=None); since = now - timedelta(minutes=minutes); session = get_scoped_session()
    llm = lambda provider, ident, name: _observed(session, since, LlmUsageLog, ident, LlmUsageLog.called_at, name, LlmUsageLog.provider == provider)
    ext = lambda ident, name: _observed(session, since, ExternalServiceEvent, ident, ExternalServiceEvent.occurred_at, name, ExternalServiceEvent.service == ident)
    return jsonify({"status": "success", "observed_at": _utc_iso(now), "window_minutes": minutes, "services": [llm("cloudferro", "cloudferro", "CloudFerro Sherlock (LLM i embeddingi)"), llm("arklabs", "arklabs", "ARK Labs (LLM)"), llm("openai", "openai", "OpenAI (LLM)"), llm("aws-bedrock", "aws_bedrock", "AWS Bedrock (LLM)"), llm("google-vertexai", "google_vertexai", "Google Vertex AI (LLM)"), ext("webshare", "Webshare proxy API"), ext("locationiq", "LocationIQ geocoding"), ext("wikidata", "Wikidata API"), ext("overpass", "Overpass / OpenStreetMap")]})
