"""add_contact_birthday_year

Revision ID: 7d6f4dbab8b1
Revises: b91d4e7a3c58
Create Date: 2026-09-28 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7d6f4dbab8b1'
down_revision: Union[str, Sequence[str], None] = 'b91d4e7a3c58'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("contacts", sa.Column("birthday_year", sa.SmallInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("contacts", "birthday_year")
