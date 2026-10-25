import datetime as dt
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from flask import Flask, g
from sqlalchemy.dialects import postgresql

from library import app_settings, feed_monitor_service as service, feed_retention, feed_routes
from library.db.models import FeedItem


def make_item():
    return FeedItem(id=7, feed_source_id=1, title="Test", url="https://example.com",
                    canonical_url="https://example.com", status="saved_for_later",
                    saved_at=dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc), review_reason="other")


@pytest.fixture
def session():
    result = MagicMock()
    result.get.return_value = make_item()
    return result


def test_lifecycle_preserves_text_decision(session):
    item = session.get.return_value
    original = (item.status, item.saved_at, item.review_reason, list(item.group_memberships))
    assert service.set_llm_discussion(session, 7, "open") is item
    flagged = item.llm_discussion_at
    service.set_llm_discussion(session, 7, "open")
    assert item.llm_discussion_at == flagged
    service.set_llm_discussion(session, 7, "done", "  https://example.com/result  ")
    assert item.llm_discussion_result == "https://example.com/result"
    assert item.llm_discussion_done_at >= flagged
    assert item.llm_discussion_at == flagged
    service.set_llm_discussion(session, 7, "open")
    assert item.llm_discussion_done_at is None
    assert item.llm_discussion_result is None
    service.set_llm_discussion(session, 7, "done", "   ")
    assert item.llm_discussion_result is None
    service.set_llm_discussion(session, 7, None)
    assert all(getattr(item, field) is None for field in (
        "llm_discussion_status", "llm_discussion_at", "llm_discussion_done_at", "llm_discussion_result"))
    assert (item.status, item.saved_at, item.review_reason, item.group_memberships) == original
    session.add.assert_not_called()
    session.execute.assert_not_called()
    assert session.commit.call_count == 6


@pytest.mark.parametrize("status", [None, "done"])
def test_done_requires_open(session, status):
    session.get.return_value.llm_discussion_status = status
    with pytest.raises(RuntimeError, match="item is not open for discussion"):
        service.set_llm_discussion(session, 7, "done")
    session.commit.assert_not_called()


def test_validation(session):
    with pytest.raises(ValueError, match="invalid discussion status"):
        service.set_llm_discussion(session, 7, [])
    session.get.return_value.llm_discussion_status = "open"
    with pytest.raises(ValueError, match="result is limited to 1000 characters"):
        service.set_llm_discussion(session, 7, "done", "x" * 1001)
    session.commit.assert_not_called()
    service.set_llm_discussion(session, 7, "done", "x" * 1000)
    session.get.return_value = None
    with pytest.raises(ValueError, match="feed item not found"):
        service.set_llm_discussion(session, 7, "open")


@pytest.fixture
def client(monkeypatch, session):
    app = Flask(__name__)
    app.register_blueprint(feed_routes.bp)

    @app.before_request
    def auth():
        g.auth = SimpleNamespace(kind="user", user_id=1)

    monkeypatch.setattr(feed_routes, "get_scoped_session", lambda: session)
    monkeypatch.setattr(app_settings, "get_setting", lambda *_: None)
    return app.test_client()


@pytest.mark.parametrize("body", [{}, [], {"status": "bad"}, {"status": []}, {"status": "open", "result": 123}])
def test_patch_bad_request(client, body):
    assert client.patch("/feed_items/7/discussion", json=body).status_code == 400


def test_patch_responses(client, session):
    assert client.patch("/feed_items/7/discussion", json={"status": "done"}).status_code == 409
    response = client.patch("/feed_items/7/discussion", json={"status": "open"})
    assert response.status_code == 200
    assert response.json["status"] == "saved_for_later"
    assert response.json["llm_discussion_status"] == "open"
    assert response.json["llm_discussion_at"]
    response = client.patch("/feed_items/7/discussion", json={"status": "done", "result": " note "})
    assert response.json["llm_discussion_result"] == "note"
    assert response.json["llm_discussion_done_at"]
    session.get.return_value = None
    assert client.patch("/feed_items/7/discussion", json={"status": None}).status_code == 404


@pytest.mark.parametrize("discussion,column", [("open", "llm_discussion_at"), ("done", "llm_discussion_done_at"), ("any", "llm_discussion_at")])
def test_queue_filters_and_order(client, session, discussion, column):
    session.scalar.return_value = 0
    session.scalars.return_value.all.return_value = []
    response = client.get(f"/feed_items?discussion={discussion}&feed_source_id=1&limit=10&offset=2")
    assert response.status_code == 200
    assert response.json == {"feed_items": [], "total": 0, "limit": 10, "offset": 2}
    query = session.scalars.call_args.args[0]
    sql = str(query.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    where = sql.split("WHERE")[1]
    assert "feed_items.status =" not in where
    assert "feed_items.feed_source_id = 1" in where
    assert f"ORDER BY feed_items.{column} DESC, feed_items.id DESC" in sql
    assert ("llm_discussion_status IS NOT NULL" if discussion == "any" else f"llm_discussion_status = '{discussion}'") in where
    client.get(f"/feed_items?discussion={discussion}&status=skipped")
    assert "feed_items.status =" in str(session.scalars.call_args.args[0])


def test_filter_validation_and_summary(client, session):
    assert client.get("/feed_items?discussion=invalid").status_code == 400
    assert client.get("/feed_items?discussion=").status_code == 400
    session.execute.return_value.all.return_value = [("open", 3)]
    response = client.get("/feed_items/discussion_summary")
    assert response.status_code == 200
    assert response.json == {"open": 3, "done": 0}


def test_expiry_keeps_discussion(monkeypatch, session):
    # Same MagicMock session / namespace groups as test_feed_retention;
    # execute applies the actual transition's SQL values to the in-memory item.
    group = SimpleNamespace(kind="priority", priority_rank=100, retention_months=None, archived_at=None)
    item = SimpleNamespace(id=7, title="Test", status="saved_for_later",
                           saved_at=dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc),
                           document_id=None, review_reason=None, ignored_pattern=None,
                           llm_discussion_status=None,
                           group_memberships=[SimpleNamespace(group=group, group_id=1)])
    session.get.return_value = item
    monkeypatch.setattr(app_settings, "get_setting", lambda *_: None)
    session.scalars.return_value.all.return_value = [item]

    def execute(statement):
        for key, value in statement.compile().params.items():
            if hasattr(item, key):
                setattr(item, key, value)
        return SimpleNamespace(rowcount=1)

    session.execute.side_effect = execute
    service.set_llm_discussion(session, item.id, "open")
    flagged = item.llm_discussion_at
    result = feed_retention.expire_saved_items(session, now=dt.datetime(2027, 1, 1, tzinfo=dt.timezone.utc))
    assert result["expired"] == 1
    assert item.status == "skipped"
    assert item.review_reason == "expired"
    assert item.llm_discussion_status == "open"
    assert item.llm_discussion_at == flagged
