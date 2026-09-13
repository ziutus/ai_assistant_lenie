"""add_contact_group_events

Revision ID: fd3c56b44cc2
Revises: 8b07952a8f81
Create Date: 2026-09-13 07:20:12.412246

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fd3c56b44cc2'
down_revision: Union[str, Sequence[str], None] = '8b07952a8f81'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "contact_group_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("group_id", sa.Integer(), sa.ForeignKey("contact_groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("source_document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_contact_group_events_group_id", "contact_group_events", ["group_id"])
    op.create_index("idx_contact_group_events_event_date", "contact_group_events", ["event_date"])
    op.create_index("ix_contact_group_events_source_document_id", "contact_group_events", ["source_document_id"])


def downgrade() -> None:
    op.drop_table("contact_group_events")
