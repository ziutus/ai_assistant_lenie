"""The registry offers what the llm_models table says (ADR-032): retirement and new models need no code change."""

import datetime

from library import llm_model_registry as registry
from library import llm_model_store as store
from library.llm_model_store import ModelEntry

TASK = "organization_description"


def _use(monkeypatch, rows, openrouter=True):
    monkeypatch.setattr(store, "_fetch_rows", lambda: list(rows))
    store.invalidate_cache()
    monkeypatch.setattr(registry, "_openrouter_enabled", lambda: openrouter)


def _ids(task=TASK):
    return [item["id"] for item in registry._base_models(task)]


def test_a_retired_model_disappears_from_every_picker(monkeypatch):
    _use(monkeypatch, [ModelEntry("gpt-4o-mini", "GPT", "openai"),
                       ModelEntry("openrouter/google/gemini-2.5-flash-lite", "G25", "openrouter", status="retired")])
    assert _ids() == ["gpt-4o-mini"]
    assert not registry.is_selectable("openrouter/google/gemini-2.5-flash-lite", TASK)


def test_a_deprecated_model_is_still_offered_with_its_retirement_date(monkeypatch):
    _use(monkeypatch, [ModelEntry("gpt-4o-mini", "GPT", "openai", status="deprecated", retires_on=datetime.date(2027, 3, 1))])
    (item,) = registry._base_models(TASK)
    assert item["status"] == "deprecated" and item["retires_on"] == "2027-03-01"


def test_a_model_added_to_the_table_is_offered_without_a_code_change(monkeypatch):
    _use(monkeypatch, [ModelEntry("gemini-4-flash", "Gemini 4 Flash", "google-vertexai", verified=True)])
    assert _ids() == ["gemini-4-flash"] and registry.is_selectable("gemini-4-flash", TASK)


def test_json_schema_tasks_only_get_providers_that_honour_it(monkeypatch):
    _use(monkeypatch, [ModelEntry("gpt-4o-mini", "GPT", "openai"), ModelEntry("gemini-4-flash", "G4", "google-vertexai")])
    assert _ids("content_group_suggestion") == ["gemini-4-flash"] and "gpt-4o-mini" in _ids("tool_tags")


def test_openrouter_models_stay_hidden_while_openrouter_is_off(monkeypatch):
    _use(monkeypatch, [ModelEntry("openrouter/google/gemma-3-27b-it", "Gemma", "openrouter")], openrouter=False)
    assert _ids() == []


def test_unreachable_database_falls_back_to_the_seed(monkeypatch):
    monkeypatch.setattr(registry, "_openrouter_enabled", lambda: False)
    assert "gpt-4o-mini" in _ids() and "gemini-3.1-flash-lite" in _ids()
