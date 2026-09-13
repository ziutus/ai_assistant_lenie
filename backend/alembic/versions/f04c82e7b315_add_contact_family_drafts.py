"""Allow unnamed contacts and atomic, retryable family creation."""

from alembic import op

revision = "f04c82e7b315"
down_revision = "e93b71d6a204"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE contacts ALTER COLUMN last_name DROP NOT NULL")
    op.execute("ALTER TABLE contacts ADD COLUMN display_label VARCHAR(200)")
    op.execute("""
        CREATE TABLE contact_family_creations (
            request_id VARCHAR(36) PRIMARY KEY,
            contact_id INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            request_payload JSONB NOT NULL,
            result JSONB NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT now()
        )
    """)


def downgrade() -> None:
    # Do not invent surnames or silently destroy unnamed family members.
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM contacts WHERE last_name IS NULL) THEN
                RAISE EXCEPTION 'Cannot downgrade while contacts without surnames exist';
            END IF;
        END $$
    """)
    op.drop_table("contact_family_creations")
    op.drop_column("contacts", "display_label")
    op.execute("ALTER TABLE contacts ALTER COLUMN last_name SET NOT NULL")
