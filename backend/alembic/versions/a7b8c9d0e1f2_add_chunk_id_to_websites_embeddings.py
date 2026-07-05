"""add chunk_id to websites_embeddings

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-07-05 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # IF NOT EXISTS: the same column may already have been added by the Docker
    # init script 16-add-chunk-id-to-embeddings.sql on a fresh database.
    op.execute(
        "ALTER TABLE websites_embeddings "
        "ADD COLUMN IF NOT EXISTS chunk_id INTEGER REFERENCES document_chunks(id) ON DELETE SET NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_websites_embeddings_chunk_id ON websites_embeddings(chunk_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_websites_embeddings_chunk_id")
    op.drop_column("websites_embeddings", "chunk_id")
