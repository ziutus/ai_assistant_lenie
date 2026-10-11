"""Add the storage key of the original source PDF to project cards."""

from alembic import op

revision = "d1e5b9c3a7f4"
down_revision = "c9d3a7e1f5b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE project_cards ADD COLUMN IF NOT EXISTS source_pdf_key TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE project_cards DROP COLUMN IF EXISTS source_pdf_key")
