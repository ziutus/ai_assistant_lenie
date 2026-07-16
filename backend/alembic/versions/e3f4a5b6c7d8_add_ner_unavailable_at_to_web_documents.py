"""add ner_unavailable_at to web_documents

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-07-16 09:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = "e3f4a5b6c7d8"
down_revision: Union[str, None] = "d2e3f4a5b6c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE web_documents ADD COLUMN IF NOT EXISTS ner_unavailable_at TIMESTAMP")


def downgrade() -> None:
    op.execute("ALTER TABLE web_documents DROP COLUMN IF EXISTS ner_unavailable_at")
