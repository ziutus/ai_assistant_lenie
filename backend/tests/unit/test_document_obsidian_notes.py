"""Unit tests for GET /document/<id>/obsidian_notes (chunk_review_routes.py).

obsidian_note_paths entries are not consistently vault-root-relative --
older data (written by the /lenie-obsidian-note skill before this was
standardized) omits the `02-wiedza/` prefix that obsidian_reimport_service.py
always includes in the reimported Document.url. Regression coverage for the
02-wiedza/ fallback lookup in document_obsidian_notes().
"""

from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")
flask = pytest.importorskip("flask")

from library import chunk_review_routes as cr  # noqa: E402
from library.db.models import Document  # noqa: E402


def _make_doc(doc_id: int, obsidian_note_paths: list[str]) -> Document:
    doc = MagicMock(spec=Document)
    doc.id = doc_id
    doc.obsidian_note_paths = obsidian_note_paths
    return doc


def _make_note(note_id: int, title: str, url: str) -> Document:
    note = MagicMock(spec=Document)
    note.id = note_id
    note.title = title
    note.url = url
    note.text_md = f"treść {title}"
    note.text = None
    return note


class TestDocumentObsidianNotes:
    @pytest.fixture
    def app(self):
        app = flask.Flask(__name__)
        app.register_blueprint(cr.bp)
        return app

    def test_missing_prefix_still_resolves_via_02_wiedza_fallback(self, app, monkeypatch):
        """Regression: /read/9394's obsidian_note_paths ("Geopolityka i
        polityka/.../Sudan.md") lack the 02-wiedza/ prefix that the
        reimported note's Document.url carries -- the reader's obsidian
        preview panel must still find the match."""
        doc = _make_doc(9394, ["Geopolityka i polityka/Kraje/Afryka/Sudan.md"])
        note = _make_note(10058, "Sudan", "obsidian://02-wiedza/Geopolityka i polityka/Kraje/Afryka/Sudan.md")

        session = MagicMock()
        session.get.side_effect = lambda model, pk: doc if model is Document and pk == doc.id else None
        session.query.return_value.filter.return_value.all.return_value = [note]
        monkeypatch.setattr(cr, "get_scoped_session", lambda: session)

        resp = app.test_client().get("/document/9394/obsidian_notes")
        data = resp.get_json()

        assert resp.status_code == 200
        assert data["notes"] == [{
            "path": "Geopolityka i polityka/Kraje/Afryka/Sudan.md",
            "id": 10058,
            "title": "Sudan",
            "text": "treść Sudan",
        }]

    def test_path_already_carrying_the_prefix_still_matches_directly(self, app, monkeypatch):
        doc = _make_doc(101, ["02-wiedza/Informatyka/linux.md"])
        note = _make_note(202, "Linux", "obsidian://02-wiedza/Informatyka/linux.md")

        session = MagicMock()
        session.get.side_effect = lambda model, pk: doc if model is Document and pk == doc.id else None
        session.query.return_value.filter.return_value.all.return_value = [note]
        monkeypatch.setattr(cr, "get_scoped_session", lambda: session)

        resp = app.test_client().get("/document/101/obsidian_notes")
        data = resp.get_json()

        assert data["notes"][0]["id"] == 202

    def test_no_matching_imported_note_returns_empty_list(self, app, monkeypatch):
        doc = _make_doc(303, ["Geopolityka i polityka/Kraje/Nieznany.md"])

        session = MagicMock()
        session.get.side_effect = lambda model, pk: doc if model is Document and pk == doc.id else None
        session.query.return_value.filter.return_value.all.return_value = []
        monkeypatch.setattr(cr, "get_scoped_session", lambda: session)

        resp = app.test_client().get("/document/303/obsidian_notes")
        data = resp.get_json()

        assert data["notes"] == []

    def test_no_paths_skips_the_query_entirely(self, app, monkeypatch):
        doc = _make_doc(404, [])

        session = MagicMock()
        session.get.side_effect = lambda model, pk: doc if model is Document and pk == doc.id else None
        monkeypatch.setattr(cr, "get_scoped_session", lambda: session)

        resp = app.test_client().get("/document/404/obsidian_notes")
        data = resp.get_json()

        assert data["notes"] == []
        session.query.assert_not_called()
