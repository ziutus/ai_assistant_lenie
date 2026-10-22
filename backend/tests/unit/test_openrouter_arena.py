"""OpenRouter provider (gated, prefix stripped) and the organization-description Arena."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("sqlalchemy")

import server  # noqa: E402
from tests.unit.test_flask_endpoints_entities import API_HEADERS  # noqa: E402
from tests.unit.test_org_description_endpoints import _session  # noqa: E402

OPENROUTER_MODEL = "openrouter/openai/gpt-4o-mini"


@pytest.fixture
def client():
    server.app.config["TESTING"] = True
    with server.app.test_client() as test_client:
        yield test_client


def test_registry_hides_openrouter_unless_enabled():
    from library.llm_model_registry import is_selectable, selectable_models

    with patch("library.api.openrouter.openrouter_completion.is_enabled", return_value=False):
        assert not is_selectable(OPENROUTER_MODEL)
        assert all(item["provider"] != "openrouter" for item in selectable_models())
    with patch("library.api.openrouter.openrouter_completion.is_enabled", return_value=True):
        assert is_selectable(OPENROUTER_MODEL)
        external = [item for item in selectable_models() if item["provider"] == "openrouter"]
        assert external and all(item["external"] and not item["verified"] for item in external)


def test_adapter_refuses_when_disabled():
    from library.api.openrouter.openrouter_completion import openrouter_get_completion

    with patch("library.api.openrouter.openrouter_completion.is_enabled", return_value=False):
        with pytest.raises(RuntimeError, match="disabled"):
            openrouter_get_completion("p", "openai/gpt-4o-mini")


def test_adapter_calls_openrouter_with_system_message_and_returns_tokens():
    from library.api.openrouter import openrouter_completion as module

    chat = SimpleNamespace(
        id="gen-1", choices=[SimpleNamespace(message=SimpleNamespace(content=" opis "))],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15))
    client = MagicMock()
    client.chat.completions.create.return_value = chat
    config = MagicMock()
    config.get.return_value = "sk-test"
    with patch.object(module, "is_enabled", return_value=True), \
            patch("library.config_loader.load_config", return_value=config), \
            patch.object(module, "OpenAI", return_value=client) as openai_cls:
        response = module.openrouter_get_completion("pytanie", "openai/gpt-4o-mini", system_prompt="sys")
    assert openai_cls.call_args.kwargs["base_url"] == module.OPENROUTER_BASE_URL
    sent = client.chat.completions.create.call_args.kwargs
    assert sent["model"] == "openai/gpt-4o-mini"
    assert sent["messages"] == [{"role": "system", "content": "sys"}, {"role": "user", "content": "pytanie"}]
    assert response.total_tokens == 15 and response.id == "gen-1"


def test_ai_ask_strips_only_the_first_openrouter_prefix_and_forwards_response_format():
    from library import ai

    reply = SimpleNamespace(response_text="x", prompt_tokens=1, completion_tokens=1, total_tokens=2, id="1")
    schema = {"type": "json_schema", "json_schema": {"name": "x", "schema": {"type": "object"}}}
    with patch("library.api.openrouter.openrouter_completion.openrouter_get_completion",
               return_value=reply) as completion, patch.object(ai, "_record_usage", return_value=None):
        ai.ai_ask("q", model=OPENROUTER_MODEL, system_prompt="s")
        assert completion.call_args.kwargs["model"] == "openai/gpt-4o-mini"
        assert completion.call_args.kwargs["response_format"] is None
        ai.ai_ask("q", model=OPENROUTER_MODEL, response_format=schema)
        assert completion.call_args.kwargs["response_format"] == schema
        # Other providers still refuse a response_format they cannot honour.
        with pytest.raises(ValueError):
            ai.ai_ask("q", model="gpt-4o-mini", response_format=schema)


def _arena(client, models, ask):
    with patch("server.get_scoped_session", return_value=_session()), \
            patch("library.ai.ai_ask", side_effect=ask):
        return client.post("/website_entities/7/describe/arena", json={"models": models}, headers=API_HEADERS)


@pytest.mark.parametrize("models", [[], ["gpt-4o-mini"], ["gpt-4o-mini", "gpt-4o-mini"],
                                    ["gpt-4o-mini", "evil/model"], ["a", "b", "c", "d", "e"]])
def test_arena_validates_model_list(client, models):
    assert _arena(client, models, lambda *a, **k: None).status_code == 400


def test_arena_runs_all_models_with_one_prompt_and_survives_a_failure(client):
    prompts = []

    def ask(prompt, model, **kwargs):
        prompts.append(prompt)
        if model == "gpt-4o-mini":
            raise RuntimeError("down")
        return SimpleNamespace(response_text=f"opis z {model}")

    response = _arena(client, ["Bielik-11B-v3.0-Instruct", "gpt-4o-mini"], ask)
    assert response.status_code == 200
    by_model = {item["model"]: item for item in response.get_json()["results"]}
    assert by_model["Bielik-11B-v3.0-Instruct"]["result_status"] == "ok"
    assert by_model["Bielik-11B-v3.0-Instruct"]["description"] == "opis z Bielik-11B-v3.0-Instruct"
    assert by_model["gpt-4o-mini"]["result_status"] == "error" and by_model["gpt-4o-mini"]["error_code"] == "RuntimeError"
    assert len(prompts) == 2 and prompts[0] == prompts[1]
    assert by_model["Bielik-11B-v3.0-Instruct"]["cost"] is None
