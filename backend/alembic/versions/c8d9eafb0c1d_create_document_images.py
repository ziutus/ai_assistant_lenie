"""create document_images

Revision ID: c8d9eafb0c1d
Revises: a4b5c6d7e8f9
Create Date: 2026-07-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c8d9eafb0c1d"
down_revision: Union[str, None] = "a4b5c6d7e8f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # IF NOT EXISTS: the same table may already have been created by the Docker
    # init script 34-create-document-images.sql on a fresh database.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS document_images (
            id               SERIAL PRIMARY KEY,
            document_id      INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            chunk_id         INTEGER REFERENCES document_chunks(id) ON DELETE SET NULL,
            position         SMALLINT,
            url              TEXT NOT NULL,
            alt_text         TEXT,
            caption_text     TEXT,
            caption_category VARCHAR(30),
            is_stock_photo   BOOLEAN NOT NULL DEFAULT FALSE,
            created_at       TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_document_images_document_id ON document_images(document_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS document_images")
