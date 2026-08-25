"""create contact_change_log

Append-only audit trail for private contacts (Contact, library/contact_routes.py)
— answers "how was this contact's data added/updated, and why" without
resorting to full row versioning. One row per create/update event: `source`
says where the data came from (manual edit in the UI, Google Contacts CSV
import, WhatsApp chat analysis, a confirmed LinkedIn/OSINT lookup, ...),
`changed_fields` is the list of Contact columns that changed in that event
(diffed by the caller before commit), `note` is an optional free-text reason
a human or a script can attach. contacts.updated_at stays the fast "last
touched" timestamp; this table is the full trail behind it.

Revision ID: bc9846bcce94
Revises: 07dd233ecf10
Create Date: 2026-08-25 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'bc9846bcce94'
down_revision: Union[str, Sequence[str], None] = '07dd233ecf10'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE contact_change_log (
            id             SERIAL PRIMARY KEY,
            contact_id     INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            source         VARCHAR(30) NOT NULL,
            changed_fields VARCHAR(50)[] NOT NULL DEFAULT '{}',
            note           TEXT,
            created_at     TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT ck_contact_change_log_source
                CHECK (source IN (
                    'manual_edit', 'google_import', 'linkedin_analysis',
                    'whatsapp_analysis', 'osint_lookup', 'other'
                ))
        )
        """
    )
    op.execute("CREATE INDEX idx_contact_change_log_contact ON contact_change_log (contact_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS contact_change_log")
