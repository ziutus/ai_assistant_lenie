"""add obsidian source hash column

Revision ID: 0f9ca717603a
Revises: ac7ab74c95bd
Create Date: 2026-08-17 16:31:37.438760

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0f9ca717603a'
down_revision: Union[str, Sequence[str], None] = 'ac7ab74c95bd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("documents", sa.Column("obsidian_source_hash", sa.String(64), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("documents", "obsidian_source_hash")
