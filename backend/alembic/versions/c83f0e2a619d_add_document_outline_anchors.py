"""Add optional outline-bound chunk anchors.

Revision ID: c83f0e2a619d
Revises: a84d921cf607
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "c83f0e2a619d"
down_revision = "a84d921cf607"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("documents", sa.Column("outline_anchors", postgresql.JSONB(), nullable=True))


def downgrade():
    op.drop_column("documents", "outline_anchors")
