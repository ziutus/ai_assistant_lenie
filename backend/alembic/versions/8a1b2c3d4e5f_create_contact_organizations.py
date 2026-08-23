"""create contact_organizations

A contact can have several simultaneous organizational affiliations — the
common Polish pattern this table is built for is one JDG (jednoosobowa
dzialalnosc gospodarcza, sole proprietorship, often opened purely for tax
optimization) alongside a separate full-time job elsewhere, plus maybe an
unpaid board seat in an association. contacts.company/position stay as a
single-value "headline" affiliation (unchanged, still shown in list views);
this table is where every affiliation - including that headline one, if the
user chooses to duplicate it here - gets tracked with its own type, dates,
registry numbers and provenance.

org_type: 'employment' (etat/umowa o prace), 'jdg' (jednoosobowa dzialalnosc
gospodarcza), 'board' (funkcja w zarzadzie/stowarzyszeniu bez wlasnosci),
'ownership' (udzialy/wspolwlasnosc spolki, nie JDG), 'other' (zlecenie, B2B
kontrakt, wolontariat itp.).

status mirrors contact_lookup_results ('candidate'/'confirmed'/'rejected')
so an OSINT hit ("prawdopodobnie ma JDG X") can be recorded here directly as
status='candidate' and promoted later, instead of only living as free text
in contacts.notes or a contact_lookup_results row.

address is this organization's own (registered/business) address - kept
separate from contacts.address, which is the contact's personal/home
address. Registering a JDG at one's home address is common in Poland, but
that's a hypothesis to verify per-contact, never assumed automatically.

Revision ID: 8a1b2c3d4e5f
Revises: 6f9222e8ebe8
Create Date: 2026-08-23 21:15:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '8a1b2c3d4e5f'
down_revision: Union[str, Sequence[str], None] = '6f9222e8ebe8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE contact_organizations (
            id                SERIAL PRIMARY KEY,
            contact_id        INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            org_type          VARCHAR(20) NOT NULL,
            organization_name VARCHAR(255) NOT NULL,
            role              VARCHAR(200),
            nip               VARCHAR(15),
            regon             VARCHAR(20),
            address           TEXT,
            is_primary        BOOLEAN NOT NULL DEFAULT FALSE,
            is_current        BOOLEAN NOT NULL DEFAULT TRUE,
            start_date        DATE,
            end_date          DATE,
            status            VARCHAR(20) NOT NULL DEFAULT 'confirmed',
            source_url        TEXT,
            notes             TEXT,
            created_at        TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at        TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT ck_contact_organizations_org_type
                CHECK (org_type IN ('employment', 'jdg', 'board', 'ownership', 'other')),
            CONSTRAINT ck_contact_organizations_status
                CHECK (status IN ('candidate', 'confirmed', 'rejected'))
        )
        """
    )
    op.execute("CREATE INDEX idx_contact_organizations_contact ON contact_organizations (contact_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS contact_organizations")
