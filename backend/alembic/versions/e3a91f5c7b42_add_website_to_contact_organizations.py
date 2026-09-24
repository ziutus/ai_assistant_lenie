"""add website to contact_organizations and backfill it from notes

CEIDG imports used to append "www: <host>" to the free-text `notes`, which
made the address neither clickable nor searchable. `website` is a proper
column; existing rows get the value moved out of `notes`.

Revision ID: e3a91f5c7b42
Revises: b7e29c4a8d10
Create Date: 2026-09-24 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "e3a91f5c7b42"
down_revision: Union[str, Sequence[str], None] = "b7e29c4a8d10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE contact_organizations ADD COLUMN website TEXT")
    # notes look like "tel.: X, e-mail: Y, www: Z" (parts optional, www last).
    # Take the first "www: <token>" as website, then strip that segment from notes.
    op.execute(
        r"""
        UPDATE contact_organizations
        SET website = substring(notes from '(?:^|,\s*)www:\s*([^,\s]+)')
        WHERE website IS NULL AND notes ~ '(?:^|,\s*)www:\s*[^,\s]+'
        """
    )
    op.execute(
        r"""
        UPDATE contact_organizations
        SET notes = NULLIF(
            btrim(regexp_replace(notes, '(?:^|,\s*)www:\s*[^,\s]+', '', 'g'), ', '),
            ''
        )
        WHERE website IS NOT NULL AND notes ~ '(?:^|,\s*)www:\s*[^,\s]+'
        """
    )


def downgrade() -> None:
    # Put the value back into notes so nothing is lost.
    op.execute(
        """
        UPDATE contact_organizations
        SET notes = CASE WHEN notes IS NULL OR notes = '' THEN 'www: ' || website
                         ELSE notes || ', www: ' || website END
        WHERE website IS NOT NULL
        """
    )
    op.execute("ALTER TABLE contact_organizations DROP COLUMN IF EXISTS website")
