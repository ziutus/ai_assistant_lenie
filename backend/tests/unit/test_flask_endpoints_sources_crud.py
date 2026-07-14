"""Unit tests for the /sources CRUD endpoints and the Source auto-create hook."""

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("flask")

API_HEADERS = {"x-api-key": "test-api-key"}


@pytest.fixture()
def client():
    """Flask test client with auth bypassed (same pattern as test_flask_endpoints_orm)."""
    import server
    server.app.config["TESTING"] = True
    with patch.object(server, "check_auth_header"):
        with server.app.test_client() as c:
            yield c


def _row(id_=1, name="own", description=None, url=None, is_active=True):
    row = MagicMock()
    row.id = id_
    row.name = name
    row.description = description
    row.url = url
    row.is_active = is_active
    return row


class TestSourcesAdd:
    def test_creates_source(self, client):
        session = MagicMock()
        with patch("server.get_scoped_session", return_value=session):
            resp = client.post("/sources", headers=API_HEADERS,
                               json={"name": " Nowy Newsletter ", "url": "https://x.example"})

        assert resp.status_code == 200
        source = resp.get_json()["source"]
        assert source["name"] == "Nowy Newsletter"
        assert source["source"] == "Nowy Newsletter"
        assert source["url"] == "https://x.example"
        assert source["is_active"] is True
        session.add.assert_called_once()
        session.commit.assert_called_once()

    def test_missing_name_is_400(self, client):
        session = MagicMock()
        with patch("server.get_scoped_session", return_value=session):
            resp = client.post("/sources", headers=API_HEADERS, json={"name": "   "})
        assert resp.status_code == 400
        session.add.assert_not_called()

    def test_duplicate_is_409(self, client):
        session = MagicMock()
        session.commit.side_effect = Exception("unique violation")
        with patch("server.get_scoped_session", return_value=session):
            resp = client.post("/sources", headers=API_HEADERS, json={"name": "own"})
        assert resp.status_code == 409
        session.rollback.assert_called_once()


class TestSourcesUpdate:
    def test_updates_fields(self, client):
        session = MagicMock()
        row = _row(id_=7, name="old-name")
        session.get.return_value = row
        session.execute.return_value.scalar_one.return_value = 42
        with patch("server.get_scoped_session", return_value=session):
            resp = client.patch("/sources/7", headers=API_HEADERS,
                                json={"name": "new-name", "description": "opis",
                                      "is_active": False})

        assert resp.status_code == 200
        assert row.name == "new-name"
        assert row.description == "opis"
        assert row.is_active is False
        assert resp.get_json()["source"]["count"] == 42
        session.commit.assert_called_once()

    def test_empty_name_is_400(self, client):
        session = MagicMock()
        session.get.return_value = _row()
        with patch("server.get_scoped_session", return_value=session):
            resp = client.patch("/sources/1", headers=API_HEADERS, json={"name": ""})
        assert resp.status_code == 400
        session.commit.assert_not_called()

    def test_missing_source_is_404(self, client):
        session = MagicMock()
        session.get.return_value = None
        with patch("server.get_scoped_session", return_value=session):
            resp = client.patch("/sources/999", headers=API_HEADERS, json={"name": "x"})
        assert resp.status_code == 404

    def test_duplicate_name_is_409(self, client):
        session = MagicMock()
        session.get.return_value = _row()
        session.commit.side_effect = Exception("unique violation")
        with patch("server.get_scoped_session", return_value=session):
            resp = client.patch("/sources/1", headers=API_HEADERS, json={"name": "taken"})
        assert resp.status_code == 409
        session.rollback.assert_called_once()


class TestSourcesDelete:
    def test_deletes_unused_source(self, client):
        session = MagicMock()
        session.get.return_value = _row(id_=3, name="unused")
        session.execute.return_value.scalar_one.return_value = 0
        with patch("server.get_scoped_session", return_value=session):
            resp = client.delete("/sources/3", headers=API_HEADERS)
        assert resp.status_code == 200
        assert resp.get_json()["deleted_id"] == 3
        session.delete.assert_called_once()

    def test_used_source_is_409(self, client):
        session = MagicMock()
        session.get.return_value = _row(name="own")
        session.execute.return_value.scalar_one.return_value = 12
        with patch("server.get_scoped_session", return_value=session):
            resp = client.delete("/sources/1", headers=API_HEADERS)
        assert resp.status_code == 409
        assert "12" in resp.get_json()["message"]
        session.delete.assert_not_called()

    def test_missing_source_is_404(self, client):
        session = MagicMock()
        session.get.return_value = None
        with patch("server.get_scoped_session", return_value=session):
            resp = client.delete("/sources/999", headers=API_HEADERS)
        assert resp.status_code == 404


class TestSourceEnsure:
    def test_returns_existing_row(self):
        from library.db.models import Source
        session = MagicMock()
        existing = MagicMock()
        session.execute.return_value.scalar_one_or_none.return_value = existing
        assert Source.ensure(session, "  own  ") is existing
        session.add.assert_not_called()

    def test_creates_missing_row(self):
        from library.db.models import Source
        session = MagicMock()
        session.execute.return_value.scalar_one_or_none.return_value = None
        row = Source.ensure(session, "nowe-zrodlo")
        assert row.name == "nowe-zrodlo"
        session.add.assert_called_once_with(row)

    def test_empty_name_returns_none(self):
        from library.db.models import Source
        session = MagicMock()
        assert Source.ensure(session, "   ") is None
        assert Source.ensure(session, None) is None
        session.add.assert_not_called()


class TestBeforeFlushHook:
    """The before_flush listener is called directly — no DB needed."""

    def _session(self, new=(), dirty=()):
        session = MagicMock()
        session.new = list(new)
        session.dirty = list(dirty)
        session.execute.return_value.scalar_one_or_none.return_value = None
        return session

    def test_auto_creates_source_for_new_document(self):
        from library.db import models
        doc = models.WebDocument(url="https://x", document_type="link", source="fresh")
        session = self._session(new=[doc])
        models._ensure_document_sources_exist(session, None, None)
        added = session.add.call_args[0][0]
        assert isinstance(added, models.Source)
        assert added.name == "fresh"

    def test_normalizes_whitespace_and_empty(self):
        from library.db import models
        doc = models.WebDocument(url="https://x", document_type="link", source="  own  ")
        blank = models.WebDocument(url="https://y", document_type="link", source="   ")
        session = self._session(new=[doc, blank])
        models._ensure_document_sources_exist(session, None, None)
        assert doc.source == "own"
        assert blank.source is None
        added = session.add.call_args[0][0]
        assert added.name == "own"
        assert session.add.call_count == 1

    def test_dedupes_names_within_one_flush(self):
        from library.db import models
        docs = [models.WebDocument(url=f"https://x{i}", document_type="link", source="feed")
                for i in range(3)]
        session = self._session(new=docs)
        models._ensure_document_sources_exist(session, None, None)
        assert session.add.call_count == 1

    def test_ignores_documents_without_source(self):
        from library.db import models
        doc = models.WebDocument(url="https://x", document_type="link")
        session = self._session(new=[doc])
        models._ensure_document_sources_exist(session, None, None)
        session.add.assert_not_called()
        assert doc.source is None
