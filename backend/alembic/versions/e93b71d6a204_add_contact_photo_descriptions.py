"""Give existing contact photos shared, independently editable descriptions."""

from alembic import op

revision = "e93b71d6a204"
down_revision = "8b07952a8f81"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE contact_photos (
            storage_key TEXT PRIMARY KEY,
            user_description TEXT,
            user_description_revision INTEGER NOT NULL DEFAULT 0,
            ai_descriptions JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMP NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        INSERT INTO contact_photos (storage_key)
        SELECT DISTINCT photo_storage_key FROM contacts
        WHERE photo_storage_key IS NOT NULL
    """)
    op.create_foreign_key(
        "fk_contacts_photo_storage_key", "contacts", "contact_photos",
        ["photo_storage_key"], ["storage_key"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_contacts_photo_storage_key", "contacts", type_="foreignkey")
    op.drop_table("contact_photos")
