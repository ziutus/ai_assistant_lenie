"""Unit tests for DELETE /chunk/<id> (chunk_review_routes.delete_noise_chunk).

Covers the szum_chunk logging added so a deleted REKLAMA/SZUM chunk's
original_text survives as DocumentRemovedLine training data instead of
vanishing with the row. LLM/DB access is mocked.
"""

from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")
flask = pytest.importorskip("flask")

from library import chunk_review_routes as crr  # noqa: E402
from library.db.models import DocumentChunk, DocumentRemovedLine  # noqa: E402


def _make_chunk(**kw) -> DocumentChunk:
    defaults = dict(
        id=201, run_id=1, document_id=77, position=3, type="SZUM", topic=None,
        original_text="Julia Lachowicz-Nowińska", corrected_text=None, summary=None,
        seg_start=None, seg_end=None, rewrite_ratio=None, status="pending",
        split_at_seg=None, split_first_type=None, split_second_type=None,
        obsidian_note_paths=[],
    )
    defaults.update(kw)
    return DocumentChunk(**defaults)


class _ScalarsResult:
    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items


@pytest.fixture
def fake_session(monkeypatch):
    session = MagicMock()
    chunk = _make_chunk()
    session.get.side_effect = lambda model, pk: chunk if model is DocumentChunk and pk == chunk.id else None
    session.scalars.side_effect = lambda *_a, **_kw: _ScalarsResult([])
    monkeypatch.setattr(crr, "get_scoped_session", lambda: session)
    return session, chunk


@pytest.fixture
def client():
    app = flask.Flask(__name__)
    app.register_blueprint(crr.bp)
    return app.test_client()


class TestDeleteNoiseChunkLogsRemovedLine:
    def test_deletes_chunk_and_logs_full_text_as_szum_chunk(self, client, fake_session):
        session, chunk = fake_session
        r = client.delete("/chunk/201")
        assert r.get_json()["status"] == "success"

        session.delete.assert_called_once_with(chunk)
        added = [c.args[0] for c in session.add.call_args_list]
        removed_lines = [a for a in added if isinstance(a, DocumentRemovedLine)]
        assert len(removed_lines) == 1
        row = removed_lines[0]
        assert row.source == "szum_chunk"
        assert row.document_id == chunk.document_id
        assert row.run_id == chunk.run_id
        assert row.chunk_id == chunk.id
        assert row.line_text == "Julia Lachowicz-Nowińska"

    def test_logging_happens_before_delete(self, client, fake_session):
        # _log_removed_lines must run while the chunk row still exists (before
        # session.delete), otherwise the FK it references would already be gone.
        session, _chunk = fake_session
        calls = []
        session.add.side_effect = lambda *_a, **_kw: calls.append("add")
        session.delete.side_effect = lambda *_a, **_kw: calls.append("delete")
        client.delete("/chunk/201")
        assert calls == ["add", "delete"]

    def test_temat_chunk_cannot_be_deleted_and_nothing_logged(self, client, monkeypatch):
        session = MagicMock()
        chunk = _make_chunk(type="TEMAT")
        session.get.side_effect = lambda model, pk: chunk if model is DocumentChunk and pk == chunk.id else None
        monkeypatch.setattr(crr, "get_scoped_session", lambda: session)

        r = client.delete("/chunk/201")
        assert r.status_code == 400
        session.delete.assert_not_called()
        session.add.assert_not_called()

    def test_missing_chunk_returns_404(self, client, monkeypatch):
        session = MagicMock()
        session.get.return_value = None
        monkeypatch.setattr(crr, "get_scoped_session", lambda: session)
        r = client.delete("/chunk/999")
        assert r.status_code == 404
