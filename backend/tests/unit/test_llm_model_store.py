"""ADR-032: cached database allowlist with a code-seed fallback, validation and migration/seed parity."""

import datetime
import importlib.util
import pathlib

import pytest

from library import llm_model_store as store
from library.llm_model_store import ModelEntry, ModelValidationError, validate_model

OK = {"model_id": "gemini-4-flash", "label": "Gemini 4 Flash", "provider": "google-vertexai"}


def _rows(monkeypatch, rows):
    calls = []

    def fetch():
        calls.append(1)
        return list(rows)

    monkeypatch.setattr(store, "_fetch_rows", fetch)
    store.invalidate_cache()
    return calls


class TestReadWithFallback:
    def test_unreachable_database_yields_the_seed(self):
        assert store.get_models() == store.SEED_MODELS and store.source() == "seed"

    def test_database_rows_replace_the_seed(self, monkeypatch):
        row = ModelEntry("gemini-4-flash", "Gemini 4", "google-vertexai")
        _rows(monkeypatch, [row])
        assert store.get_models() == (row,) and store.source() == "database"

    def test_empty_table_is_respected_not_replaced_by_the_seed(self, monkeypatch):
        _rows(monkeypatch, [])
        assert store.get_models() == () and store.source() == "database"

    def test_system_exit_from_missing_config_falls_back_to_the_seed(self, monkeypatch):
        def fetch():
            raise SystemExit(1)

        monkeypatch.setattr(store, "_fetch_rows", fetch)
        store.invalidate_cache()
        assert store.get_models() == store.SEED_MODELS

    def test_reads_are_cached_until_invalidated(self, monkeypatch):
        calls = _rows(monkeypatch, [ModelEntry("a", "A", "openai")])
        store.get_models()
        store.get_models()
        assert len(calls) == 1
        store.invalidate_cache()
        store.get_models()
        assert len(calls) == 2


class TestProviderOf:
    def test_returns_the_provider_of_an_active_or_deprecated_model(self, monkeypatch):
        _rows(monkeypatch, [ModelEntry("m1", "M1", "cloudferro"), ModelEntry("m2", "M2", "openai", status="deprecated")])
        assert store.provider_of("m1") == "cloudferro" and store.provider_of("m2") == "openai"

    def test_retired_and_unknown_models_have_no_provider(self, monkeypatch):
        _rows(monkeypatch, [ModelEntry("old", "Old", "openai", status="retired")])
        assert store.provider_of("old") is None and store.provider_of("nope") is None


class TestValidation:
    def test_normalizes_a_valid_row(self):
        values = validate_model(**OK, retires_on="2027-05-01", note="  uwaga  ")
        assert values["external"] is False and values["status"] == "active"
        assert values["retires_on"] == datetime.date(2027, 5, 1) and values["note"] == "uwaga"

    def test_openrouter_models_are_external_by_default(self):
        values = validate_model(model_id="openrouter/google/gemma-3-27b-it", label="G", provider="openrouter")
        assert values["external"] is True

    @pytest.mark.parametrize("override", [
        {"model_id": ""}, {"model_id": "has space"}, {"model_id": "x" * 101}, {"label": " "}, {"label": "x" * 121},
        {"provider": "bedrock"}, {"status": "gone"}, {"retires_on": "jutro"}, {"external": "yes"},
        {"note": "x" * 1001}, {"provider": "openrouter"},  # openrouter needs the openrouter/<vendor>/<model> shape
        {"model_id": "openrouter/gemini"}, {"model_id": "openrouter/google/gemma"},  # prefix reserved for openrouter
    ])
    def test_rejects_invalid_rows(self, override):
        with pytest.raises(ModelValidationError):
            validate_model(**{**OK, **override})

    def test_blank_note_means_no_note(self):
        assert validate_model(**OK, note="")["note"] is None


class TestCheckModel:
    """check_model() is the form the REST layer uses: a result tuple, never an exception."""

    def test_valid_row_returns_values_and_no_problem(self):
        values, problem = store.check_model(**OK, retires_on="2027-05-01")
        assert problem is None and values["retires_on"] == datetime.date(2027, 5, 1)

    @pytest.mark.parametrize("override, fragment", [
        ({"model_id": ""}, "model_id"), ({"model_id": "has space"}, "białych znaków"), ({"provider": "bedrock"}, "provider"),
        ({"status": "gone"}, "status"), ({"retires_on": "jutro"}, "RRRR-MM-DD"), ({"external": "yes"}, "logicznymi"),
        ({"label": " "}, "label"), ({"note": "x" * 1001}, "note"), ({"model_id": "openrouter/gemini"}, "zarezerwowany"),
    ])
    def test_invalid_row_returns_a_message_without_raising(self, override, fragment):
        values, problem = store.check_model(**{**OK, **override})
        assert values is None and fragment in problem

    def test_validate_model_still_raises_with_the_same_message(self):
        _, problem = store.check_model(**{**OK, "status": "gone"})
        with pytest.raises(ModelValidationError, match="status"):
            validate_model(**{**OK, "status": "gone"})
        assert "status" in problem


def test_migration_seed_matches_the_code_seed():
    path = next(pathlib.Path(__file__).resolve().parents[2].glob("alembic/versions/f2c8a4d6b190_*.py"))
    spec = importlib.util.spec_from_file_location("llm_models_migration", path)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except ImportError:
        pytest.skip("alembic is not installed")
    migrated = [ModelEntry(model_id, label, provider, external, verified, status,
                           datetime.date.fromisoformat(retires_on) if retires_on else None, note)
                for model_id, label, provider, external, verified, status, retires_on, note in module.SEED]
    assert migrated == list(store.SEED_MODELS)
