from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from flask import Flask, g
from sqlalchemy.dialects import postgresql

from library import app_settings, feed_routes


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


def where_sql(session):
    query = session.scalars.call_args.args[0]
    return str(query.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


@pytest.mark.parametrize("media,negated", [("video", False), ("article", True)])
def test_media_filter(client, session, media, negated):
    assert client.get(f"/feed_items?status=saved_for_later&media={media}").status_code == 200
    where = where_sql(session)
    assert "youtube_channel" in where and "youtu" in where
    assert ("NOT (" in where) is negated


@pytest.mark.parametrize("value,negated", [("only", False), ("exclude", True)])
def test_maybe_later_filter(client, session, value, negated):
    assert client.get(f"/feed_items?status=saved_for_later&maybe_later={value}").status_code == 200
    where = where_sql(session)
    assert "content_groups.priority_rank = 100" in where and "content_groups.kind = 'priority'" in where
    assert ("NOT (EXISTS" in where) is negated


def test_filters_absent_by_default(client, session):
    client.get("/feed_items?status=saved_for_later")
    where = where_sql(session)
    assert "youtube_channel" not in where and "priority_rank" not in where


@pytest.mark.parametrize("query", ["media=podcast", "maybe_later=maybe"])
def test_invalid_values_rejected(client, query):
    assert client.get(f"/feed_items?{query}").status_code == 400
