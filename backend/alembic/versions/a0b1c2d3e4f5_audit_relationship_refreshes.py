"""audit relationship refreshes and preserve approved organizations

Revision ID: a0b1c2d3e4f5
Revises: ff6a7b8c9d0e
"""
from alembic import op

revision = "a0b1c2d3e4f5"
down_revision = "ff6a7b8c9d0e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE document_organizations ADD COLUMN IF NOT EXISTS review_status VARCHAR(30) NOT NULL DEFAULT 'auto_accepted'")
    op.execute("""CREATE TABLE IF NOT EXISTS document_relationship_removals (
        id BIGSERIAL PRIMARY KEY, document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
        relation_type VARCHAR(40) NOT NULL, original_row_id BIGINT, snapshot JSONB NOT NULL,
        removal_reason VARCHAR(80) NOT NULL, removed_at TIMESTAMP NOT NULL DEFAULT NOW())""")
    op.execute("CREATE INDEX IF NOT EXISTS idx_document_relationship_removals_doc_time ON document_relationship_removals (document_id, removed_at DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS document_relationship_removals")
    op.execute("ALTER TABLE document_organizations DROP COLUMN IF EXISTS review_status")
