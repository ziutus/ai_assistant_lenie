"""tools: the catalog tool a tool being phased out is migrated to

Revision ID: c4e8a2d6f1b7
Revises: b5d1f7a3c926
Create Date: 2026-10-23
"""

from alembic import op
import sqlalchemy as sa

revision = "c4e8a2d6f1b7"
down_revision = "b5d1f7a3c926"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tools",
        sa.Column("migration_target_tool_id", sa.Integer, sa.ForeignKey("tools.id", ondelete="SET NULL")),
    )


def downgrade() -> None:
    op.drop_column("tools", "migration_target_tool_id")
