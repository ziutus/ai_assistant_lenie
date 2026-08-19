"""obsidian reimport schedule: daily safety net instead of every 5 minutes

Story 42.3 adds an inotify-based watcher (library/obsidian_vault_watcher.py)
that reimports a changed note within seconds of the write, so the scheduled
full-vault scan no longer needs to run every 5 minutes to catch edits. Left
as-is, the every-5-minutes schedule was also the root cause of two
consecutive NAS hard hangs (2026-08-18/19): a run that finishes in ~3s when
nothing changed left _is_due() true and no job "active" for the rest of that
same minute, so the worker's zero-sleep-between-jobs loop kept re-enqueuing
it -- thousands of full-vault scans a day instead of ~288. worker.py's
_schedule_obsidian_reimport() now also carries a per-minute idempotency_key
(same fix independently caps it to one run per matching minute regardless of
how many times are configured), but the schedule itself only needs to run
once a day now, as a safety net for changes made while the watcher/worker
was down.

Revision ID: 7a8b9c0d1e2f
Revises: 6f7a8b9c0d1e
Create Date: 2026-08-19 00:00:00.000000

"""
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7a8b9c0d1e2f"
down_revision: Union[str, Sequence[str], None] = "6f7a8b9c0d1e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NEW_TIMES = json.dumps(["03:30"])
_OLD_TIMES = json.dumps([f"{h:02d}:{m:02d}" for h in range(24) for m in range(0, 60, 5)])


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        sa.text(
            "UPDATE scheduled_tasks SET enabled = TRUE, times = CAST(:times AS jsonb) "
            "WHERE id = 'obsidian_reimport'"
        ).bindparams(times=_NEW_TIMES)
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        sa.text("UPDATE scheduled_tasks SET times = CAST(:times AS jsonb) WHERE id = 'obsidian_reimport'").bindparams(
            times=_OLD_TIMES
        )
    )
