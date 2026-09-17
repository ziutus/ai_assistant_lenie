"""add verification/suspension dates and correspondence address to contact_organizations

CEIDG (and similar registries) status can change after the fact - a JDG that
existed at lookup time can later be suspended or closed. verified_at records
when a human last cross-checked this row against the source registry, so a
'confirmed' status can be judged as stale or fresh. suspended_at is the
registry's own suspension date (zawieszenie dzialalnosci gospodarczej) -
distinct from end_date, which means the affiliation itself ended.

correspondence_address (adres do doreczen) is a second, separate address a
registry entry can carry alongside the registered/business address already
in `address` - both are still the organization's own addresses, not the
contact's personal one.

Revision ID: b66730cf146e
Revises: 63f91b7e2a84
Create Date: 2026-09-17 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b66730cf146e'
down_revision: Union[str, Sequence[str], None] = '63f91b7e2a84'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE contact_organizations
            ADD COLUMN correspondence_address TEXT,
            ADD COLUMN suspended_at DATE,
            ADD COLUMN verified_at DATE
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE contact_organizations
            DROP COLUMN IF EXISTS correspondence_address,
            DROP COLUMN IF EXISTS suspended_at,
            DROP COLUMN IF EXISTS verified_at
        """
    )
