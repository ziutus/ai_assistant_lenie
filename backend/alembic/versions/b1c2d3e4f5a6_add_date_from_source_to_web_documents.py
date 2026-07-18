"""add date_from_source to web_documents

Revision ID: b1c2d3e4f5a6
Revises: f0a1b2c3d4e5
Create Date: 2026-07-18 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, None] = "f0a1b2c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE web_documents ADD COLUMN IF NOT EXISTS date_from_source VARCHAR(10)")
    op.execute("""
        ALTER TABLE web_documents ADD CONSTRAINT ck_web_documents_date_from_source
        CHECK (date_from_source IS NULL OR date_from_source IN ('manual', 'llm'))
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE web_documents DROP CONSTRAINT IF EXISTS ck_web_documents_date_from_source")
    op.execute("ALTER TABLE web_documents DROP COLUMN IF EXISTS date_from_source")
