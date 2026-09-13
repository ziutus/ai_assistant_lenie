"""add nationality to contacts

Nationality/nationalities of a contact — a JSONB list of plain strings
rather than a single value, since dual/multiple citizenship is common.
Same shape/rationale as languages (412270d27536): independent of it, a
contact's spoken languages don't determine their nationality or vice
versa.

Revision ID: 18ae0750559d
Revises: 412270d27536
Create Date: 2026-09-13 00:30:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '18ae0750559d'
down_revision: Union[str, Sequence[str], None] = '412270d27536'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE contacts ADD COLUMN nationality JSONB NOT NULL DEFAULT '[]'::jsonb")


def downgrade() -> None:
    op.execute("ALTER TABLE contacts DROP COLUMN IF EXISTS nationality")
