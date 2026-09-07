"""Unit tests for the "Obsidian note not needed" reviewer flag.

Covers PATCH /chunk/<id> {"obsidian_note_not_needed": bool} and
POST /analysis_run/<id>/mark_notes_not_needed. DB access is mocked.
"""

from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")
flask = pytest.importorskip("flask")

from library import chunk_review_routes as crr  # noqa: E402
from library.db.models import DocumentAnalysisRun, DocumentChunk  # noqa: E402


def _make_chunk(**kw) -> DocumentChunk:
    defaults = dict(
        id=201, run_id=1, document_id=77, position=1, type="TEMAT", topic=None,
        original_text="body", corrected_text=None, summary=None,
        seg_start=None, seg_end=None, rewrite_ratio=None, status="approved",
        split_at_seg=None, split_first_type=None, split_second_type=None,
        obsidian_note_paths=[], obsidian_note_not_needed=False,
    )
    defaults.update(kw)
    return DocumentChunk(**defaults)


class _ScalarsResult:
    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items


@pytest.fixture
def client():
    app = flask.Flask(__name__)
    app.register_blueprint(crr.bp)
    return app.test_client()


class TestPatchChunkNoteNotNeeded:
    def test_sets_flag(self, client, monkeypatch):
        session = MagicMock()
        chunk = _make_chunk()
        session.get.side_effect = lambda model, pk: chunk if model is DocumentChunk else None
        monkeypatch.setattr(crr, "get_scoped_session", lambda: session)

        r = client.patch("/chunk/201", json={"obsidian_note_not_needed": True})

        assert r.get_json()["status"] == "success"
        assert chunk.obsidian_note_not_needed is True
        session.commit.assert_called_once()
        assert r.get_json()["chunk"]["obsidian_note_not_needed"] is True

    def test_rejects_non_boolean(self, client, monkeypatch):
        session = MagicMock()
        chunk = _make_chunk()
        session.get.side_effect = lambda model, pk: chunk if model is DocumentChunk else None
        monkeypatch.setattr(crr, "get_scoped_session", lambda: session)

        r = client.patch("/chunk/201", json={"obsidian_note_not_needed": "yes"})

        assert r.status_code == 400
        session.commit.assert_not_called()


class TestBulkMarkNotesNotNeeded:
    def _setup(self, monkeypatch, chunks):
        session = MagicMock()
        run = DocumentAnalysisRun(id=1, document_id=77, model="Bielik", mode="article", status="reviewed")
        session.get.side_effect = lambda model, pk: run if model is DocumentAnalysisRun else None
        session.scalars.side_effect = lambda *_a, **_kw: _ScalarsResult(chunks)
        monkeypatch.setattr(crr, "get_scoped_session", lambda: session)
        return session

    def test_flags_only_chunks_without_a_note(self, client, monkeypatch):
        no_note = _make_chunk(id=1, position=1)
        with_note = _make_chunk(id=2, position=2, obsidian_note_paths=["Vault/Note.md"])
        session = self._setup(monkeypatch, [no_note, with_note])

        r = client.post("/analysis_run/1/mark_notes_not_needed", json={})

        body = r.get_json()
        assert body["status"] == "success"
        assert body["chunks_changed"] == 1
        assert no_note.obsidian_note_not_needed is True
        assert with_note.obsidian_note_not_needed is False
        session.commit.assert_called_once()

    def test_value_false_clears_the_flag(self, client, monkeypatch):
        flagged = _make_chunk(id=1, obsidian_note_not_needed=True)
        self._setup(monkeypatch, [flagged])

        r = client.post("/analysis_run/1/mark_notes_not_needed", json={"value": False})

        assert r.get_json()["chunks_changed"] == 1
        assert flagged.obsidian_note_not_needed is False

    def test_no_change_does_not_commit(self, client, monkeypatch):
        already = _make_chunk(id=1, obsidian_note_not_needed=True)
        session = self._setup(monkeypatch, [already])

        r = client.post("/analysis_run/1/mark_notes_not_needed", json={"value": True})

        assert r.get_json()["chunks_changed"] == 0
        session.commit.assert_not_called()

    def test_rejects_non_boolean_value(self, client, monkeypatch):
        self._setup(monkeypatch, [_make_chunk()])

        r = client.post("/analysis_run/1/mark_notes_not_needed", json={"value": 1})

        assert r.status_code == 400
