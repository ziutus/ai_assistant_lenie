"""Metadata tests for the ObsidianNoteVersion model (Epic 47, Story 47.1).

Pins the ORM mapping to the shape created by the raw-SQL Alembic migration
(6f7a8b9c0d1e) so a drift is caught without a database. The
(note_path, created_at DESC) index is created via op.execute() raw SQL and
is not visible in ORM metadata -- verified against a live database in Task 5,
not here (same precedent as Tool/idx_tools_name_trgm, test_tool_model.py).
"""

import pytest

pytest.importorskip("sqlalchemy")

from library.db.models import ObsidianNoteVersion


class TestObsidianNoteVersionModel:
    def test_table_name(self):
        assert ObsidianNoteVersion.__table__.name == "obsidian_note_versions"

    def test_required_columns_not_nullable(self):
        table = ObsidianNoteVersion.__table__
        for column in ("id", "note_path", "content_after", "changed_by", "created_at"):
            assert table.c[column].nullable is False

    def test_optional_columns_nullable(self):
        table = ObsidianNoteVersion.__table__
        for column in ("content_before", "user_prompt", "tool_id"):
            assert table.c[column].nullable is True

    def test_changed_by_default(self):
        assert str(ObsidianNoteVersion.__table__.c.changed_by.server_default.arg) == "'backend'"

    def test_tool_fk_set_null(self):
        fk = next(iter(ObsidianNoteVersion.__table__.c.tool_id.foreign_keys))
        assert fk.column.table.name == "tools"
        assert fk.ondelete == "SET NULL"
