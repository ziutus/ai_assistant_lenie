"""Create database-owned definitions for scheduled jobs."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "fb2c3d4e5f6a"
down_revision = "fa1b2c3d4e5f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scheduled_tasks",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("times", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.execute("""
        INSERT INTO scheduled_tasks (id, enabled, timezone, times)
        VALUES
          ('feed_daily', TRUE, 'Europe/Warsaw', '["04:00"]'::jsonb),
          ('legacy_aws_pull', TRUE, 'Europe/Warsaw', '["05:00", "17:00"]'::jsonb)
    """)


def downgrade() -> None:
    op.drop_table("scheduled_tasks")
