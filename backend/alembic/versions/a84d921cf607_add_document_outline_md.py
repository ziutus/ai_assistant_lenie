"""Add a topical Markdown outline separate from timestamped chapters.

Revision ID: a84d921cf607
Revises: e7b2a6d91f03
"""

from alembic import op
import sqlalchemy as sa

revision = "a84d921cf607"
down_revision = "e7b2a6d91f03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("outline_md", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("documents", "outline_md")
