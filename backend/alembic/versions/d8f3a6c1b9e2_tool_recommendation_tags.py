"""tool_recommendations.tags: free-form lowercase tags (docker, kubernetes, ...) next to the single catalog category

Revision ID: d8f3a6c1b9e2
Revises: c5a2e8b4d1f7
Create Date: 2026-10-23
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "d8f3a6c1b9e2"
down_revision = "c5a2e8b4d1f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tool_recommendations",
        sa.Column("tags", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
    )
    op.create_index("idx_tool_recommendations_tags", "tool_recommendations", ["tags"], postgresql_using="gin")


def downgrade() -> None:
    op.drop_index("idx_tool_recommendations_tags", table_name="tool_recommendations")
    op.drop_column("tool_recommendations", "tags")
