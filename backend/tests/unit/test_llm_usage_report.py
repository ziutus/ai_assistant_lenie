"""Tests for library/llm_usage/report.py (stage 3b of the search rebuild).

No sqlalchemy import needed here — `usage` is duck-typed, so a plain
SimpleNamespace mimicking UsageRecord/CostEstimate is enough.
"""

from decimal import Decimal
from types import SimpleNamespace

from library.llm_usage.report import combine_usage_reports, usage_report


def fake_usage(usage_log_id=1, total_tokens=100, cost_amount=None, cost_currency=None, cost_status="unknown"):
    status = SimpleNamespace(value=cost_status) if cost_status is not None else None
    return SimpleNamespace(
        usage_log_id=usage_log_id,
        total_tokens=total_tokens,
        cost=SimpleNamespace(total_cost=cost_amount, currency=cost_currency, status=status),
    )


class TestUsageReport:
    def test_none_usage_yields_unknown_report(self):
        report = usage_report(None).as_dict()
        assert report == {
            "llm_calls": 1,
            "usage_log_ids": [],
            "llm_tokens": None,
            "llm_cost_amount": None,
            "llm_cost_currency": None,
            "llm_cost_status": "unknown",
        }

    def test_estimated_cost_shaped_as_string(self):
        usage = fake_usage(usage_log_id=7, total_tokens=120, cost_amount=Decimal("0.0008400000"),
                           cost_currency="EUR", cost_status="estimated")
        report = usage_report(usage).as_dict()
        assert report["usage_log_ids"] == [7]
        assert report["llm_tokens"] == 120
        assert report["llm_cost_amount"] == "0.0008400000"
        assert report["llm_cost_currency"] == "EUR"
        assert report["llm_cost_status"] == "estimated"

    def test_missing_usage_log_id_yields_empty_list(self):
        usage = fake_usage(usage_log_id=None)
        assert usage_report(usage).as_dict()["usage_log_ids"] == []

    def test_plain_string_status_accepted(self):
        # Duck typing: a bare string status (no .value) must work too.
        usage = SimpleNamespace(
            usage_log_id=1, total_tokens=10,
            cost=SimpleNamespace(total_cost=None, currency=None, status="unknown"),
        )
        assert usage_report(usage).as_dict()["llm_cost_status"] == "unknown"


class TestCombineUsageReports:
    def test_sums_tokens_and_costs_same_currency(self):
        reports = [
            usage_report(fake_usage(1, 100, Decimal("0.001"), "EUR", "estimated")).as_dict(),
            usage_report(fake_usage(2, 50, Decimal("0.0005"), "EUR", "estimated")).as_dict(),
        ]
        combined = combine_usage_reports(reports)
        assert combined["llm_calls"] == 2
        assert combined["usage_log_ids"] == [1, 2]
        assert combined["llm_tokens"] == 150
        assert combined["llm_cost_amount"] == "0.0015"
        assert combined["llm_cost_currency"] == "EUR"
        assert combined["llm_cost_status"] == "estimated"

    def test_mixed_currency_never_summed(self):
        reports = [
            usage_report(fake_usage(1, 100, Decimal("0.001"), "EUR", "estimated")).as_dict(),
            usage_report(fake_usage(2, 50, Decimal("1"), "PLN", "estimated")).as_dict(),
        ]
        combined = combine_usage_reports(reports)
        assert combined["llm_cost_amount"] is None
        assert combined["llm_cost_currency"] is None
        assert combined["llm_cost_status"] == "unknown"
        # Tokens and ids still aggregate even when cost cannot be summed.
        assert combined["llm_tokens"] == 150
        assert combined["usage_log_ids"] == [1, 2]

    def test_any_unknown_cost_poisons_the_total(self):
        reports = [
            usage_report(fake_usage(1, 100, Decimal("0.001"), "EUR", "estimated")).as_dict(),
            usage_report(fake_usage(2, 50, None, None, "unknown")).as_dict(),
        ]
        combined = combine_usage_reports(reports)
        assert combined["llm_cost_amount"] is None
        assert combined["llm_cost_status"] == "unknown"

    def test_missing_token_count_poisons_token_total(self):
        reports = [
            usage_report(fake_usage(1, 100)).as_dict(),
            usage_report(fake_usage(2, None)).as_dict(),
        ]
        assert combine_usage_reports(reports)["llm_tokens"] is None

    def test_mixed_status_reported_as_estimated(self):
        reports = [
            usage_report(fake_usage(1, 100, Decimal("0.001"), "EUR", "reported")).as_dict(),
            usage_report(fake_usage(2, 50, Decimal("0.0005"), "EUR", "estimated")).as_dict(),
        ]
        assert combine_usage_reports(reports)["llm_cost_status"] == "estimated"

    def test_empty_list_yields_zero_calls_and_unknown_cost(self):
        combined = combine_usage_reports([])
        assert combined["llm_calls"] == 0
        assert combined["usage_log_ids"] == []
        assert combined["llm_tokens"] is None
        assert combined["llm_cost_status"] == "unknown"

    def test_single_report_passthrough(self):
        report = usage_report(fake_usage(5, 77, Decimal("0.002"), "EUR", "estimated")).as_dict()
        combined = combine_usage_reports([report])
        assert combined == report
