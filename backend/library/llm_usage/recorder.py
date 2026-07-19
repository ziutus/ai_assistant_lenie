"""Central recorder of LLM/embedding usage (search-rebuild plan, stage 2B).

This is the single write path for llm_usage_logs: one call to
``record_llm_usage()`` per LLM call leaves exactly one row. Domain modules
never compute costs themselves — they receive the returned ``UsageRecord``
summary (stage 3 wires this into ``ai.py``).

Writes use their own short-lived session, independent of any business
transaction: a database failure is logged and swallowed, because usage
accounting must never break the operation that triggered the LLM call.
Provider-reported data (token counts) is sanitized, not validated — a
malformed value from the API becomes NULL with a warning. Money arguments
built by our own code (``reported_cost``, ``credits_used``) are validated
strictly: a float raises ``PricingError``.
"""

import logging
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select

from library.db.engine import get_session
from library.db.models import LlmPricing, LlmUsageLog
from library.llm_usage.pricing import (
    UNKNOWN_COST,
    CostEstimate,
    CostStatus,
    PricingError,
    PricingMode,
    estimate_cost,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class UsageRecord:
    """Summary handed back to the caller of ``record_llm_usage()``.

    ``usage_log_id`` is None when the database write failed (the call
    itself must not fail because of that). ``cost`` carries the resolved
    cost with its status (reported/estimated/unknown) and currency.
    """

    usage_log_id: int | None
    cost: CostEstimate
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    pricing_version: str | None
    latency_ms: int | None = None


def _decimal_money(name: str, value) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, float):
        raise PricingError(f"{name} must be Decimal, not float (money is never float)")
    if isinstance(value, int):
        value = Decimal(value)
    if not isinstance(value, Decimal):
        raise PricingError(f"{name} must be Decimal, got {type(value).__name__}")
    if value < 0:
        raise PricingError(f"{name} must not be negative")
    return value


def _sanitize_tokens(name: str, value) -> int | None:
    """Token counts are provider-reported facts: drop bad values, never raise."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        logger.warning("Ignoring invalid %s reported by provider: %r", name, value)
        return None
    return value


def _active_pricing(session, provider: str, model: str) -> LlmPricing | None:
    stmt = select(LlmPricing).where(
        LlmPricing.provider == provider,
        LlmPricing.model == model,
        LlmPricing.effective_to.is_(None),
    )
    return session.execute(stmt).scalar_one_or_none()


def _resolve_cost(
    pricing: LlmPricing | None,
    reported_cost: Decimal | None,
    reported_cost_currency: str | None,
    prompt_tokens: int | None,
    completion_tokens: int | None,
) -> CostEstimate:
    if reported_cost is not None:
        # A provider-reported cost always wins over the local estimate.
        return CostEstimate(
            input_cost=None,
            output_cost=None,
            total_cost=reported_cost,
            currency=reported_cost_currency,
            status=CostStatus.REPORTED,
        )
    if pricing is None or prompt_tokens is None or completion_tokens is None:
        return UNKNOWN_COST
    return estimate_cost(
        pricing_mode=pricing.pricing_mode,
        input_price_per_million=pricing.input_price_per_million,
        output_price_per_million=pricing.output_price_per_million,
        currency=pricing.currency,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )


def record_llm_usage(
    *,
    operation: str,
    provider: str,
    model: str,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    total_tokens: int | None = None,
    endpoint: str | None = None,
    request_id: str | None = None,
    search_interpretation_log_id: int | None = None,
    document_id: int | None = None,
    analysis_job_id: str | None = None,
    analysis_run_id: int | None = None,
    credits_used: Decimal | None = None,
    reported_cost: Decimal | None = None,
    reported_cost_currency: str | None = None,
    success: bool = True,
    error_code: str | None = None,
    latency_ms: int | None = None,
    session_factory=get_session,
) -> UsageRecord:
    """Persist exactly one llm_usage_logs row for one LLM/embedding call.

    Token counts are stored even when no price is known; a missing price
    yields ``cost_status='unknown'``, never an exception or a zero cost.
    ``reported_cost`` (Decimal + ``reported_cost_currency``) takes priority
    over the local estimate. Rates and currency of the matched price-list
    row are snapshotted onto the usage row, so later price changes never
    alter history.
    """
    reported = _decimal_money("reported_cost", reported_cost)
    if reported is not None and not reported_cost_currency:
        raise PricingError("reported_cost requires reported_cost_currency")
    credits = _decimal_money("credits_used", credits_used)

    prompt = _sanitize_tokens("prompt_tokens", prompt_tokens)
    completion = _sanitize_tokens("completion_tokens", completion_tokens)
    total = _sanitize_tokens("total_tokens", total_tokens)
    if total is None and (prompt is not None or completion is not None):
        total = (prompt or 0) + (completion or 0)

    session = None
    try:
        session = session_factory()
        pricing = _active_pricing(session, provider, model)
        cost = _resolve_cost(pricing, reported, reported_cost_currency, prompt, completion)

        from library.llm_usage.context import current_usage_context
        context_document_id, context_job_id, context_run_id = current_usage_context()
        document_id = document_id if document_id is not None else context_document_id
        analysis_job_id = analysis_job_id if analysis_job_id is not None else context_job_id
        analysis_run_id = analysis_run_id if analysis_run_id is not None else context_run_id

        log = LlmUsageLog(
            request_id=request_id,
            search_interpretation_log_id=search_interpretation_log_id,
            document_id=document_id,
            analysis_job_id=analysis_job_id,
            analysis_run_id=analysis_run_id,
            operation=operation,
            provider=provider,
            model=model,
            endpoint=endpoint,
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=total,
            credits_used=credits,
            pricing_mode=pricing.pricing_mode if pricing else PricingMode.UNKNOWN.value,
            pricing_version=pricing.pricing_version if pricing else None,
            input_price_per_million=pricing.input_price_per_million if pricing else None,
            output_price_per_million=pricing.output_price_per_million if pricing else None,
            cost_amount=cost.total_cost,
            cost_currency=cost.currency,
            cost_status=cost.status.value,
            success=success,
            error_code=error_code,
            latency_ms=latency_ms,
        )
        session.add(log)
        session.commit()
        return UsageRecord(
            usage_log_id=log.id,
            cost=cost,
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=total,
            pricing_version=pricing.pricing_version if pricing else None,
            latency_ms=latency_ms,
        )
    except (SystemExit, Exception):
        # Usage accounting must never break (or kill — config_loader's
        # require() raises SystemExit when DB config is missing) the business
        # call that used the LLM. A lost record violates the
        # one-record-per-call guarantee, so log loudly with the full context.
        logger.exception(
            "Failed to record LLM usage (operation=%s, provider=%s, model=%s)", operation, provider, model
        )
        if session is not None:
            try:
                session.rollback()
            except Exception:
                logger.exception("Rollback after failed usage write also failed")
        return UsageRecord(
            usage_log_id=None,
            cost=UNKNOWN_COST,
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=total,
            pricing_version=None,
            latency_ms=latency_ms,
        )
    finally:
        if session is not None:
            try:
                session.close()
            except Exception:
                logger.exception("Closing usage-recorder session failed")
