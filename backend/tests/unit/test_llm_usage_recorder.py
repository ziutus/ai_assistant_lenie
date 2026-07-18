"""Tests for library/llm_usage/recorder.py (stage 2B of the search rebuild).

No database: the session factory is faked. The fake mimics the two calls
the recorder makes (pricing lookup via execute().scalar_one_or_none() and
the add/commit of exactly one LlmUsageLog row) and assigns ids on commit.
"""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")

from library.db.models import LlmPricing, LlmUsageLog  # noqa: E402
from library.llm_usage.pricing import CostStatus, PricingError  # noqa: E402
from library.llm_usage.recorder import record_llm_usage  # noqa: E402

BIELIK_PRICING = dict(
    pricing_version="cloudferro-bielik-2026-07-18",
    provider="cloudferro",
    model="Bielik-11B-v3.0-Instruct",
    pricing_mode="per_token",
    input_price_per_million=Decimal("0.56"),
    output_price_per_million=Decimal("0.56"),
    currency="EUR",
    effective_from=date(2026, 7, 18),
)


class FakeSessionFactory:
    """One reusable fake Session; records added objects, assigns ids on commit."""

    def __init__(self, pricing: LlmPricing | None = None, fail: str | None = None):
        self.added: list = []
        self.session = MagicMock()
        self.session.add.side_effect = self.added.append
        if fail == "execute":
            self.session.execute.side_effect = RuntimeError("db down")
        else:
            self.session.execute.return_value.scalar_one_or_none.return_value = pricing
        if fail == "commit":
            self.session.commit.side_effect = RuntimeError("db down")
        else:
            self.session.commit.side_effect = self._assign_ids

    def _assign_ids(self):
        for i, obj in enumerate(self.added, start=1):
            if getattr(obj, "id", None) is None:
                obj.id = i

    def __call__(self):
        return self.session


def bielik_factory(**kwargs) -> FakeSessionFactory:
    return FakeSessionFactory(pricing=LlmPricing(**BIELIK_PRICING), **kwargs)


class TestEstimatedCost:
    def test_per_token_pricing_writes_estimated_cost(self):
        factory = bielik_factory()
        record = record_llm_usage(
            operation="search_query_parse",
            provider="cloudferro",
            model="Bielik-11B-v3.0-Instruct",
            prompt_tokens=1000,
            completion_tokens=500,
            latency_ms=1234,
            session_factory=factory,
        )
        assert len(factory.added) == 1
        log = factory.added[0]
        assert isinstance(log, LlmUsageLog)
        # 1000 * 0.56 / 1e6 = 0.00056; 500 * 0.56 / 1e6 = 0.00028
        assert log.cost_amount == Decimal("0.0008400000")
        assert log.cost_currency == "EUR"
        assert log.cost_status == "estimated"
        assert log.pricing_mode == "per_token"
        assert log.pricing_version == "cloudferro-bielik-2026-07-18"
        assert log.input_price_per_million == Decimal("0.56")
        assert log.output_price_per_million == Decimal("0.56")
        assert log.latency_ms == 1234
        assert record.usage_log_id == 1
        assert record.cost.status is CostStatus.ESTIMATED
        assert record.cost.total_cost == Decimal("0.0008400000")
        assert record.latency_ms == 1234

    def test_total_tokens_autofilled_from_components(self):
        factory = bielik_factory()
        record = record_llm_usage(
            operation="search_query_parse",
            provider="cloudferro",
            model="Bielik-11B-v3.0-Instruct",
            prompt_tokens=100,
            completion_tokens=25,
            session_factory=factory,
        )
        assert factory.added[0].total_tokens == 125
        assert record.total_tokens == 125

    def test_explicit_total_tokens_kept(self):
        factory = bielik_factory()
        record_llm_usage(
            operation="search_query_parse",
            provider="cloudferro",
            model="Bielik-11B-v3.0-Instruct",
            prompt_tokens=100,
            completion_tokens=25,
            total_tokens=130,
            session_factory=factory,
        )
        assert factory.added[0].total_tokens == 130

    def test_embedding_call_output_tokens_zero(self):
        factory = FakeSessionFactory(
            pricing=LlmPricing(
                pricing_version="cloudferro-bge-2026-07-18",
                provider="cloudferro",
                model="BAAI/bge-multilingual-gemma2",
                pricing_mode="per_token",
                input_price_per_million=Decimal("0.50"),
                output_price_per_million=Decimal("0.50"),
                currency="PLN",
                effective_from=date(2026, 7, 18),
            )
        )
        record = record_llm_usage(
            operation="embedding_generation",
            provider="cloudferro",
            model="BAAI/bge-multilingual-gemma2",
            prompt_tokens=2_000_000,
            completion_tokens=0,
            session_factory=factory,
        )
        assert factory.added[0].cost_amount == Decimal("1.0000000000")
        assert factory.added[0].cost_currency == "PLN"
        assert record.cost.output_cost == Decimal("0")


