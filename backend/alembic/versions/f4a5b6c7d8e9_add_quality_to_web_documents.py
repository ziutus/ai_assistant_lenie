"""add quality to web_documents

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
Create Date: 2026-07-16 10:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = "f4a5b6c7d8e9"
down_revision: Union[str, None] = "e3f4a5b6c7d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE web_documents ADD COLUMN IF NOT EXISTS quality JSONB")


def downgrade() -> None:
    op.execute("ALTER TABLE web_documents DROP COLUMN IF EXISTS quality")
