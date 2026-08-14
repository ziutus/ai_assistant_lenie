"""create external service events

Revision ID: 1b2c3d4e5f60
Revises: 0a1b2c3d4e5f
"""

from alembic import op
import sqlalchemy as sa

revision = "1b2c3d4e5f60"
down_revision = "0a1b2c3d4e5f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "external_service_events",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("service", sa.String(length=50), nullable=False),
        sa.Column("operation", sa.String(length=100), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("status_code", sa.Integer()),
        sa.Column("error_code", sa.String(length=100)),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column("occurred_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_external_service_events_service_occurred", "external_service_events", ["service", "occurred_at"])


def downgrade() -> None:
    op.drop_index("idx_external_service_events_service_occurred", table_name="external_service_events")
    op.drop_table("external_service_events")
