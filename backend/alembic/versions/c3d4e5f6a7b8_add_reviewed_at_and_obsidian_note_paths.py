"""add reviewed_at and obsidian_note_paths columns to web_documents

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-03-30 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add reviewed_at TIMESTAMP and obsidian_note_paths JSONB columns."""
    op.add_column('web_documents', sa.Column('reviewed_at', sa.DateTime(), nullable=True))
    op.add_column('web_documents', sa.Column(
        'obsidian_note_paths', JSONB(), nullable=False, server_default=sa.text("'[]'"),
    ))


def downgrade() -> None:
    """Remove reviewed_at and obsidian_note_paths columns."""
    op.drop_column('web_documents', 'obsidian_note_paths')
    op.drop_column('web_documents', 'reviewed_at')
