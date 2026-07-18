"""add author_source to web_documents

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-07-18 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = "c2d3e4f5a6b7"
down_revision: Union[str, None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE web_documents ADD COLUMN IF NOT EXISTS author_source VARCHAR(10)")
    op.execute("""
        ALTER TABLE web_documents ADD CONSTRAINT ck_web_documents_author_source
        CHECK (author_source IS NULL OR author_source IN ('manual', 'llm'))
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE web_documents DROP CONSTRAINT IF EXISTS ck_web_documents_author_source")
    op.execute("ALTER TABLE web_documents DROP COLUMN IF EXISTS author_source")
