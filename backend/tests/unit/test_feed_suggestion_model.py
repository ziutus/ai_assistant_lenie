from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from flask import Flask, g

from library import app_settings, content_group_suggestion_service as svc, feed_routes, llm_model_registry
from library.db.models import ContentGroupSuggestionRun, Document, FeedItem, Job


@pytest.fixture(autouse=True)
def stub_config(monkeypatch):
    monkeypatch.setattr(svc, "load_config", lambda: {})


@pytest.mark.parametrize("saved,enabled,expected", [
    ("gpt-4o-mini", True, "gpt-4o-mini"),
    (None, True, svc.FEED_DEFAULT_MODEL),
    ("invalid", True, svc.FEED_DEFAULT_MODEL),
    (svc.FEED_DEFAULT_MODEL, False, "Bielik"),
])
def test_default_model(monkeypatch, saved, enabled, expected):
    monkeypatch.setattr(app_settings, "get_setting", lambda *_: saved)
    monkeypatch.setattr(llm_model_registry, "_openrouter_enabled", lambda: enabled)
    monkeypatch.setattr(svc, "suggestion_model", lambda: "Bielik")
    assert svc.default_model(MagicMock()) == expected


@pytest.fixture
def client(monkeypatch):
    app = Flask(__name__)
    app.register_blueprint(feed_routes.bp)

    @app.before_request
    def auth():
        g.auth = SimpleNamespace(kind="user", user_id=1)

    monkeypatch.setattr(feed_routes, "get_scoped_session", MagicMock())
    monkeypatch.setattr(app_settings, "get_setting", lambda *_: None)
    monkeypatch.setattr(llm_model_registry, "_openrouter_enabled", lambda: False)
    return app.test_client()


def test_model_routes(client, monkeypatch):
    setter = MagicMock()
    monkeypatch.setattr(app_settings, "set_setting", setter)
    assert client.put('/feed_items/content_group_model', json={"model": "invalid"}).status_code == 400
    response = client.put('/feed_items/content_group_model', json={"model": None})
    assert response.status_code == 200
    assert response.json["saved"] is False
    assert setter.call_args.args[1:] == (svc.SETTING_KEY, None)
    assert client.post('/feed_items/1/group-suggestions', json={"model": "invalid"}).status_code == 400


@pytest.mark.parametrize("requested,cached,force,reused", [
    ("gpt-4o-mini", "gpt-4o-mini", False, True),
    ("gpt-4o-mini", "Bielik-11B-v3.0-Instruct", False, False),
    ("gpt-4o-mini", "gpt-4o-mini", True, False),
])
def test_cache_model(monkeypatch, requested, cached, force, reused):
    monkeypatch.setattr(svc, "active_topic_catalog", lambda _: [])
    monkeypatch.setattr(svc, "is_selectable", lambda *_: True)
    session = MagicMock()
    session.get.return_value = FeedItem(id=1, title="Title")
    completed = ContentGroupSuggestionRun(model=cached)

    def scalar(stmt):
        params = stmt.compile().params
        return completed if params.get("model_1") == cached else None

    session.scalar.side_effect = scalar
    _, run = svc.request_suggestions(session, "feed_item", 1, model=requested, force=force)
    assert (run is completed) is reused
    assert run.model == requested


def test_document_ignores_feed_model(monkeypatch):
    monkeypatch.setattr(svc, "active_topic_catalog", lambda _: [])
    monkeypatch.setattr(svc, "suggestion_model", lambda: "Bielik")
    session = MagicMock()
    session.get.return_value = Document(id=1)
    session.scalar.return_value = None
    _, run = svc.request_suggestions(session, "document", 1, model=svc.FEED_DEFAULT_MODEL)
    assert run.model == "Bielik"


def test_active_run_is_returned_even_for_other_model(monkeypatch):
    monkeypatch.setattr(svc, "active_topic_catalog", lambda _: [])
    monkeypatch.setattr(svc, "is_selectable", lambda *_: True)
    session = MagicMock()
    session.get.return_value = FeedItem(id=1)
    active = ContentGroupSuggestionRun(model="old", status="running")
    session.scalar.return_value = active
    assert svc.request_suggestions(session, "feed_item", 1, model="new", force=True)[1] is active


@pytest.mark.parametrize("structured", [True, False])
def test_feed_execution_supports_schema_and_plain_json(monkeypatch, structured):
    monkeypatch.setattr(svc, "supports_structured_output", lambda _: structured)
    ask = MagicMock(return_value=SimpleNamespace(response_text='```json\n{"suggestions": [], "no_match": true}\n```'))
    monkeypatch.setattr(svc, "ai_ask", ask)
    run = ContentGroupSuggestionRun(id=2, model=svc.FEED_DEFAULT_MODEL, catalog_snapshot=[{"id": 1, "name": "AI"}])
    session = MagicMock()
    session.get.side_effect = [FeedItem(id=1, title="News"), run]
    svc.execute_suggestion_job(session, Job(id="job", parameters={"feed_item_id": 1, "run_id": 2}))
    assert ask.call_args.kwargs["model"] == svc.FEED_DEFAULT_MODEL
    assert (ask.call_args.kwargs["response_format"] is not None) is structured
    assert run.status == "completed"
    assert run.raw_result == {"suggestions": [], "no_match": True}
