"""Track the last conclusive on-demand address registry check."""
from alembic import op
import sqlalchemy as sa

revision = "f4b9c8d2a671"
down_revision = "e71f4a9d260b"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("addresses", sa.Column("verified_at", sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column("addresses", "verified_at")
