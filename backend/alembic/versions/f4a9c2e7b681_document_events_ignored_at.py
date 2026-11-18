"""document_events.ignored_at: a timeline proposal the reader dismissed

Revision ID: f4a9c2e7b681
Revises: e5b8d2f6a173
Create Date: 2026-11-11 12:00:00.000000

Detection replaces a chapter's timeline proposals on every run, so a proposal that is no event ("XIX wieku - okres,
w którym używany był symbol piratów") came back each time. A dismissed proposal is now kept with ``ignored_at`` set:
the list hides it, a re-detection leaves it alone and skips any new proposal quoting the same passage.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f4a9c2e7b681"
down_revision: Union[str, None] = "e5b8d2f6a173"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("document_events", sa.Column("ignored_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("document_events", "ignored_at")