class TestReportedCost:
    def test_reported_cost_wins_over_estimate(self):
        factory = bielik_factory()
        record = record_llm_usage(
            operation="search_query_parse",
            provider="cloudferro",
            model="Bielik-11B-v3.0-Instruct",
            prompt_tokens=1000,
            completion_tokens=500,
            reported_cost=Decimal("0.001"),
            reported_cost_currency="EUR",
            session_factory=factory,
        )
        log = factory.added[0]
        assert log.cost_amount == Decimal("0.001")
        assert log.cost_status == "reported"
        # Pricing snapshot is still recorded for the audit trail.
        assert log.pricing_version == "cloudferro-bielik-2026-07-18"
        assert record.cost.status is CostStatus.REPORTED

    def test_reported_cost_as_float_raises(self):
        with pytest.raises(PricingError, match="float"):
            record_llm_usage(
                operation="search_query_parse",
                provider="cloudferro",
                model="Bielik-11B-v3.0-Instruct",
                reported_cost=0.001,
                reported_cost_currency="EUR",
                session_factory=bielik_factory(),
            )

    def test_reported_cost_requires_currency(self):
        with pytest.raises(PricingError, match="currency"):
            record_llm_usage(
                operation="search_query_parse",
                provider="cloudferro",
                model="Bielik-11B-v3.0-Instruct",
                reported_cost=Decimal("0.001"),
                session_factory=bielik_factory(),
            )

    def test_negative_reported_cost_raises(self):
        with pytest.raises(PricingError, match="negative"):
            record_llm_usage(
                operation="search_query_parse",
                provider="cloudferro",
                model="Bielik-11B-v3.0-Instruct",
                reported_cost=Decimal("-1"),
                reported_cost_currency="EUR",
                session_factory=bielik_factory(),
            )


class TestUnknownCost:
    def test_no_pricing_row_stores_tokens_with_unknown_cost(self):
        factory = FakeSessionFactory(pricing=None)
        record = record_llm_usage(
            operation="document_analysis",
            provider="openai",
            model="gpt-4o-mini",
            prompt_tokens=1000,
            completion_tokens=200,
            session_factory=factory,
        )
        log = factory.added[0]
        assert log.prompt_tokens == 1000
        assert log.completion_tokens == 200
        assert log.cost_amount is None
        assert log.cost_currency is None
        assert log.cost_status == "unknown"
        assert log.pricing_mode == "unknown"
        assert log.pricing_version is None
        assert record.cost.status is CostStatus.UNKNOWN

    def test_subscription_pricing_snapshot_kept_cost_unknown(self):
        factory = FakeSessionFactory(
            pricing=LlmPricing(
                pricing_version="acme-flat-2026-01-01",
                provider="acme",
                model="acme-large",
                pricing_mode="subscription",
                input_price_per_million=None,
                output_price_per_million=None,
                currency="EUR",
                effective_from=date(2026, 1, 1),
            )
        )
        record = record_llm_usage(
            operation="document_analysis",
            provider="acme",
            model="acme-large",
            prompt_tokens=10,
            completion_tokens=10,
            session_factory=factory,
        )
        log = factory.added[0]
        assert log.pricing_mode == "subscription"
        assert log.pricing_version == "acme-flat-2026-01-01"
        assert log.cost_status == "unknown"
        assert record.cost.status is CostStatus.UNKNOWN

    def test_credits_mode_stores_credits_used(self):
        factory = FakeSessionFactory(
            pricing=LlmPricing(
                pricing_version="acme-credits-2026-01-01",
                provider="acme",
                model="acme-credits",
                pricing_mode="credits",
                input_price_per_million=None,
                output_price_per_million=None,
                currency="USD",
                effective_from=date(2026, 1, 1),
            )
        )
        record_llm_usage(
            operation="document_analysis",
            provider="acme",
            model="acme-credits",
            credits_used=Decimal("3.5"),
            session_factory=factory,
        )
        log = factory.added[0]
        assert log.credits_used == Decimal("3.5")
        assert log.cost_status == "unknown"

    def test_credits_as_float_raises(self):
        with pytest.raises(PricingError, match="float"):
            record_llm_usage(
                operation="document_analysis",
                provider="acme",
                model="acme-credits",
                credits_used=3.5,
                session_factory=FakeSessionFactory(),
            )

    def test_missing_tokens_never_estimate(self):
        factory = bielik_factory()
        record = record_llm_usage(
            operation="search_query_parse",
            provider="cloudferro",
            model="Bielik-11B-v3.0-Instruct",
            prompt_tokens=None,
            completion_tokens=None,
            session_factory=factory,
        )
        log = factory.added[0]
        assert log.total_tokens is None
        assert log.cost_status == "unknown"
        assert record.cost.total_cost is None


