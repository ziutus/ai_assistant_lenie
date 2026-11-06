"""Add organizations.links ([{url, label}], e.g. Wikipedia) — same shape as persons.links."""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b6e1d4a8c273"
down_revision = "a4c8e2f6b913"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "organizations",
        sa.Column("links", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
    )


def downgrade():
    op.drop_column("organizations", "links")
