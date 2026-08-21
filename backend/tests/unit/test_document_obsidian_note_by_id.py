"""Unit tests for GET /document/<id>/obsidian_note (chunk_review_routes.py).

Backs the reader's Obsidian panel in-panel wikilink browsing: following a
[[wikilink]] inside a previewed note fetches the target note by its own
document id, independent of any host document/chapter -- distinct from
GET /document/<id>/obsidian_notes (test_document_obsidian_notes.py), which
resolves notes linked to a *host* document/chapter.
"""

from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")
flask = pytest.importorskip("flask")

from library import chunk_review_routes as cr  # noqa: E402
from library.db.models import Document  # noqa: E402


def _make_note(note_id: int, title: str, url: str, text_md: str | None = None) -> Document:
    note = MagicMock(spec=Document)
    note.id = note_id
    note.document_type = "obsidian_note"
    note.title = title
    note.url = url
    note.text_md = text_md if text_md is not None else f"treść {title}"
    note.text = None
    return note


class TestDocumentObsidianNoteById:
    @pytest.fixture
    def app(self):
        app = flask.Flask(__name__)
        app.register_blueprint(cr.bp)
        return app

    def test_returns_note_content_with_resolved_wiki_links(self, app, monkeypatch):
        note = _make_note(
            20001, "Bliski Wschod", "obsidian://02-wiedza/Geopolityka i polityka/Bliski Wschod.md",
            text_md="Szczegóły: [[Sudan#Wojna domowa]]",
        )
        session = MagicMock()
        session.get.side_effect = lambda model, pk: note if model is Document and pk == note.id else None
        session.query.return_value.filter.return_value.in_.return_value = None
        session.query.return_value.filter.return_value.all.return_value = [(10058, "Sudan")]
        monkeypatch.setattr(cr, "get_scoped_session", lambda: session)

        resp = app.test_client().get("/document/20001/obsidian_note")
        data = resp.get_json()

        assert resp.status_code == 200
        assert data["note"] == {
            "path": "02-wiedza/Geopolityka i polityka/Bliski Wschod.md",
            "id": 20001,
            "title": "Bliski Wschod",
            "text": "Szczegóły: [[Sudan#Wojna domowa]]",
            "wiki_links": {"sudan": 10058},
        }

    def test_missing_document_returns_404(self, app, monkeypatch):
        session = MagicMock()
        session.get.return_value = None
        monkeypatch.setattr(cr, "get_scoped_session", lambda: session)

        resp = app.test_client().get("/document/999999/obsidian_note")

        assert resp.status_code == 404

    def test_non_obsidian_note_document_returns_404(self, app, monkeypatch):
        doc = MagicMock(spec=Document)
        doc.id = 42
        doc.document_type = "webpage"
        session = MagicMock()
        session.get.side_effect = lambda model, pk: doc if model is Document and pk == doc.id else None
        monkeypatch.setattr(cr, "get_scoped_session", lambda: session)

        resp = app.test_client().get("/document/42/obsidian_note")

        assert resp.status_code == 404
