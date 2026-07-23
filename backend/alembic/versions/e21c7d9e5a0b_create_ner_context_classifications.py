"""create NER context classifications

Revision ID: e21c7d9e5a0b
Revises: e20b6c8d4f9a
"""

from alembic import op
import sqlalchemy as sa


revision = "e21c7d9e5a0b"
down_revision = "e20b6c8d4f9a"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ner_context_classifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "document_id",
            sa.Integer(),
            sa.ForeignKey("documents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("entity_text", sa.Text(), nullable=False),
        sa.Column("predicted_class", sa.String(length=20), nullable=False),
        sa.Column("confidence", sa.String(length=10), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("context_excerpt", sa.Text(), nullable=True),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("dropped", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "idx_ner_context_classifications_document_created",
        "ner_context_classifications",
        ["document_id", "created_at"],
    )
    op.create_index(
        "idx_ner_context_classifications_entity",
        "ner_context_classifications",
        ["entity_text", "predicted_class"],
    )


def downgrade():
    op.drop_index("idx_ner_context_classifications_entity", table_name="ner_context_classifications")
    op.drop_index(
        "idx_ner_context_classifications_document_created",
        table_name="ner_context_classifications",
    )
    op.drop_table("ner_context_classifications")
