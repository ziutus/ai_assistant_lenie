"""alter import_logs parameters column from json to jsonb

Note: The initial migration (a1b2c3d4e5f6) was later fixed to create
the column as JSONB directly. This ALTER migration remains for databases
that ran the original (pre-fix) version with JSON type. On a fresh install
this is a harmless no-op (JSONB -> JSONB).

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-03-29 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Convert parameters column from json to jsonb for better query support."""
    op.execute("ALTER TABLE import_logs ALTER COLUMN parameters TYPE jsonb USING parameters::jsonb")


def downgrade() -> None:
    """Revert parameters column from jsonb to json."""
    op.execute("ALTER TABLE import_logs ALTER COLUMN parameters TYPE json USING parameters::json")
