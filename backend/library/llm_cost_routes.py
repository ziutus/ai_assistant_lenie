"""HTTP reporting API for LLM usage costs."""

from datetime import date, datetime, time, timedelta

from flask import Blueprint, abort, g, jsonify, request
from sqlalchemy import func, select

from library.db.engine import get_scoped_session
from library.db.models import Document, DocumentAnalysisJob, LlmCallPayload, LlmUsageLog

bp = Blueprint("llm_costs", __name__)


def _date_arg(name: str, default: date) -> date:
    value = request.args.get(name)
    if not value:
        return default
    return date.fromisoformat(value)


def _money(value):
    return str(value) if value is not None else None


@bp.get("/openrouter_balance")
def openrouter_balance():
    """What is left of the OpenRouter key's spending limit (``/key``), for the cost page and the tool radar header.

    ``balance.status`` is ``ok`` (with ``has_limit``, ``limit_usd``, ``remaining_usd``, ``usage_usd``, ``reset``,
    ``low``, ``exhausted``), ``not_configured`` or ``unavailable``. Cached for a minute; reads only the key's own data.
    """
    from library.api.openrouter.openrouter_key import fetch_key_status

    return jsonify({"balance": fetch_key_status()})


@bp.get("/llm_costs")
def llm_costs():
    today = date.today()
    document_id = request.args.get("document_id", type=int)
    # A document report should cover its full lifecycle when opened directly.
    # The global report deliberately retains its month-to-date default.
    has_date_filter = bool(request.args.get("from") or request.args.get("to"))
    try:
        date_from = _date_arg("from", today.replace(day=1)) if (has_date_filter or document_id is None) else None
        date_to = _date_arg("to", today) if (has_date_filter or document_id is None) else None
        if date_from is not None and date_to is not None and date_to < date_from:
            raise ValueError("to must not be earlier than from")
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400

    filters = []
    if date_from is not None and date_to is not None:
        start = datetime.combine(date_from, time.min)
        end = datetime.combine(date_to + timedelta(days=1), time.min)
        filters.extend([LlmUsageLog.called_at >= start, LlmUsageLog.called_at < end])
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
    providers = session.execute(
        select(
            LlmUsageLog.provider,
            LlmUsageLog.cost_currency,
            func.count().label("calls"),
            func.coalesce(func.sum(LlmUsageLog.total_tokens), 0).label("tokens"),
            func.sum(LlmUsageLog.cost_amount).label("cost"),
            func.count().filter(LlmUsageLog.cost_status == "unknown").label("unknown_calls"),
            func.count().filter(LlmUsageLog.success.is_(False)).label("failed_calls"),
        ).where(*filters).group_by(LlmUsageLog.provider, LlmUsageLog.cost_currency)
        .order_by(func.sum(LlmUsageLog.cost_amount).desc().nullslast(), func.count().desc())
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
    documents = session.execute(
        select(
            LlmUsageLog.document_id,
            Document.title,
            LlmUsageLog.cost_currency,
            func.count().label("calls"),
            func.coalesce(func.sum(LlmUsageLog.total_tokens), 0).label("tokens"),
            func.sum(LlmUsageLog.cost_amount).label("cost"),
            func.count().filter(LlmUsageLog.cost_status == "unknown").label("unknown_calls"),
        )
        .outerjoin(Document, LlmUsageLog.document_id == Document.id)
        .where(*filters)
        .group_by(LlmUsageLog.document_id, Document.title, LlmUsageLog.cost_currency)
        .order_by(func.sum(LlmUsageLog.cost_amount).desc().nullslast(), LlmUsageLog.document_id)
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
    calls = []
    payload_ids = set()
    if document_id is not None:
        calls = session.scalars(
            select(LlmUsageLog).where(*filters).order_by(LlmUsageLog.called_at.desc()).limit(1000)
        ).all()

    if calls:
        payload_ids = set(session.scalars(select(LlmCallPayload.usage_log_id).where(
            LlmCallPayload.usage_log_id.in_([row.id for row in calls]),
        )).all())

    return jsonify({
        "status": "success", "from": date_from.isoformat() if date_from else None,
        "to": date_to.isoformat() if date_to else None,
        "document_id": document_id,
        "totals": [{"currency": r.cost_currency, "calls": r.calls, "tokens": r.tokens,
                    "cost": _money(r.cost), "unknown_calls": r.unknown_calls} for r in totals],
        "providers": [{"provider": r.provider, "currency": r.cost_currency, "calls": r.calls, "tokens": r.tokens,
                       "cost": _money(r.cost), "unknown_calls": r.unknown_calls, "failed_calls": r.failed_calls}
                      for r in providers],
        "daily": [{"day": str(r.day), "currency": r.cost_currency, "calls": r.calls,
                   "tokens": r.tokens, "cost": _money(r.cost)} for r in daily],
        "operations": [{"operation": r.operation, "model": r.model, "currency": r.cost_currency,
                        "calls": r.calls, "tokens": r.tokens, "cost": _money(r.cost)} for r in operations],
        "documents": [{"document_id": r.document_id, "title": r.title, "currency": r.cost_currency,
                       "calls": r.calls, "tokens": r.tokens, "cost": _money(r.cost),
                       "unknown_calls": r.unknown_calls} for r in documents],
        "analyses": [{"job_id": r.analysis_job_id, "run_id": r.run_id, "currency": r.cost_currency,
                      "started_at": r.started_at.isoformat() if r.started_at else None,
                      "calls": r.calls, "tokens": r.tokens, "cost": _money(r.cost)} for r in jobs],
        "calls": [{
            "id": r.id, "has_payload": r.id in payload_ids, "document_id": r.document_id, "job_id": r.analysis_job_id,
            "run_id": r.analysis_run_id, "called_at": r.called_at.isoformat(),
            "operation": r.operation, "provider": r.provider, "model": r.model,
            "prompt_tokens": r.prompt_tokens, "completion_tokens": r.completion_tokens,
            "tokens": r.total_tokens, "cost": _money(r.cost_amount), "currency": r.cost_currency,
            "cost_status": r.cost_status, "success": r.success, "error_code": r.error_code,
        } for r in calls],
    })


@bp.get("/llm_usage/<int:usage_id>/payload")
def llm_usage_payload(usage_id):
    """Full retained audit for one usage row; absence/expiration is payload=null."""
    # Authentication is resolved by the application's before_request hook.
    auth = getattr(g, "auth", None)
    if auth is None:
        abort(401)
    if auth.kind not in {"user", "service"}:
        abort(403)
    session = get_scoped_session()
    usage = session.get(LlmUsageLog, usage_id)
    if usage is None:
        abort(404)
    row = session.scalar(select(LlmCallPayload).where(LlmCallPayload.usage_log_id == usage_id)
                         .order_by(LlmCallPayload.id.desc()).limit(1))
    fields = ("id", "operation", "provider", "model", "success", "error_code", "prompt_tokens",
              "completion_tokens", "total_tokens", "cost_currency", "document_id")
    data = {field: getattr(usage, field) for field in fields}
    data.update(called_at=usage.called_at.isoformat(), cost_amount=_money(usage.cost_amount))
    payload = None
    if row is not None:
        payload = {field: getattr(row, field) for field in (
            "system_prompt", "request_text", "response_text", "error", "request_extra",
            "request_truncated", "response_truncated",
        )}
        payload["created_at"] = row.created_at.isoformat()
    return jsonify(usage=data, payload=payload)


@bp.get("/document/<int:doc_id>/llm_payloads")
def document_llm_payloads(doc_id):
    """Retained document audits, including decisions without a usage-log row."""
    auth = getattr(g, "auth", None)
    if auth is None:
        abort(401)
    if auth.kind not in {"user", "service"}:
        abort(403)
    try:
        limit = int(request.args.get("limit", "20"))
        offset = int(request.args.get("offset", "0"))
        if not 1 <= limit <= 100 or not 0 <= offset <= 2**63 - 1:
            raise ValueError
    except ValueError:
        abort(400, "limit must be an integer from 1 to 100; offset must be a nonnegative 64-bit integer")

    session = get_scoped_session()
    if session.scalar(select(Document.id).where(Document.id == doc_id)) is None:
        abort(404)
    filters = [LlmCallPayload.document_id == doc_id]
    operation = request.args.get("operation")
    if operation:
        filters.append(LlmCallPayload.operation == operation)
    total = session.scalar(select(func.count()).select_from(LlmCallPayload).where(*filters))
    rows = session.scalars(
        select(LlmCallPayload).where(*filters)
        .order_by(LlmCallPayload.created_at.desc(), LlmCallPayload.id.desc()).limit(limit).offset(offset)
    ).all()
    fields = ("id", "usage_log_id", "operation", "provider", "model", "system_prompt", "request_text",
              "response_text", "error", "request_extra", "request_truncated", "response_truncated")
    return jsonify(payloads=[{**{field: getattr(row, field) for field in fields},
                              "created_at": row.created_at.isoformat()} for row in rows], total=total)
