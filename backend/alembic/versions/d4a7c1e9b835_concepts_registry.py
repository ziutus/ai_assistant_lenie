"""registry of concepts (conceptName entities)

Revision ID: d4a7c1e9b835
Revises: b6e1d4a8c273
Create Date: 2026-11-08 00:00:00.000000

A concept, ideology or term the reader wants to remember ("Ciemne oświecenie") gets one canonical entry
(``concepts``) with a description and aliases; manual ``conceptName`` mentions of documents are linked to it by
(document, normalized name) in ``concept_mention_links`` because ``document_entities`` rows are rebuilt on every
NER refresh.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d4a7c1e9b835"
down_revision: Union[str, None] = "b6e1d4a8c273"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "concepts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("trim(name) <> ''", name="ck_concepts_name"),
    )
    op.create_table(
        "concept_aliases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("concept_id", sa.Integer(), sa.ForeignKey("concepts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("alias", sa.Text(), nullable=False),
        sa.Column("name_key", sa.Text(), nullable=False),
        sa.Column("search_key", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("concept_id", "name_key", name="uq_concept_aliases"),
        sa.CheckConstraint("name_key <> ''", name="ck_concept_aliases_key"),
    )
    op.create_index("idx_concept_aliases_name_key", "concept_aliases", ["name_key"])
    op.execute("CREATE INDEX idx_concept_aliases_search ON concept_aliases USING gin (search_key gin_trgm_ops)")
    op.create_table(
        "concept_mention_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name_key", sa.Text(), nullable=False),
        sa.Column("surface", sa.Text(), nullable=False),
        sa.Column("concept_id", sa.Integer(), sa.ForeignKey("concepts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="confirmed"),
        sa.Column("decided_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("decided_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("document_id", "name_key", "concept_id", name="uq_concept_mention_links"),
        sa.CheckConstraint("status IN ('confirmed', 'rejected')", name="ck_concept_mention_links_status"),
    )
    op.create_index("idx_concept_mention_links_concept", "concept_mention_links", ["concept_id", "status"])
    op.create_index("idx_concept_mention_links_name", "concept_mention_links", ["name_key"])


def downgrade() -> None:
    op.drop_table("concept_mention_links")
    op.drop_table("concept_aliases")
    op.drop_table("concepts")
