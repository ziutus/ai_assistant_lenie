"""create document_links

Revision ID: f2a91c04d7b3
Revises: a7c3e1f9d2b4
Create Date: 2026-09-08 00:00:00.000000

A typed, directed relation between two documents in the library ("this
LinkedIn post discusses that GitHub repo"). Distinct from:
  - collections / content_groups — broad thematic buckets, not a tight pair;
  - document_source_relationships — provenance of claims *inside* one article,
    keyed by entity name, not by another Document.

One row per (from, to, relation). The reader renders both endpoints, so a
relation is stored once and shown from each side with its own phrasing.
`status` mirrors document_source_relationships: an auto-detected link lands
as 'proposed' and needs one click to become 'confirmed'.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f2a91c04d7b3"
down_revision: Union[str, None] = "a7c3e1f9d2b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "document_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "from_document_id",
            sa.Integer(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "to_document_id",
            sa.Integer(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("relation", sa.String(length=30), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="confirmed"),
        sa.Column("detection_method", sa.String(length=20), nullable=False, server_default="manual"),
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint("from_document_id <> to_document_id", name="ck_document_links_distinct"),
        sa.UniqueConstraint(
            "from_document_id", "to_document_id", "relation", name="uq_document_links_edge"
        ),
    )
    op.create_index(
        "idx_document_links_from", "document_links", ["from_document_id", "status"]
    )
    op.create_index(
        "idx_document_links_to", "document_links", ["to_document_id", "status"]
    )


def downgrade() -> None:
    op.drop_index("idx_document_links_to", table_name="document_links")
    op.drop_index("idx_document_links_from", table_name="document_links")
    op.drop_table("document_links")
