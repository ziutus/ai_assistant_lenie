"""Merge the chapter-notes and geopolitics migration heads.

Revision ID: a4c8e2f6b013
Revises: 6e12b8a4d903, d7e1a4b9c205
Create Date: 2026-11-01 00:00:00.000000

Both branched from c5a1d9e7f204 on the same day; ``alembic upgrade head`` refuses to run
with two heads. Nothing to change in the schema.
"""

revision = "a4c8e2f6b013"
down_revision = ("6e12b8a4d903", "d7e1a4b9c205")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
