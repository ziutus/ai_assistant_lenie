"""add is_archived to contacts

Revision ID: b7c8d9e0f1a2
Revises: a6b7c8d9e0f1
Create Date: 2026-08-25 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "07dd233ecf10"
down_revision: Union[str, None] = "a6b7c8d9e0f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE contacts ADD COLUMN IF NOT EXISTS is_archived BOOLEAN NOT NULL DEFAULT FALSE")
    op.execute("CREATE INDEX IF NOT EXISTS idx_contacts_is_archived ON contacts (is_archived)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_contacts_is_archived")
    op.execute("ALTER TABLE contacts DROP COLUMN IF EXISTS is_archived")
