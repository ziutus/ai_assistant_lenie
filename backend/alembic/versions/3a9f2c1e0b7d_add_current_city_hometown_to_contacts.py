"""add current_city and hometown to contacts

Structured small-talk-relevant facts (where a contact currently lives,
where they originally come from) surfaced e.g. on a Facebook profile's
"Informacje" tab. Kept separate from the pre-existing `address` column,
which holds a full postal/home address rather than a casual "lives in
city X" fact.

Revision ID: 3a9f2c1e0b7d
Revises: 299034ef547c
Create Date: 2026-09-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3a9f2c1e0b7d'
down_revision: Union[str, Sequence[str], None] = '299034ef547c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('contacts', sa.Column('current_city', sa.String(200), nullable=True))
    op.add_column('contacts', sa.Column('hometown', sa.String(200), nullable=True))


def downgrade() -> None:
    op.drop_column('contacts', 'hometown')
    op.drop_column('contacts', 'current_city')
