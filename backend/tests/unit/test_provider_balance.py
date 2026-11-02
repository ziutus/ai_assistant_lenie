import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("flask")

from flask import Flask, g

from library import provider_balance as pb

CONFIG = {"amount": 18.98, "as_of": "2026-11-02", "fixed_monthly": 0, "warn_days": 14, "pln_per_eur": 4.0}


class TestValidateConfig:
    def test_defaults(self):
        config = pb.validate_config({"amount": 18.98}, today=datetime.date(2026, 11, 2))
        assert config == {"amount": 18.98, "as_of": "2026-11-02", "fixed_monthly": 0.0, "warn_days": 14,
                          "pln_per_eur": 4.25}

    @pytest.mark.parametrize("body", [
        {}, {"amount": "18"}, {"amount": True}, {"amount": -1}, {"amount": 5, "as_of": "yesterday"},
        {"amount": 5, "warn_days": 0}, {"amount": 5, "warn_days": 1.5}, {"amount": 5, "fixed_monthly": -2},
        {"amount": 5, "pln_per_eur": 0},
    ])
    def test_rejects_bad_input(self, body):
        with pytest.raises(ValueError):
            pb.validate_config(body)


class TestToEur:
    def test_converts_pln_and_skips_what_it_cannot_price(self):
        eur, skipped = pb.to_eur([("EUR", Decimal("1.5")), ("PLN", Decimal("4")), (None, None), ("USD", Decimal("9"))], 4.0)
        assert eur == Decimal("2.5")
        assert skipped == 2


class TestEstimate:
    def test_runway_in_days(self):
        # 18.98 left, 0.3 EUR a month -> 0.01 a day -> 1898 days
        result = pb.estimate(CONFIG, spent_eur=0, window_eur=0.3)
        assert result["remaining"] == 18.98
        assert result["days_left"] == pytest.approx(1898, rel=0.01)
        assert result["low"] is False and result["exhausted"] is False

    def test_fixed_monthly_cost_shortens_the_runway_and_raises_the_warning(self):
        result = pb.estimate({**CONFIG, "fixed_monthly": 30}, spent_eur=0, window_eur=0)
        assert result["daily_burn"] == 1.0
        assert result["days_left"] == 19.0  # 18.98 / 1.0, rounded to one decimal
        assert result["low"] is False
        assert pb.estimate({**CONFIG, "fixed_monthly": 60}, 0, 0)["low"] is True  # 9.5 days < 14

    def test_usage_since_the_base_date_is_subtracted(self):
        assert pb.estimate(CONFIG, spent_eur=1.5, window_eur=0)["remaining"] == 17.48

    def test_no_consumption_means_unknown_runway_not_a_warning(self):
        result = pb.estimate(CONFIG, 0, 0)
        assert result["days_left"] is None and result["low"] is False

    def test_exhausted(self):
        result = pb.estimate(CONFIG, spent_eur=20, window_eur=1)
        assert result["exhausted"] is True and result["low"] is False and result["days_left"] == 0


def _session(config, since_rows, window_rows):
    session = MagicMock()
    session.execute.side_effect = [MagicMock(all=MagicMock(return_value=since_rows)),
                                   MagicMock(all=MagicMock(return_value=window_rows))]
    return session


class TestEstimatedBalance:
    def test_not_configured(self, monkeypatch):
        monkeypatch.setattr(pb.app_settings, "get_setting", lambda *_: None)
        assert pb.estimated_balance(MagicMock(), "cloudferro") == {
            "provider": "cloudferro", "name": "CloudFerro", "source": "estimated", "unit": "BU", "status": "not_configured"}

    def test_configured_combines_both_queries(self, monkeypatch):
        monkeypatch.setattr(pb.app_settings, "get_setting", lambda *_: CONFIG)
        session = _session(CONFIG, [("PLN", Decimal("4"))], [("PLN", Decimal("12")), ("EUR", Decimal("0.5"))])
        result = pb.estimated_balance(session, "cloudferro", now=datetime.datetime(2026, 11, 10))
        assert result["status"] == "ok" and result["source"] == "estimated" and result["unit"] == "BU"
        assert result["spent_since"] == 1.0 and result["remaining"] == 17.98
        assert result["daily_burn"] == pytest.approx(3.5 / 30, abs=1e-4)
        assert result["base_amount"] == 18.98 and result["as_of"] == "2026-11-02"

    def test_a_row_without_a_price_is_reported_not_guessed(self, monkeypatch):
        monkeypatch.setattr(pb.app_settings, "get_setting", lambda *_: CONFIG)
        session = _session(CONFIG, [(None, None)], [])
        assert pb.estimated_balance(session, "cloudferro", now=datetime.datetime(2026, 11, 10))["unpriced_rows"] == 1


class TestOpenRouterEntry:
    def test_limited_key(self, monkeypatch):
        monkeypatch.setattr("library.api.openrouter.openrouter_key.fetch_key_status", lambda: {
            "status": "ok", "has_limit": True, "limit_usd": 10.0, "remaining_usd": 1.5, "usage_usd": 8.5, "low": True,
            "exhausted": False})
        entry = pb.openrouter_balance()
        assert (entry["provider"], entry["source"], entry["unit"], entry["remaining"], entry["low"]) == (
            "openrouter", "api", "USD", 1.5, True)

    def test_not_configured_has_only_the_status(self, monkeypatch):
        monkeypatch.setattr("library.api.openrouter.openrouter_key.fetch_key_status", lambda: {"status": "not_configured"})
        assert pb.openrouter_balance()["status"] == "not_configured"


class TestRoutes:
    def _client(self, monkeypatch, kind="service"):
        from library import provider_balance_routes as routes

        stored = {}
        monkeypatch.setattr(routes, "get_scoped_session", lambda: MagicMock())
        monkeypatch.setattr(routes.app_settings, "set_setting", lambda _s, key, value: stored.update({key: value}))
        monkeypatch.setattr(routes.provider_balance, "estimated_balance", lambda *_: {"status": "ok"})
        app = Flask(__name__)

        @app.before_request
        def _auth():
            g.auth = SimpleNamespace(kind=kind, user_id=1)

        app.register_blueprint(routes.bp)
        return app.test_client(), stored

    def test_put_stores_the_validated_config(self, monkeypatch):
        client, stored = self._client(monkeypatch)
        response = client.put("/provider_balances/cloudferro", json={"amount": 18.98, "as_of": "2026-11-02"})
        assert response.status_code == 200
        assert stored["provider_balance:cloudferro"]["amount"] == 18.98

    def test_put_bad_body_is_400_and_unknown_provider_404(self, monkeypatch):
        client, stored = self._client(monkeypatch)
        assert client.put("/provider_balances/cloudferro", json={"amount": "x"}).status_code == 400
        assert client.put("/provider_balances/openrouter", json={"amount": 1}).status_code == 404
        assert stored == {}

    def test_delete_clears_the_setting(self, monkeypatch):
        client, stored = self._client(monkeypatch)
        assert client.delete("/provider_balances/cloudferro").status_code == 200
        assert stored == {"provider_balance:cloudferro": None}

    def test_reader_key_cannot_write(self, monkeypatch):
        client, _ = self._client(monkeypatch, kind="reader")
        assert client.put("/provider_balances/cloudferro", json={"amount": 1}).status_code == 403