class TestFailurePaths:
    def test_llm_error_call_still_writes_one_row(self):
        factory = bielik_factory()
        record = record_llm_usage(
            operation="search_query_parse",
            provider="cloudferro",
            model="Bielik-11B-v3.0-Instruct",
            success=False,
            error_code="timeout",
            session_factory=factory,
        )
        assert len(factory.added) == 1
        log = factory.added[0]
        assert log.success is False
        assert log.error_code == "timeout"
        assert record.usage_log_id == 1

    def test_invalid_provider_tokens_dropped_not_raised(self):
        factory = bielik_factory()
        record = record_llm_usage(
            operation="search_query_parse",
            provider="cloudferro",
            model="Bielik-11B-v3.0-Instruct",
            prompt_tokens=-5,
            completion_tokens="oops",
            session_factory=factory,
        )
        log = factory.added[0]
        assert log.prompt_tokens is None
        assert log.completion_tokens is None
        assert record.cost.status is CostStatus.UNKNOWN

    def test_db_failure_swallowed_returns_no_id(self):
        factory = bielik_factory(fail="commit")
        record = record_llm_usage(
            operation="search_query_parse",
            provider="cloudferro",
            model="Bielik-11B-v3.0-Instruct",
            prompt_tokens=10,
            completion_tokens=10,
            session_factory=factory,
        )
        assert record.usage_log_id is None
        assert record.cost.status is CostStatus.UNKNOWN
        assert record.prompt_tokens == 10
        factory.session.rollback.assert_called_once()
        factory.session.close.assert_called_once()

    def test_systemexit_from_session_factory_swallowed(self):
        # config_loader's require() calls sys.exit(1) when DB config is
        # missing; SystemExit is not an Exception and must be caught too.
        def factory():
            raise SystemExit(1)

        record = record_llm_usage(
            operation="search_query_parse",
            provider="cloudferro",
            model="Bielik-11B-v3.0-Instruct",
            prompt_tokens=10,
            completion_tokens=10,
            session_factory=factory,
        )
        assert record.usage_log_id is None
        assert record.cost.status is CostStatus.UNKNOWN

    def test_pricing_lookup_failure_swallowed(self):
        factory = FakeSessionFactory(fail="execute")
        record = record_llm_usage(
            operation="search_query_parse",
            provider="cloudferro",
            model="Bielik-11B-v3.0-Instruct",
            prompt_tokens=10,
            completion_tokens=10,
            session_factory=factory,
        )
        assert record.usage_log_id is None

    def test_session_closed_on_success(self):
        factory = bielik_factory()
        record_llm_usage(
            operation="search_query_parse",
            provider="cloudferro",
            model="Bielik-11B-v3.0-Instruct",
            prompt_tokens=1,
            completion_tokens=1,
            session_factory=factory,
        )
        factory.session.close.assert_called_once()
