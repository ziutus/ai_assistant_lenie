"""Offline recorder, route, schema, report and retention coverage."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import flask
import pytest
from sqlalchemy.dialects import postgresql

from imports.browse_events_report import aggregate_events
from library import browse_event_transport as transport
from library import browse_events as recorder
from library.browse_events import (
    delete_expired_browse_events,
    record_browse_event,
    telemetry_context,
    validate_criteria,
)
from library.db.models import DocumentBrowseEvent
from library.search.audit_repository import TRUNCATION_SUFFIX
from library.search.types import MAX_QUERY_LENGTH
import library.search_routes as routes
from test_search_routes import _parse_result


def context(**overrides):
    return dict(
        event_id=str(uuid4()),
        session_id=str(uuid4()),
        browse_id=str(uuid4()),
        action="submit",
        requested_mode="explicit",
        changed_fields=["languages"],
        criteria_origin={"languages": "manual"},
        **overrides,
    )


def event(**overrides):
    values = dict(
        **context(),
        source_view="search",
        execution_mode="explicit",
        query_text="  Cold  War ",
        effective_query="Cold War",
        filters={"languages": ["PL"]},
        sort="relevance",
        page_size=10,
        offset=0,
        returned_count=3,
        total_count=None,
        has_more=False,
        outcome="success",
        created_at=datetime.now(timezone.utc),
    )
    values.update(overrides)
    return values


def test_own_transaction_caps_and_dedup_sql():
    session = MagicMock()
    session.execute.return_value.scalar_one_or_none.side_effect = [7, None]
    values = event(query_text="x" * 2000, effective_query="y" * 2000)
    assert record_browse_event(session_factory=lambda: session, **values) == 7
    assert record_browse_event(session_factory=lambda: session, **values) is None
    stmt = session.execute.call_args.args[0]
    compiled = stmt.compile(dialect=postgresql.dialect())
    assert "ON CONFLICT (event_id) DO NOTHING" in str(compiled)
    for key in ("query_text", "effective_query"):
        assert len(compiled.params[key]) == MAX_QUERY_LENGTH
        assert compiled.params[key].endswith(TRUNCATION_SUFFIX)
    assert session.commit.call_count == session.close.call_count == 2
    assert "statement_timeout" in str(session.execute.call_args_list[0].args[0])


def test_bounded_connection_uses_own_session_and_engine(monkeypatch):
    session = MagicMock()
    engine = MagicMock()
    monkeypatch.setattr(recorder, "_write_engine", None)
    with (
        patch.object(recorder, "get_session", return_value=session) as factory,
        patch.object(recorder, "create_engine", return_value=engine) as create,
        patch("library.config_loader.load_config", return_value={"POSTGRESQL_SSLMODE": "require"}),
    ):
        assert recorder._write_session() is session
    factory.assert_called_once()
    assert session.bind is engine
    assert create.call_args.kwargs["connect_args"] == {"connect_timeout": 2, "sslmode": "require"}
    assert create.call_args.kwargs["poolclass"] is recorder.NullPool


@pytest.mark.parametrize(
    "filters,changed,origins",
    [
        ({"api_key": "secret"}, [], {}),
        ({"without_embedding": "true"}, [], {}),
        ({"priority_group_id": True}, [], {}),
        ({"languages": ["a" * 301]}, [], {}),
        ({"topic_group_ids": [1] * 101}, [], {}),
        ({"author_name": "x" * 301}, [], {}),
        ({}, ["unknown"], {}),
        ({}, "languages", {}),
        ({}, [], {"languages": "invented"}),
        ({}, [], {"api_key": "manual"}),
    ],
)
def test_validation(filters, changed, origins):
    with pytest.raises(ValueError):
        validate_criteria(filters, changed, origins)
    factory = MagicMock()
    record_browse_event(
        session_factory=factory, **event(filters=filters, changed_fields=changed, criteria_origin=origins)
    )
    factory.assert_not_called()


def test_topic_empty_choices_remain_distinct():
    states = [
        dict(topic_filter_active=False, topic_group_ids=[], include_without_topics=False),
        dict(topic_filter_active=True, topic_group_ids=[], include_without_topics=True),
        dict(topic_filter_active=True, topic_group_ids=[], include_without_topics=False),
    ]
    assert len({str(validate_criteria(state, [], {})[0]) for state in states}) == 3


@pytest.mark.parametrize("failure", [RuntimeError("down"), SystemExit(1)])
def test_write_failure_including_cleanup_is_swallowed(failure):
    session = MagicMock()
    session.execute.side_effect = failure
    session.rollback.side_effect = failure
    session.close.side_effect = failure
    assert record_browse_event(session_factory=lambda: session, **event()) is None
    session.rollback.assert_called_once()
    session.close.assert_called_once()
    assert record_browse_event(session_factory=MagicMock(side_effect=failure), **event()) is None


def test_retention_and_job():
    session = MagicMock()
    session.execute.return_value.rowcount = 12
    assert delete_expired_browse_events(session_factory=lambda: session) == 12
    sql = str(session.execute.call_args.args[0])
    assert "DELETE FROM document_browse_events" in sql and "expires_at < now()" in sql
    session.commit.assert_called_once()
    session.execute.side_effect = RuntimeError("down")
    with pytest.raises(RuntimeError):
        delete_expired_browse_events(session_factory=lambda: session)
    import worker

    with patch("library.browse_events.delete_expired_browse_events", return_value=2) as browse:
        with patch("library.search.audit_repository.delete_expired_interpretations", return_value=3) as interpretations:
            assert worker.execute(session, SimpleNamespace(type="retention_sweep")) == {
                "browse_events": 2,
                "interpretations": 3,
            }
    browse.assert_called_once()
    interpretations.assert_called_once()
    session.scalars.return_value.all.return_value = [
        SimpleNamespace(
            id="retention_sweep",
            enabled=True,
            timezone="Europe/Warsaw",
            times=["03:30"],
        )
    ]
    with patch.object(worker, "enqueue") as enqueue:
        worker.scheduler(session, datetime(2026, 9, 10, 1, 30, tzinfo=timezone.utc))
    enqueue.assert_called_once_with(session, "retention_sweep", idempotency_key="retention_sweep:2026-09-10")


def test_schema():
    table = DocumentBrowseEvent.__table__
    assert len(table.columns) == 25
    assert table.c.schema_version.server_default.arg.text == "1"
    assert table.c.expires_at.type.timezone
    assert next(iter(table.c.interpretation_log_id.foreign_keys)).ondelete == "SET NULL"
    assert len(table.indexes) == 3


def test_report_dedup_manual_ai_restoration_empty_pages():
    first = event(returned_count=0)
    page = {**first, "event_id": str(uuid4()), "action": "page_change", "offset": 20}
    refresh = {**first, "event_id": str(uuid4()), "action": "refresh"}
    rows = [
        first,
        first,
        page,
        refresh,
        event(action="initial_load", criteria_origin={"languages": "remembered"}),
        event(criteria_origin={"languages": "ai"}, action="submit"),
        event(outcome="error", returned_count=0),
        event(action="correction", returned_count=None),
    ]
    report = aggregate_events(SimpleNamespace(**row) for row in rows)
    assert report["events"] == 7
    assert report["outcomes"][("search", "empty_first_page")] == 1
    assert report["outcomes"][("search", "error")] == 1
    assert report["outcomes"][("search", "correction")] == 1
    assert report["depth"][("search", 3)] == 1
    assert report["restored"][("search", "languages", "remembered")] == 1
    assert sum(report["phrases"].values()) == 4
    assert sum(report["filters"].values()) == 3
    assert all(key[-1] == "cold war" for key in report["phrases"])


@pytest.fixture
def client():
    app = flask.Flask(__name__)
    app.register_blueprint(routes.bp)
    app.config["TESTING"] = True
    return app.test_client()


@pytest.mark.parametrize("natural", [False, True])
def test_search_paths_linkage_and_provenance(client, natural):
    payload = {"natural_query": "wojna"} if natural else {"query": "wojna", "filters": {"languages": ["pl"]}}
    payload.update(telemetry=context(), limit=5, offset=10)
    with (
        patch.object(routes, "get_scoped_session", return_value=MagicMock()),
        patch.object(routes, "parse_search_query", return_value=_parse_result(languages=("pl",))),
        patch.object(routes, "SearchService") as service,
        patch.object(transport, "record_browse_event") as record,
    ):
        service.return_value.search.return_value = [{"id": i} for i in range(6)]
        assert client.post("/search", json=payload).status_code == 200
    values = record.call_args.kwargs
    assert values["source_view"] == "search"
    assert values["execution_mode"] == ("natural" if natural else "explicit")
    assert values["interpretation_log_id"] == (123 if natural else None)
    assert values["criteria_origin"]["languages"] == ("ai" if natural else "manual")
    assert values["offset"] == 10 and values["returned_count"] == 5 and values["has_more"]


def test_search_clarification_error_feedback_and_no_context(client):
    with (
        patch.object(routes, "get_scoped_session", return_value=MagicMock()),
        patch.object(routes, "SearchService") as service,
        patch.object(transport, "record_browse_event") as record,
    ):
        service.return_value.search.return_value = []
        client.post("/search", json={"query": "x"})
        record.assert_not_called()
        service.return_value.search.side_effect = RuntimeError("down")
        assert client.post("/search", json={"query": "x", "telemetry": context()}).status_code == 503
        assert record.call_args.kwargs["outcome"] == "error"
        with patch.object(routes, "parse_search_query", return_value=_parse_result(clarification_required=True)):
            client.post("/search", json={"natural_query": "x", "telemetry": context()})
            assert record.call_args.kwargs["outcome"] == "clarification_required"
            assert record.call_args.kwargs["execution_mode"] == "clarification"
            before = record.call_count
            client.post("/search/parse", json={"natural_query": "x"})
            assert record.call_count == before
        with patch.object(routes, "record_feedback", return_value=True):
            client.post("/search/123/feedback", json={"verdict": "incorrect", "telemetry": context()})
            assert record.call_args.kwargs["action"] == "correction"
            assert record.call_args.kwargs["interpretation_log_id"] == 123


def test_list_transport_applied_filters_and_no_context():
    with patch("library.chunk_review_routes.start_analysis_worker"):
        import server

    with (
        patch.object(server, "check_auth_header"),
        patch.object(server, "get_scoped_session", return_value=MagicMock()),
        patch.object(server, "DocumentRepository") as repository,
        patch.object(transport, "record_browse_event") as record,
    ):
        repository.return_value.get_list.side_effect = lambda **kw: 100 if kw.get("count") else [{"id": 1}]
        client = server.app.test_client()
        assert client.get("/website_list").status_code == 200
        record.assert_not_called()
        ctx = context()
        ctx.update(action="page_change", requested_mode="similar", changed_fields="[]", criteria_origin="{}")
        params = {f"_tel_{key}": value for key, value in ctx.items()}
        params.update(page=3, limit=25, type="link", topic_filter="true", without_embedding="true")
        assert client.get("/website_list", query_string=params).status_code == 200
        values = record.call_args.kwargs
        assert values["source_view"] == "document_list" and values["execution_mode"] == "ilike"
        assert values["requested_mode"] == "similar" and values["offset"] == 50
        assert values["total_count"] == 100 and values["has_more"]
        assert values["filters"]["topic_filter_active"] is True
        assert values["filters"]["topic_group_ids"] == []
        assert values["filters"]["without_embedding"] is True


def test_malformed_optional_context():
    assert telemetry_context({}) is None
    value = context()
    value["changed_fields"] = "[" + " " * 9000
    assert telemetry_context(value) is None
