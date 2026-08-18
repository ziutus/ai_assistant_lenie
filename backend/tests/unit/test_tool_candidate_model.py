"""Metadata tests for the ToolCandidate model (Epic 43, Story 43.1).

The table is created by a raw-SQL Alembic migration (0b1c2d3e4f5a); this test
pins the ORM mapping to the same shape so a drift between models.py and the
migration is caught without a database.
"""

import pytest

pytest.importorskip("sqlalchemy")

import sqlalchemy as sa

from library.db.models import ToolCandidate


def check_constraint_names(table):
    return {c.name for c in table.constraints if isinstance(c, sa.CheckConstraint)}


class TestToolCandidate:
    def test_table_name(self):
        assert ToolCandidate.__table__.name == "tool_candidates"

    def test_required_columns_not_nullable(self):
        table = ToolCandidate.__table__
        for column in ("name", "status", "source_document_id", "detected_by", "created_at"):
            assert table.c[column].nullable is False

    def test_optional_columns_nullable(self):
        table = ToolCandidate.__table__
        for column in ("context_snippet", "reviewed_at"):
            assert table.c[column].nullable is True

    def test_status_default(self):
        assert str(ToolCandidate.__table__.c.status.server_default.arg) == "'pending'"

    def test_detected_by_default(self):
        assert str(ToolCandidate.__table__.c.detected_by.server_default.arg) == "'bielik'"

    def test_status_check_constraint(self):
        assert "ck_tool_candidates_status" in check_constraint_names(ToolCandidate.__table__)

    def test_source_document_fk_cascade(self):
        fk = next(iter(ToolCandidate.__table__.c.source_document_id.foreign_keys))
        assert fk.column.table.name == "documents"
        assert fk.ondelete == "CASCADE"

    def test_source_status_index(self):
        assert "idx_tool_candidates_source_status" in {i.name for i in ToolCandidate.__table__.indexes}
