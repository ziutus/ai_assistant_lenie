"""add reason and comment to entity review decisions

Revision ID: e20b6c8d4f9a
Revises: e19a5b7c3d8f
"""

from alembic import op
import sqlalchemy as sa


revision = "e20b6c8d4f9a"
down_revision = "e19a5b7c3d8f"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "entity_review_decisions",
        sa.Column("reason_code", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "entity_review_decisions",
        sa.Column("comment", sa.Text(), nullable=True),
    )
    op.create_index(
        "idx_entity_review_decisions_reason",
        "entity_review_decisions",
        ["reason_code"],
    )


def downgrade():
    op.drop_index("idx_entity_review_decisions_reason", table_name="entity_review_decisions")
    op.drop_column("entity_review_decisions", "comment")
    op.drop_column("entity_review_decisions", "reason_code")
