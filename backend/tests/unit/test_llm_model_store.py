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


def _load_migration(revision):
    path = next(pathlib.Path(__file__).resolve().parents[2].glob(f"alembic/versions/{revision}_*.py"))
    spec = importlib.util.spec_from_file_location(f"llm_models_migration_{revision}", path)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except ImportError:
        pytest.skip("alembic is not installed")
    return module


def _removed_model_ids():
    """Ids dropped from the allowlist after the seed migrations were written (b3f7d1a9c248, f6b1a9c4d7e2)."""
    return {row[0] for row in _load_migration("b3f7d1a9c248").REMOVED} | {
        row[0] for row in _load_migration("f6b1a9c4d7e2").REMOVED
    }


def _retired_model_ids():
    """Ids hidden (status retired) by f6b1a9c4d7e2: direct providers other than CloudFerro."""
    return set(_load_migration("f6b1a9c4d7e2").RETIRED)


def _added_models():
    """(model_id, label) pairs the allowlist gained after the seed migrations were written (d8a2f5c1e963)."""
    path = next(pathlib.Path(__file__).resolve().parents[2].glob("alembic/versions/d8a2f5c1e963_*.py"))
    spec = importlib.util.spec_from_file_location("llm_models_added_migration", path)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except ImportError:
        pytest.skip("alembic is not installed")
    return list(module.ADDED) + list(_load_migration("e4b8c2a79061").ADDED)


def test_only_openrouter_and_cloudferro_models_are_visible_in_the_seed():
    visible = {m.model_id: m.provider for m in store.SEED_MODELS if m.status != "retired"}
    assert set(visible.values()) == {"openrouter", "cloudferro"}
    assert _retired_model_ids() == {m.model_id for m in store.SEED_MODELS if m.status == "retired"}


def test_removed_models_are_gone_from_the_code_seed():
    assert not _removed_model_ids() & {m.model_id for m in store.SEED_MODELS}


def test_migration_seed_matches_the_code_seed():
    path = next(pathlib.Path(__file__).resolve().parents[2].glob("alembic/versions/f2c8a4d6b190_*.py"))
    spec = importlib.util.spec_from_file_location("llm_models_migration", path)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except ImportError:
        pytest.skip("alembic is not installed")
    retired = _retired_model_ids()
    migrated = [ModelEntry(model_id, label, provider, external, verified,
                           "retired" if model_id in retired else status,
                           datetime.date.fromisoformat(retires_on) if retires_on else None, note)
                for model_id, label, provider, external, verified, status, retires_on, note in module.SEED
                if model_id not in _removed_model_ids()]
    migrated += [ModelEntry(model_id, label, "openrouter", external=True) for model_id, label in _added_models()]
    # The first migration predates the token limits (added by a4c8e2f6b913): compare everything else.
    without_limits = [ModelEntry(m.model_id, m.label, m.provider, m.external, m.verified, m.status, m.retires_on, m.note)
                      for m in store.SEED_MODELS]
    assert migrated == without_limits


def test_limits_migration_matches_the_code_seed():
    path = next(pathlib.Path(__file__).resolve().parents[2].glob("alembic/versions/a4c8e2f6b913_*.py"))
    spec = importlib.util.spec_from_file_location("llm_models_limits_migration", path)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except ImportError:
        pytest.skip("alembic is not installed")
    seeded = {m.model_id: (m.context_length, m.max_output_tokens) for m in store.SEED_MODELS if m.context_length}
    removed = _removed_model_ids()
    assert {model_id: (context, output) for model_id, context, output in module.LIMITS
            if model_id not in removed} == seeded
    # every direct (non-OpenRouter) model of the seed has a window; OpenRouter ones read it from the live catalog
    assert all(m.context_length for m in store.SEED_MODELS if m.provider != "openrouter")


class TestTokenLimits:
    def test_limits_are_optional_and_normalized(self):
        values = validate_model(**OK)
        assert values["context_length"] is None and values["max_output_tokens"] is None
        values = validate_model(**OK, context_length=32768, max_output_tokens="")
        assert values["context_length"] == 32768 and values["max_output_tokens"] is None

    @pytest.mark.parametrize("override", [
        {"context_length": 0}, {"context_length": -1}, {"context_length": 1.5}, {"context_length": "32768"},
        {"context_length": True}, {"max_output_tokens": 0}, {"max_output_tokens": 10 ** 9},
    ])
    def test_rejects_invalid_limits(self, override):
        values, problem = store.check_model(**{**OK, **override})
        assert values is None and ("context_length" in problem or "max_output_tokens" in problem)
