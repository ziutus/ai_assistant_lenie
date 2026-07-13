"""create document_events

Revision ID: a9b0c1d2e3f4
Revises: f8a9b0c1d2e3
Create Date: 2026-07-13 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a9b0c1d2e3f4"
down_revision: Union[str, None] = "f8a9b0c1d2e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PRECISIONS = "'day', 'month', 'year', 'decade', 'century', 'era', 'unknown'"


def upgrade() -> None:
    op.create_table(
        "document_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "document_id",
            sa.Integer(),
            sa.ForeignKey("web_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chapter_position", sa.Integer()),
        sa.Column("event_date", sa.Date()),
        sa.Column("event_date_end", sa.Date()),
        sa.Column("date_precision", sa.String(length=10), nullable=False),
        sa.Column("date_text", sa.Text(), nullable=False),
        sa.Column("sort_year", sa.Integer()),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("anchor_quote", sa.Text()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            f"date_precision IN ({_PRECISIONS})",
            name="ck_document_events_date_precision",
        ),
    )
    op.create_index(
        "idx_document_events_document_sort_year",
        "document_events",
        ["document_id", "sort_year"],
    )


def downgrade() -> None:
    op.drop_index("idx_document_events_document_sort_year", table_name="document_events")
    op.drop_table("document_events")
