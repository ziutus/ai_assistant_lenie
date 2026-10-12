"""Add an inline SVG illustration to project cards."""

from alembic import op

revision = "c9d3a7e1f5b2"
down_revision = "b4c8e1a9d2f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE project_cards ADD COLUMN IF NOT EXISTS illustration_svg TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE project_cards DROP COLUMN IF EXISTS illustration_svg")
