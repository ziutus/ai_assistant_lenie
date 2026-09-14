"""add_contact_event_participants

Revision ID: b4cfbc7ccf11
Revises: a7c91e2d6b40
Create Date: 2026-09-14 06:28:56.124516

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b4cfbc7ccf11'
down_revision: Union[str, Sequence[str], None] = 'a7c91e2d6b40'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("contact_group_events", "group_id", existing_type=sa.Integer(), nullable=True)
    op.create_table(
        "contact_event_participants",
        sa.Column("event_id", sa.Integer(), sa.ForeignKey("contact_group_events.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("contact_id", sa.Integer(), sa.ForeignKey("contacts.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_contact_event_participants_contact_id", "contact_event_participants", ["contact_id"])


def downgrade() -> None:
    # Refuse to discard participant-only events when restoring the required group.
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM contact_group_events WHERE group_id IS NULL) THEN
                RAISE EXCEPTION 'Cannot downgrade while events without groups exist';
            END IF;
        END $$
    """)
    op.alter_column("contact_group_events", "group_id", existing_type=sa.Integer(), nullable=False)
    op.drop_table("contact_event_participants")
