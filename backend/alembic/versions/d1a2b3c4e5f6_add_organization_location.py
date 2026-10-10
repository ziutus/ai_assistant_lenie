"""Add headquarters location, website and Obsidian note path to organizations.

Revision ID: d1a2b3c4e5f6
Revises: c83f0e2a619d
"""

from alembic import op
import sqlalchemy as sa

revision = "d1a2b3c4e5f6"
down_revision = "c83f0e2a619d"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("organizations", sa.Column("headquarters_address", sa.Text(), nullable=True))
    op.add_column("organizations", sa.Column("latitude", sa.Numeric(9, 6), nullable=True))
    op.add_column("organizations", sa.Column("longitude", sa.Numeric(9, 6), nullable=True))
    op.add_column("organizations", sa.Column("website", sa.Text(), nullable=True))
    op.add_column("organizations", sa.Column("obsidian_note_path", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("organizations", "obsidian_note_path")
    op.drop_column("organizations", "website")
    op.drop_column("organizations", "longitude")
    op.drop_column("organizations", "latitude")
    op.drop_column("organizations", "headquarters_address")
