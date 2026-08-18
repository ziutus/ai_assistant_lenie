"""create obsidian_note_versions table

Revision ID: 6f7a8b9c0d1e
Revises: 4d5e6f7a8b9c
Create Date: 2026-08-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "6f7a8b9c0d1e"
down_revision: Union[str, Sequence[str], None] = "4d5e6f7a8b9c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "obsidian_note_versions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("note_path", sa.Text, nullable=False),
        sa.Column("content_before", sa.Text),
        sa.Column("content_after", sa.Text, nullable=False),
        sa.Column("user_prompt", sa.Text),
        sa.Column("tool_id", sa.Integer, sa.ForeignKey("tools.id", ondelete="SET NULL")),
        sa.Column("changed_by", sa.Text, nullable=False, server_default="backend"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.execute(
        "CREATE INDEX idx_obsidian_note_versions_note_path "
        "ON obsidian_note_versions (note_path, created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_obsidian_note_versions_note_path")
    op.drop_table("obsidian_note_versions")
