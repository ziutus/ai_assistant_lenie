"""Diagnostic usage/cost summaries for document-extraction modules (stage 3b).

timeline_events.py, tones.py and time_periods.py each make one or more
ai_ask() calls per fragment/chapter and want to report tokens and cost in
their dry-run/CLI output. Cost is never computed here — it is read straight
from the UsageRecord that ai_ask() already attached to response.usage
(library.llm_usage.recorder, stage 3). This module only shapes and
aggregates that data into JSON-friendly dicts, replacing the per-module
private `_response_usage()`/`_combine_costs()` duplication (which always
returned None: AiResponse has no cost_usd/cost/credits_used attribute).

No sqlalchemy import here on purpose — response.usage is duck-typed
(usage_log_id/total_tokens/cost.total_cost/cost.currency/cost.status), so
this module stays importable in the lightweight (uvx) test environment.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

UNKNOWN_STATUS = "unknown"


@dataclass(frozen=True)
class UsageReport:
    llm_calls: int
    usage_log_ids: tuple[int, ...]
    llm_tokens: int | None
    llm_cost_amount: str | None
    llm_cost_currency: str | None
    llm_cost_status: str

    def as_dict(self) -> dict:
        return {
            "llm_calls": self.llm_calls,
            "usage_log_ids": list(self.usage_log_ids),
            "llm_tokens": self.llm_tokens,
            "llm_cost_amount": self.llm_cost_amount,
            "llm_cost_currency": self.llm_cost_currency,
            "llm_cost_status": self.llm_cost_status,
        }


def usage_report(usage) -> UsageReport:
    """Shape one ai_ask() call's usage for a diagnostic report.

    ``usage`` is ``response.usage`` (a ``UsageRecord``, or ``None`` when the
    central recorder was never reached — e.g. tests that stub ``ai_ask()``
    directly). Money is read as-is from ``usage.cost``, never recomputed;
    it is rendered as ``str(Decimal)`` to keep exact precision in JSON.
    """
    if usage is None:
        return UsageReport(1, (), None, None, None, UNKNOWN_STATUS)
    cost = usage.cost
    return UsageReport(
        llm_calls=1,
        usage_log_ids=(usage.usage_log_id,) if usage.usage_log_id is not None else (),
        llm_tokens=usage.total_tokens,
        llm_cost_amount=str(cost.total_cost) if cost.total_cost is not None else None,
        llm_cost_currency=cost.currency,
        llm_cost_status=cost.status.value if hasattr(cost.status, "value") else cost.status,
    )


def combine_usage_reports(reports: Iterable[dict]) -> dict:
    """Aggregate several ``usage_report(...).as_dict()``-shaped dicts into one.

    Amounts are only summed when every component has a known amount in the
    *same* currency (plan rule: never silently mix currencies, never turn a
    missing price into a zero cost). Otherwise the combined cost is
    ``None``/``unknown`` even though individual calls may have a known cost.
    """
    reports = list(reports)
    llm_calls = sum(r["llm_calls"] for r in reports)
    usage_log_ids = [id_ for r in reports for id_ in r["usage_log_ids"]]
    tokens = [r["llm_tokens"] for r in reports]
    llm_tokens = sum(tokens) if tokens and all(t is not None for t in tokens) else None

    amounts = [r["llm_cost_amount"] for r in reports]
    currencies = {r["llm_cost_currency"] for r in reports if r["llm_cost_currency"] is not None}
    statuses = {r["llm_cost_status"] for r in reports}

    if amounts and all(a is not None for a in amounts) and len(currencies) == 1:
        total_amount = str(sum(Decimal(a) for a in amounts))
        total_currency = next(iter(currencies))
        # A mix of e.g. "reported" and "estimated" components is reported as
        # the more conservative "estimated" rather than inventing a status.
        total_status = statuses.pop() if len(statuses) == 1 else "estimated"
    else:
        total_amount = None
        total_currency = None
        total_status = UNKNOWN_STATUS

    return {
        "llm_calls": llm_calls,
        "usage_log_ids": usage_log_ids,
        "llm_tokens": llm_tokens,
        "llm_cost_amount": total_amount,
        "llm_cost_currency": total_currency,
        "llm_cost_status": total_status,
    }
