"""add email to contact_lookup_results lookup_type

OSINT-discovered emails (e.g. found in a public CEIDG/KRS business registry
entry while verifying a contact's company affiliation) need the same
candidate/confirmed/rejected provenance tracking already used for phone/
linkedin/web lookups, instead of being silently written into
contacts.email_addresses with no trail of where they came from.

Revision ID: d3f7a1c9b8e2
Revises: c4e8b1a93d72
Create Date: 2026-09-22 05:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'd3f7a1c9b8e2'
down_revision: Union[str, Sequence[str], None] = 'c4e8b1a93d72'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE contact_lookup_results DROP CONSTRAINT ck_contact_lookup_results_lookup_type"
    )
    op.execute(
        """
        ALTER TABLE contact_lookup_results
            ADD CONSTRAINT ck_contact_lookup_results_lookup_type
            CHECK (lookup_type IN ('phone', 'linkedin', 'web', 'email'))
        """
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM contact_lookup_results WHERE lookup_type = 'email'"
    )
    op.execute(
        "ALTER TABLE contact_lookup_results DROP CONSTRAINT ck_contact_lookup_results_lookup_type"
    )
    op.execute(
        """
        ALTER TABLE contact_lookup_results
            ADD CONSTRAINT ck_contact_lookup_results_lookup_type
            CHECK (lookup_type IN ('phone', 'linkedin', 'web'))
        """
    )
