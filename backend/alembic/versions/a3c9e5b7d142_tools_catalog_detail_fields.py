"""tools: detail fields of the catalog entry (links, pricing type, key points, migrating away)

Revision ID: a3c9e5b7d142
Revises: d7e2a9b4c1f6
Create Date: 2026-10-23
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "a3c9e5b7d142"
down_revision = "d7e2a9b4c1f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tools", sa.Column("github_url", sa.Text))
    op.add_column("tools", sa.Column("wikipedia_url", sa.Text))
    op.add_column("tools", sa.Column("pricing_url", sa.Text))
    op.add_column("tools", sa.Column("pricing_type", sa.String(30)))
    op.add_column("tools", sa.Column("app_type", sa.String(100)))
    op.add_column(
        "tools",
        sa.Column("key_points", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
    )
    op.add_column("tools", sa.Column("important_commands", sa.Text))
    op.add_column("tools", sa.Column("migrating_away", sa.Boolean, nullable=False, server_default=sa.text("false")))
    op.add_column("tools", sa.Column("migration_note", sa.Text))
    # Backfill the repository link for tools whose homepage already is a GitHub repository.
    op.execute(
        "UPDATE tools SET github_url = homepage_url "
        "WHERE github_url IS NULL AND homepage_url ~* '^https?://(www\\.)?github\\.com/[^/]+/[^/]+'"
    )


def downgrade() -> None:
    for column in (
        "migration_note", "migrating_away", "important_commands", "key_points",
        "app_type", "pricing_type", "pricing_url", "wikipedia_url", "github_url",
    ):
        op.drop_column("tools", column)
