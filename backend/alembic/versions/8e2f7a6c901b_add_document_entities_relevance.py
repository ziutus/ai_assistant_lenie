"""Add manual relevance to the document topic for NER entities."""
from alembic import op
import sqlalchemy as sa

revision = "8e2f7a6c901b"
down_revision = "c4d9e1a7b3f2"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("document_entities", sa.Column("relevance", sa.String(12), nullable=False, server_default="central"))


def downgrade():
    op.drop_column("document_entities", "relevance")
