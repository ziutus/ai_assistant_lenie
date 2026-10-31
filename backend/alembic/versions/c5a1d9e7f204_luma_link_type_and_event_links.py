"""Add the luma contact link type and per-event links.

Revision ID: c5a1d9e7f204
Revises: b8e4f6a2c913
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c5a1d9e7f204"
down_revision: Union[str, Sequence[str], None] = "b8e4f6a2c913"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_LUMA_URL = r"^https?://(www\.)?(luma\.com|lu\.ma)/user/"


def upgrade() -> None:
    op.execute("ALTER TABLE contact_links DROP CONSTRAINT ck_contact_links_link_type")
    op.execute("""
        ALTER TABLE contact_links ADD CONSTRAINT ck_contact_links_link_type
        CHECK (link_type IN ('linkedin', 'facebook', 'instagram', 'twitter', 'website', 'fixly', 'luma', 'other'))
    """)
    op.execute(f"UPDATE contact_links SET link_type = 'luma' WHERE link_type = 'other' AND url ~* '{_LUMA_URL}'")
    op.create_table(
        "contact_group_event_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_id", sa.Integer(), sa.ForeignKey("contact_group_events.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("link_type", sa.String(20), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("label", sa.String(200)),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("link_type IN ('luma', 'meetup', 'slides', 'recording', 'other')",
                           name="ck_contact_group_event_links_link_type"),
    )
    op.create_index("idx_contact_group_event_links_event", "contact_group_event_links", ["event_id"])


def downgrade() -> None:
    op.drop_index("idx_contact_group_event_links_event", table_name="contact_group_event_links")
    op.drop_table("contact_group_event_links")
    op.execute("UPDATE contact_links SET link_type = 'other' WHERE link_type = 'luma'")
    op.execute("ALTER TABLE contact_links DROP CONSTRAINT ck_contact_links_link_type")
    op.execute("""
        ALTER TABLE contact_links ADD CONSTRAINT ck_contact_links_link_type
        CHECK (link_type IN ('linkedin', 'facebook', 'instagram', 'twitter', 'website', 'fixly', 'other'))
    """)
