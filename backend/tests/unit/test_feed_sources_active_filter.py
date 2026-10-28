from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from flask import Flask, g
from sqlalchemy.dialects import postgresql

from library import app_settings, feed_routes
from library.feed_source_service import list_feeds, feed_filter_metadata


@pytest.fixture
def session():
    result = MagicMock()
    result.scalar.return_value = 0
    result.scalars.return_value.all.return_value = []
    return result


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


def rows():
    return [SimpleNamespace(id=1, name="A", disabled=False, tags=["aws", "cloud"], updated_at=None),
            SimpleNamespace(id=2, name="B", disabled=True, tags=["aws"], updated_at=None),
            SimpleNamespace(id=3, name="C", disabled=False, tags=["gcp"], updated_at=None)]


def sql(query):
    return str(query.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


def test_filter_metadata_and_exact_tag_or(session):
    session.scalars.return_value.all.return_value = rows()
    assert [f.id for f in list_feeds(session, tags=["aws", "gcp"])] == [1, 2, 3]
    assert list_feeds(session, tags=["aw"]) == []
    assert feed_filter_metadata(session, ["aws"]) == {
        "counts": {"active": 1, "disabled": 1},
        "tags": [{"tag": "aws", "count": 2}, {"tag": "cloud", "count": 1}, {"tag": "gcp", "count": 1}],
    }


@pytest.mark.parametrize("value,condition", [(None, None), ("0", "disabled IS false"), ("1", "disabled IS true")])
def test_list_route(client, session, monkeypatch, value, condition):
    monkeypatch.setattr(feed_routes, "feed_to_dict", lambda f: {"id": f.id})
    session.scalars.return_value.all.return_value = rows()
    result = client.get("/feed_sources" + (f"?disabled={value}&tag=aws" if value else ""))
    assert result.status_code == 200
    assert result.json["feed_sources"] == [{"id": 1}, {"id": 2}] if value else result.json["feed_sources"] == [{"id": 1}, {"id": 2}, {"id": 3}]
    query = sql(session.scalars.call_args_list[0].args[0])
    assert condition in query if condition else "WHERE" not in query
    assert result.json["counts"] == ({"active": 1, "disabled": 1} if value else {"active": 2, "disabled": 1})


def test_invalid_disabled(client):
    assert client.get("/feed_sources?disabled=yes").status_code == 400


@pytest.mark.parametrize("target", [{"feed_ids": [1, 2, 3]}, {"tag": "aws"}])
def test_bulk_and_idempotency(client, session, target):
    feeds = rows()
    session.scalars.return_value.all.return_value = feeds
    result = client.post("/feed_sources/bulk-disable", json={"disabled": True, **target})
    expected = [1, 3] if "feed_ids" in target else [1]
    assert result.json == {"changed": len(expected), "feed_ids": expected}
    assert all(f.updated_at is not None for f in feeds if f.id in expected)
    assert feeds[1].updated_at is None
    assert client.post("/feed_sources/bulk-disable", json={"disabled": True, **target}).json["changed"] == 0
    assert client.post("/feed_sources/bulk-disable", json={"disabled": False, **target}).status_code == 200


@pytest.mark.parametrize("body", [None, [], {}, {"disabled": True}, {"disabled": True, "feed_ids": [], "tag": "aws"},
    {"disabled": 1, "feed_ids": [1]}, {"disabled": "true", "tag": "aws"}, {"disabled": True, "feed_ids": [True]},
    {"disabled": True, "feed_ids": "1"}, {"disabled": True, "tag": ""}])
def test_invalid_bulk(client, session, body):
    assert client.post("/feed_sources/bulk-disable", json=body).status_code == 400
    session.commit.assert_not_called()


def test_missing_id_is_atomic(client, session):
    feeds = rows()
    session.scalars.return_value.all.return_value = feeds
    assert client.post("/feed_sources/bulk-disable", json={"disabled": True, "feed_ids": [1, 2, 3, 999]}).status_code == 400
    assert feeds[0].disabled is False
    assert all(f.updated_at is None for f in feeds)
    session.commit.assert_not_called()
    session.rollback.assert_called()


def test_unknown_tag_changes_nothing(client, session):
    session.scalars.return_value.all.return_value = rows()
    assert client.post("/feed_sources/bulk-disable", json={"disabled": True, "tag": "unknown"}).json == {"changed": 0, "feed_ids": []}


@pytest.mark.parametrize("status", [None, "new", "llm_analysis_requested", "error", "saved_for_later", "imported", "skipped", "ignored"])
@pytest.mark.parametrize("include", [False, True])
def test_item_filter_and_total(client, session, status, include):
    params = {"include_disabled_sources": "1" if include else "0"}
    if status:
        params["status"] = status
    assert client.get("/feed_items", query_string=params).status_code == 200
    expected = not include and status in {"new", "llm_analysis_requested", "error"}
    assert ("feed_sources.disabled IS false" in sql(session.scalars.call_args.args[0])) == expected
    assert ("feed_sources.disabled IS false" in sql(session.scalar.call_args.args[0])) == expected


def test_disabled_check(client, session):
    session.get.return_value = rows()[1]
    response = client.post("/feed_sources/2/check")
    assert response.status_code == 409
    assert "Feed jest wyłączony" == response.json["message"]
    session.scalars.assert_not_called()
