"""add photo_storage_key to contacts

Revision ID: a6b7c8d9e0f1
Revises: dd4c059abc7c
Create Date: 2026-08-24 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a6b7c8d9e0f1"
down_revision: Union[str, None] = "dd4c059abc7c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE contacts ADD COLUMN IF NOT EXISTS photo_storage_key TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE contacts DROP COLUMN IF EXISTS photo_storage_key")
