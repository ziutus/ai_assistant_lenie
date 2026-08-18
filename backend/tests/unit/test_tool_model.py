"""Metadata tests for the Tool model (Epic 44, Story 44.2).

The table is created by a raw-SQL Alembic migration (4d5e6f7a8b9c); this test
pins the ORM mapping to the same shape so a drift between models.py and the
migration is caught without a database. The GIN trigram index
(idx_tools_name_trgm) is created via op.execute() raw SQL and is not visible
in ORM metadata — it is verified against a live database in Task 4, not here.
"""

import pytest

pytest.importorskip("sqlalchemy")

from library.db.models import Tool


class TestToolModel:
    def test_table_name(self):
        assert Tool.__table__.name == "tools"

    def test_required_columns_not_nullable(self):
        table = Tool.__table__
        for column in ("id", "uuid", "name", "category_tags", "status", "created_at", "updated_at"):
            assert table.c[column].nullable is False

    def test_optional_columns_nullable(self):
        table = Tool.__table__
        for column in (
            "homepage_url", "license", "pricing", "personal_notes",
            "source_document_id", "source_candidate_id", "obsidian_note_path",
        ):
            assert table.c[column].nullable is True

    def test_category_tags_default(self):
        assert str(Tool.__table__.c.category_tags.server_default.arg) == "'[]'::jsonb"

    def test_status_default(self):
        assert str(Tool.__table__.c.status.server_default.arg) == "'accepted'"

    def test_source_document_fk_set_null(self):
        fk = next(iter(Tool.__table__.c.source_document_id.foreign_keys))
        assert fk.column.table.name == "documents"
        assert fk.ondelete == "SET NULL"

    def test_source_candidate_fk_set_null(self):
        fk = next(iter(Tool.__table__.c.source_candidate_id.foreign_keys))
        assert fk.column.table.name == "tool_candidates"
        assert fk.ondelete == "SET NULL"

    def test_uuid_unique(self):
        assert Tool.__table__.c.uuid.unique is True
