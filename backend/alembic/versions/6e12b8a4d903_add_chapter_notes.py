"""Add positional chapter notes."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "6e12b8a4d903"
down_revision = "c5a1d9e7f204"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("documents", sa.Column("chapter_notes", postgresql.JSONB(none_as_null=True), nullable=True))


def downgrade():
    op.drop_column("documents", "chapter_notes")
