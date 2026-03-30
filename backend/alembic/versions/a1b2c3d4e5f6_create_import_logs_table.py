"""create import_logs table

Revision ID: a1b2c3d4e5f6
Revises: 7d0f82796715
Create Date: 2026-03-29 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '7d0f82796715'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create import_logs table for tracking import script operations."""
    op.create_table(
        "import_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("script_name", sa.String(length=100), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="running"),
        sa.Column("since_date", sa.Date(), nullable=True),
        sa.Column("until_date", sa.Date(), nullable=True),
        sa.Column("items_found", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("items_added", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("items_skipped", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("items_error", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("parameters", postgresql.JSONB(), nullable=True, server_default="{}"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_import_logs_script",
        "import_logs",
        ["script_name", sa.text("started_at DESC")],
    )


def downgrade() -> None:
    """Drop import_logs table."""
    op.drop_index("idx_import_logs_script", table_name="import_logs")
    op.drop_table("import_logs")
