"""Price historical unknown calls without changing measured token counts."""

import argparse
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, or_, select, update

from library.db.engine import get_session
from library.db.models import LlmPricing, LlmUsageLog
from library.llm_usage.pricing import CostStatus, estimate_cost


@dataclass
class Summary:
    rows: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_cost: Decimal = Decimal(0)


def plan_backfill(
    rows: Iterable[LlmUsageLog], pricing_rows: Iterable[LlmPricing],
) -> tuple[list[dict], dict[tuple[str, str, str], Summary], Counter]:
    """Use historical prices; never mutate input rows or infer missing chat tokens."""
    prices = defaultdict(list)
    for price in pricing_rows:
        prices[price.provider, price.model].append(price)
    updates = []
    summary = defaultdict(Summary)
    skipped = Counter()
    for row in rows:
        if row.cost_status != "unknown" or row.cost_amount is not None or not row.success:
            continue
        completion = 0 if row.operation == "embedding" else row.completion_tokens
        if row.prompt_tokens is None or completion is None:
            skipped["no tokens"] += 1
            continue
        day = row.called_at.date()
        candidates = [
            price for price in prices[row.provider, row.model]
            if price.effective_from <= day and (price.effective_to is None or price.effective_to > day)
        ]
        # Overlapping prices are ambiguous; do not silently choose one.
        if len(candidates) != 1:
            skipped["no price"] += 1
            continue
        price = candidates[0]
        cost = estimate_cost(
            pricing_mode=price.pricing_mode,
            input_price_per_million=price.input_price_per_million,
            output_price_per_million=price.output_price_per_million,
            currency=price.currency, prompt_tokens=row.prompt_tokens, completion_tokens=completion,
        )
        if cost.status != CostStatus.ESTIMATED:
            skipped["no price"] += 1
            continue
        updates.append(dict(
            id=row.id, cost_amount=cost.total_cost, cost_currency=cost.currency, cost_status="estimated",
            pricing_mode=price.pricing_mode, pricing_version=price.pricing_version,
            input_price_per_million=price.input_price_per_million,
            output_price_per_million=price.output_price_per_million,
        ))
        group = summary[row.provider, row.model, cost.currency]
        group.rows += 1
        group.prompt_tokens += row.prompt_tokens
        group.completion_tokens += completion
        group.total_cost += cost.total_cost
    return updates, dict(summary), skipped


def run_backfill(*, apply: bool = False, batch_size: int = 1000,
                 provider: str | None = None, model: str | None = None) -> None:
    """Keyset pagination advances past unpriceable rows in both dry-run and apply modes."""
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    session = get_session()
    summary = defaultdict(Summary)
    skipped = Counter()
    eligible = [
        LlmUsageLog.cost_status == "unknown", LlmUsageLog.cost_amount.is_(None),
        LlmUsageLog.success.is_(True),
    ]
    if provider is not None:
        eligible.append(LlmUsageLog.provider == provider)
    if model is not None:
        eligible.append(LlmUsageLog.model == model)
    has_tokens = (
        LlmUsageLog.prompt_tokens.is_not(None)
        & or_(LlmUsageLog.completion_tokens.is_not(None), LlmUsageLog.operation == "embedding")
    )
    try:
        skipped["no tokens"] = session.scalar(
            select(func.count()).select_from(LlmUsageLog).where(*eligible, ~has_tokens)
        )
        prices = list(session.scalars(select(LlmPricing)))
        last_id = 0
        while True:
            rows = list(session.scalars(
                select(LlmUsageLog).where(*eligible, has_tokens, LlmUsageLog.id > last_id)
                .order_by(LlmUsageLog.id).limit(batch_size)
            ))
            if not rows:
                break
            last_id = rows[-1].id
            updates, batch_summary, batch_skipped = plan_backfill(rows, prices)
            skipped.update(batch_skipped)
            for key, value in batch_summary.items():
                group = summary[key]
                group.rows += value.rows
                group.prompt_tokens += value.prompt_tokens
                group.completion_tokens += value.completion_tokens
                group.total_cost += value.total_cost
            if apply:
                for values in updates:
                    session.execute(
                        update(LlmUsageLog).where(*eligible, has_tokens, LlmUsageLog.id == values["id"])
                        .values(**{key: value for key, value in values.items() if key != "id"})
                    )
                session.commit()
        print("APPLY" if apply else "DRY-RUN (use --apply to write)")
        for (provider_name, model_name, currency), value in sorted(summary.items()):
            print(f"{provider_name} / {model_name}: {value.rows} rows, "
                  f"input={value.prompt_tokens}, output={value.completion_tokens}, "
                  f"total_tokens={value.prompt_tokens + value.completion_tokens}, "
                  f"cost={value.total_cost} {currency}")
        print(f"{sum(skipped.values())} rows skipped: "
              f"{skipped['no price']} no price / {skipped['no tokens']} no tokens")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--provider")
    parser.add_argument("--model")
    args = parser.parse_args()
    if args.batch_size <= 0:
        parser.error("--batch-size must be positive")
    run_backfill(**vars(args))


if __name__ == "__main__":
    main()
