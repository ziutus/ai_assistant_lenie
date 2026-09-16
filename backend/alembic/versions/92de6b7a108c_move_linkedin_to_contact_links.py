"""Move the current LinkedIn profile into generic contact links.

Revision ID: 92de6b7a108c
Revises: 7c4d8e1f2a3b
"""
from typing import Sequence, Union

from alembic import op

revision: str = "92de6b7a108c"
down_revision: Union[str, Sequence[str], None] = "7c4d8e1f2a3b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE contact_links DROP CONSTRAINT ck_contact_links_link_type")
    op.execute("""
        ALTER TABLE contact_links ADD CONSTRAINT ck_contact_links_link_type
        CHECK (link_type IN ('linkedin', 'facebook', 'instagram', 'twitter', 'website', 'other'))
    """)
    op.execute("""
        INSERT INTO contact_links (contact_id, link_type, url)
        SELECT id, 'linkedin', linkedin_url FROM contacts
        WHERE linkedin_url IS NOT NULL AND trim(linkedin_url) <> ''
    """)
    op.execute("ALTER TABLE contacts DROP COLUMN linkedin_url")


def downgrade() -> None:
    op.execute("ALTER TABLE contacts ADD COLUMN linkedin_url TEXT")
    # Lossy when multiple LinkedIn links exist: retain only the most recent one.
    op.execute("""
        UPDATE contacts AS c SET linkedin_url = latest.url
        FROM (
            SELECT DISTINCT ON (contact_id) contact_id, url
            FROM contact_links WHERE link_type = 'linkedin'
            ORDER BY contact_id, updated_at DESC, id DESC
        ) AS latest
        WHERE c.id = latest.contact_id
    """)
    op.execute("DELETE FROM contact_links WHERE link_type = 'linkedin'")
    op.execute("ALTER TABLE contact_links DROP CONSTRAINT ck_contact_links_link_type")
    op.execute("""
        ALTER TABLE contact_links ADD CONSTRAINT ck_contact_links_link_type
        CHECK (link_type IN ('facebook', 'instagram', 'twitter', 'website', 'other'))
    """)
