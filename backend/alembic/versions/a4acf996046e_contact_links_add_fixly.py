"""Add fixly to contact_links.link_type."""
from alembic import op

revision = "a4acf996046e"
down_revision = "f001eb38307e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE contact_links DROP CONSTRAINT ck_contact_links_link_type")
    op.execute("""
        ALTER TABLE contact_links ADD CONSTRAINT ck_contact_links_link_type
        CHECK (link_type IN ('linkedin', 'facebook', 'instagram', 'twitter', 'website', 'fixly', 'other'))
    """)


def downgrade() -> None:
    op.execute("UPDATE contact_links SET link_type = 'other' WHERE link_type = 'fixly'")
    op.execute("ALTER TABLE contact_links DROP CONSTRAINT ck_contact_links_link_type")
    op.execute("""
        ALTER TABLE contact_links ADD CONSTRAINT ck_contact_links_link_type
        CHECK (link_type IN ('linkedin', 'facebook', 'instagram', 'twitter', 'website', 'other'))
    """)
