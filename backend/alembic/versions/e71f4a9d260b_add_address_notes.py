"""Add practical access and delivery notes to shared addresses."""
from alembic import op
import sqlalchemy as sa

revision = "e71f4a9d260b"
down_revision = "c2e8a6f41903"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("addresses", sa.Column("notes", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("addresses", "notes")
