"""tool_recommendations.links and GitLab support in github_repo_stats (provider, host)

Revision ID: b7d3e1f9a4c2
Revises: f1b6c3a8d2e4
Create Date: 2026-10-23
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b7d3e1f9a4c2"
down_revision = "f1b6c3a8d2e4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tool_recommendations",
        sa.Column("links", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
    )
    op.add_column("github_repo_stats", sa.Column("provider", sa.String(20), nullable=False, server_default="github"))
    op.add_column("github_repo_stats", sa.Column("host", sa.String(255), nullable=False, server_default="github.com"))
    op.create_check_constraint(
        "ck_github_repo_stats_provider", "github_repo_stats", "provider IN ('github', 'gitlab')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_github_repo_stats_provider", "github_repo_stats", type_="check")
    op.drop_column("github_repo_stats", "host")
    op.drop_column("github_repo_stats", "provider")
    op.drop_column("tool_recommendations", "links")
