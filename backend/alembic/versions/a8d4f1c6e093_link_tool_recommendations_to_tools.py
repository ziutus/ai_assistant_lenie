"""link radar entries to catalog tools with a foreign key (tool_recommendations.tool_id)

Revision ID: a8d4f1c6e093
Revises: f7c3e9a2b516
Create Date: 2026-10-23
"""

from alembic import op
import sqlalchemy as sa

revision = "a8d4f1c6e093"
down_revision = "f7c3e9a2b516"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tool_recommendations", sa.Column("tool_id", sa.Integer, sa.ForeignKey("tools.id", ondelete="SET NULL")))
    op.create_index("idx_tool_recommendations_tool", "tool_recommendations", ["tool_id"])
    # One-off backfill of the link that used to be implied by name/homepage: an exact-name tool wins over
    # a homepage match, then the lowest id.
    op.execute(
        """
        UPDATE tool_recommendations r SET tool_id = (
            SELECT t.id FROM tools t
            WHERE lower(t.name) = lower(r.name) OR (r.homepage_url IS NOT NULL AND t.homepage_url = r.homepage_url)
            ORDER BY (lower(t.name) = lower(r.name)) DESC, t.id
            LIMIT 1
        )
        """
    )


def downgrade() -> None:
    op.drop_index("idx_tool_recommendations_tool", table_name="tool_recommendations")
    op.drop_column("tool_recommendations", "tool_id")
