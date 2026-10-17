"""HTTP contract of /ner_gazetteer with the session replaced by a mock."""

import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("flask")

import flask
from sqlalchemy.exc import IntegrityError

from library import ner_gazetteer_routes as routes
from library.db.models import NerGazetteerEntry


@pytest.fixture
def api(monkeypatch):
    app = flask.Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(routes.bp)

    @app.before_request
    def auth():
        flask.g.auth = SimpleNamespace(kind=flask.request.headers.get("X-Kind", "service"), key_name="test-key")

    session = MagicMock()
    session.get.return_value = None
    session.scalars.return_value.first.return_value = None
    monkeypatch.setattr(routes, "get_scoped_session", lambda: session)
    invalidate = MagicMock()
    monkeypatch.setattr(routes, "invalidate_cache", invalidate)
    return app.test_client(), session, invalidate


def city(**overrides):
    return {"kind": "city", "name_pl": "Teksas", "patterns": ["teksas*"], **overrides}


def stored(**overrides):
    values = dict(id=7, kind="city", name_pl="Teksas", patterns=["teksas*"], geocode_alias=None, note=None,
                  source_document_id=None, created_by="test-key", created_at=datetime.datetime(2026, 10, 17))
    values.update(overrides)
    return NerGazetteerEntry(**values)


@pytest.mark.parametrize("kind", ["user", "read_only", ""])
@pytest.mark.parametrize("method,path", [("post", "/ner_gazetteer"), ("patch", "/ner_gazetteer/7"),
                                         ("delete", "/ner_gazetteer/7")])
def test_writes_service_only(api, kind, method, path):
    client, session, invalidate = api
    assert getattr(client, method)(path, json=city(), headers={"X-Kind": kind}).status_code == 403
    session.add.assert_not_called()
    session.commit.assert_not_called()
    invalidate.assert_not_called()


def test_list_filters_by_kind_and_validates(api):
    client, session, _ = api
    session.scalars.return_value.all.return_value = [stored()]
    response = client.get("/ner_gazetteer?kind=city")
    assert response.status_code == 200
    assert response.get_json()["entries"][0]["name_pl"] == "Teksas"
    assert client.get("/ner_gazetteer?kind=nope").status_code == 400


def test_post_creates_and_invalidates(api):
    client, session, invalidate = api
    response = client.post("/ner_gazetteer", json=city(note="doc 10872", source_document_id=10872))
    assert response.status_code == 201
    added = session.add.call_args.args[0]
    assert added.name_pl == "Teksas"
    assert added.patterns == ["teksas*"]
    assert added.created_by == "test-key"
    assert added.source_document_id == 10872
    session.commit.assert_called_once()
    invalidate.assert_called_once()


@pytest.mark.parametrize("payload", [
    city(patterns=["a*"]), city(kind="nope"), city(name_pl=""), {"kind": "geocode_alias", "name_pl": "X"},
])
def test_post_validation_errors(api, payload):
    client, session, invalidate = api
    assert client.post("/ner_gazetteer", json=payload).status_code == 400
    session.add.assert_not_called()
    invalidate.assert_not_called()


def test_post_bad_body_and_source_id(api):
    client, _, _ = api
    assert client.post("/ner_gazetteer", data="x", content_type="application/json").status_code == 400
    assert client.post("/ner_gazetteer", json=city(source_document_id=-1)).status_code == 400
    assert client.post("/ner_gazetteer", json=city(note=5)).status_code == 400


def test_post_duplicate_conflict(api):
    client, session, invalidate = api
    session.scalars.return_value.first.return_value = 3
    assert client.post("/ner_gazetteer", json=city()).status_code == 409
    session.add.assert_not_called()
    invalidate.assert_not_called()


def test_post_race_integrity_error_is_conflict(api):
    client, session, invalidate = api
    session.commit.side_effect = IntegrityError("stmt", {}, Exception("dup"))
    assert client.post("/ner_gazetteer", json=city()).status_code == 409
    session.rollback.assert_called_once()
    invalidate.assert_not_called()


def test_patch_updates_validates_and_invalidates(api):
    client, session, invalidate = api
    entry = stored()
    session.get.return_value = entry
    response = client.patch("/ner_gazetteer/7", json={"patterns": ["teksas*", "texas*"], "note": "x"})
    assert response.status_code == 200
    assert entry.patterns == ["teksas*", "texas*"]
    assert entry.note == "x"
    invalidate.assert_called_once()


def test_patch_not_found_invalid_and_duplicate(api):
    client, session, invalidate = api
    assert client.patch("/ner_gazetteer/7", json={"note": "x"}).status_code == 404
    session.get.return_value = stored()
    assert client.patch("/ner_gazetteer/7", json={"patterns": ["a*"]}).status_code == 400
    session.scalars.return_value.first.return_value = 9
    assert client.patch("/ner_gazetteer/7", json={"name_pl": "Inny"}).status_code == 409
    invalidate.assert_not_called()


def test_delete(api):
    client, session, invalidate = api
    assert client.delete("/ner_gazetteer/7").status_code == 404
    session.get.return_value = stored()
    response = client.delete("/ner_gazetteer/7")
    assert response.status_code == 200
    assert response.get_json()["deleted_entry_id"] == 7
    session.delete.assert_called_once()
    invalidate.assert_called_once()
