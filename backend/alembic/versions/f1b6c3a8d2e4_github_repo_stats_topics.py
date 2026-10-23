"""github_repo_stats.topics: the repository's own GitHub topics, next to its description

Revision ID: f1b6c3a8d2e4
Revises: e9a4b7d2c1f3
Create Date: 2026-10-23
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f1b6c3a8d2e4"
down_revision = "e9a4b7d2c1f3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "github_repo_stats",
        sa.Column("topics", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
    )


def downgrade() -> None:
    op.drop_column("github_repo_stats", "topics")
