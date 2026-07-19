"""rename web_documents to documents (with its indexes and constraints)

Stage 11f of docs/search-rebuild-implementation-plan.md. Foreign keys in the
15 referencing tables (document_chunks, document_entities, ...) follow the
rename automatically and their constraint names never contained
"web_documents", so only this table's own objects are renamed. The PG18
auto-generated *_not_null constraint names are left alone (internal noise).

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-07-19 06:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = "f7a8b9c0d1e2"
down_revision: Union[str, None] = "e6f7a8b9c0d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PLAIN_INDEXES = [
    "idx_web_documents_ai_flag",
    "idx_web_documents_collection_id",
    "idx_web_documents_created_at",
    "idx_web_documents_discovery_source_id",
    "idx_web_documents_document_state",
    "idx_web_documents_document_type",
    "idx_web_documents_paywall",
    "idx_web_documents_published_on",
    "idx_web_documents_publisher_id",
    "idx_web_documents_url",
]

# Constraint renames also rename their backing indexes (pkey, unique).
_CONSTRAINTS = [
    ("web_documents_pkey", "documents_pkey"),
    ("uq_web_documents_uuid", "uq_documents_uuid"),
    ("ck_web_documents_byline_method", "ck_documents_byline_method"),
    ("ck_web_documents_published_on_method", "ck_documents_published_on_method"),
    ("web_documents_collection_id_fkey", "documents_collection_id_fkey"),
    ("web_documents_discovery_source_id_fkey", "documents_discovery_source_id_fkey"),
    ("web_documents_publisher_id_fkey", "documents_publisher_id_fkey"),
]


def upgrade() -> None:
    op.execute("ALTER TABLE web_documents RENAME TO documents")
    op.execute("ALTER SEQUENCE web_documents_id_seq RENAME TO documents_id_seq")
    for old in _PLAIN_INDEXES:
        new = old.replace("idx_web_documents_", "idx_documents_")
        op.execute(f"ALTER INDEX {old} RENAME TO {new}")
    for old, new in _CONSTRAINTS:
        op.execute(f"ALTER TABLE documents RENAME CONSTRAINT {old} TO {new}")


def downgrade() -> None:
    for old, new in reversed(_CONSTRAINTS):
        op.execute(f"ALTER TABLE documents RENAME CONSTRAINT {new} TO {old}")
    for old in reversed(_PLAIN_INDEXES):
        new = old.replace("idx_web_documents_", "idx_documents_")
        op.execute(f"ALTER INDEX {new} RENAME TO {old}")
    op.execute("ALTER SEQUENCE documents_id_seq RENAME TO web_documents_id_seq")
    op.execute("ALTER TABLE documents RENAME TO web_documents")
