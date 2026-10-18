"""Add document_entities.description: reviewer-approved description of an event entity."""
from alembic import op
import sqlalchemy as sa

revision = "c4d9e1a7b3f2"
down_revision = "a7c2f9d4b1e6"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("document_entities", sa.Column("description", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("document_entities", "description")
