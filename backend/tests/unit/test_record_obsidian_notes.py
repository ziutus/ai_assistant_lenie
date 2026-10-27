"""Unit tests for POST /document/<id>/obsidian_notes (chunk_review_routes.py).

Records vault note paths on a document (and optionally on TEMAT chunks of one of
its analysis runs) in one transaction -- the sync step of the Lenie MCP server /
/lenie-obsidian-note workflow.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")
flask = pytest.importorskip("flask")

from library import chunk_review_routes as cr  # noqa: E402
from library.db.models import Document, DocumentAnalysisRun  # noqa: E402

NOTE = "02-wiedza/Technologia/Lokalne LLM.md"


def _doc(paths=None, reviewed_at=None):
    return SimpleNamespace(id=11176, obsidian_note_paths=paths or [], reviewed_at=reviewed_at)


def _chunk(position, paths=None):
    return SimpleNamespace(position=position, type="TEMAT", obsidian_note_paths=paths or [], updated_at=None)


@pytest.fixture
def app():
    app = flask.Flask(__name__)
    app.register_blueprint(cr.bp)
    return app


def _setup(monkeypatch, doc, run=None, chunks=()):
    session = MagicMock()

    def get(model, pk):
        if model is Document:
            return doc if pk == doc.id else None
        if model is DocumentAnalysisRun:
            return run if run is not None and pk == run.id else None
        return None

    session.get.side_effect = get
    session.scalars.return_value.all.return_value = list(chunks)
    monkeypatch.setattr(cr, "get_scoped_session", lambda: session)
    return session


def _post(app, body, doc_id=11176):
    return app.test_client().post(f"/document/{doc_id}/obsidian_notes", json=body)


def test_records_document_path_and_sets_reviewed_at(app, monkeypatch):
    doc = _doc()
    session = _setup(monkeypatch, doc)
    resp = _post(app, {"notes": [{"path": NOTE}]})
    data = resp.get_json()
    assert resp.status_code == 200
    assert doc.obsidian_note_paths == [NOTE]
    assert doc.reviewed_at is not None
    assert data["chunks_changed"] == 0
    session.commit.assert_called_once()


def test_does_not_overwrite_reviewed_at_and_dedupes(app, monkeypatch):
    stamp = SimpleNamespace(isoformat=lambda: "2026-01-01T00:00:00")
    doc = _doc(paths=[NOTE], reviewed_at=stamp)
    _setup(monkeypatch, doc)
    resp = _post(app, {"notes": [{"path": NOTE}]})
    assert resp.status_code == 200
    assert doc.obsidian_note_paths == [NOTE]
    assert doc.reviewed_at is stamp


def test_maps_note_to_chunks_of_run(app, monkeypatch):
    doc = _doc()
    run = SimpleNamespace(id=253, document_id=11176, status="reviewed")
    chunks = [_chunk(0), _chunk(1), _chunk(2, paths=[NOTE])]
    _setup(monkeypatch, doc, run, chunks)
    resp = _post(app, {"run_id": 253, "notes": [{"path": NOTE, "chunk_positions": [0, 1, 2]}]})
    data = resp.get_json()
    assert resp.status_code == 200
    assert [c.obsidian_note_paths for c in chunks] == [[NOTE], [NOTE], [NOTE]]
    assert data["chunks_changed"] == 2  # chunk 2 already had it


def test_unknown_position_rejects_whole_request(app, monkeypatch):
    doc = _doc()
    run = SimpleNamespace(id=253, document_id=11176, status="reviewed")
    session = _setup(monkeypatch, doc, run, [_chunk(0)])
    resp = _post(app, {"run_id": 253, "notes": [{"path": NOTE, "chunk_positions": [0, 9]}]})
    assert resp.status_code == 400
    assert doc.obsidian_note_paths == []
    session.commit.assert_not_called()


@pytest.mark.parametrize("status,other_doc", [("superseded", False), ("reviewed", True)])
def test_rejects_superseded_or_foreign_run(app, monkeypatch, status, other_doc):
    doc = _doc()
    run = SimpleNamespace(id=253, document_id=1 if other_doc else 11176, status=status)
    session = _setup(monkeypatch, doc, run, [_chunk(0)])
    resp = _post(app, {"run_id": 253, "notes": [{"path": NOTE, "chunk_positions": [0]}]})
    assert resp.status_code == 400
    session.commit.assert_not_called()


@pytest.mark.parametrize("path", ["../x.md", "/abs/x.md", "C:/x.md", "a/../b.md", "note.txt", "", None, 5])
def test_rejects_bad_paths(app, monkeypatch, path):
    _setup(monkeypatch, _doc())
    assert _post(app, {"notes": [{"path": path}]}).status_code == 400


def test_chunk_positions_require_run_id(app, monkeypatch):
    _setup(monkeypatch, _doc())
    assert _post(app, {"notes": [{"path": NOTE, "chunk_positions": [0]}]}).status_code == 400


def test_missing_document_is_404(app, monkeypatch):
    _setup(monkeypatch, _doc())
    assert _post(app, {"notes": [{"path": NOTE}]}, doc_id=999).status_code == 404


def test_db_error_rolls_back(app, monkeypatch):
    session = _setup(monkeypatch, _doc())
    session.commit.side_effect = RuntimeError("boom")
    resp = _post(app, {"notes": [{"path": NOTE}]})
    assert resp.status_code == 500
    session.rollback.assert_called_once()
