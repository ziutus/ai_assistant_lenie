from types import SimpleNamespace
from unittest.mock import MagicMock

import json

import pytest
from flask import Flask, g

from library import app_settings, content_group_suggestion_service as svc, feed_routes, llm_model_registry
from library.db.models import ContentGroup, ContentGroupSuggestionRun, Document, FeedItem, FeedItemGroupMembership, Job


@pytest.fixture(autouse=True)
def stub_config(monkeypatch):
    monkeypatch.setattr(svc, "load_config", lambda: {})


@pytest.mark.parametrize("saved,enabled,expected", [
    ("openrouter/openai/gpt-4o-mini", True, "openrouter/openai/gpt-4o-mini"),
    ("gpt-4o-mini", True, svc.FEED_DEFAULT_MODEL),  # direct OpenAI has no JSON-schema response_format: no longer offered
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
    assert run.prompt_version == "document-builtin"


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
    assert run.raw_result == {"suggestions": [], "no_match": True, "new_topics": []}


def test_feed_schema_and_version():
    catalog = [{"id": 1, "name": "AI"}]
    doc = svc.response_schema(catalog)["json_schema"]["schema"]
    feed = svc.response_schema(catalog, allow_new_topics=True)["json_schema"]["schema"]
    assert "new_topics" not in doc["properties"]
    assert "new_topics" in feed["required"]
    assert feed["properties"]["new_topics"]["maxItems"] == 3
    assert svc.input_hash("text", catalog) != svc.input_hash("text", catalog, "feed_item")
    assert svc.PROMPT_VERSION == "content-groups-v1"
    empty = svc.response_schema([], allow_new_topics=True)["json_schema"]["schema"]
    assert empty["properties"]["suggestions"]["maxItems"] == 0


def test_sanitize_new_topics():
    def proposal(name, confidence=0.8):
        return {"name": name, "confidence": confidence, "reason": "r" * 250}
    result = svc.sanitize_new_topics([
        proposal("  ZOLW  "), proposal("  Nowy   temat "), proposal("nowy temat"),
        proposal(""), proposal(42), proposal("Slaby", 0.59), proposal("NaN", float("nan")),
        proposal("A" * 70), proposal("Trzeci"), proposal("Czwarty"),
    ], [{"id": 1, "name": "Żółw"}])
    assert [item["name"] for item in result] == ["Nowy temat", "A" * 60, "Trzeci"]
    assert all(len(item["reason"]) == 200 for item in result)
    assert len(svc.sanitize_new_topics([proposal("Łąki"), proposal("laki")], [])) == 1


def test_triage_new_topics_names_the_reason_for_every_dropped_proposal():
    def proposal(name, confidence=0.8):
        return {"name": name, "confidence": confidence, "reason": "r"}
    kept, dropped = svc.triage_new_topics([
        proposal("Opsec i ochrona danych"), proposal("Nowy temat"), proposal("nowy TEMAT"), proposal("Slaby", 0.59),
        proposal("Zly", "abc"), proposal("Drugi"), proposal("Trzeci"), proposal("Czwarty"),
    ], [{"id": 1, "name": "Opsec i ochrona danych"}])
    assert [item["name"] for item in kept] == ["Nowy temat", "Drugi", "Trzeci"]
    assert [(item["name"], item["dropped_because"]) for item in dropped] == [
        ("Opsec i ochrona danych", "duplicate_of_catalog"), ("nowy TEMAT", "duplicate_in_answer"),
        ("Slaby", "low_confidence"), ("Zly", "bad_confidence"), ("Czwarty", "over_limit"),
    ]


def test_feed_keeps_dropped_proposals_on_the_run(monkeypatch):
    proposals = [{"name": "AI", "confidence": 0.9, "reason": "same as catalog"}, {"name": "Nowy temat", "confidence": 0.9, "reason": "ok"}]
    ask = MagicMock(return_value=SimpleNamespace(response_text=json.dumps({"suggestions": [], "no_match": True, "new_topics": proposals})))
    monkeypatch.setattr(svc, "ai_ask", ask)
    monkeypatch.setattr(svc, "supports_structured_output", lambda _: True)
    monkeypatch.setattr(svc, "active_topic_catalog", lambda _: [{"id": 1, "name": "AI"}])
    run = ContentGroupSuggestionRun(id=2, model=svc.FEED_DEFAULT_MODEL, catalog_snapshot=[{"id": 1, "name": "AI"}])
    session = MagicMock()
    session.get.side_effect = [FeedItem(id=1), run]
    svc.execute_suggestion_job(session, Job(id="job", parameters={"feed_item_id": 1, "run_id": 2}))
    assert [item["name"] for item in run.raw_result["new_topics"]] == ["Nowy temat"]
    assert run.raw_result["dropped_new_topics"] == [
        {"name": "AI", "reason": "same as catalog", "confidence": 0.9, "dropped_because": "duplicate_of_catalog"}]


def test_successful_retry_keeps_the_earlier_error_in_the_result_and_clears_the_error_column(monkeypatch):
    ask = MagicMock(return_value=SimpleNamespace(response_text='{"suggestions": [], "no_match": true}'))
    monkeypatch.setattr(svc, "ai_ask", ask)
    monkeypatch.setattr(svc, "supports_structured_output", lambda _: True)
    monkeypatch.setattr(svc, "active_topic_catalog", lambda _: [])
    run = ContentGroupSuggestionRun(id=2, model=svc.FEED_DEFAULT_MODEL, catalog_snapshot=[], status="error",
                                    error="Error code: 429 - rate-limited upstream")
    session = MagicMock()
    session.get.side_effect = [FeedItem(id=1), run]
    svc.execute_suggestion_job(session, Job(id="job", attempt=3, parameters={"feed_item_id": 1, "run_id": 2}))
    assert run.status == "completed"
    assert run.error is None
    assert run.raw_result["retried_after"] == "Error code: 429 - rate-limited upstream"
    assert run.raw_result["attempts"] == 3


def test_clean_run_has_no_retry_marker(monkeypatch):
    monkeypatch.setattr(svc, "ai_ask", MagicMock(return_value=SimpleNamespace(response_text='{"suggestions": [], "no_match": true}')))
    monkeypatch.setattr(svc, "supports_structured_output", lambda _: True)
    monkeypatch.setattr(svc, "active_topic_catalog", lambda _: [])
    run = ContentGroupSuggestionRun(id=2, model=svc.FEED_DEFAULT_MODEL, catalog_snapshot=[])
    session = MagicMock()
    session.get.side_effect = [FeedItem(id=1), run]
    svc.execute_suggestion_job(session, Job(id="job", attempt=1, parameters={"feed_item_id": 1, "run_id": 2}))
    assert "retried_after" not in run.raw_result and "attempts" not in run.raw_result


def test_model_call_is_not_tied_to_a_document_analysis_job(monkeypatch):
    # llm_usage_logs.analysis_job_id is a foreign key to document_analysis_jobs; a jobs.id there made every usage insert fail
    ask = MagicMock(return_value=SimpleNamespace(response_text='{"suggestions": [], "no_match": true}'))
    monkeypatch.setattr(svc, "ai_ask", ask)
    monkeypatch.setattr(svc, "supports_structured_output", lambda _: True)
    monkeypatch.setattr(svc, "active_topic_catalog", lambda _: [])
    run = ContentGroupSuggestionRun(id=2, model=svc.FEED_DEFAULT_MODEL, catalog_snapshot=[])
    session = MagicMock()
    session.get.side_effect = [FeedItem(id=1), run]
    svc.execute_suggestion_job(session, Job(id="job", parameters={"feed_item_id": 1, "run_id": 2}))
    assert "analysis_job_id" not in ask.call_args.kwargs


@pytest.mark.parametrize("structured", [True, False])
def test_feed_stores_proposals_without_creating_groups(monkeypatch, structured):
    proposals = [{"name": "Nowy temat", "confidence": 0.9, "reason": "Useful"}]
    ask = MagicMock(return_value=SimpleNamespace(response_text=json.dumps({"suggestions": [], "no_match": True, "new_topics": proposals})))
    monkeypatch.setattr(svc, "ai_ask", ask)
    monkeypatch.setattr(svc, "supports_structured_output", lambda _: structured)
    monkeypatch.setattr(svc, "active_topic_catalog", lambda _: [])
    run = ContentGroupSuggestionRun(id=2, model=svc.FEED_DEFAULT_MODEL, catalog_snapshot=[])
    session = MagicMock()
    session.get.side_effect = [FeedItem(id=1), run]
    svc.execute_suggestion_job(session, Job(id="job", parameters={"feed_item_id": 1, "run_id": 2}))
    assert run.raw_result["new_topics"] == proposals
    assert not any(isinstance(call.args[0], (ContentGroup, FeedItemGroupMembership)) for call in session.add.call_args_list)
    schema = ask.call_args.kwargs["response_format"]
    assert "new_topics" in (schema["json_schema"]["schema"]["required"] if structured else ask.call_args.args[0])
    assert "Nie tw" not in (ask.call_args.kwargs["system_prompt"] or "")


def test_read_filters_current_catalog_and_documents(monkeypatch):
    monkeypatch.setattr(feed_routes, "active_topic_catalog", lambda _: [{"id": 1, "name": "Nowy temat"}])
    run = ContentGroupSuggestionRun(id=1, raw_result={"new_topics": [{"name": "NOWY TEMAT", "confidence": 0.9, "reason": ""}]})
    session = MagicMock()
    session.scalar.return_value = run
    assert feed_routes._suggestions_response(session, "feed_item", 1)["new_topics"] == []
    run.raw_result = {"new_topics": [{"name": "Other", "confidence": 0.9, "reason": ""}]}
    assert feed_routes._suggestions_response(session, "document", 1)["new_topics"] == []
    assert len(feed_routes._suggestions_response(session, "feed_item", 1)["new_topics"]) == 1


def test_new_model_job_has_unique_run_key_even_with_same_digest(monkeypatch):
    monkeypatch.setattr(svc, "active_topic_catalog", lambda _: [])
    monkeypatch.setattr(svc, "is_selectable", lambda *_: True)
    session = MagicMock()
    session.get.return_value = FeedItem(id=1)
    session.scalar.return_value = None
    runs = []
    def add(run):
        run.id = len(runs) + 1
        runs.append(run)
    session.add.side_effect = add
    enqueue = MagicMock(return_value=Job(id="job"))
    monkeypatch.setattr(svc, "enqueue", enqueue)
    svc.request_suggestions(session, "feed_item", 1, model="old")
    svc.request_suggestions(session, "feed_item", 1, model="new")
    assert runs[0].input_hash == runs[1].input_hash
    assert runs[0].prompt_version == "feed_item-builtin"
    assert enqueue.call_args_list[0].kwargs["idempotency_key"] != enqueue.call_args_list[1].kwargs["idempotency_key"]
