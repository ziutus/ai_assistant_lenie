"""create NER temporal candidates

Revision ID: e22d8e0f6b1c
Revises: e21c7d9e5a0b
"""

from alembic import op
import sqlalchemy as sa


revision = "e22d8e0f6b1c"
down_revision = "e21c7d9e5a0b"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ner_temporal_candidates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "document_id",
            sa.Integer(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("entity_type", sa.String(length=10), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("lemma", sa.Text(), nullable=True),
        sa.Column("char_start", sa.Integer(), nullable=True),
        sa.Column("context_excerpt", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "idx_ner_temporal_candidates_document_position",
        "ner_temporal_candidates",
        ["document_id", "char_start"],
    )


def downgrade():
    op.drop_index(
        "idx_ner_temporal_candidates_document_position",
        table_name="ner_temporal_candidates",
    )
    op.drop_table("ner_temporal_candidates")
