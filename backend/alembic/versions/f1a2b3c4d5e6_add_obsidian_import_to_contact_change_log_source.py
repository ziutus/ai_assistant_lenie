"""add obsidian_import to contact_change_log source check constraint

PR #667 added "obsidian_import" to the Python-level CONTACT_CHANGE_SOURCES
tuple (library/contact_change_log.py) but missed the database-level CHECK
constraint created in bc9846bcce94_create_contact_change_log.py, so any
insert with source="obsidian_import" fails with a CheckViolation.

Revision ID: f1a2b3c4d5e6
Revises: a72d9e41bc06
Create Date: 2026-09-14 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = 'a72d9e41bc06'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE contact_change_log DROP CONSTRAINT ck_contact_change_log_source")
    op.execute(
        """
        ALTER TABLE contact_change_log
            ADD CONSTRAINT ck_contact_change_log_source
                CHECK (source IN (
                    'manual_edit', 'google_import', 'linkedin_analysis',
                    'whatsapp_analysis', 'osint_lookup', 'other', 'obsidian_import'
                ))
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE contact_change_log DROP CONSTRAINT ck_contact_change_log_source")
    op.execute(
        """
        ALTER TABLE contact_change_log
            ADD CONSTRAINT ck_contact_change_log_source
                CHECK (source IN (
                    'manual_edit', 'google_import', 'linkedin_analysis',
                    'whatsapp_analysis', 'osint_lookup', 'other'
                ))
        """
    )
