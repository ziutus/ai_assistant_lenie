"""Project cards: kind, free-form sections and the source PDF page for card-book families."""

from alembic import op

revision = "e2f6c0b4d8a5"
down_revision = "d1e5b9c3a7f4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE project_cards ADD COLUMN IF NOT EXISTS kind VARCHAR(20) NOT NULL DEFAULT 'project'")
    op.execute("ALTER TABLE project_cards ADD COLUMN IF NOT EXISTS sections JSONB NOT NULL DEFAULT '[]'::jsonb")
    op.execute("ALTER TABLE project_cards ADD COLUMN IF NOT EXISTS source_page SMALLINT")
    op.execute("CREATE INDEX IF NOT EXISTS idx_project_cards_kind ON project_cards (kind)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_project_cards_kind")
    op.execute("ALTER TABLE project_cards DROP COLUMN IF EXISTS source_page")
    op.execute("ALTER TABLE project_cards DROP COLUMN IF EXISTS sections")
    op.execute("ALTER TABLE project_cards DROP COLUMN IF EXISTS kind")
