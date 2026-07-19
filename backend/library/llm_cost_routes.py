"""HTTP reporting API for LLM usage costs."""

from datetime import date, datetime, time, timedelta

from flask import Blueprint, jsonify, request
from sqlalchemy import func, select

from library.db.engine import get_scoped_session
from library.db.models import DocumentAnalysisJob, LlmUsageLog

bp = Blueprint("llm_costs", __name__)


def _date_arg(name: str, default: date) -> date:
    value = request.args.get(name)
    if not value:
        return default
    return date.fromisoformat(value)


def _money(value):
    return str(value) if value is not None else None


@bp.get("/llm_costs")
def llm_costs():
    today = date.today()
    try:
        date_from = _date_arg("from", today.replace(day=1))
        date_to = _date_arg("to", today)
        if date_to < date_from:
            raise ValueError("to must not be earlier than from")
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400

    document_id = request.args.get("document_id", type=int)
    start = datetime.combine(date_from, time.min)
    end = datetime.combine(date_to + timedelta(days=1), time.min)
    filters = [LlmUsageLog.called_at >= start, LlmUsageLog.called_at < end]
    if document_id is not None:
        filters.append(LlmUsageLog.document_id == document_id)

    session = get_scoped_session()
    totals = session.execute(
        select(
            LlmUsageLog.cost_currency,
            func.count().label("calls"),
            func.coalesce(func.sum(LlmUsageLog.total_tokens), 0).label("tokens"),
            func.sum(LlmUsageLog.cost_amount).label("cost"),
            func.count().filter(LlmUsageLog.cost_status == "unknown").label("unknown_calls"),
        ).where(*filters).group_by(LlmUsageLog.cost_currency)
    ).all()
    day = func.date(LlmUsageLog.called_at).label("day")
    daily = session.execute(
        select(day, LlmUsageLog.cost_currency, func.count().label("calls"),
               func.coalesce(func.sum(LlmUsageLog.total_tokens), 0).label("tokens"),
               func.sum(LlmUsageLog.cost_amount).label("cost"))
        .where(*filters).group_by(day, LlmUsageLog.cost_currency).order_by(day)
    ).all()
    operations = session.execute(
        select(LlmUsageLog.operation, LlmUsageLog.model, LlmUsageLog.cost_currency,
               func.count().label("calls"), func.coalesce(func.sum(LlmUsageLog.total_tokens), 0).label("tokens"),
               func.sum(LlmUsageLog.cost_amount).label("cost"))
        .where(*filters).group_by(LlmUsageLog.operation, LlmUsageLog.model, LlmUsageLog.cost_currency)
        .order_by(func.sum(LlmUsageLog.cost_amount).desc().nullslast())
    ).all()
    jobs = session.execute(
        select(LlmUsageLog.analysis_job_id, DocumentAnalysisJob.run_id, LlmUsageLog.cost_currency,
               func.min(LlmUsageLog.called_at).label("started_at"), func.count().label("calls"),
               func.coalesce(func.sum(LlmUsageLog.total_tokens), 0).label("tokens"),
               func.sum(LlmUsageLog.cost_amount).label("cost"))
        .outerjoin(DocumentAnalysisJob, LlmUsageLog.analysis_job_id == DocumentAnalysisJob.id)
        .where(*filters, LlmUsageLog.analysis_job_id.isnot(None))
        .group_by(LlmUsageLog.analysis_job_id, DocumentAnalysisJob.run_id, LlmUsageLog.cost_currency)
        .order_by(func.min(LlmUsageLog.called_at).desc())
    ).all()

    return jsonify({
        "status": "success", "from": date_from.isoformat(), "to": date_to.isoformat(),
        "document_id": document_id,
        "totals": [{"currency": r.cost_currency, "calls": r.calls, "tokens": r.tokens,
                    "cost": _money(r.cost), "unknown_calls": r.unknown_calls} for r in totals],
        "daily": [{"day": str(r.day), "currency": r.cost_currency, "calls": r.calls,
                   "tokens": r.tokens, "cost": _money(r.cost)} for r in daily],
        "operations": [{"operation": r.operation, "model": r.model, "currency": r.cost_currency,
                        "calls": r.calls, "tokens": r.tokens, "cost": _money(r.cost)} for r in operations],
        "analyses": [{"job_id": r.analysis_job_id, "run_id": r.run_id, "currency": r.cost_currency,
                      "started_at": r.started_at.isoformat() if r.started_at else None,
                      "calls": r.calls, "tokens": r.tokens, "cost": _money(r.cost)} for r in jobs],
    })
