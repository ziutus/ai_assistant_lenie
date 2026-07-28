"""add storage_key/page_number/chapter_position to document_images

Revision ID: b7c8d9e0f1a2
Revises: fa1b2c3d4e5f
Create Date: 2026-07-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7c8d9e0f1a2"
down_revision: Union[str, None] = "fa1b2c3d4e5f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # IF NOT EXISTS: the same columns may already have been added by the Docker
    # init script 36-document-images-storage-key.sql on a fresh database.
    op.execute("ALTER TABLE document_images ADD COLUMN IF NOT EXISTS storage_key TEXT")
    op.execute("ALTER TABLE document_images ADD COLUMN IF NOT EXISTS page_number SMALLINT")
    op.execute("ALTER TABLE document_images ADD COLUMN IF NOT EXISTS chapter_position SMALLINT")
    op.execute("ALTER TABLE document_images ALTER COLUMN url DROP NOT NULL")
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'document_images_source_present'
            ) THEN
                ALTER TABLE document_images ADD CONSTRAINT document_images_source_present
                    CHECK (url IS NOT NULL OR storage_key IS NOT NULL);
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE document_images DROP CONSTRAINT IF EXISTS document_images_source_present")
    op.execute("UPDATE document_images SET url = '' WHERE url IS NULL")
    op.execute("ALTER TABLE document_images ALTER COLUMN url SET NOT NULL")
    op.execute("ALTER TABLE document_images DROP COLUMN IF EXISTS chapter_position")
    op.execute("ALTER TABLE document_images DROP COLUMN IF EXISTS page_number")
    op.execute("ALTER TABLE document_images DROP COLUMN IF EXISTS storage_key")
