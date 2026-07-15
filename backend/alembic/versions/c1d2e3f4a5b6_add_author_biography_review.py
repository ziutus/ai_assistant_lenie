"""add author biography review fields

Revision ID: c1d2e3f4a5b6
Revises: b0c1d2e3f4a5
Create Date: 2026-07-15 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, None] = "b0c1d2e3f4a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE document_persons ADD COLUMN IF NOT EXISTS role VARCHAR(30) NOT NULL DEFAULT 'mentioned'")
    op.execute("ALTER TABLE document_persons ADD COLUMN IF NOT EXISTS source_excerpt TEXT")
    op.execute("ALTER TABLE document_persons ADD COLUMN IF NOT EXISTS bio_review_status VARCHAR(30)")
    op.execute("ALTER TABLE document_persons ADD COLUMN IF NOT EXISTS bio_review_result JSONB")
    op.execute("ALTER TABLE document_persons ADD COLUMN IF NOT EXISTS bio_reviewed_at TIMESTAMP")
    op.execute("CREATE INDEX IF NOT EXISTS idx_document_persons_bio_review ON document_persons (bio_review_status)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_document_persons_bio_review")
    op.execute("ALTER TABLE document_persons DROP COLUMN IF EXISTS bio_reviewed_at")
    op.execute("ALTER TABLE document_persons DROP COLUMN IF EXISTS bio_review_result")
    op.execute("ALTER TABLE document_persons DROP COLUMN IF EXISTS bio_review_status")
    op.execute("ALTER TABLE document_persons DROP COLUMN IF EXISTS source_excerpt")
    op.execute("ALTER TABLE document_persons DROP COLUMN IF EXISTS role")
