"""merge detected tool candidates into the unified radar

Revision ID: c2a3b4c5d6e7
Revises: c1a2b3c4d5e6
Create Date: 2026-08-23
"""

from alembic import op

revision = "c2a3b4c5d6e7"
down_revision = "c1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO tool_recommendations
          (name, description, source_url, source_context, source_document_id, source_candidate_id, status)
        SELECT c.name, c.context_snippet, d.url, d.title, c.source_document_id, c.id,
          CASE WHEN c.status = 'rejected' THEN 'rejected' ELSE 'watchlist' END
        FROM tool_candidates c JOIN documents d ON d.id = c.source_document_id
        WHERE NOT EXISTS (SELECT 1 FROM tool_recommendations r WHERE r.source_candidate_id = c.id)
    """)
    op.execute("""
        INSERT INTO tool_recommendation_evidence
          (tool_recommendation_id, relation_type, catalog_url, catalog_label, context, recommender_document_id)
        SELECT r.id, 'mentioned_in', d.url, d.title, c.context_snippet, c.source_document_id
        FROM tool_recommendations r JOIN tool_candidates c ON c.id = r.source_candidate_id
        JOIN documents d ON d.id = c.source_document_id
        WHERE NOT EXISTS (SELECT 1 FROM tool_recommendation_evidence e WHERE e.tool_recommendation_id = r.id AND e.recommender_document_id = c.source_document_id)
    """)


def downgrade() -> None:
    op.execute("DELETE FROM tool_recommendation_evidence WHERE tool_recommendation_id IN (SELECT id FROM tool_recommendations WHERE source_candidate_id IS NOT NULL)")
    op.execute("DELETE FROM tool_recommendations WHERE source_candidate_id IS NOT NULL")
