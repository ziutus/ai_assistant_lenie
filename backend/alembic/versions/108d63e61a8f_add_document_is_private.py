"""add_document_is_private

Revision ID: 108d63e61a8f
Revises: fd3c56b44cc2
Create Date: 2026-09-13 07:20:28.049983

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '108d63e61a8f'
down_revision: Union[str, Sequence[str], None] = 'fd3c56b44cc2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("is_private", sa.Boolean(), nullable=False, server_default=sa.text("false")))


def downgrade() -> None:
    op.drop_column("documents", "is_private")
