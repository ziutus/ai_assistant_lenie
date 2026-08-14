"""create reader-chunk category memberships

Revision ID: 0a1b2c3d4e5f
Revises: ff6a7b8c9d0e
"""

from alembic import op
import sqlalchemy as sa


revision = "0a1b2c3d4e5f"
down_revision = "ff6a7b8c9d0e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_chunk_group_memberships",
        sa.Column("chunk_id", sa.Integer, sa.ForeignKey("document_chunks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("group_id", sa.Integer, sa.ForeignKey("content_groups.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("chunk_id", "group_id"),
    )
    op.create_index("idx_document_chunk_group_memberships_group_id", "document_chunk_group_memberships", ["group_id"])


def downgrade() -> None:
    op.drop_index("idx_document_chunk_group_memberships_group_id", table_name="document_chunk_group_memberships")
    op.drop_table("document_chunk_group_memberships")
