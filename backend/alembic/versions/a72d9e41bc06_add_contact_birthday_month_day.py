"""add_contact_birthday_month_day

Revision ID: a72d9e41bc06
Revises: b4cfbc7ccf11
Create Date: 2026-09-14 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a72d9e41bc06'
down_revision: Union[str, Sequence[str], None] = 'b4cfbc7ccf11'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("contacts", sa.Column("birthday_month", sa.SmallInteger(), nullable=True))
    op.add_column("contacts", sa.Column("birthday_day", sa.SmallInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("contacts", "birthday_day")
    op.drop_column("contacts", "birthday_month")
