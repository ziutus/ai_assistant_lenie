"""create tool recommendations radar

Revision ID: c0a1b2c3d4e5
Revises: af09cbe12345, b7a9d8c6e5f4
Create Date: 2026-08-23
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c0a1b2c3d4e5"
down_revision: Union[str, Sequence[str], None] = ("af09cbe12345", "b7a9d8c6e5f4")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tool_recommendations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("homepage_url", sa.Text),
        sa.Column("description", sa.Text),
        sa.Column("category", sa.String(255)),
        sa.Column("status", sa.String(20), nullable=False, server_default="watchlist"),
        sa.Column("personal_note", sa.Text),
        sa.Column("source_url", sa.Text),
        sa.Column("source_context", sa.Text),
        sa.Column("source_document_id", sa.Integer, sa.ForeignKey("documents.id", ondelete="SET NULL")),
        sa.Column("source_candidate_id", sa.Integer, sa.ForeignKey("tool_candidates.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('watchlist', 'compare', 'testing', 'adopted', 'rejected', 'archived')", name="ck_tool_recommendations_status"),
    )
    op.create_index("idx_tool_recommendations_status_created", "tool_recommendations", ["status", "created_at"])
    op.create_index("idx_tool_recommendations_source_candidate", "tool_recommendations", ["source_candidate_id"])


def downgrade() -> None:
    op.drop_index("idx_tool_recommendations_source_candidate", table_name="tool_recommendations")
    op.drop_index("idx_tool_recommendations_status_created", table_name="tool_recommendations")
    op.drop_table("tool_recommendations")
