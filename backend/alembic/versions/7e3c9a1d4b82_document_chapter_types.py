"""Store ordered H2 chapter types independently of transcript headings."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "7e3c9a1d4b82"
down_revision = "b9d4f2a6c801"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("documents", sa.Column("chapter_types", postgresql.JSONB(none_as_null=True), nullable=True))


def downgrade():
    op.drop_column("documents", "chapter_types")
