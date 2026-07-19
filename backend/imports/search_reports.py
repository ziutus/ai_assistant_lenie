#!/usr/bin/env python
"""Reporting queries for search interpretation quality and LLM costs (stage 12).

Two reports over the audit tables the search rebuild introduced (stages 2-4):

- ``--interpretations``: per-day interpretation outcomes from
  search_interpretation_logs — status breakdown, fallback rate, latency,
  feedback verdicts and the top error codes. This is the "dashboard" for
  parser mistakes the plan calls for; run it before/after prompt changes.
- ``--llm-costs``: per-day cost/token totals from llm_usage_logs grouped by
  provider, model and operation (same-currency sums only), followed by an
  ALERT section listing calls whose cost is unknown — i.e. models missing an
  active llm_pricing row. A non-empty alert section sets exit code 2 so the
  report can act as a cron check.

Both reports default to the last 30 days; read-only, safe to run anytime.

Usage:
    cd backend
    python imports/search_reports.py                      # both reports
    python imports/search_reports.py --interpretations --days 7
    python imports/search_reports.py --llm-costs --days 90
"""

import argparse
import datetime
import sys
from collections import defaultdict

sys.path.insert(0, ".")

from sqlalchemy import func, select  # noqa: E402

from library.db.engine import get_session  # noqa: E402
from library.db.models import LlmPricing, LlmUsageLog, SearchInterpretationLog  # noqa: E402


def _since(days: int) -> datetime.datetime:
    return datetime.datetime.now() - datetime.timedelta(days=days)


# --------------------------------------------------------------------------
# Interpretation quality
# --------------------------------------------------------------------------


def interpretation_daily_rows(session, days: int):
    """(day, status, fallback_used) -> count, plus latency averages."""
    day = func.date(SearchInterpretationLog.created_at).label("day")
    stmt = (
        select(
            day,
            SearchInterpretationLog.status,
            func.count().label("cnt"),
            func.count().filter(SearchInterpretationLog.fallback_used.is_(True)).label("fallbacks"),
            func.avg(SearchInterpretationLog.llm_latency_ms).label("avg_llm_ms"),
        )
        .where(SearchInterpretationLog.created_at >= _since(days))
        .group_by(day, SearchInterpretationLog.status)
        .order_by(day.desc(), SearchInterpretationLog.status)
    )
    return session.execute(stmt).all()


def interpretation_error_rows(session, days: int, limit: int = 10):
    """Top error codes for non-ok interpretations."""
    stmt = (
        select(SearchInterpretationLog.error_code, func.count().label("cnt"))
        .where(
            SearchInterpretationLog.created_at >= _since(days),
            SearchInterpretationLog.error_code.isnot(None),
        )
        .group_by(SearchInterpretationLog.error_code)
        .order_by(func.count().desc())
        .limit(limit)
    )
    return session.execute(stmt).all()


def interpretation_feedback_rows(session, days: int):
    """Feedback verdict breakdown (rows without feedback are counted as NULL)."""
    stmt = (
        select(SearchInterpretationLog.feedback_verdict, func.count().label("cnt"))
        .where(SearchInterpretationLog.created_at >= _since(days))
        .group_by(SearchInterpretationLog.feedback_verdict)
        .order_by(func.count().desc())
    )
    return session.execute(stmt).all()


def print_interpretation_report(session, days: int) -> None:
    print(f"=== Interpretacje zapytań (ostatnie {days} dni) ===")
    rows = interpretation_daily_rows(session, days)
    if not rows:
        print("(brak rekordów)")
    else:
        print(f"{'dzień':<12} {'status':<18} {'ile':>5} {'fallback':>9} {'śr. LLM ms':>11}")
        for r in rows:
            avg = f"{float(r.avg_llm_ms):.0f}" if r.avg_llm_ms is not None else "-"
            print(f"{str(r.day):<12} {r.status:<18} {r.cnt:>5} {r.fallbacks or 0:>9} {avg:>11}")

    err = interpretation_error_rows(session, days)
    if err:
        print("\nNajczęstsze kody błędów:")
        for r in err:
            print(f"  {r.error_code:<40} {r.cnt}")

    fb = interpretation_feedback_rows(session, days)
    if fb:
        print("\nFeedback użytkowników:")
        for r in fb:
            print(f"  {r.feedback_verdict or '(brak feedbacku)':<20} {r.cnt}")
    print()


# --------------------------------------------------------------------------
# LLM costs
# --------------------------------------------------------------------------


