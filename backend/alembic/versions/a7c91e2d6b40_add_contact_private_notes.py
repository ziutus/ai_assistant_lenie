"""add_contact_private_notes

Revision ID: a7c91e2d6b40
Revises: 18ae0750559d
Create Date: 2026-09-14 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7c91e2d6b40'
down_revision: Union[str, Sequence[str], None] = '18ae0750559d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("contacts", sa.Column("private_notes", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("contacts", "private_notes")
