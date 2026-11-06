"""Offline audit contract: real SQLite transactions, provider and HTTP boundaries."""

import json
import ast
import importlib.util
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flask import Flask, g
from sqlalchemy import create_engine, event, func, null, select, text
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateTable

from library import ai, fabryka_client, llm_cost_routes
from library.db.models import LlmCallPayload, LlmPricing, LlmUsageLog
from library.llm_usage import payloads, recorder

MODEL = "Bielik-11B-v3.0-Instruct"


@pytest.fixture
def db(monkeypatch):
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE documents (id INTEGER PRIMARY KEY, title TEXT)"))
        conn.execute(text("INSERT INTO documents VALUES (42, 'Article')"))
        conn.execute(text("CREATE TABLE document_analysis_jobs (id TEXT PRIMARY KEY, run_id INTEGER)"))
        # SQLite only autoincrements INTEGER primary keys; production usage ids are BIGINT.
        for table in (LlmPricing.__table__, LlmUsageLog.__table__, LlmCallPayload.__table__):
            conn.execute(text(str(CreateTable(table).compile(engine)).replace("BIGINT", "INTEGER")))
    monkeypatch.setattr(payloads, "load_config", lambda: {})
    monkeypatch.setattr(payloads, "get_session", lambda: Session(engine))
    original = recorder.record_llm_usage
    monkeypatch.setattr(recorder, "record_llm_usage", lambda **kw: original(**kw, session_factory=lambda: Session(engine)))
    with Session(engine) as session:
        monkeypatch.setattr(llm_cost_routes, "get_scoped_session", lambda: session)
        yield session
    engine.dispose()


@pytest.fixture
def provider(monkeypatch):
    from library.api.cloudferro.sherlock import sherlock

    call = Mock(return_value=SimpleNamespace(response_text='  {"raw": true}\n', prompt_tokens=12,
                                            completion_tokens=3, total_tokens=15))
    monkeypatch.setattr(sherlock, "sherlock_get_completion", call)
    return call


def build(**kw):
    return payloads.build_payload(**{"system_prompt": "system", "request_text": "request",
                                    "response_text": "response", "error": None, "request_extra": {}, **kw})


def test_ai_roundtrip(db, provider):
    result = ai.ai_ask("Full question", MODEL, system_prompt="System", document_id=42)
    row = db.scalar(select(LlmCallPayload))
    assert row.usage_log_id == result.usage.usage_log_id
    assert row.document_id == 42 and row.operation == "ai_ask"
    assert row.system_prompt == "System" and row.request_text == "Full question"
    assert row.response_text == '  {"raw": true}\n'
    assert row.request_extra == {"response_format": None, "temperature": 0.7, "max_token_count": 4096}
    assert db.scalar(select(func.count()).select_from(LlmUsageLog)) == 1


@pytest.mark.parametrize("opt_out,flag", [(True, "true"), (False, "false")])
def test_disabled_keeps_usage(db, provider, monkeypatch, opt_out, flag):
    monkeypatch.setattr(payloads, "load_config", lambda: {"LLM_PAYLOAD_STORE": flag})
    result = ai.ai_ask("private", MODEL, store_payload=not opt_out)
    assert result.usage.usage_log_id
    assert db.scalar(select(func.count()).select_from(LlmCallPayload)) == 0


def test_provider_exception_keeps_prompt_error_and_usage(db, provider):
    exc = RuntimeError("Provider failed")
    provider.side_effect = exc
    with pytest.raises(RuntimeError) as raised:
        ai.ai_ask("Question", MODEL)
    assert raised.value is exc
    row = db.scalar(select(LlmCallPayload))
    assert row.request_text == "Question" and row.response_text is None and row.error == str(exc)
    usage = db.get(LlmUsageLog, row.usage_log_id)
    assert not usage.success and usage.error_code == "RuntimeError"


def test_real_savepoint_failure_preserves_usage_and_ai_result(db, provider, monkeypatch):
    original = payloads.build_payload
    monkeypatch.setattr(payloads, "build_payload", lambda **kw: {**original(**kw), "request_truncated": null()})
    # Actual NOT NULL violation inside the payload INSERT, not a mocked storage function.
    response = ai.ai_ask("Question", MODEL)
    assert response.response_text == provider.return_value.response_text
    assert db.get(LlmUsageLog, response.usage.usage_log_id) is not None
    assert db.scalar(select(func.count()).select_from(LlmCallPayload)) == 0


