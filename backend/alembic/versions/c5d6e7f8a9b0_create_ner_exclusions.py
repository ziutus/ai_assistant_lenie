"""create ner_exclusions

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
Create Date: 2026-07-10 23:30:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c5d6e7f8a9b0"
down_revision: Union[str, None] = "b4c5d6e7f8a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # IF NOT EXISTS: the same objects may already have been created by the
    # Docker init script 24-create-ner-exclusions.sql on a fresh database.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ner_exclusions (
            id          SERIAL PRIMARY KEY,
            entity_text TEXT NOT NULL,
            entity_type VARCHAR(20) NOT NULL DEFAULT '*',
            scope       VARCHAR(10) NOT NULL DEFAULT 'global',
            author      TEXT,
            note        TEXT,
            created_at  TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT ner_exclusions_scope_check CHECK (scope IN ('global', 'author')),
            CONSTRAINT ner_exclusions_author_required CHECK (scope != 'author' OR author IS NOT NULL)
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_ner_exclusions_unique "
        "ON ner_exclusions (LOWER(entity_text), entity_type, scope, COALESCE(LOWER(author), ''))"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ner_exclusions")
