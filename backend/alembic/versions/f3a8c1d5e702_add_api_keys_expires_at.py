"""add expires_at to api_keys (temporary keys)

Revision ID: f3a8c1d5e702
Revises: e9b4c7a2d561
Create Date: 2026-11-02
"""
from typing import Sequence, Union

from alembic import op


revision: str = "f3a8c1d5e702"
down_revision: Union[str, Sequence[str], None] = "e9b4c7a2d561"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS expires_at TIMESTAMP")


def downgrade() -> None:
    op.execute("ALTER TABLE api_keys DROP COLUMN IF EXISTS expires_at")