def llm_cost_rows(session, days: int):
    """(day, provider, model, operation) -> calls, tokens, cost per currency."""
    day = func.date(LlmUsageLog.called_at).label("day")
    stmt = (
        select(
            day,
            LlmUsageLog.provider,
            LlmUsageLog.model,
            LlmUsageLog.operation,
            LlmUsageLog.cost_currency,
            func.count().label("calls"),
            func.coalesce(func.sum(LlmUsageLog.total_tokens), 0).label("tokens"),
            func.sum(LlmUsageLog.cost_amount).label("cost"),
        )
        .where(LlmUsageLog.called_at >= _since(days))
        .group_by(day, LlmUsageLog.provider, LlmUsageLog.model,
                  LlmUsageLog.operation, LlmUsageLog.cost_currency)
        .order_by(day.desc(), LlmUsageLog.provider, LlmUsageLog.model)
    )
    return session.execute(stmt).all()


def unknown_cost_rows(session, days: int):
    """Calls whose cost is unknown, grouped by provider/model — the pricing alert."""
    stmt = (
        select(
            LlmUsageLog.provider,
            LlmUsageLog.model,
            func.count().label("calls"),
            func.max(LlmUsageLog.called_at).label("last_call"),
        )
        .where(
            LlmUsageLog.called_at >= _since(days),
            LlmUsageLog.cost_status == "unknown",
        )
        .group_by(LlmUsageLog.provider, LlmUsageLog.model)
        .order_by(func.count().desc())
    )
    return session.execute(stmt).all()


def models_without_pricing(session):
    """Distinct provider/model pairs seen in usage logs without ANY llm_pricing row."""
    priced = select(LlmPricing.provider, LlmPricing.model).distinct()
    used = select(LlmUsageLog.provider, LlmUsageLog.model).distinct()
    priced_set = set(session.execute(priced).all())
    return [pair for pair in session.execute(used).all() if pair not in priced_set]


def print_llm_cost_report(session, days: int) -> bool:
    """Print the cost report; return True when the pricing alert fired."""
    print(f"=== Koszty LLM (ostatnie {days} dni) ===")
    rows = llm_cost_rows(session, days)
    if not rows:
        print("(brak rekordów)")
    else:
        print(f"{'dzień':<12} {'provider':<12} {'model':<34} {'operacja':<24} {'ile':>5} {'tokeny':>9} {'koszt':>14}")
        totals: dict[str, object] = defaultdict(lambda: 0)
        for r in rows:
            cost = f"{r.cost:.6f} {r.cost_currency}" if r.cost is not None and r.cost_currency else "-"
            print(f"{str(r.day):<12} {r.provider:<12} {r.model[:34]:<34} {r.operation[:24]:<24}"
                  f" {r.calls:>5} {r.tokens:>9} {cost:>14}")
            if r.cost is not None and r.cost_currency:
                totals[r.cost_currency] += r.cost
        if totals:
            print("\nSuma kosztów:")
            for currency, amount in sorted(totals.items()):
                print(f"  {amount:.6f} {currency}")

    alert = False
    unknown = unknown_cost_rows(session, days)
    if unknown:
        alert = True
        print("\nALERT — wywołania bez wyliczonego kosztu (cost_status='unknown'):")
        for r in unknown:
            print(f"  {r.provider}/{r.model}: {r.calls} wywołań (ostatnie: {r.last_call})")
    missing = models_without_pricing(session)
    if missing:
        alert = True
        print("\nALERT — modele używane bez JAKIEGOKOLWIEK wpisu w llm_pricing:")
        for provider, model in missing:
            print(f"  {provider}/{model}")
    if not alert:
        print("\nPricing OK — każde wywołanie ma wyliczony koszt.")
    print()
    return alert


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--interpretations", action="store_true", help="tylko raport interpretacji")
    parser.add_argument("--llm-costs", action="store_true", help="tylko raport kosztów LLM")
    parser.add_argument("--days", type=int, default=30, help="okno raportu w dniach (domyślnie 30)")
    args = parser.parse_args()

    run_interp = args.interpretations or not args.llm_costs
    run_costs = args.llm_costs or not args.interpretations

    session = get_session()
    alert = False
    try:
        if run_interp:
            print_interpretation_report(session, args.days)
        if run_costs:
            alert = print_llm_cost_report(session, args.days)
    finally:
        session.close()
    return 2 if alert else 0


if __name__ == "__main__":
    sys.exit(main())
