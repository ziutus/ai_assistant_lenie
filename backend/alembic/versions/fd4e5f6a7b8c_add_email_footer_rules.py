"""Add sender identity and reusable email footer rules.

Revision ID: fd4e5f6a7b8c
Revises: fc3d4e5f6a7b
Create Date: 2026-08-11 00:00:00.000000
"""

from alembic import op

revision = "fd4e5f6a7b8c"
down_revision = "fc3d4e5f6a7b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS email_sender VARCHAR(320)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_documents_email_sender ON documents (email_sender)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS email_footer_rules (
            id SERIAL PRIMARY KEY,
            sender_email VARCHAR(320) NOT NULL,
            footer_text TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_email_footer_rules_sender_email UNIQUE (sender_email)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS email_footer_rules")
    op.execute("DROP INDEX IF EXISTS ix_documents_email_sender")
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS email_sender")
