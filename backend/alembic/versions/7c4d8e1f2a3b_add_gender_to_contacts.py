"""add gender to contacts

Useful as a disambiguation aid for foreign names/surnames where gender
isn't obvious from the name alone and no photo has been added yet (real
incident: a Korean contact's gender was mistakenly assumed from the name).

Revision ID: 7c4d8e1f2a3b
Revises: 3a9f2c1e0b7d
Create Date: 2026-09-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7c4d8e1f2a3b'
down_revision: Union[str, Sequence[str], None] = '3a9f2c1e0b7d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('contacts', sa.Column('gender', sa.String(20), nullable=True))
    op.create_check_constraint(
        'ck_contacts_gender',
        'contacts',
        "gender IN ('male', 'female', 'other')",
    )


def downgrade() -> None:
    op.drop_constraint('ck_contacts_gender', 'contacts', type_='check')
    op.drop_column('contacts', 'gender')
