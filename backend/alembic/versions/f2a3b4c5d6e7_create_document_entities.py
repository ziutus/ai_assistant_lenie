"""create document_entities

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-07-10 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f2a3b4c5d6e7"
down_revision: Union[str, None] = "e1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # IF NOT EXISTS: the same table may already have been created by the Docker
    # init script 21-create-document-entities.sql on a fresh database.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS document_entities (
            id            SERIAL PRIMARY KEY,
            document_id   INTEGER NOT NULL REFERENCES web_documents(id) ON DELETE CASCADE,
            entity_type   VARCHAR(20) NOT NULL,
            entity_text   TEXT NOT NULL,
            mention_count INTEGER NOT NULL DEFAULT 1,
            created_at    TIMESTAMP NOT NULL DEFAULT NOW(),
            UNIQUE (document_id, entity_type, entity_text)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_document_entities_document_id ON document_entities(document_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_document_entities_type ON document_entities(entity_type)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS document_entities")
