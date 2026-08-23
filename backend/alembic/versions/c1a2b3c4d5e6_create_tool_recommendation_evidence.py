"""create multi-source tool recommendation evidence

Revision ID: c1a2b3c4d5e6
Revises: c0a1b2c3d4e5
Create Date: 2026-08-23
"""

from alembic import op
import sqlalchemy as sa

revision = "c1a2b3c4d5e6"
down_revision = "c0a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tool_recommendation_evidence",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tool_recommendation_id", sa.Integer, sa.ForeignKey("tool_recommendations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("relation_type", sa.String(30), nullable=False, server_default="listed_in"),
        sa.Column("catalog_url", sa.Text),
        sa.Column("catalog_label", sa.String(255)),
        sa.Column("context", sa.Text),
        sa.Column("recommender_document_id", sa.Integer, sa.ForeignKey("documents.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("relation_type IN ('listed_in', 'recommended_by', 'mentioned_in')", name="ck_tool_recommendation_evidence_relation_type"),
    )
    op.create_index("idx_tool_recommendation_evidence_tool", "tool_recommendation_evidence", ["tool_recommendation_id"])
    op.create_index("idx_tool_recommendation_evidence_recommender", "tool_recommendation_evidence", ["recommender_document_id"])
    op.execute("""
        INSERT INTO tool_recommendation_evidence
            (tool_recommendation_id, relation_type, catalog_url, catalog_label, context, recommender_document_id)
        SELECT id, 'listed_in', source_url, source_context, category, source_document_id
        FROM tool_recommendations
        WHERE source_url IS NOT NULL OR source_document_id IS NOT NULL
    """)


def downgrade() -> None:
    op.drop_index("idx_tool_recommendation_evidence_recommender", table_name="tool_recommendation_evidence")
    op.drop_index("idx_tool_recommendation_evidence_tool", table_name="tool_recommendation_evidence")
    op.drop_table("tool_recommendation_evidence")