def test_payload_shares_outer_transaction(db):
    db.execute(text("UPDATE documents SET title='changed' WHERE id=42"))
    assert payloads.store_payload(db, usage_log_id=None, document_id=42, operation="test",
                                 provider="test", model="test", payload=build())
    db.rollback()
    assert db.scalar(select(func.count()).select_from(LlmCallPayload)) == 0
    assert db.scalar(text("SELECT title FROM documents WHERE id=42")) == "Article"


@pytest.mark.parametrize("field,flag", [("system_prompt", "request_truncated"), ("request_text", "request_truncated"),
                                       ("response_text", "response_truncated"), ("error", "response_truncated")])
def test_text_limits(field, flag):
    value = "x" * payloads.MAX_FIELD_CHARS
    assert not build(**{field: value})[flag]
    result = build(**{field: value + "x"})
    assert result[field] == value and result[flag]


@pytest.mark.parametrize("extra", [{"bad": object()}, {"bad": float("nan")}, {"bad": {1, 2}}])
def test_invalid_extra_is_omitted(extra):
    assert build(request_extra=extra)["request_extra"] is None


def test_image_never_stored(db, provider):
    ai.ai_ask("Describe", "google/gemma-4-31B-it", image_base64="PRIVATE_BASE64")
    row = db.scalar(select(LlmCallPayload))
    assert row.request_text == "Describe" and row.request_extra["image"] == "omitted"
    assert "PRIVATE_BASE64" not in str({key: value for key, value in vars(row).items()})


def test_retention_only_old_payloads(db, provider, monkeypatch):
    for _ in range(2):
        ai.ai_ask("Question", MODEL)
    rows = db.scalars(select(LlmCallPayload).order_by(LlmCallPayload.id)).all()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    rows[0].created_at = now - timedelta(days=11)
    rows[1].created_at = now - timedelta(days=9)
    db.commit()
    monkeypatch.setattr(payloads, "load_config", lambda: {"LLM_PAYLOAD_RETENTION_DAYS": "10"})
    assert payloads.delete_expired_llm_payloads() == 1
    assert db.scalars(select(LlmCallPayload.id)).all() == [rows[1].id]
    assert db.scalar(select(func.count()).select_from(LlmUsageLog)) == 2


@pytest.mark.parametrize("value", [None, "invalid", 0, -1])
def test_retention_invalid_defaults(monkeypatch, value):
    monkeypatch.setattr(payloads, "load_config", lambda: {"LLM_PAYLOAD_RETENTION_DAYS": value})
    assert payloads.retention_days() == 30


def test_missing_config_and_failed_standalone_never_raise(monkeypatch):
    monkeypatch.setattr(payloads, "load_config", Mock(side_effect=SystemExit(1)))
    assert payloads.payload_enabled() and payloads.retention_days() == 30
    monkeypatch.setattr(payloads, "get_session", Mock(side_effect=SystemExit(1)))
    assert payloads.store_payload_standalone(operation="test", provider="test", model="test", payload=build()) is None


@pytest.fixture
def client(db):
    app = Flask(__name__)
    app.register_blueprint(llm_cost_routes.bp)

    @app.before_request
    def auth():
        g.auth = SimpleNamespace(kind=app.config.get("KEY_KIND", "user"))

    return app.test_client()


def test_payload_endpoint_and_bulk_has_payload(db, provider, client):
    first = ai.ai_ask("question", MODEL, document_id=42).usage.usage_log_id
    second = ai.ai_ask("private", MODEL, document_id=42, store_payload=False).usage.usage_log_id
    usage = db.get(LlmUsageLog, first)
    usage.cost_amount, usage.cost_currency = Decimal("0.1234567890"), "USD"
    db.commit()
    assert client.get("/llm_usage/999/payload").status_code == 404
    response = client.get(f"/llm_usage/{first}/payload")
    assert response.status_code == 200
    assert response.json["usage"]["cost_amount"] == "0.1234567890"
    assert response.json["payload"]["response_text"] == provider.return_value.response_text
    datetime.fromisoformat(response.json["payload"]["created_at"])
    assert client.get(f"/llm_usage/{second}/payload").json["payload"] is None
    queries = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        queries.append(statement)

    event.listen(db.bind, "before_cursor_execute", capture)
    try:
        result = client.get("/llm_costs?document_id=42")
    finally:
        event.remove(db.bind, "before_cursor_execute", capture)
    assert result.status_code == 200
    assert {row["id"]: row["has_payload"] for row in result.json["calls"]} == {first: True, second: False}
    assert len([sql for sql in queries if "llm_call_payloads" in sql]) == 1
    client.application.config["KEY_KIND"] = "service"
    assert client.get(f"/llm_usage/{first}/payload").status_code == 200
    client.application.config["KEY_KIND"] = "read_only"
    assert client.get(f"/llm_usage/{first}/payload").status_code == 403


