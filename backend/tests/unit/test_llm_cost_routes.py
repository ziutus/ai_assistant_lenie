from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")

from flask import Flask


def _result(rows):
    result = MagicMock()
    result.all.return_value = rows
    return result


def _call(monkeypatch, provider_rows, query="/llm_costs"):
    from library.llm_cost_routes import llm_costs

    session = MagicMock()
    # The route runs six aggregate queries in this order: totals, providers, daily, operations, documents, jobs.
    session.execute.side_effect = [_result([]), _result(provider_rows), _result([]), _result([]), _result([]), _result([])]
    monkeypatch.setattr("library.llm_cost_routes.get_scoped_session", lambda: session)
    with Flask(__name__).test_request_context(query):
        return llm_costs().json


def _provider(provider, currency, calls, tokens, cost, unknown=0, failed=0):
    return SimpleNamespace(provider=provider, cost_currency=currency, calls=calls, tokens=tokens, cost=cost,
                           unknown_calls=unknown, failed_calls=failed)


class TestProviderBreakdown:
    def test_each_provider_has_cost_calls_tokens_unpriced_and_failed(self, monkeypatch):
        report = _call(monkeypatch, [
            _provider("cloudferro", "EUR", 17703, 9_000_000, Decimal("6.80716456")),
            _provider("openrouter", "USD", 13, 12_000, Decimal("0.00131647")),
            _provider("openai", None, 3, 900, None, unknown=3),
            _provider("google-vertexai", None, 2, 500, None, unknown=2, failed=1),
        ])

        assert report["status"] == "success"
        by_provider = {row["provider"]: row for row in report["providers"]}
        assert list(by_provider) == ["cloudferro", "openrouter", "openai", "google-vertexai"]  # order of the query is kept
        assert by_provider["cloudferro"] == {
            "provider": "cloudferro", "currency": "EUR", "calls": 17703, "tokens": 9_000_000, "cost": "6.80716456",
            "unknown_calls": 0, "failed_calls": 0,
        }
        assert by_provider["openrouter"]["currency"] == "USD" and by_provider["openrouter"]["cost"] == "0.00131647"
        assert by_provider["openai"]["cost"] is None and by_provider["openai"]["unknown_calls"] == 3
        assert by_provider["google-vertexai"]["failed_calls"] == 1

    def test_same_provider_in_two_currencies_stays_two_rows(self, monkeypatch):
        report = _call(monkeypatch, [_provider("openrouter", "USD", 5, 100, Decimal("0.01")),
                                     _provider("openrouter", "EUR", 1, 10, Decimal("0.001"))])
        assert [(row["provider"], row["currency"]) for row in report["providers"]] == [("openrouter", "USD"), ("openrouter", "EUR")]

    def test_empty_period_has_no_providers(self, monkeypatch):
        assert _call(monkeypatch, [])["providers"] == []
