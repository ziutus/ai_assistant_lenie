from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("flask")
pytest.importorskip("jinja2")

from flask import Flask, g

from library import content_group_suggestion_service as svc, feed_routes, llm_model_registry as registry, prompt_templates as pt
from library.db.models import FeedItem

TASK = pt.TASK_CONTENT_GROUPS
CATALOG = [{"id": 1, "name": "AI"}]


def test_suggestion_models_exclude_providers_without_json_schema(monkeypatch):
    monkeypatch.setattr(registry, "_openrouter_enabled", lambda: True)
    ids = {item["id"] for item in registry._base_models(TASK)}
    assert "Bielik-11B-v3.0-Instruct" in ids and "openrouter/google/gemini-2.5-flash-lite" in ids
    assert not ids & {"gpt-4o-mini", "gemini-3.5-flash-lite"}
    # the other tasks keep the full list
    assert "gpt-4o-mini" in {item["id"] for item in registry._base_models("tool_tags")}
    assert registry.is_selectable("gpt-4o-mini", "tool_tags") and not registry.is_selectable("gpt-4o-mini", TASK)


def test_openrouter_model_without_structured_outputs_is_dropped_unknown_is_kept(monkeypatch):
    monkeypatch.setattr(registry, "_openrouter_enabled", lambda: True)
    monkeypatch.setattr(registry, "_database_prices", lambda _models: {})
    flags = {"openrouter/meta-llama/llama-3.1-8b-instruct": False, "openrouter/qwen/qwen-2.5-7b-instruct": None}

    def details(model_id):
        return {**registry._empty_details(), "supports_structured_outputs": flags.get(model_id, True)}

    monkeypatch.setattr(registry, "_openrouter_details", details)
    ids = [item["id"] for item in registry.selectable_models(TASK)]
    assert "openrouter/meta-llama/llama-3.1-8b-instruct" not in ids
    assert "openrouter/qwen/qwen-2.5-7b-instruct" in ids  # catalog unreachable = unknown, not "unsupported"
    assert "openrouter/meta-llama/llama-3.1-8b-instruct" in [item["id"] for item in registry.selectable_models("tool_tags")]


def test_build_request_puts_the_schema_in_the_prompt_only_for_plain_json_models(monkeypatch):
    item = FeedItem(id=1, title="News")
    template = pt.builtin(TASK, "feed_item")
    monkeypatch.setattr(svc, "supports_structured_output", lambda _: True)
    structured = svc.build_request("feed_item", item, "openrouter/x/y", CATALOG, template)
    assert structured["structured"] and structured["response_format"] is not None and structured["system_sent"]
    assert "JSON SCHEMA:" not in structured["prompt"]
    monkeypatch.setattr(svc, "supports_structured_output", lambda _: False)
    plain = svc.build_request("feed_item", item, "Bielik", CATALOG, template)
    assert plain["response_format"] is None and "JSON SCHEMA:" in plain["prompt"]
    assert plain["system_prompt"] and plain["system_sent"] is False  # system message dropped on this path
    assert svc.build_request("feed_item", item, "openrouter/x/y", CATALOG, template)["system_sent"] is True


def test_preview_route_returns_the_request_without_calling_a_model(monkeypatch):
    app = Flask(__name__)
    app.register_blueprint(feed_routes.bp)

    @app.before_request
    def auth():
        g.auth = SimpleNamespace(kind="user", user_id=1)

    session = MagicMock()
    session.get.return_value = FeedItem(id=5, title="Starlink news")
    session.scalar.return_value = None
    monkeypatch.setattr(feed_routes, "get_scoped_session", lambda: session)
    monkeypatch.setattr(feed_routes, "active_topic_catalog", lambda _: CATALOG)
    monkeypatch.setattr(svc, "supports_structured_output", lambda _: True)
    monkeypatch.setattr(registry, "_openrouter_enabled", lambda: True)
    ask = MagicMock()
    monkeypatch.setattr(svc, "ai_ask", ask)
    client = app.test_client()

    response = client.post("/feed_items/5/group-suggestions/preview", json={"model": "openrouter/google/gemini-2.5-flash-lite"})
    assert response.status_code == 200
    assert response.json["prompt_version"] == "feed_item-builtin"
    assert "TYTUŁ: Starlink news" in response.json["prompt"] and response.json["response_format"] is not None
    assert (response.json["model"], response.json["structured"], response.json["system_sent"]) == ("openrouter/google/gemini-2.5-flash-lite", True, True)
    ask.assert_not_called()
    session.add.assert_not_called()

    assert client.post("/feed_items/5/group-suggestions/preview", json={"model": "gpt-4o-mini"}).status_code == 400
    assert client.post("/feed_items/5/group-suggestions/preview", json={"template_id": "x"}).status_code == 400
    session.get.return_value = None
    assert client.post("/feed_items/5/group-suggestions/preview", json={}).status_code == 404
