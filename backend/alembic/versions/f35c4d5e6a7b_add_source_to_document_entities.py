"""add source to document_entities

Revision ID: f35c4d5e6a7b
Revises: e24b2c3d4e5f
"""

from alembic import op
import sqlalchemy as sa


revision = "f35c4d5e6a7b"
down_revision = "e24b2c3d4e5f"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "document_entities",
        sa.Column("source", sa.String(length=20), server_default="ner", nullable=False),
    )


def downgrade():
    op.drop_column("document_entities", "source")
