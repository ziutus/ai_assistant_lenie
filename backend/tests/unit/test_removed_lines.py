"""Unit tests for removed-lines tracking (document_removed_lines).

Lines removed during manual chunk-review cleanup are persisted as training
data for improving article_cleaner.py / site_rules.json. Covers the ORM model
and the pure helpers in chunk_review_routes.py.
"""

from unittest.mock import MagicMock

import pytest

sa = pytest.importorskip("sqlalchemy")
pytest.importorskip("flask")

from sqlalchemy import inspect  # noqa: E402

from library.chunk_review_routes import _chunk_to_dict, _log_removed_lines, _removed_lines_diff  # noqa: E402
from library.db.models import DocumentRemovedLine  # noqa: E402


def test_chunk_payload_marks_photo_caption_candidates():
    chunk = type("Chunk", (), {
        "id": 1, "position": 1, "type": "TEMAT", "topic": None,
        "original_text": "Treść artykułu.\nFot. Jan Kowalski / PAP\nDalsza treść.",
        "corrected_text": None, "summary": None, "seg_start": None, "seg_end": None,
        "rewrite_ratio": None, "status": "pending", "split_at_seg": None,
        "split_first_type": None, "split_second_type": None,
        "obsidian_note_paths": [],
    })()

    payload = _chunk_to_dict(chunk)

    assert payload["photo_caption_line_indices"] == [1]
    assert "Fot. Jan Kowalski / PAP" in payload["original_text"]


# ---------------------------------------------------------------------------
# ORM model
# ---------------------------------------------------------------------------


class TestDocumentRemovedLineModel:
    EXPECTED_COLUMNS = {
        "id", "document_id", "run_id", "chunk_id", "source", "line_text",
        "review_status", "reviewed_at", "review_note", "rule_reference", "created_at",
    }

    def test_tablename(self):
        assert DocumentRemovedLine.__tablename__ == "document_removed_lines"

    def test_columns(self):
        mapper = inspect(DocumentRemovedLine).mapper
        assert {col.key for col in mapper.columns} == self.EXPECTED_COLUMNS

    def test_document_fk_cascade(self):
        col = inspect(DocumentRemovedLine).mapper.columns["document_id"]
        fk = next(iter(col.foreign_keys))
        assert fk.column.table.name == "web_documents"
        assert fk.ondelete == "CASCADE"
        assert col.nullable is False

    def test_run_and_chunk_fks_set_null(self):
        """Rows must survive run/chunk deletion — FKs are SET NULL, nullable."""
        mapper = inspect(DocumentRemovedLine).mapper
        for name, table in (("run_id", "document_analysis_runs"),
                            ("chunk_id", "document_chunks")):
            col = mapper.columns[name]
            fk = next(iter(col.foreign_keys))
            assert fk.column.table.name == table
            assert fk.ondelete == "SET NULL"
            assert col.nullable is True


# ---------------------------------------------------------------------------
# _removed_lines_diff
# ---------------------------------------------------------------------------


class TestRemovedLinesDiff:
    def test_removed_lines_reported_in_order(self):
        old = "keep one\nAD BANNER\nkeep two\nSubscribe now\nkeep three"
        new = "keep one\nkeep two\nkeep three"
        assert _removed_lines_diff(old, new) == ["AD BANNER", "Subscribe now"]

    def test_no_removal_returns_empty(self):
        text = "line a\nline b"
        assert _removed_lines_diff(text, text) == []

    def test_whitespace_only_lines_ignored(self):
        old = "keep\n   \n\t\nnoise"
        new = "keep"
        assert _removed_lines_diff(old, new) == ["noise"]

    def test_comparison_is_stripped(self):
        old = "  keep  \n  noise  "
        new = "keep"
        assert _removed_lines_diff(old, new) == ["noise"]

    def test_duplicate_removed_line_reported_once(self):
        old = "Udostępnij\nkeep\nUdostępnij"
        new = "keep"
        assert _removed_lines_diff(old, new) == ["Udostępnij"]

    def test_line_still_present_elsewhere_not_reported(self):
        # One of two occurrences removed — line still in new text, so not reported
        old = "Udostępnij\nkeep\nUdostępnij"
        new = "keep\nUdostępnij"
        assert _removed_lines_diff(old, new) == []

    def test_added_lines_do_not_matter(self):
        old = "keep"
        new = "keep\nbrand new line"
        assert _removed_lines_diff(old, new) == []


# ---------------------------------------------------------------------------
# _log_removed_lines
# ---------------------------------------------------------------------------


class TestLogRemovedLines:
    def _added_rows(self, session):
        return [call.args[0] for call in session.add.call_args_list]

    def test_adds_one_row_per_line(self):
        session = MagicMock(spec=["add"])
        count = _log_removed_lines(
            session, document_id=9202, run_id=17, chunk_id=101,
            lines=["Skróć artykuł", "Udostępnij"], source="manual",
        )

        assert count == 2
        rows = self._added_rows(session)
        assert [r.line_text for r in rows] == ["Skróć artykuł", "Udostępnij"]
        for r in rows:
            assert isinstance(r, DocumentRemovedLine)
            assert (r.document_id, r.run_id, r.chunk_id, r.source) == (9202, 17, 101, "manual")
            assert r.review_status is None  # database server default: pending

    def test_skips_empty_and_whitespace_lines(self):
        session = MagicMock(spec=["add"])
        count = _log_removed_lines(
            session, document_id=1, run_id=None, chunk_id=None,
            lines=["", "   ", "real line"], source="manual",
        )

        assert count == 1
        assert self._added_rows(session)[0].line_text == "real line"

    def test_strips_stored_text_and_allows_null_run_chunk(self):
        session = MagicMock(spec=["add"])
        _log_removed_lines(
            session, document_id=1, run_id=None, chunk_id=None,
            lines=["  block text  "], source="szum_chunk",
        )

        row = self._added_rows(session)[0]
        assert row.line_text == "block text"
        assert row.run_id is None
        assert row.chunk_id is None
        assert row.source == "szum_chunk"

    def test_does_not_commit(self):
        """Caller owns the transaction — helper must only queue adds."""
        session = MagicMock(spec=["add", "commit"])
        _log_removed_lines(
            session, document_id=1, run_id=2, chunk_id=3,
            lines=["x"], source="manual",
        )
        session.commit.assert_not_called()
