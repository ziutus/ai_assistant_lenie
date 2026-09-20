"""Keep estate block numbers separate from street building numbers."""
from alembic import op
import sqlalchemy as sa

revision = "a6d31e8b902f"
down_revision = "f4b9c8d2a671"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("addresses", sa.Column("block_number", sa.String(20), nullable=True))


def downgrade():
    op.drop_column("addresses", "block_number")
