"""create github_repo_stats (latest public GitHub numbers per repository)

Revision ID: d5a1c7e92b34
Revises: b8d2f4a61c93
Create Date: 2026-10-22
"""

from alembic import op
import sqlalchemy as sa

revision = "d5a1c7e92b34"
down_revision = "b8d2f4a61c93"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "github_repo_stats",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("full_name_key", sa.String(512), nullable=False, unique=True),
        sa.Column("owner", sa.String(255), nullable=False),
        sa.Column("repo", sa.String(255), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("stars", sa.Integer),
        sa.Column("forks", sa.Integer),
        sa.Column("watchers", sa.Integer),
        sa.Column("open_issues", sa.Integer),
        sa.Column("language", sa.String(100)),
        sa.Column("license", sa.String(100)),
        sa.Column("archived", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("repo_created_at", sa.DateTime(timezone=True)),
        sa.Column("pushed_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(20), nullable=False, server_default="ok"),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('ok', 'not_found')", name="ck_github_repo_stats_status"),
    )


def downgrade() -> None:
    op.drop_table("github_repo_stats")
