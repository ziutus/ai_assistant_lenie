"""create collections table, replace web_documents.project with collection_id

Stage 11c of docs/search-rebuild-implementation-plan.md. ADR-017: a document
belongs to at most one collection (1:N); web_documents.project was 100% NULL
on production (9220 docs, 2026-07-18), but the data move below is written
defensively so any value that appeared since is preserved losslessly.

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-07-19 03:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = "c4d5e6f7a8b9"
down_revision: Union[str, None] = "b3c4d5e6f7a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE collections (
            id          SERIAL PRIMARY KEY,
            name        TEXT NOT NULL UNIQUE,
            description TEXT,
            created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    op.execute(
        "ALTER TABLE web_documents ADD COLUMN collection_id INTEGER"
        " REFERENCES collections(id) ON DELETE SET NULL"
    )
    op.execute(
        "INSERT INTO collections (name)"
        " SELECT DISTINCT project FROM web_documents WHERE project IS NOT NULL"
    )
    op.execute(
        "UPDATE web_documents SET collection_id = c.id"
        " FROM collections c WHERE web_documents.project = c.name"
    )
    op.execute("CREATE INDEX idx_web_documents_collection_id ON web_documents(collection_id)")
    op.execute("DROP INDEX IF EXISTS idx_web_documents_project")
    op.execute("ALTER TABLE web_documents DROP COLUMN project")


def downgrade() -> None:
    op.execute("ALTER TABLE web_documents ADD COLUMN project VARCHAR(100)")
    op.execute(
        "UPDATE web_documents SET project = c.name"
        " FROM collections c WHERE web_documents.collection_id = c.id"
    )
    op.execute("CREATE INDEX idx_web_documents_project ON web_documents(project)")
    op.execute("ALTER TABLE web_documents DROP COLUMN collection_id")
    op.execute("DROP TABLE collections")
