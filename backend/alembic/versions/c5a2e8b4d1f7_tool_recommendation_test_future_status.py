"""tool_recommendations.status accepts 'test_future' (to be tested later, e.g. once suitable hardware is bought)

Revision ID: c5a2e8b4d1f7
Revises: b4f1d7a3c9e2
Create Date: 2026-10-23
"""

from alembic import op

revision = "c5a2e8b4d1f7"
down_revision = "b4f1d7a3c9e2"
branch_labels = None
depends_on = None

OLD = "status IN ('watchlist', 'compare', 'testing', 'adopted', 'phasing_out', 'rejected', 'archived')"
NEW = "status IN ('watchlist', 'compare', 'testing', 'test_future', 'adopted', 'phasing_out', 'rejected', 'archived')"


def upgrade() -> None:
    op.drop_constraint("ck_tool_recommendations_status", "tool_recommendations", type_="check")
    op.create_check_constraint("ck_tool_recommendations_status", "tool_recommendations", NEW)


def downgrade() -> None:
    op.execute("UPDATE tool_recommendations SET status = 'watchlist' WHERE status = 'test_future'")
    op.drop_constraint("ck_tool_recommendations_status", "tool_recommendations", type_="check")
    op.create_check_constraint("ck_tool_recommendations_status", "tool_recommendations", OLD)
