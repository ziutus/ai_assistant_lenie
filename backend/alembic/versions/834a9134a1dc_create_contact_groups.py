"""create contact_groups

Many-to-many grouping for the private contact book, independent of
contact_categories (a single-value "type" classification, e.g. "Osoba
prywatna"). A contact can belong to several groups at once — the motivating
case is a full Google Contacts export where the same person is both a
"Tuwima Gardens" neighbor and, say, "Rodzina" — something a single FK
can't represent. Mirrors the content_groups / document_group_memberships
pattern (library/db/models.py) but kept deliberately simpler (no
kind/priority_rank) since contact grouping here is plain user-managed
tagging, not the topic/priority distinction content groups need.

Revision ID: 834a9134a1dc
Revises: d70f0918d734
Create Date: 2026-08-24 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '834a9134a1dc'
down_revision: Union[str, Sequence[str], None] = 'd70f0918d734'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE contact_groups (
            id          SERIAL PRIMARY KEY,
            name        VARCHAR(100) UNIQUE NOT NULL,
            description TEXT,
            created_at  TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE contact_group_memberships (
            contact_id INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            group_id   INTEGER NOT NULL REFERENCES contact_groups(id) ON DELETE RESTRICT,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            PRIMARY KEY (contact_id, group_id)
        )
        """
    )
    op.execute("CREATE INDEX idx_contact_group_memberships_group_id ON contact_group_memberships (group_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS contact_group_memberships")
    op.execute("DROP TABLE IF EXISTS contact_groups")
