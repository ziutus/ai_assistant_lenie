"""Unit tests for the reader's whole-document-chapter fallback.

A document with real text but neither markdown H1/H2 headers nor a
chunk-analysis run used to be unreadable: GET /document/<id>/chapters
returned an empty list and GET /document/<id>/chapter/1 hard-failed with
"Document has no detectable chapters". This is the common case for short
Obsidian notes (obsidian_reimport_service.py never runs chunk analysis on
them, and most personal notes have no headers) -- see /read/9766.
"""

from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")
flask = pytest.importorskip("flask")

from library import chunk_review_routes as cr  # noqa: E402
from library.db.models import Document  # noqa: E402

NOTE_TEXT = (
    "---\ntags:\n  - wiedza/informatyka\n---\n\n"
    "[[Linux]]\n\nTreść notatki bez żadnych nagłówków markdown, "
    "wystarczająco długa by przejść próg _extract_text (>100 znaków)."
)

# Under the old fixed 100-char floor in _extract_text(), a stub this short
# came back as "" (empty) and never reached _whole_document_chapter at all --
# GET /document/<id>/chapters returned an empty chapter list and
# GET /document/<id>/chapter/1 failed with "no detectable chapters", even
# though the note plainly has real (just short) content. See /read/9923.
SHORT_NOTE_TEXT = "[[Linux|Linuksowe]] narzędzia, z którymi można pracować w konsoli w shell [[bash]], [[zsh]] itp."
assert len(SHORT_NOTE_TEXT) < 100


def _make_obsidian_note(doc_id=9766, text_md=NOTE_TEXT) -> Document:
    doc = MagicMock(spec=Document)
    doc.id = doc_id
    doc.document_type = "obsidian_note"
    doc.text = None
    doc.text_md = text_md
    doc.text_raw = None
    doc.title = "Linux i BIOS"
    doc.url = "obsidian://02-wiedza/Informatyka/linux-i-bios.md"
    doc.tags = ""
    doc.quality = None
    doc.published_on = None
    doc.ingested_at = None
    doc.obsidian_note_paths = []
    return doc


class TestWholeDocumentChapter:
    def test_covers_the_full_text(self):
        chapters = cr._whole_document_chapter(NOTE_TEXT)
        assert chapters == [{
            "position": 1, "level": 1, "title": "(całość)",
            "char_start": 0, "char_end": len(NOTE_TEXT), "length": len(NOTE_TEXT),
        }]


class TestResolveChapterText:
    def test_headerless_note_without_analysis_run_reads_as_one_chapter(self, monkeypatch):
        session = MagicMock()
        monkeypatch.setattr(cr, "_latest_run_for_document", lambda _session, _doc_id: None)
        doc = _make_obsidian_note()

        result, error = cr._resolve_chapter_text(session, doc, 1)

        assert error is None
        text, title, chapter_total = result
        assert text == NOTE_TEXT
        assert title == "(całość)"
        assert chapter_total == 1

    def test_position_out_of_range_for_the_single_chapter(self, monkeypatch):
        session = MagicMock()
        monkeypatch.setattr(cr, "_latest_run_for_document", lambda _session, _doc_id: None)
        doc = _make_obsidian_note()

        result, error = cr._resolve_chapter_text(session, doc, 2)

        assert result is None
        assert error == "position 2 out of range (1..1)"

    def test_short_note_under_100_chars_still_reads_as_one_chapter(self, monkeypatch):
        session = MagicMock()
        monkeypatch.setattr(cr, "_latest_run_for_document", lambda _session, _doc_id: None)
        doc = _make_obsidian_note(text_md=SHORT_NOTE_TEXT)

        result, error = cr._resolve_chapter_text(session, doc, 1)

        assert error is None
        text, title, chapter_total = result
        assert text == SHORT_NOTE_TEXT
        assert title == "(całość)"
        assert chapter_total == 1


class TestDocumentChaptersEndpoint:
    @pytest.fixture
    def client(self, monkeypatch):
        doc = _make_obsidian_note()
        session = MagicMock()
        session.get.side_effect = lambda model, pk: doc if model is Document and pk == doc.id else None
        # document_chapters() separately looks up a whole-document run for its
        # "synthesis" field -- none exists here, keep it out of the JSON body.
        session.scalars.return_value.first.return_value = None
        monkeypatch.setattr(cr, "get_scoped_session", lambda: session)
        monkeypatch.setattr(cr, "_latest_run_for_document", lambda _session, _doc_id: None)

        app = flask.Flask(__name__)
        app.register_blueprint(cr.bp)
        return app.test_client()

    def test_returns_one_whole_document_chapter(self, client):
        response = client.get("/document/9766/chapters")

        assert response.status_code == 200
        body = response.get_json()
        assert body["chapters"] == [{
            "position": 1, "level": 1, "title": "(całość)",
            "char_start": 0, "char_end": len(NOTE_TEXT), "length": len(NOTE_TEXT),
        }]
        assert body["chapter_source"] == "whole_document"


class TestDocumentChaptersEndpointShortNote:
    """Same as TestDocumentChaptersEndpoint but with a <100-char note (/read/9923 case)."""

    @pytest.fixture
    def client(self, monkeypatch):
        doc = _make_obsidian_note(doc_id=9923, text_md=SHORT_NOTE_TEXT)
        session = MagicMock()
        session.get.side_effect = lambda model, pk: doc if model is Document and pk == doc.id else None
        session.scalars.return_value.first.return_value = None
        monkeypatch.setattr(cr, "get_scoped_session", lambda: session)
        monkeypatch.setattr(cr, "_latest_run_for_document", lambda _session, _doc_id: None)

        app = flask.Flask(__name__)
        app.register_blueprint(cr.bp)
        return app.test_client()

    def test_short_note_does_not_report_no_usable_text(self, client):
        response = client.get("/document/9923/chapters")

        assert response.status_code == 200
        body = response.get_json()
        assert body["status"] == "success"
        assert body["chapter_source"] == "whole_document"
        assert body["chapters"] == [{
            "position": 1, "level": 1, "title": "(całość)",
            "char_start": 0, "char_end": len(SHORT_NOTE_TEXT), "length": len(SHORT_NOTE_TEXT),
        }]
