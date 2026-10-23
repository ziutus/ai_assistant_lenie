"""github_repo_stats.homepage: the repository's own "Website" field, offered as a hint for the entry's homepage

Revision ID: c2e8a5d1f9b3
Revises: b7d3e1f9a4c2
Create Date: 2026-10-23
"""

import sqlalchemy as sa
from alembic import op

revision = "c2e8a5d1f9b3"
down_revision = "b7d3e1f9a4c2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("github_repo_stats", sa.Column("homepage", sa.Text()))


def downgrade() -> None:
    op.drop_column("github_repo_stats", "homepage")
