"""add obsidian_note_not_needed to document_chunks

Revision ID: a7c3e1f9d2b4
Revises: bc9846bcce94
Create Date: 2026-09-03 00:00:00.000000

A reviewer flag: this TEMAT chunk is not worth a standalone Obsidian note
(too thin / not interesting). It keeps the chunk in every other pipeline
(it still gets embedded when approved) but drops it from the "chunks still
missing an Obsidian note" counter and filter.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "a7c3e1f9d2b4"
down_revision: Union[str, None] = "bc9846bcce94"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "document_chunks",
        sa.Column(
            "obsidian_note_not_needed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("document_chunks", "obsidian_note_not_needed")
