"""HTTP contract of /ner_channel_glossary with the session replaced by a mock."""

import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("flask")

import flask
from sqlalchemy.exc import IntegrityError

from library import ner_channel_glossary_routes as routes
from library.db.models import NerChannelGlossaryEntry


@pytest.fixture
def api(monkeypatch):
    app = flask.Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(routes.bp)

    @app.before_request
    def auth():
        flask.g.auth = SimpleNamespace(kind="user", key_name="test-key")

    session = MagicMock()
    session.get.return_value = None
    monkeypatch.setattr(routes, "get_scoped_session", lambda: session)
    return app.test_client(), session


def stored(**overrides):
    values = dict(id=3, author="Kanał", canonical_name="Pete Hegseth", aliases=["He H"], fuzzy=True, note=None,
                  created_by="test-key", created_at=datetime.datetime(2026, 10, 18))
    values.update(overrides)
    return NerChannelGlossaryEntry(**values)


def test_add_with_explicit_author(api):
    client, session = api
    response = client.post("/ner_channel_glossary", json={
        "author": " Kanał ", "canonical_name": " Pete Hegseth ", "aliases": ["He H", "He H", "Hekset"]})
    assert response.status_code == 201
    entry = session.add.call_args.args[0]
    assert (entry.author, entry.canonical_name, entry.aliases, entry.fuzzy) == (
        "Kanał", "Pete Hegseth", ["He H", "Hekset"], True)
    session.commit.assert_called_once()


def test_author_is_taken_from_the_document(api):
    client, session = api
    session.get.return_value = SimpleNamespace(byline="Na Wschód od Bliskiego Wschodu")
    response = client.post("/ner_channel_glossary", json={"document_id": 10872, "canonical_name": "Marco Rubio"})
    assert response.status_code == 201
    assert session.add.call_args.args[0].author == "Na Wschód od Bliskiego Wschodu"


@pytest.mark.parametrize("body", [
    {"canonical_name": "Marco Rubio"},
    {"author": "K"},
    {"author": "K", "canonical_name": "x" * 201},
    {"author": "K", "canonical_name": "Marco Rubio", "aliases": "He H"},
    {"author": "K", "canonical_name": "Marco Rubio", "aliases": ["ab"]},
    {"author": "K", "canonical_name": "Marco Rubio", "fuzzy": "yes"},
])
def test_rejects_invalid_bodies(api, body):
    client, session = api
    assert client.post("/ner_channel_glossary", json=body).status_code == 400
    session.add.assert_not_called()


def test_duplicate_is_a_conflict(api):
    client, session = api
    session.commit.side_effect = IntegrityError("x", {}, Exception())
    response = client.post("/ner_channel_glossary", json={"author": "K", "canonical_name": "Marco Rubio"})
    assert response.status_code == 409
    session.rollback.assert_called_once()


def test_patch_updates_fields(api):
    client, session = api
    entry = stored()
    session.get.return_value = entry
    response = client.patch("/ner_channel_glossary/3", json={"aliases": ["Hekset"], "fuzzy": False, "note": "n"})
    assert response.status_code == 200
    assert (entry.aliases, entry.fuzzy, entry.note) == (["Hekset"], False, "n")


def test_patch_and_delete_unknown_entry(api):
    client, _ = api
    assert client.patch("/ner_channel_glossary/9", json={"fuzzy": True}).status_code == 404
    assert client.delete("/ner_channel_glossary/9").status_code == 404


def test_delete(api):
    client, session = api
    entry = stored()
    session.get.return_value = entry
    assert client.delete("/ner_channel_glossary/3").status_code == 200
    session.delete.assert_called_once_with(entry)


def test_list_returns_entries_and_authors(api):
    client, session = api
    session.scalars.side_effect = [SimpleNamespace(all=lambda: [stored()]), SimpleNamespace(all=lambda: ["Kanał"])]
    body = client.get("/ner_channel_glossary?author=kanał").get_json()
    assert body["authors"] == ["Kanał"]
    assert body["entries"][0]["canonical_name"] == "Pete Hegseth"
    assert body["entries"][0]["created_at"] == "2026-10-18T00:00:00"


def test_applications_need_a_document_id(api):
    client, _ = api
    assert client.get("/ner_channel_glossary/applications").status_code == 400
