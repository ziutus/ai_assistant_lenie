from types import SimpleNamespace

import pytest
import requests

pytest.importorskip("sqlalchemy")

from flask import Flask

from library.api.openrouter import openrouter_key as key

LIMITED = {"data": {"label": "sk-or-v1-abc...xyz", "limit": 3, "limit_remaining": 2.87, "limit_reset": "monthly",
                    "usage": 0.1316, "is_free_tier": False}}


@pytest.fixture(autouse=True)
def _fresh_state(monkeypatch):
    key._cache.update(at=None, value=None)
    monkeypatch.setattr(key, "_api_key", lambda: "sk-or-test")
    yield
    key._cache.update(at=None, value=None)


def _response(payload, status=200):
    def parse():
        if isinstance(payload, Exception):
            raise payload
        return payload

    return SimpleNamespace(status_code=status, ok=200 <= status < 300, json=parse)


def _patch_request(monkeypatch, response=None, error=None):
    calls = []

    def fake(*, service, operation, request_fn):
        calls.append((service, operation))
        if error:
            raise error
        return response

    monkeypatch.setattr(key, "observed_request", fake)
    return calls


class TestInterpret:
    def test_limited_key(self):
        result = key.interpret_key_data(LIMITED["data"])
        assert result == {
            "status": "ok", "has_limit": True, "limit_usd": 3.0, "remaining_usd": 2.87, "usage_usd": 0.1316,
            "reset": "monthly", "free_tier": False, "low": False, "exhausted": False,
        }

    @pytest.mark.parametrize("remaining, low, exhausted", [
        (3, False, False), (0.61, False, False), (0.6, True, False), (0.05, True, False), (0, True, True), (-0.2, True, True),
    ])
    def test_low_and_exhausted_thresholds(self, remaining, low, exhausted):
        result = key.interpret_key_data({"limit": 3, "limit_remaining": remaining})
        assert (result["low"], result["exhausted"]) == (low, exhausted)

    def test_key_without_a_limit_reports_usage_only(self):
        result = key.interpret_key_data({"limit": None, "limit_remaining": None, "usage": 1.5})
        assert (result["has_limit"], result["remaining_usd"], result["usage_usd"]) == (False, None, 1.5)
        assert (result["low"], result["exhausted"]) == (False, False)

    def test_garbage_values_become_none(self):
        result = key.interpret_key_data({"limit": "3", "limit_remaining": True, "usage": None, "limit_reset": 5})
        assert result["has_limit"] is False and result["usage_usd"] is None and result["reset"] is None


class TestFetch:
    def test_ok_and_cached_for_a_minute(self, monkeypatch):
        calls = _patch_request(monkeypatch, _response(LIMITED))

        first = key.fetch_key_status()
        second = key.fetch_key_status()

        assert first["remaining_usd"] == 2.87 and second == first
        assert calls == [("openrouter", "key")]  # the second read came from the cache

    def test_cache_can_be_bypassed(self, monkeypatch):
        calls = _patch_request(monkeypatch, _response(LIMITED))
        key.fetch_key_status()
        key.fetch_key_status(use_cache=False)
        assert len(calls) == 2

    def test_cache_expires(self, monkeypatch):
        calls = _patch_request(monkeypatch, _response(LIMITED))
        key.fetch_key_status()
        key._cache["at"] -= key.CACHE_TTL_S + 1
        key.fetch_key_status()
        assert len(calls) == 2

    def test_no_key_configured_makes_no_request(self, monkeypatch):
        calls = _patch_request(monkeypatch, _response(LIMITED))
        monkeypatch.setattr(key, "_api_key", lambda: None)
        assert key.fetch_key_status() == {"status": "not_configured"}
        assert calls == []

    @pytest.mark.parametrize("response", [_response({}, 401), _response({"data": "x"}), _response({"error": "boom"}, 500)])
    def test_bad_answers_are_unavailable_and_not_cached(self, monkeypatch, response):
        _patch_request(monkeypatch, response)
        assert key.fetch_key_status() == {"status": "unavailable"}
        assert key._cache["at"] is None

    @pytest.mark.parametrize("error", [requests.ConnectionError("down"), ValueError("not json")])
    def test_transport_and_parse_failures_are_unavailable(self, monkeypatch, error):
        _patch_request(monkeypatch, _response(error)) if isinstance(error, ValueError) else _patch_request(monkeypatch, error=error)
        assert key.fetch_key_status() == {"status": "unavailable"}


class TestRoute:
    def test_returns_the_balance(self, monkeypatch):
        from library.llm_cost_routes import openrouter_balance

        monkeypatch.setattr(key, "fetch_key_status", lambda: {"status": "ok", "remaining_usd": 2.87})
        with Flask(__name__).test_request_context("/openrouter_balance"):
            assert openrouter_balance().json == {"balance": {"status": "ok", "remaining_usd": 2.87}}
