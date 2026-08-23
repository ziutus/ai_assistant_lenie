"""create contacts tables

Private contact book (personal CRM), independent of the NER persons/
document_persons registry (library/person_registry.py) — a contact here
may never appear in any document. category_id is a lookup FK
(contact_categories) rather than a free-text column, per the user's explicit
choice, so new categories can be managed from the UI without a migration.
contact_relationships is directional and single-row: relationship_type
describes what related_contact_id is to contact_id (e.g. contact_id=Adam,
related_contact_id=Zofia, relationship_type="żona" reads "Zofia is Adam's
wife") — no automatic reciprocal row/label is generated.

Revision ID: 27a6dc4749c3
Revises: c2a3b4c5d6e7
Create Date: 2026-08-23 21:24:33.960729

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '27a6dc4749c3'
down_revision: Union[str, Sequence[str], None] = 'c2a3b4c5d6e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE contact_categories (
            id          SERIAL PRIMARY KEY,
            name        VARCHAR UNIQUE NOT NULL,
            description TEXT,
            is_active   BOOLEAN NOT NULL DEFAULT TRUE,
            created_at  TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "INSERT INTO contact_categories (name) VALUES ('Osoba prywatna')"
    )
    op.execute(
        """
        CREATE TABLE contacts (
            id                           SERIAL PRIMARY KEY,
            uuid                         VARCHAR(100) NOT NULL DEFAULT gen_random_uuid() UNIQUE,
            category_id                  INTEGER NOT NULL REFERENCES contact_categories(id),
            first_name                   VARCHAR(100),
            last_name                    VARCHAR(100) NOT NULL,
            phone_number                 VARCHAR(30),
            email                        VARCHAR(255),
            linkedin_url                 TEXT,
            company                      VARCHAR(200),
            position                     VARCHAR(200),
            address                      TEXT,
            birthday                     DATE,
            notes                        TEXT,
            google_contact_resource_name VARCHAR(255) UNIQUE,
            created_at                   TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at                   TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX idx_contacts_last_name ON contacts (last_name)")
    op.execute("CREATE INDEX idx_contacts_category ON contacts (category_id)")
    op.execute(
        """
        CREATE TABLE contact_relationships (
            id                 SERIAL PRIMARY KEY,
            contact_id         INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            related_contact_id INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            relationship_type  VARCHAR(50) NOT NULL,
            note               TEXT,
            created_at         TIMESTAMP NOT NULL DEFAULT NOW(),
            CHECK (contact_id != related_contact_id),
            UNIQUE (contact_id, related_contact_id, relationship_type)
        )
        """
    )
    op.execute("CREATE INDEX idx_contact_relationships_contact ON contact_relationships (contact_id)")
    op.execute("CREATE INDEX idx_contact_relationships_related ON contact_relationships (related_contact_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS contact_relationships")
    op.execute("DROP TABLE IF EXISTS contacts")
    op.execute("DROP TABLE IF EXISTS contact_categories")
