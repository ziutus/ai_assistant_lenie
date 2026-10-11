"""Add per-document human place verification state."""

from alembic import op
import sqlalchemy as sa

revision = "7bc921e40a63"
down_revision = "e2b3c4d5f6a7"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("document_entities", sa.Column("place_verification_status", sa.String(20), nullable=True))
    op.add_column("document_entities", sa.Column("place_review_reason", sa.String(100), nullable=True))


def downgrade():
    op.drop_column("document_entities", "place_review_reason")
    op.drop_column("document_entities", "place_verification_status")
