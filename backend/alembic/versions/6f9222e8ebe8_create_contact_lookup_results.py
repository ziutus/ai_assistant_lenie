"""create contact_lookup_results

Records OSINT lookup attempts made for a private contact (e.g. by the
/lenie-person-lookup skill) — both "searched and found nothing" (status
no_results, e.g. a phone number search) and "found a possible match but not
confirmed" (status candidate, e.g. a LinkedIn profile that might be the
right person). A contact can accumulate several candidate rows of the same
lookup_type (several plausible LinkedIn profiles); confirming one is a
status update here plus, by convention, copying its url into the existing
single-valued contacts.linkedin_url — this table never replaces that column,
it just tracks the search trail leading up to it.

Revision ID: 6f9222e8ebe8
Revises: 27a6dc4749c3
Create Date: 2026-08-23 22:10:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '6f9222e8ebe8'
down_revision: Union[str, Sequence[str], None] = '27a6dc4749c3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE contact_lookup_results (
            id           SERIAL PRIMARY KEY,
            contact_id   INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            lookup_type  VARCHAR(30) NOT NULL,
            status       VARCHAR(20) NOT NULL,
            url          TEXT,
            query_used   TEXT,
            notes        TEXT,
            searched_at  TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT ck_contact_lookup_results_lookup_type
                CHECK (lookup_type IN ('phone', 'linkedin', 'web')),
            CONSTRAINT ck_contact_lookup_results_status
                CHECK (status IN ('no_results', 'candidate', 'confirmed', 'rejected'))
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_contact_lookup_results_contact ON contact_lookup_results (contact_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS contact_lookup_results")
