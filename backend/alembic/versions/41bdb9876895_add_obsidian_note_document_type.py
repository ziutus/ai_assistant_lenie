"""add obsidian_note document type

Revision ID: 41bdb9876895
Revises: 2c3d4e5f6a7b
Create Date: 2026-08-17 12:07:46.508460

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '41bdb9876895'
down_revision: Union[str, Sequence[str], None] = '2c3d4e5f6a7b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add 'obsidian_note' to the document_types lookup table (Epic 42, Story 42.1)."""
    op.execute("""
        INSERT INTO document_types (name) VALUES ('obsidian_note')
        ON CONFLICT (name) DO NOTHING
    """)


def downgrade() -> None:
    """Remove 'obsidian_note' from the document_types lookup table."""
    op.execute("DELETE FROM document_types WHERE name = 'obsidian_note'")
