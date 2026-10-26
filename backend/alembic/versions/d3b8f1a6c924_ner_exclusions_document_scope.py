"""ner_exclusions: scope 'document' (one rule for one document only)

Revision ID: d3b8f1a6c924
Revises: b5f2c8e1a7d3
Create Date: 2026-10-26 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d3b8f1a6c924"
down_revision: Union[str, None] = "b5f2c8e1a7d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE ner_exclusions "
        "ADD COLUMN IF NOT EXISTS document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE"
    )
    op.execute("ALTER TABLE ner_exclusions DROP CONSTRAINT IF EXISTS ner_exclusions_scope_check")
    op.execute(
        "ALTER TABLE ner_exclusions ADD CONSTRAINT ner_exclusions_scope_check "
        "CHECK (scope IN ('global', 'author', 'document'))"
    )
    op.execute("ALTER TABLE ner_exclusions DROP CONSTRAINT IF EXISTS ner_exclusions_document_required")
    op.execute(
        "ALTER TABLE ner_exclusions ADD CONSTRAINT ner_exclusions_document_required "
        "CHECK (scope != 'document' OR document_id IS NOT NULL)"
    )
    op.execute("DROP INDEX IF EXISTS idx_ner_exclusions_unique")
    op.execute(
        "CREATE UNIQUE INDEX idx_ner_exclusions_unique "
        "ON ner_exclusions (LOWER(entity_text), entity_type, scope, COALESCE(LOWER(author), ''), "
        "COALESCE(document_id, 0))"
    )


def downgrade() -> None:
    op.execute("DELETE FROM ner_exclusions WHERE scope = 'document'")
    op.execute("DROP INDEX IF EXISTS idx_ner_exclusions_unique")
    op.execute(
        "CREATE UNIQUE INDEX idx_ner_exclusions_unique "
        "ON ner_exclusions (LOWER(entity_text), entity_type, scope, COALESCE(LOWER(author), ''))"
    )
    op.execute("ALTER TABLE ner_exclusions DROP CONSTRAINT IF EXISTS ner_exclusions_document_required")
    op.execute("ALTER TABLE ner_exclusions DROP CONSTRAINT IF EXISTS ner_exclusions_scope_check")
    op.execute(
        "ALTER TABLE ner_exclusions ADD CONSTRAINT ner_exclusions_scope_check "
        "CHECK (scope IN ('global', 'author'))"
    )
    op.execute("ALTER TABLE ner_exclusions DROP COLUMN IF EXISTS document_id")
