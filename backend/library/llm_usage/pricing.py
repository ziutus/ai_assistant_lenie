"""Provider-agnostic LLM cost estimation (search-rebuild plan, stage 2).

This module is the only place allowed to compute an LLM call cost from a
price list. Money is Decimal end to end: passing a float for any rate is a
programming error and raises immediately, because binary floats cannot
represent prices like 0.56 exactly.

Input and output components are computed separately even when the rates are
currently equal (CloudFerro Bielik: 0.56 EUR both ways), so a future change
of a single rate needs no data-model rework. Results are quantized to
10 decimal places — the scale of llm_usage_logs.cost_amount (NUMERIC(18, 10)).
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum

TOKENS_PER_MILLION = Decimal(1_000_000)
COST_SCALE = Decimal("1E-10")


class PricingMode(str, Enum):
    PER_TOKEN = "per_token"
    PER_REQUEST = "per_request"
    CREDITS = "credits"
    SUBSCRIPTION = "subscription"
    FREE = "free"
    UNKNOWN = "unknown"


class CostStatus(str, Enum):
    REPORTED = "reported"
    ESTIMATED = "estimated"
    ALLOCATED = "allocated"
    UNKNOWN = "unknown"


class PricingError(ValueError):
    """Raised for invalid pricing inputs (float money, negative tokens/rates)."""


@dataclass(frozen=True)
class CostEstimate:
    """Cost of a single LLM call, split into components.

    When the cost cannot be computed (non-token pricing, missing rates),
    ``status`` is UNKNOWN and every money field is None — a missing price
    must never turn into a zero cost or an exception in a business path.
    """

    input_cost: Decimal | None
    output_cost: Decimal | None
    total_cost: Decimal | None
    currency: str | None
    status: CostStatus


UNKNOWN_COST = CostEstimate(
    input_cost=None, output_cost=None, total_cost=None, currency=None, status=CostStatus.UNKNOWN,
)


def _decimal_rate(name: str, value) -> Decimal:
    if isinstance(value, float):
        raise PricingError(f"{name} must be Decimal, not float (money is never float)")
    if isinstance(value, int):
        value = Decimal(value)
    if not isinstance(value, Decimal):
        raise PricingError(f"{name} must be Decimal, got {type(value).__name__}")
    if value < 0:
        raise PricingError(f"{name} must not be negative")
    return value


def _token_count(name: str, value) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise PricingError(f"{name} must be an int, got {type(value).__name__}")
    if value < 0:
        raise PricingError(f"{name} must not be negative")
    return value


def estimate_cost(
    *,
    pricing_mode: PricingMode | str,
    input_price_per_million: Decimal | int | None,
    output_price_per_million: Decimal | int | None,
    currency: str | None,
    prompt_tokens: int,
    completion_tokens: int,
) -> CostEstimate:
    """Estimate the cost of one call from a versioned price list entry.

    Only per-token pricing is computable locally; every other mode returns
    UNKNOWN_COST (subscription allocation is a reporting concern, stage 12).
    """
    mode = PricingMode(pricing_mode)
    prompt = _token_count("prompt_tokens", prompt_tokens)
    completion = _token_count("completion_tokens", completion_tokens)

    if mode is not PricingMode.PER_TOKEN:
        return UNKNOWN_COST
    if input_price_per_million is None or output_price_per_million is None or not currency:
        return UNKNOWN_COST

    input_rate = _decimal_rate("input_price_per_million", input_price_per_million)
    output_rate = _decimal_rate("output_price_per_million", output_price_per_million)

    input_cost = (Decimal(prompt) * input_rate / TOKENS_PER_MILLION).quantize(COST_SCALE, rounding=ROUND_HALF_UP)
    output_cost = (Decimal(completion) * output_rate / TOKENS_PER_MILLION).quantize(COST_SCALE, rounding=ROUND_HALF_UP)

    return CostEstimate(
        input_cost=input_cost,
        output_cost=output_cost,
        total_cost=input_cost + output_cost,
        currency=currency,
        status=CostStatus.ESTIMATED,
    )
