"""Photo identity, classification and persistent contact links."""
from alembic import op

revision = "b7e41c9a620d"
down_revision = "a5c27d9e4b18"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""ALTER TABLE contact_photos
        ADD COLUMN id UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
        ADD COLUMN subject_kind TEXT NOT NULL DEFAULT 'unknown'
            CONSTRAINT ck_contact_photos_subject_kind CHECK (subject_kind IN ('people', 'no_people', 'unknown')),
        ADD COLUMN people_count INTEGER CONSTRAINT ck_contact_photos_people_count CHECK (people_count >= 0),
        ADD COLUMN classification_revision INTEGER NOT NULL DEFAULT 0""")
    op.execute("""CREATE TABLE contact_photo_links (
        contact_id INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
        storage_key TEXT NOT NULL REFERENCES contact_photos(storage_key),
        depicts_contact BOOLEAN,
        revision INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMP NOT NULL DEFAULT now(),
        PRIMARY KEY (contact_id, storage_key))""")
    op.execute("""INSERT INTO contact_photo_links (contact_id, storage_key)
        SELECT id, photo_storage_key FROM contacts WHERE photo_storage_key IS NOT NULL""")


def downgrade():
    op.drop_table("contact_photo_links")
    for column in ("classification_revision", "people_count", "subject_kind", "id"):
        op.drop_column("contact_photos", column)
