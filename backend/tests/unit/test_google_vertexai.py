"""Vertex AI completion wrapper: client selection, config forwarding, token accounting."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from library.api.google import google_vertexai as gv


class _FakeTypes:
    @staticmethod
    def GenerateContentConfig(**kwargs):
        return SimpleNamespace(**kwargs)


def _setup(monkeypatch, settings, response):
    client = MagicMock()
    client.models.generate_content.return_value = response
    genai = MagicMock()
    genai.Client.return_value = client
    monkeypatch.setattr(gv, "_genai", lambda: (genai, _FakeTypes))
    monkeypatch.setattr(gv, "_setting", lambda name: settings.get(name))
    return genai, client


def _response(text="odpowiedź", usage=None):
    return SimpleNamespace(text=text, usage_metadata=usage, response_id="resp-1")


USAGE = SimpleNamespace(prompt_token_count=100, candidates_token_count=40, thoughts_token_count=60, total_token_count=200)


def test_adc_client_uses_project_and_global_location_by_default(monkeypatch):
    genai, _ = _setup(monkeypatch, {"GCP_PROJECT_ID": "proj"}, _response())
    gv.connect_to_google_llm_with_role("pytanie", "gemini-3.5-flash-lite")
    genai.Client.assert_called_once_with(vertexai=True, project="proj", location="global")


def test_configured_location_is_used(monkeypatch):
    genai, _ = _setup(monkeypatch, {"GCP_PROJECT_ID": "proj", "GCP_LOCATION": "europe-west4"}, _response())
    gv.connect_to_google_llm_with_role("pytanie", "gemini-3.5-flash-lite")
    genai.Client.assert_called_once_with(vertexai=True, project="proj", location="europe-west4")


def test_api_key_wins_and_is_not_combined_with_project(monkeypatch):
    genai, _ = _setup(monkeypatch, {"GCP_VERTEX_API_KEY": "k", "GCP_PROJECT_ID": "proj"}, _response())
    gv.connect_to_google_llm_with_role("pytanie", "gemini-3.5-flash-lite")
    genai.Client.assert_called_once_with(vertexai=True, api_key="k")


def test_missing_project_without_api_key_raises(monkeypatch):
    _setup(monkeypatch, {}, _response())
    with pytest.raises(ValueError, match="GCP_PROJECT_ID"):
        gv.connect_to_google_llm_with_role("pytanie", "gemini-3.5-flash-lite")


def test_generation_settings_are_forwarded(monkeypatch):
    _, client = _setup(monkeypatch, {"GCP_PROJECT_ID": "proj"}, _response())
    gv.connect_to_google_llm_with_role(
        "pytanie", "gemini-3.5-flash-lite", temperature=0.2, max_output_tokens=512, top_p=0.8)
    kwargs = client.models.generate_content.call_args.kwargs
    assert kwargs["model"] == "gemini-3.5-flash-lite" and kwargs["contents"] == "pytanie"
    assert (kwargs["config"].temperature, kwargs["config"].max_output_tokens, kwargs["config"].top_p) == (0.2, 512, 0.8)


def test_reasoning_tokens_count_as_output_tokens(monkeypatch):
    _setup(monkeypatch, {"GCP_PROJECT_ID": "proj"}, _response(usage=USAGE))
    result = gv.connect_to_google_llm_with_role("pytanie", "gemini-3.5-flash-lite")
    assert result.response_text == "odpowiedź"
    assert (result.prompt_tokens, result.completion_tokens, result.total_tokens) == (100, 100, 200)
    assert result.id == "resp-1"


def test_missing_usage_leaves_tokens_unset(monkeypatch):
    _setup(monkeypatch, {"GCP_PROJECT_ID": "proj"}, _response(usage=None))
    result = gv.connect_to_google_llm_with_role("pytanie", "gemini-3.5-flash-lite")
    assert result.prompt_tokens is None and result.completion_tokens is None


def test_empty_answer_raises(monkeypatch):
    _setup(monkeypatch, {"GCP_PROJECT_ID": "proj"}, _response(text=""))
    with pytest.raises(ValueError, match="empty response"):
        gv.connect_to_google_llm_with_role("pytanie", "gemini-3.5-flash-lite")


@pytest.mark.parametrize("prompt,model", [("", "m"), ("  ", "m"), ("p", ""), ("p", " ")])
def test_blank_arguments_are_rejected(monkeypatch, prompt, model):
    _setup(monkeypatch, {"GCP_PROJECT_ID": "proj"}, _response())
    with pytest.raises(ValueError):
        gv.connect_to_google_llm_with_role(prompt, model)
