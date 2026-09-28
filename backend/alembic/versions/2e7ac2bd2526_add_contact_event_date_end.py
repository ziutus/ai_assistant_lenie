"""add_contact_event_date_end

Revision ID: 2e7ac2bd2526
Revises: b91d4e7a3c58
Create Date: 2026-09-28 07:00:02.682347

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2e7ac2bd2526'
down_revision: Union[str, Sequence[str], None] = 'b91d4e7a3c58'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("contact_group_events", sa.Column("event_date_end", sa.Date(), nullable=True))
    op.create_check_constraint(
        "ck_contact_group_events_date_range",
        "contact_group_events",
        "event_date_end IS NULL OR event_date_end >= event_date",
    )


def downgrade() -> None:
    op.drop_constraint("ck_contact_group_events_date_range", "contact_group_events", type_="check")
    op.drop_column("contact_group_events", "event_date_end")
