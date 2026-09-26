"""partial dates for an address stay: year or month precision

"Lives there since 2016" is enough; nobody needs a made-up day. The stored
date stays a real ``date`` (first day of the period for valid_from, last day
for valid_to, so the existing ordering CHECK and "already ended" comparisons
keep working) and the precision says how much of it is meaningful. NULL means
a full day, which is what every existing row is.

Revision ID: b91d4e7a3c58
Revises: a4f8c2d6b913
Create Date: 2026-09-26 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'b91d4e7a3c58'
down_revision: Union[str, Sequence[str], None] = 'a4f8c2d6b913'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE contact_addresses ADD COLUMN valid_from_precision text, ADD COLUMN valid_to_precision text")
    op.execute(
        """
        ALTER TABLE contact_addresses ADD CONSTRAINT ck_contact_addresses_date_precision CHECK (
            (valid_from_precision IS NULL OR (valid_from IS NOT NULL AND valid_from_precision IN ('day', 'month', 'year')))
            AND (valid_to_precision IS NULL OR (valid_to IS NOT NULL AND valid_to_precision IN ('day', 'month', 'year')))
        )
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE contact_addresses DROP CONSTRAINT IF EXISTS ck_contact_addresses_date_precision")
    op.execute("ALTER TABLE contact_addresses DROP COLUMN IF EXISTS valid_to_precision, DROP COLUMN IF EXISTS valid_from_precision")
