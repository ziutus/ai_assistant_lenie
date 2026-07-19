"""rename websites_embeddings to document_embeddings and website_id to document_id

Stage 11e of docs/search-rebuild-implementation-plan.md: physical renames only
— types, FKs semantics and the per-model HNSW partial indexes (idx_emb_*,
named after models, not the table) stay identical.

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-07-19 05:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = "e6f7a8b9c0d1"
down_revision: Union[str, None] = "d5e6f7a8b9c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_RENAMES = [
    ("ALTER TABLE websites_embeddings RENAME TO document_embeddings",
     "ALTER TABLE document_embeddings RENAME TO websites_embeddings"),
    ("ALTER TABLE document_embeddings RENAME COLUMN website_id TO document_id",
     "ALTER TABLE document_embeddings RENAME COLUMN document_id TO website_id"),
    ("ALTER INDEX websites_embeddings_pkey RENAME TO document_embeddings_pkey",
     "ALTER INDEX document_embeddings_pkey RENAME TO websites_embeddings_pkey"),
    ("ALTER INDEX idx_websites_embeddings_website_id RENAME TO idx_document_embeddings_document_id",
     "ALTER INDEX idx_document_embeddings_document_id RENAME TO idx_websites_embeddings_website_id"),
    ("ALTER INDEX idx_websites_embeddings_chunk_id RENAME TO idx_document_embeddings_chunk_id",
     "ALTER INDEX idx_document_embeddings_chunk_id RENAME TO idx_websites_embeddings_chunk_id"),
    ("ALTER INDEX idx_websites_embeddings_model RENAME TO idx_document_embeddings_model",
     "ALTER INDEX idx_document_embeddings_model RENAME TO idx_websites_embeddings_model"),
    # NOTE: downgrade statements run in reversed order, when the table is
    # still named document_embeddings — they must reference that name.
    ("ALTER TABLE document_embeddings RENAME CONSTRAINT websites_embeddings_website_id_fkey"
     " TO document_embeddings_document_id_fkey",
     "ALTER TABLE document_embeddings RENAME CONSTRAINT document_embeddings_document_id_fkey"
     " TO websites_embeddings_website_id_fkey"),
    ("ALTER TABLE document_embeddings RENAME CONSTRAINT websites_embeddings_chunk_id_fkey"
     " TO document_embeddings_chunk_id_fkey",
     "ALTER TABLE document_embeddings RENAME CONSTRAINT document_embeddings_chunk_id_fkey"
     " TO websites_embeddings_chunk_id_fkey"),
]


def upgrade() -> None:
    for up_sql, _ in _RENAMES:
        op.execute(up_sql)


def downgrade() -> None:
    for _, down_sql in reversed(_RENAMES):
        op.execute(down_sql)
