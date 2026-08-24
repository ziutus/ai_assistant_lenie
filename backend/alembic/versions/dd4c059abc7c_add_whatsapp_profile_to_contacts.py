"""add whatsapp_profile to contacts

Structured social-memory-aid profile (occupation, hobbies, pets, recent
events, small-talk suggestions — see imports/whatsapp_neighbor_profiles.py)
built incrementally from WhatsApp neighbor-group chats, keyed per contact
rather than living in a separate synthetic Document ("Sąsiad: ..." /
whatsapp://... URL). Moving it onto Contact removes the duplicate place a
person's info had to be looked up in — the whatsapp:// Documents this
replaces are deleted by
imports/whatsapp_neighbor_profiles_migrate_to_contacts.py.

Revision ID: dd4c059abc7c
Revises: 834a9134a1dc
Create Date: 2026-08-24 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'dd4c059abc7c'
down_revision: Union[str, Sequence[str], None] = '834a9134a1dc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE contacts ADD COLUMN whatsapp_profile JSONB")


def downgrade() -> None:
    op.execute("ALTER TABLE contacts DROP COLUMN IF EXISTS whatsapp_profile")
