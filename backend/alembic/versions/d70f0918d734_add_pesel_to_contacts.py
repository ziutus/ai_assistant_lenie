"""add pesel to contacts

PESEL is a stable Polish national ID number for a private individual —
unlike NIP/REGON (company identifiers, already on contact_organizations),
it belongs on the person-level Contact row. It also encodes the date of
birth (library/pesel.py decodes it), which backfills contacts.birthday for
individuals matched from external data sources that carry a PESEL (e.g. a
court registry export) but not a birthday directly.

Revision ID: d70f0918d734
Revises: 8a1b2c3d4e5f
Create Date: 2026-08-24 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'd70f0918d734'
down_revision: Union[str, Sequence[str], None] = '8a1b2c3d4e5f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE contacts ADD COLUMN pesel VARCHAR(11)")
    op.execute("CREATE UNIQUE INDEX idx_contacts_pesel ON contacts (pesel) WHERE pesel IS NOT NULL")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_contacts_pesel")
    op.execute("ALTER TABLE contacts DROP COLUMN IF EXISTS pesel")