@pytest.mark.parametrize("route", ["basal", "decisions"])
def test_entity_decisions_store_complete_raw_envelope(db, monkeypatch, route):
    from library.entity_sense_classifier import SenseProvider

    config = {"FABRYKA_API_KEY": "fake", "OPENROUTER_API_KEY": "fake", "OPENROUTER_ENABLED": True}
    monkeypatch.setattr("library.config_loader.load_config", lambda: config)
    monkeypatch.setattr("library.entity_sense_classifier._daily_calls", lambda: 0)
    monkeypatch.setattr("library.external_service_events.record_external_service_event", Mock())
    raw = ' {"answers":{"sense":{"choice":"kraj","confidence":0.95}},"usage":{"tokens":17}}\n'
    response = Mock(status_code=200, text=raw)
    response.json.return_value = json.loads(raw)
    monkeypatch.setattr(fabryka_client.requests, "post", Mock(return_value=response))
    service = SenseProvider()
    args = ({"entity_text": "Salvador", "country": "Salwador"}, "context", "title", 42, config)
    result = service.basal(*args) if route == "basal" else service.decisions("decision-model", *args)
    assert result["sense"] == "kraj"
    row = db.scalar(select(LlmCallPayload))
    assert row.response_text == raw and row.document_id == 42 and row.usage_log_id is None
    assert row.provider == ("fabryka" if route == "basal" else "openrouter-decisions")
    assert row.request_extra["state"]["candidate"] == "Salvador"
    assert "sense" in row.request_extra["questions"] and row.operation == "entity_sense_decision"


def test_decision_failure_and_global_opt_out(db, monkeypatch):
    monkeypatch.setattr(fabryka_client, "_api_key", lambda: "test")
    monkeypatch.setattr("library.external_service_events.record_external_service_event", Mock())
    response = Mock(status_code=429, text='{"error":"quota"}')
    monkeypatch.setattr(fabryka_client.requests, "post", Mock(return_value=response))
    for enabled in (True, False):
        monkeypatch.setattr(payloads, "load_config", lambda: {"LLM_PAYLOAD_STORE": enabled})
        with pytest.raises(fabryka_client.FabrykaRateLimited):
            fabryka_client.yes_probability("Article", "Matches?")
    rows = db.scalars(select(LlmCallPayload)).all()
    assert len(rows) == 1 and rows[0].error and rows[0].response_text == response.text


def test_migration_roundtrip_and_foreign_keys():
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import inspect

    path = Path(__file__).parents[2] / "alembic/versions/8b6f2d9a0c41_llm_call_payloads.py"
    spec = importlib.util.spec_from_file_location("payload_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys=ON"))
        conn.execute(text("CREATE TABLE documents (id INTEGER PRIMARY KEY)"))
        conn.execute(text("CREATE TABLE llm_usage_logs (id INTEGER PRIMARY KEY)"))
        migration.op = Operations(MigrationContext.configure(conn))
        migration.upgrade()
        assert len(inspect(conn).get_indexes("llm_call_payloads")) == 3
        conn.execute(text("INSERT INTO documents VALUES (42)"))
        conn.execute(text("INSERT INTO llm_usage_logs VALUES (1)"))
        conn.execute(text("INSERT INTO llm_call_payloads (usage_log_id, document_id, operation, provider, model) "
                          "VALUES (1, 42, 'test', 'test', 'test')"))
        conn.execute(text("DELETE FROM documents"))
        conn.execute(text("DELETE FROM llm_usage_logs"))
        assert conn.execute(text("SELECT usage_log_id, document_id FROM llm_call_payloads")).one() == (None, None)
        migration.downgrade()
        assert "llm_call_payloads" not in inspect(conn).get_table_names()
    engine.dispose()


