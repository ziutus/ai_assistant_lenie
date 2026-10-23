"""tool_recommendations.status accepts 'phasing_out' (a tool still in use that the owner is moving away from)

Revision ID: b4f1d7a3c9e2
Revises: a3e9c6d2b8f1
Create Date: 2026-10-23
"""

from alembic import op

revision = "b4f1d7a3c9e2"
down_revision = "a3e9c6d2b8f1"
branch_labels = None
depends_on = None

OLD = "status IN ('watchlist', 'compare', 'testing', 'adopted', 'rejected', 'archived')"
NEW = "status IN ('watchlist', 'compare', 'testing', 'adopted', 'phasing_out', 'rejected', 'archived')"


def upgrade() -> None:
    op.drop_constraint("ck_tool_recommendations_status", "tool_recommendations", type_="check")
    op.create_check_constraint("ck_tool_recommendations_status", "tool_recommendations", NEW)


def downgrade() -> None:
    op.execute("UPDATE tool_recommendations SET status = 'archived' WHERE status = 'phasing_out'")
    op.drop_constraint("ck_tool_recommendations_status", "tool_recommendations", type_="check")
    op.create_check_constraint("ck_tool_recommendations_status", "tool_recommendations", OLD)
