"""OpenRouter live catalog, dynamic limits/prices in the model registry and the recorder's catalog fallback."""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("sqlalchemy")

from library.api.openrouter import openrouter_catalog as catalog_module  # noqa: E402

PAYLOAD = {"data": [
    {"id": "openai/gpt-4o-mini", "context_length": 128000,
     "pricing": {"prompt": "0.00000015", "completion": "0.0000006"},
     "top_provider": {"max_completion_tokens": 16384}, "supported_parameters": ["structured_outputs", "tools"]},
    {"id": "openrouter/auto", "context_length": 2000000,
     "pricing": {"prompt": "-1", "completion": "-1"}, "top_provider": {}, "supported_parameters": []},
    {"id": "free/model", "context_length": 8192, "pricing": {"prompt": "0", "completion": "0"},
     "top_provider": {"max_completion_tokens": None}, "supported_parameters": []},
    {"no_id": True},
    "garbage",
]}


@pytest.fixture(autouse=True)
def _fresh_catalog():
    catalog_module.reset_cache()
    yield
    catalog_module.reset_cache()


def test_parse_catalog_converts_prices_to_decimal_per_million():
    catalog = catalog_module.parse_catalog(PAYLOAD)
    mini = catalog["openai/gpt-4o-mini"]
    assert mini.input_price_per_million == Decimal("0.150000")
    assert mini.output_price_per_million == Decimal("0.600000")
    assert isinstance(mini.input_price_per_million, Decimal)
    assert mini.context_length == 128000 and mini.max_completion_tokens == 16384
    assert mini.supports_structured_outputs is True
    assert mini.currency == "USD"


def test_parse_catalog_handles_router_free_and_malformed_entries():
    catalog = catalog_module.parse_catalog(PAYLOAD)
    assert catalog["openrouter/auto"].input_price_per_million is None  # -1 = no fixed price
    assert catalog["free/model"].input_price_per_million == Decimal("0.000000")  # free is a price, not "unknown"
    assert catalog["free/model"].max_completion_tokens is None
    assert set(catalog) == {"openai/gpt-4o-mini", "openrouter/auto", "free/model"}
    assert catalog_module.parse_catalog({}) == {}


def test_catalog_is_cached_between_calls():
    with patch.object(catalog_module, "_fetch", return_value=catalog_module.parse_catalog(PAYLOAD)) as fetch:
        first = catalog_module.get_catalog()
        second = catalog_module.get_catalog()
    assert first is second and fetch.call_count == 1
    assert catalog_module.get_model_info("openai/gpt-4o-mini").context_length == 128000
    assert catalog_module.get_model_info("nope/none") is None


def test_failed_fetch_returns_empty_and_backs_off():
    with patch.object(catalog_module, "_fetch", side_effect=OSError("down")) as fetch:
        assert catalog_module.get_catalog() == {}
        assert catalog_module.get_catalog() == {}
    assert fetch.call_count == 1  # second call is inside the failure back-off window


def test_failed_refresh_keeps_the_stale_catalog():
    with patch.object(catalog_module, "_fetch", return_value=catalog_module.parse_catalog(PAYLOAD)):
        catalog_module.get_catalog()
    with patch.object(catalog_module, "_fetch", side_effect=OSError("down")):
        assert "openai/gpt-4o-mini" in catalog_module.get_catalog(refresh=True)


def _registry_with(catalog, *, database=None):
    from library import llm_model_registry

    patches = (
        patch("library.api.openrouter.openrouter_completion.is_enabled", return_value=True),
        patch.object(catalog_module, "get_catalog", return_value=catalog),
        patch.object(llm_model_registry, "_database_prices", return_value=database or {}),
    )
    return patches


def test_registry_fills_openrouter_limits_and_prices_from_catalog():
    from library.llm_model_registry import selectable_models

    p1, p2, p3 = _registry_with(catalog_module.parse_catalog(PAYLOAD))
    with p1, p2, p3:
        items = {item["id"]: item for item in selectable_models()}
    mini = items["openrouter/openai/gpt-4o-mini"]
    assert mini["input_price_per_million"] == "0.15" and mini["output_price_per_million"] == "0.6"
    assert mini["currency"] == "USD" and mini["price_source"] == "openrouter_api"
    assert mini["context_length"] == 128000 and mini["max_output_tokens"] == 16384
    assert mini["listed_by_provider"] is True
    # Not in the payload -> the catalog no longer knows it.
    assert items["openrouter/qwen/qwen-2.5-7b-instruct"]["listed_by_provider"] is False
    assert items["openrouter/qwen/qwen-2.5-7b-instruct"]["input_price_per_million"] is None


