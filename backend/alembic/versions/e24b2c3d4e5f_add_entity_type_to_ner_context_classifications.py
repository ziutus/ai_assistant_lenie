"""add entity_type to ner_context_classifications

Revision ID: e24b2c3d4e5f
Revises: e23a1b2c3d4e
"""

from alembic import op
import sqlalchemy as sa


revision = "e24b2c3d4e5f"
down_revision = "e23a1b2c3d4e"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "ner_context_classifications",
        sa.Column("entity_type", sa.String(length=20), server_default="persName", nullable=False),
    )
    op.create_index(
        "idx_ner_context_classifications_entity_type",
        "ner_context_classifications",
        ["entity_type", "predicted_class"],
    )


def downgrade():
    op.drop_index("idx_ner_context_classifications_entity_type", table_name="ner_context_classifications")
    op.drop_column("ner_context_classifications", "entity_type")
