"""one radar entry per tool name

Revision ID: d7e2a9b4c1f6
Revises: a8d4f1c6e093
Create Date: 2026-10-23
"""

from alembic import op

revision = "d7e2a9b4c1f6"
down_revision = "a8d4f1c6e093"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Merge existing same-name entries first (keeper: an adopted one, else the oldest) so the index can be built.
    op.execute("""
        CREATE TEMP TABLE _radar_dupes ON COMMIT DROP AS
        SELECT id, first_value(id) OVER (
            PARTITION BY lower(name) ORDER BY (status = 'adopted') DESC, id
        ) AS keeper_id
        FROM tool_recommendations
    """)
    op.execute("""
        UPDATE tool_recommendation_evidence e SET tool_recommendation_id = d.keeper_id
        FROM _radar_dupes d WHERE e.tool_recommendation_id = d.id AND d.id <> d.keeper_id
    """)
    # Relations are re-pointed only when the edge stays valid; the rest cascade away with the duplicate.
    op.execute("""
        UPDATE tool_relations r SET from_tool_id = d.keeper_id
        FROM _radar_dupes d WHERE r.from_tool_id = d.id AND d.id <> d.keeper_id
          AND d.keeper_id <> r.to_tool_id
          AND NOT EXISTS (SELECT 1 FROM tool_relations x WHERE x.from_tool_id = d.keeper_id
                          AND x.to_tool_id = r.to_tool_id AND x.relation = r.relation)
    """)
    op.execute("""
        UPDATE tool_relations r SET to_tool_id = d.keeper_id
        FROM _radar_dupes d WHERE r.to_tool_id = d.id AND d.id <> d.keeper_id
          AND d.keeper_id <> r.from_tool_id
          AND NOT EXISTS (SELECT 1 FROM tool_relations x WHERE x.to_tool_id = d.keeper_id
                          AND x.from_tool_id = r.from_tool_id AND x.relation = r.relation)
    """)
    op.execute("DELETE FROM tool_recommendations WHERE id IN (SELECT id FROM _radar_dupes WHERE id <> keeper_id)")
    op.execute("CREATE UNIQUE INDEX uq_tool_recommendations_name_lower ON tool_recommendations (lower(name))")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_tool_recommendations_name_lower")
