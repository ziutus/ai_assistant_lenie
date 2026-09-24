"""add registry to contact_organizations (which official register the entity is in)

org_type describes the *person's relation* to the organization (employment,
board, ...), not the entity's legal form, so it cannot tell whether to look the
entity up in CEIDG (sole proprietorships) or KRS (companies, foundations, ...).
`registry` records that explicitly: 'ceidg', 'krs', 'other'; NULL = not known
yet (the UI then offers both registers).

Existing 'jdg' rows are by definition CEIDG entries, so they are backfilled.

Revision ID: a5c27d9e4b18
Revises: e3a91f5c7b42
Create Date: 2026-09-24 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "a5c27d9e4b18"
down_revision: Union[str, Sequence[str], None] = "e3a91f5c7b42"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE contact_organizations ADD COLUMN registry VARCHAR(10)")
    op.execute(
        "ALTER TABLE contact_organizations ADD CONSTRAINT ck_contact_organizations_registry "
        "CHECK (registry IS NULL OR registry IN ('ceidg', 'krs', 'other'))"
    )
    op.execute("UPDATE contact_organizations SET registry = 'ceidg' WHERE org_type = 'jdg'")


def downgrade() -> None:
    op.execute("ALTER TABLE contact_organizations DROP CONSTRAINT IF EXISTS ck_contact_organizations_registry")
    op.execute("ALTER TABLE contact_organizations DROP COLUMN IF EXISTS registry")
