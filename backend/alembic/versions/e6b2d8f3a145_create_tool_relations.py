"""create tool_relations (auto-proposed links between radar entries)

Revision ID: e6b2d8f3a145
Revises: d5a1c7e92b34
Create Date: 2026-10-23
"""

from alembic import op
import sqlalchemy as sa

revision = "e6b2d8f3a145"
down_revision = "d5a1c7e92b34"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tool_relations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("from_tool_id", sa.Integer, sa.ForeignKey("tool_recommendations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("to_tool_id", sa.Integer, sa.ForeignKey("tool_recommendations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("relation", sa.String(30), nullable=False, server_default="works_with"),
        sa.Column("status", sa.String(20), nullable=False, server_default="proposed"),
        sa.Column("detected_by", sa.String(30), nullable=False, server_default="name_match"),
        sa.Column("context", sa.Text),
        sa.Column("source_document_id", sa.Integer, sa.ForeignKey("documents.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("relation IN ('works_with', 'emulates', 'alternative_to')", name="ck_tool_relations_relation"),
        sa.CheckConstraint("status IN ('proposed', 'confirmed', 'rejected')", name="ck_tool_relations_status"),
        sa.CheckConstraint("from_tool_id <> to_tool_id", name="ck_tool_relations_not_self"),
        sa.UniqueConstraint("from_tool_id", "to_tool_id", "relation", name="uq_tool_relations_edge"),
    )
    op.create_index("idx_tool_relations_to", "tool_relations", ["to_tool_id"])


def downgrade() -> None:
    op.drop_index("idx_tool_relations_to", table_name="tool_relations")
    op.drop_table("tool_relations")
