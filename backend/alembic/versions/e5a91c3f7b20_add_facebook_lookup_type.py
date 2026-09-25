"""add facebook to contact_lookup_results lookup_type

The lenie-contact-facebook-enrich skill records each profile check (what was
found, what was missing or hidden by privacy settings) so the same profile is
not re-scraped again and again.

Revision ID: e5a91c3f7b20
Revises: b7e41c9a620d
Create Date: 2026-09-25 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'e5a91c3f7b20'
down_revision: Union[str, Sequence[str], None] = 'b7e41c9a620d'
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
            CHECK (lookup_type IN ('phone', 'linkedin', 'web', 'email', 'facebook'))
        """
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM contact_lookup_results WHERE lookup_type = 'facebook'"
    )
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
