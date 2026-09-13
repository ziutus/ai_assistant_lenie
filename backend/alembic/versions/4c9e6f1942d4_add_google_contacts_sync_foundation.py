"""add google contacts sync foundation

Schema groundwork for a future Google Contacts (People API) sync — no sync
logic exists yet, this is purely additive:

1. contacts.google_etag — Google's per-resource version stamp (paired with
   the existing google_contact_resource_name), required by the People API
   to detect concurrent edits before writing a contact back.
2. contact_groups.google_group_resource_name — Google's contactGroups are
   their own top-level resource with their own resourceName/etag, so a
   local group needs its Google counterpart's resourceName recorded once
   created via the API.
3. contact_phones / contact_emails — contacts.phone_number/email stay
   single-value "headline" fields (unchanged); these new tables are the
   structured, multi-row picture a real sync needs, mirroring the existing
   company/position-vs-contact_organizations split. Google's People API
   represents phones/emails as repeated, labeled values
   (phoneNumbers[]/emailAddresses[]) — collapsing them to one value each,
   as imports/google_contacts_import.py's CSV import does today, would
   lose data on any real two-way sync.

Revision ID: 4c9e6f1942d4
Revises: 18ae0750559d
Create Date: 2026-09-13 12:05:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '4c9e6f1942d4'
down_revision: Union[str, Sequence[str], None] = '18ae0750559d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE contacts ADD COLUMN google_etag VARCHAR(255)")
    op.execute("ALTER TABLE contact_groups ADD COLUMN google_group_resource_name VARCHAR(255) UNIQUE")

    op.execute(
        """
        CREATE TABLE contact_phones (
            id            SERIAL PRIMARY KEY,
            contact_id    INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            label         VARCHAR(20) NOT NULL DEFAULT 'other',
            value         VARCHAR(30) NOT NULL,
            is_primary    BOOLEAN NOT NULL DEFAULT FALSE,
            notes         TEXT,
            created_at    TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at    TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT ck_contact_phones_label CHECK (label IN ('mobile', 'home', 'work', 'other'))
        )
        """
    )
    op.execute("CREATE INDEX idx_contact_phones_contact ON contact_phones (contact_id)")

    op.execute(
        """
        CREATE TABLE contact_emails (
            id            SERIAL PRIMARY KEY,
            contact_id    INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            label         VARCHAR(20) NOT NULL DEFAULT 'other',
            value         VARCHAR(255) NOT NULL,
            is_primary    BOOLEAN NOT NULL DEFAULT FALSE,
            notes         TEXT,
            created_at    TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at    TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT ck_contact_emails_label CHECK (label IN ('home', 'work', 'other'))
        )
        """
    )
    op.execute("CREATE INDEX idx_contact_emails_contact ON contact_emails (contact_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS contact_emails")
    op.execute("DROP TABLE IF EXISTS contact_phones")
    op.execute("ALTER TABLE contact_groups DROP COLUMN IF EXISTS google_group_resource_name")
    op.execute("ALTER TABLE contacts DROP COLUMN IF EXISTS google_etag")
