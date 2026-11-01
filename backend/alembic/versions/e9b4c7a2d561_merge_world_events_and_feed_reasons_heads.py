"""Merge the world-events registry and feed-review reasons migration heads.

Revision ID: e9b4c7a2d561
Revises: c7e2b5a9d814, d4e6a8c1b573
Create Date: 2026-11-01 00:00:00.000000

Both branched from b9d3f1a7c526; ``alembic upgrade head`` refuses to run with two heads.
Nothing to change in the schema.
"""

revision = "e9b4c7a2d561"
down_revision = ("c7e2b5a9d814", "d4e6a8c1b573")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
