"""add photo_thumbnail_storage_key to contacts

Revision ID: 8b07952a8f81
Revises: c4a8d2b1f5e6
Create Date: 2026-09-13
"""
from typing import Sequence, Union

from alembic import op

revision: str = "8b07952a8f81"
down_revision: Union[str, None] = "c4a8d2b1f5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE contacts ADD COLUMN IF NOT EXISTS photo_thumbnail_storage_key TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE contacts DROP COLUMN IF EXISTS photo_thumbnail_storage_key")
