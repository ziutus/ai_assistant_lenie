"""A model whose provider has no credentials stays visible in the pickers but cannot be chosen (ADR-032)."""

import pytest

from library import llm_model_registry as registry
from library import llm_model_store as store
from library.api.google import google_vertexai as gv
from library.llm_model_store import ModelEntry

TASK = "organization_description"
REASON = "brak poświadczeń Google: ustaw GCP_VERTEX_API_KEY"


@pytest.fixture
def vertex_without_credentials(monkeypatch):
    rows = [ModelEntry("gpt-4o-mini", "GPT", "openai"), ModelEntry("gemini-3.1-flash-lite", "Gemini 3.1", "google-vertexai")]
    monkeypatch.setattr(store, "_fetch_rows", lambda: list(rows))
    store.invalidate_cache()
    monkeypatch.setattr(registry, "_openrouter_enabled", lambda: False)
    monkeypatch.setattr(registry, "_provider_problem", lambda provider: REASON if provider == "google-vertexai" else None)


class TestRegistry:
    def test_listed_with_the_reason_but_not_selectable(self, vertex_without_credentials):
        by_id = {item["id"]: item for item in registry._base_models(TASK)}
        assert by_id["gemini-3.1-flash-lite"]["available"] is False
        assert by_id["gemini-3.1-flash-lite"]["unavailable_reason"] == REASON
        assert by_id["gpt-4o-mini"]["available"] is True and by_id["gpt-4o-mini"]["unavailable_reason"] is None
        assert registry.is_selectable("gpt-4o-mini", TASK)
        assert not registry.is_selectable("gemini-3.1-flash-lite", TASK)

    def test_the_picker_data_carries_the_flag(self, vertex_without_credentials, monkeypatch):
        monkeypatch.setattr(registry, "_database_prices", lambda models: {})
        items = {item["id"]: item for item in registry.selectable_models(TASK)}
        assert items["gemini-3.1-flash-lite"]["available"] is False

    def test_becomes_selectable_once_the_credential_exists(self, vertex_without_credentials, monkeypatch):
        monkeypatch.setattr(registry, "_provider_problem", lambda provider: None)
        assert registry.is_selectable("gemini-3.1-flash-lite", TASK)

    def test_other_providers_have_no_local_credential_check(self):
        assert registry._provider_problem("openrouter") is None and registry._provider_problem("openai") is None


class TestConfigurationProblem:
    """configuration_problem() is the cheap local check behind the 'unavailable' mark."""

    @staticmethod
    def _config(monkeypatch, settings, adc_file=False):
        monkeypatch.setattr(gv, "_setting", lambda name: settings.get(name))
        monkeypatch.setattr(gv, "_adc_file_exists", lambda: adc_file)

    def test_api_key_is_enough(self, monkeypatch):
        self._config(monkeypatch, {"GCP_VERTEX_API_KEY": "k"})
        assert gv.configuration_problem() is None

    def test_nothing_configured_names_both_options(self, monkeypatch):
        self._config(monkeypatch, {})
        problem = gv.configuration_problem()
        assert "GCP_VERTEX_API_KEY" in problem and "GCP_PROJECT_ID" in problem

    def test_project_without_a_credential_file_is_a_problem(self, monkeypatch):
        self._config(monkeypatch, {"GCP_PROJECT_ID": "proj"}, adc_file=False)
        assert "GOOGLE_APPLICATION_CREDENTIALS" in gv.configuration_problem()

    def test_project_with_a_credential_file_is_fine(self, monkeypatch):
        self._config(monkeypatch, {"GCP_PROJECT_ID": "proj"}, adc_file=True)
        assert gv.configuration_problem() is None

    def test_unreachable_config_does_not_claim_the_model_is_broken(self, monkeypatch):
        def broken(name):
            raise SystemExit(1)

        monkeypatch.setattr(gv, "_setting", broken)
        assert gv.configuration_problem() is None

    def test_credential_file_lookup_honours_the_explicit_variable(self, monkeypatch, tmp_path):
        key = tmp_path / "sa.json"
        key.write_text("{}", encoding="utf-8")
        monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(key))
        assert gv._adc_file_exists() is True
        monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(tmp_path / "missing.json"))
        assert gv._adc_file_exists() is False
