"""seed obsidian reimport scheduled task

Revision ID: 868602adab5b
Revises: 0f9ca717603a
Create Date: 2026-08-17 16:34:05.105676

"""
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '868602adab5b'
down_revision: Union[str, Sequence[str], None] = '0f9ca717603a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Every 5 minutes across the day (288 entries) -- Story 42.2's Dev Notes:
# reuses the existing scheduled_tasks "times" mechanism (feed_daily,
# legacy_aws_pull) instead of inventing an interval concept, and is tunable
# post-deploy via a plain UPDATE once real reimport latency is measured.
_TIMES = json.dumps([f"{h:02d}:{m:02d}" for h in range(24) for m in range(0, 60, 5)])


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        sa.text(
            "INSERT INTO scheduled_tasks (id, enabled, timezone, times) "
            "VALUES ('obsidian_reimport', TRUE, 'Europe/Warsaw', CAST(:times AS jsonb))"
        ).bindparams(times=_TIMES)
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DELETE FROM scheduled_tasks WHERE id = 'obsidian_reimport'")
