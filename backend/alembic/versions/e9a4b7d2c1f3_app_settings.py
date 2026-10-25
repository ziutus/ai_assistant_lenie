"""app_settings: small key/value store for choices made in the UI (e.g. the default model of a task)

Revision ID: e9a4b7d2c1f3
Revises: d8f3a6c1b9e2
Create Date: 2026-10-23
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "e9a4b7d2c1f3"
down_revision = "d8f3a6c1b9e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(100), primary_key=True),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("app_settings")