@pytest.mark.parametrize("module,operations", [
    ("library/contact_photos.py", {"contact_photo_description", "contact_photo_classification"}),
    ("library/address_parsing.py", {"address_parse"}),
    ("library/ai_intent_parser.py", {"intent_parsing"}),
    ("imports/whatsapp_neighbor_profiles.py", {"whatsapp_neighbor_profile"}),
])
def test_private_call_sites_explicitly_opt_out(module, operations):
    tree = ast.parse((Path(__file__).parents[2] / module).read_text(encoding="utf-8"))
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "ai_ask":
            keywords = {kw.arg: kw.value for kw in node.keywords}
            assert ast.literal_eval(keywords["store_payload"]) is False
            found.add(ast.literal_eval(keywords["operation"]))
    assert found == operations


def test_decision_storage_failure_preserves_answer(db, monkeypatch):
    monkeypatch.setattr(fabryka_client, "_api_key", lambda: "test")
    monkeypatch.setattr("library.external_service_events.record_external_service_event", Mock())
    response = Mock(status_code=200, text='{"answers":{"match":{"noul":0.9}}}')
    response.json.return_value = json.loads(response.text)
    monkeypatch.setattr(fabryka_client.requests, "post", Mock(return_value=response))
    monkeypatch.setattr(payloads, "get_session", Mock(side_effect=RuntimeError("database down")))
    assert fabryka_client.yes_probability("Article", "Matches?") == 0.9


def test_document_payloads_filter_pagination_and_standalone(db, provider, client):
    usage_id = ai.ai_ask("question", MODEL, document_id=42).usage.usage_log_id
    linked = db.scalar(select(LlmCallPayload))
    linked.created_at = datetime(2026, 1, 3)
    standalone = LlmCallPayload(document_id=42, operation="entity_sense_decision", provider="fabryka",
                                model="basal", created_at=datetime(2026, 1, 2), **build())
    narrative = LlmCallPayload(document_id=42, operation="narrative_decision", provider="fabryka",
                              model="basal", created_at=datetime(2026, 1, 2), **build(error="failed"))
    unrelated = LlmCallPayload(document_id=43, operation="entity_sense_decision", provider="fabryka",
                              model="basal", **build())
    db.add_all([standalone, narrative, unrelated])
    db.commit()

    assert client.get("/document/999/llm_payloads").status_code == 404
    response = client.get("/document/42/llm_payloads")
    assert response.status_code == 200 and response.json["total"] == 3
    rows = response.json["payloads"]
    assert [row["id"] for row in rows] == [linked.id, narrative.id, standalone.id]
    assert rows[0]["usage_log_id"] == usage_id
    assert rows[2] == {"id": standalone.id, "usage_log_id": None, "operation": "entity_sense_decision",
                       "provider": "fabryka", "model": "basal", "created_at": "2026-01-02T00:00:00", **build()}
    filtered = client.get("/document/42/llm_payloads?operation=entity_sense_decision").json
    assert filtered == {"payloads": [rows[2]], "total": 1}
    assert client.get("/document/42/llm_payloads?operation=entity_sense").json == {"payloads": [], "total": 0}
    assert client.get("/document/42/llm_payloads?limit=1&offset=1").json == {"payloads": [rows[1]], "total": 3}
    assert client.get("/document/42/llm_payloads?limit=100&offset=3").json == {"payloads": [], "total": 3}
    assert client.get("/document/42/llm_payloads?operation=entity_sense_decision&offset=1").json == {
        "payloads": [], "total": 1,
    }


def test_document_payloads_default_limit_and_empty_document(db, client):
    assert client.get("/document/42/llm_payloads").json == {"payloads": [], "total": 0}
    db.add_all([LlmCallPayload(document_id=42, operation="narrative_decision", provider="fabryka",
                              model="basal", **build()) for _ in range(21)])
    db.commit()
    response = client.get("/document/42/llm_payloads").json
    assert response["total"] == 21 and len(response["payloads"]) == 20


@pytest.mark.parametrize("query", ["limit=0", "limit=101", "limit=-1", "limit=abc", "limit=1.5", "limit=",
                                   "offset=-1", "offset=abc", "offset=1.5", "offset=",
                                   "offset=9223372036854775808"])
def test_document_payloads_invalid_parameters(client, query):
    assert client.get(f"/document/42/llm_payloads?{query}").status_code == 400


@pytest.mark.parametrize("kind,status", [("user", 200), ("service", 200), ("read_only", 403)])
def test_document_payloads_authorization(client, kind, status):
    client.application.config["KEY_KIND"] = kind
    assert client.get("/document/42/llm_payloads").status_code == status


def test_document_payloads_requires_authentication(db):
    app = Flask(__name__)
    app.register_blueprint(llm_cost_routes.bp)
    assert app.test_client().get("/document/42/llm_payloads").status_code == 401