def test_registry_reports_unknown_when_catalog_is_unreachable():
    from library.llm_model_registry import selectable_models

    p1, p2, p3 = _registry_with({})
    with p1, p2, p3:
        mini = next(item for item in selectable_models() if item["id"] == "openrouter/openai/gpt-4o-mini")
    assert mini["input_price_per_million"] is None and mini["listed_by_provider"] is None


def test_registry_uses_llm_pricing_rows_for_other_providers():
    from library.llm_model_registry import selectable_models

    database = {("cloudferro", "Bielik-11B-v3.0-Instruct"): (Decimal("0.56"), Decimal("0.56"), "EUR")}
    p1, p2, p3 = _registry_with({}, database=database)
    with p1, p2, p3:
        items = {item["id"]: item for item in selectable_models()}
    bielik = items["Bielik-11B-v3.0-Instruct"]
    assert (bielik["input_price_per_million"], bielik["currency"], bielik["price_source"]) == ("0.56", "EUR", "llm_pricing")
    assert items["gpt-4o-mini"]["input_price_per_million"] is None  # no row -> unknown, not a guess


def test_registry_flags_json_schema_support_per_provider():
    from library.llm_model_registry import selectable_models

    p1, p2, p3 = _registry_with(catalog_module.parse_catalog(PAYLOAD))
    with p1, p2, p3:
        items = {item["id"]: item for item in selectable_models()}
    assert items["Bielik-11B-v3.0-Instruct"]["supports_structured_outputs"] is True
    assert items["gpt-4o-mini"]["supports_structured_outputs"] is False  # ai_ask() does not forward a schema there
    assert items["gemini-3.5-flash-lite"]["supports_structured_outputs"] is False
    assert items["openrouter/openai/gpt-4o-mini"]["supports_structured_outputs"] is True  # from the catalog
    assert items["openrouter/qwen/qwen-2.5-7b-instruct"]["supports_structured_outputs"] is None  # not in the catalog


def test_is_selectable_never_touches_catalog_or_database():
    from library import llm_model_registry

    with patch("library.api.openrouter.openrouter_completion.is_enabled", return_value=True), \
            patch.object(catalog_module, "get_catalog", side_effect=AssertionError("network")), \
            patch.object(llm_model_registry, "_database_prices", side_effect=AssertionError("db")):
        assert llm_model_registry.is_selectable("openrouter/openai/gpt-4o-mini")
        assert not llm_model_registry.is_selectable("openrouter/unknown/model")


def test_recorder_prices_openrouter_calls_from_the_catalog_when_no_row_exists():
    from library.llm_usage import recorder

    session = MagicMock()
    session.execute.return_value.scalar_one_or_none.return_value = None
    with patch.object(catalog_module, "get_catalog", return_value=catalog_module.parse_catalog(PAYLOAD)):
        pricing = recorder._active_pricing(session, "openrouter", "openrouter/openai/gpt-4o-mini")
        cost = recorder._resolve_cost(pricing, None, None, 1000, 500)
    assert pricing.pricing_version is None
    assert cost.currency == "USD" and cost.status.value == "estimated"
    assert cost.total_cost == Decimal("0.00015") + Decimal("0.0003")


def test_recorder_does_not_invent_prices_for_other_providers_or_missing_models():
    from library.llm_usage import recorder

    session = MagicMock()
    session.execute.return_value.scalar_one_or_none.return_value = None
    with patch.object(catalog_module, "get_catalog", return_value=catalog_module.parse_catalog(PAYLOAD)):
        assert recorder._active_pricing(session, "cloudferro", "Bielik-11B-v3.0-Instruct") is None
        assert recorder._active_pricing(session, "openrouter", "openrouter/nope/none") is None
        assert recorder._active_pricing(session, "openrouter", "openrouter/openrouter/auto") is None
