"""create contact_links

Generic multi-value social/profile link storage for a contact (Facebook,
Instagram, X/Twitter, personal website, other). contacts.linkedin_url stays
as the pre-existing single-value legacy field and is not migrated into this
table — adding this table only closes the gap for every other platform,
where the contact edit form previously had nowhere to put a URL.

Revision ID: 299034ef547c
Revises: f1a2b3c4d5e6
Create Date: 2026-09-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '299034ef547c'
down_revision: Union[str, Sequence[str], None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE contact_links (
            id           SERIAL PRIMARY KEY,
            contact_id   INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            link_type    VARCHAR(20) NOT NULL,
            url          TEXT NOT NULL,
            label        VARCHAR(200),
            created_at   TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at   TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT ck_contact_links_link_type
                CHECK (link_type IN ('facebook', 'instagram', 'twitter', 'website', 'other'))
        )
        """
    )
    op.execute("CREATE INDEX idx_contact_links_contact ON contact_links (contact_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS contact_links")
