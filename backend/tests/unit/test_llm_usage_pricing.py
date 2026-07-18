"""Tests for library/llm_usage/pricing.py — Decimal-only LLM cost estimation.

Covers the stage-2 requirements from docs/search-rebuild-implementation-plan.md:
exact Bielik arithmetic for various input/output token counts, separate
input/output components, UNKNOWN for non-token pricing, and a hard ban on
float money.
"""

from decimal import Decimal

import pytest

from library.llm_usage import (
    UNKNOWN_COST,
    CostStatus,
    PricingError,
    PricingMode,
    estimate_cost,
)

BIELIK_RATE = Decimal("0.56")
BGE_RATE = Decimal("0.50")


def bielik_cost(prompt_tokens: int, completion_tokens: int):
    return estimate_cost(
        pricing_mode=PricingMode.PER_TOKEN,
        input_price_per_million=BIELIK_RATE,
        output_price_per_million=BIELIK_RATE,
        currency="EUR",
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )


class TestBielikArithmetic:
    def test_example_from_plan(self):
        estimate = bielik_cost(1000, 500)
        assert estimate.input_cost == Decimal("0.00056")
        assert estimate.output_cost == Decimal("0.00028")
        assert estimate.total_cost == Decimal("0.00084")
        assert estimate.currency == "EUR"
        assert estimate.status is CostStatus.ESTIMATED

    def test_single_token(self):
        estimate = bielik_cost(1, 0)
        assert estimate.input_cost == Decimal("0.00000056")
        assert estimate.output_cost == Decimal("0")
        assert estimate.total_cost == Decimal("0.00000056")

    def test_zero_tokens_is_zero_cost_not_unknown(self):
        estimate = bielik_cost(0, 0)
        assert estimate.total_cost == Decimal("0")
        assert estimate.status is CostStatus.ESTIMATED

    def test_one_million_tokens_each_way(self):
        estimate = bielik_cost(1_000_000, 1_000_000)
        assert estimate.input_cost == BIELIK_RATE
        assert estimate.output_cost == BIELIK_RATE
        assert estimate.total_cost == Decimal("1.12")

    def test_components_add_up_for_asymmetric_counts(self):
        estimate = bielik_cost(123_456, 7_891)
        assert estimate.input_cost == Decimal("123456") * BIELIK_RATE / Decimal(1_000_000)
        assert estimate.output_cost == Decimal("7891") * BIELIK_RATE / Decimal(1_000_000)
        assert estimate.total_cost == estimate.input_cost + estimate.output_cost

    def test_no_float_artifacts(self):
        # 0.56 is not representable in binary floating point; Decimal math
        # must give the exact product for an awkward token count.
        estimate = bielik_cost(3, 0)
        assert estimate.input_cost == Decimal("0.00000168")

    def test_result_scale_matches_cost_amount_column(self):
        estimate = bielik_cost(1, 1)
        assert estimate.input_cost.as_tuple().exponent == -10
        assert estimate.output_cost.as_tuple().exponent == -10


class TestEmbeddingPricing:
    def test_embedding_charges_input_only(self):
        estimate = estimate_cost(
            pricing_mode="per_token",
            input_price_per_million=BGE_RATE,
            output_price_per_million=BGE_RATE,
            currency="PLN",
            prompt_tokens=2000,
            completion_tokens=0,
        )
        assert estimate.input_cost == Decimal("0.001")
        assert estimate.output_cost == Decimal("0")
        assert estimate.total_cost == Decimal("0.001")
        assert estimate.currency == "PLN"


class TestUnknownCost:
    @pytest.mark.parametrize(
        "mode",
        [PricingMode.PER_REQUEST, PricingMode.CREDITS, PricingMode.SUBSCRIPTION, PricingMode.FREE, PricingMode.UNKNOWN],
    )
    def test_non_token_modes_are_unknown(self, mode):
        estimate = estimate_cost(
            pricing_mode=mode,
            input_price_per_million=BIELIK_RATE,
            output_price_per_million=BIELIK_RATE,
            currency="EUR",
            prompt_tokens=100,
            completion_tokens=100,
        )
        assert estimate is UNKNOWN_COST
        assert estimate.total_cost is None
        assert estimate.status is CostStatus.UNKNOWN

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"input_price_per_million": None},
            {"output_price_per_million": None},
            {"currency": None},
            {"currency": ""},
        ],
    )
    def test_missing_rate_or_currency_is_unknown_not_error(self, kwargs):
        args = {
            "pricing_mode": PricingMode.PER_TOKEN,
            "input_price_per_million": BIELIK_RATE,
            "output_price_per_million": BIELIK_RATE,
            "currency": "EUR",
            "prompt_tokens": 10,
            "completion_tokens": 10,
        }
        args.update(kwargs)
        assert estimate_cost(**args) is UNKNOWN_COST


class TestInputValidation:
    def test_float_rate_is_rejected(self):
        with pytest.raises(PricingError, match="float"):
            bielik_cost_with_rate(0.56)

    def test_int_rate_is_accepted(self):
        estimate = estimate_cost(
            pricing_mode=PricingMode.PER_TOKEN,
            input_price_per_million=1,
            output_price_per_million=1,
            currency="EUR",
            prompt_tokens=1_000_000,
            completion_tokens=0,
        )
        assert estimate.input_cost == Decimal("1")

    def test_negative_rate_is_rejected(self):
        with pytest.raises(PricingError, match="negative"):
            bielik_cost_with_rate(Decimal("-0.56"))

    @pytest.mark.parametrize("tokens", [-1, 1.5, "10", None, True])
    def test_bad_token_counts_are_rejected(self, tokens):
        with pytest.raises(PricingError):
            bielik_cost(tokens, 0)

    def test_invalid_mode_string_is_rejected(self):
        with pytest.raises(ValueError):
            estimate_cost(
                pricing_mode="per_word",
                input_price_per_million=BIELIK_RATE,
                output_price_per_million=BIELIK_RATE,
                currency="EUR",
                prompt_tokens=1,
                completion_tokens=1,
            )


def bielik_cost_with_rate(rate):
    return estimate_cost(
        pricing_mode=PricingMode.PER_TOKEN,
        input_price_per_million=rate,
        output_price_per_million=rate,
        currency="EUR",
        prompt_tokens=100,
        completion_tokens=100,
    )
