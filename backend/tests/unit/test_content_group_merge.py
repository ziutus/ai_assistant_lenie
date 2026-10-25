from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("flask")

from flask import Flask, g
from sqlalchemy.dialects import postgresql

from library import content_group_service as service, feed_routes
from library.db.models import ContentGroup


def group(group_id, name="AI", kind="topic", archived=None):
    return ContentGroup(id=group_id, name=name, kind=kind, archived_at=archived)


def sql(statement) -> str:
    return " ".join(str(statement.compile(dialect=postgresql.dialect())).split())


def fake_session(rowcounts):
    session = MagicMock()
    session.execute.side_effect = [SimpleNamespace(rowcount=count) for count in rowcounts]
    return session


def test_merge_moves_memberships_drops_duplicates_and_archives_the_source():
    source, target = group(1), group(2, "Agenci AI")
    session = fake_session([5, 1, 3, 0, 2, 0, 4, 0])
    result = service.merge_groups(session, source, target)
    assert result == {
        "feed_items": 5, "feed_items_duplicates": 1, "documents": 3, "documents_duplicates": 0,
        "chunks": 2, "chunks_duplicates": 0, "suggestions": 4,
    }
    statements = [sql(call.args[0]) for call in session.execute.call_args_list]
    assert statements[0].startswith("UPDATE feed_item_group_memberships SET group_id=") and "NOT IN (SELECT" in statements[0]
    assert statements[1].startswith("DELETE FROM feed_item_group_memberships")
    assert statements[2].startswith("UPDATE document_group_memberships") and statements[4].startswith("UPDATE document_chunk_group_memberships")
    assert statements[6].startswith("UPDATE content_group_suggestions SET group_id=") and "run_id NOT IN" in statements[6]
    assert statements[7].startswith("UPDATE content_group_suggestions SET status=")
    assert source.archived_at is not None and target.archived_at is None
    session.commit.assert_called_once()


@pytest.mark.parametrize("source,target,message", [
    (group(1), group(1), "itself"),
    (group(1, archived="2026-01-01"), group(2), "archived"),
    (group(1), group(2, archived="2026-01-01"), "archived"),
    (group(1, kind="priority"), group(2), "only topics"),
    (group(1), group(2, kind="priority"), "only topics"),
])
def test_merge_rejects_invalid_pairs_without_touching_data(source, target, message):
    session = MagicMock()
    with pytest.raises(ValueError, match=message):
        service.merge_groups(session, source, target)
    session.execute.assert_not_called()
    session.commit.assert_not_called()


@pytest.fixture
def client(monkeypatch):
    app = Flask(__name__)
    app.register_blueprint(feed_routes.bp)

    @app.before_request
    def auth():
        g.auth = SimpleNamespace(kind="user", user_id=1)

    session = MagicMock()
    groups = {1: group(1), 2: group(2, "Agenci AI")}
    session.get.side_effect = lambda _model, group_id: groups.get(group_id)
    monkeypatch.setattr(feed_routes, "get_scoped_session", lambda: session)
    monkeypatch.setattr(feed_routes, "group_to_dict", lambda row, _session=None: {"id": row.id, "name": row.name})
    return app.test_client(), session


def test_merge_route_returns_counts_and_both_groups(client, monkeypatch):
    http, _ = client
    monkeypatch.setattr(feed_routes, "merge_groups", lambda _session, source, target: {"documents": 3, "from": source.id, "to": target.id})
    response = http.post("/content_groups/1/merge", json={"target_id": 2})
    assert response.status_code == 200
    assert response.json == {"moved": {"documents": 3, "from": 1, "to": 2}, "source": {"id": 1, "name": "AI"}, "target": {"id": 2, "name": "Agenci AI"}}


def test_merge_route_validates_input(client, monkeypatch):
    http, session = client
    assert http.post("/content_groups/1/merge", json={}).status_code == 400
    assert http.post("/content_groups/1/merge", json={"target_id": "2"}).status_code == 400
    assert http.post("/content_groups/1/merge", json={"target_id": 99}).status_code == 404
    assert http.post("/content_groups/99/merge", json={"target_id": 2}).status_code == 404
    monkeypatch.setattr(feed_routes, "merge_groups", MagicMock(side_effect=ValueError("cannot merge a topic into itself")))
    response = http.post("/content_groups/1/merge", json={"target_id": 1})
    assert response.status_code == 400
    session.rollback.assert_called()


def test_renaming_an_archived_topic_is_a_conflict_not_a_server_error(client, monkeypatch):
    http, session = client
    session.get.side_effect = lambda _model, group_id: group(group_id, archived="2026-01-01")
    monkeypatch.setattr(feed_routes, "update_group", MagicMock(side_effect=RuntimeError("archived group cannot be edited")))
    assert http.patch("/content_groups/1", json={"name": "Nowa"}).status_code == 409
