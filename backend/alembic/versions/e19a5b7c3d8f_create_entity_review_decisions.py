"""create entity review decisions audit trail

Revision ID: e19a5b7c3d8f
Revises: d18f4a6b2c7e
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "e19a5b7c3d8f"
down_revision = "d18f4a6b2c7e"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "entity_review_decisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "document_id",
            sa.Integer(),
            sa.ForeignKey("documents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("document_entity_id", sa.BigInteger(), nullable=True),
        sa.Column("document_person_id", sa.BigInteger(), nullable=True),
        sa.Column("person_id", sa.BigInteger(), nullable=True),
        sa.Column("entity_type", sa.String(length=20), nullable=False),
        sa.Column("entity_text", sa.Text(), nullable=False),
        sa.Column("decision", sa.String(length=30), nullable=False),
        sa.Column("original_confidence", sa.String(length=30), nullable=True),
        sa.Column("replacement_person_id", sa.BigInteger(), nullable=True),
        sa.Column("source_excerpt", sa.Text(), nullable=True),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "idx_entity_review_decisions_document_created",
        "entity_review_decisions",
        ["document_id", "created_at"],
    )
    op.create_index(
        "idx_entity_review_decisions_text_type",
        "entity_review_decisions",
        ["entity_text", "entity_type"],
    )
    op.create_index(
        "idx_entity_review_decisions_decision",
        "entity_review_decisions",
        ["decision"],
    )


def downgrade():
    op.drop_index("idx_entity_review_decisions_decision", table_name="entity_review_decisions")
    op.drop_index("idx_entity_review_decisions_text_type", table_name="entity_review_decisions")
    op.drop_index("idx_entity_review_decisions_document_created", table_name="entity_review_decisions")
    op.drop_table("entity_review_decisions")
