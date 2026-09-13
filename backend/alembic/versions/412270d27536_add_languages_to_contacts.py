"""add languages to contacts

Languages a contact speaks, each entry {"language": str, "native": bool,
"level": str|None} — level is a CEFR code (A1-C2), only meaningful when
native is false. JSONB list rather than a free-text field so a contact can
record several languages with independent proficiency, similar in shape to
whatsapp_profile.

Revision ID: 412270d27536
Revises: f04c82e7b315
Create Date: 2026-09-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '412270d27536'
down_revision: Union[str, Sequence[str], None] = 'f04c82e7b315'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE contacts ADD COLUMN languages JSONB NOT NULL DEFAULT '[]'::jsonb")


def downgrade() -> None:
    op.execute("ALTER TABLE contacts DROP COLUMN IF EXISTS languages")
