"""rename sources to discovery_sources, replace web_documents.source with discovery_source_id

Stage 11d of docs/search-rebuild-implementation-plan.md. The old name-based FK
(fk_source, ON UPDATE CASCADE) becomes a plain integer FK to the renamed
lookup table. Every non-NULL web_documents.source value is guaranteed to have
a lookup row (fk_source enforced that), so the data move is a pure join. The
HTTP wire format keeps the `source` NAME field (decision 2026-07-19: the
Chrome extension is updated manually per device, renaming the wire field
would silently break old installs) — only storage and ORM change here.

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-07-19 04:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = "d5e6f7a8b9c0"
down_revision: Union[str, None] = "c4d5e6f7a8b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE sources RENAME TO discovery_sources")
    op.execute(
        "ALTER TABLE web_documents ADD COLUMN discovery_source_id INTEGER"
        " REFERENCES discovery_sources(id)"
    )
    op.execute(
        "UPDATE web_documents SET discovery_source_id = s.id"
        " FROM discovery_sources s WHERE web_documents.source = s.name"
    )
    op.execute(
        "CREATE INDEX idx_web_documents_discovery_source_id"
        " ON web_documents(discovery_source_id)"
    )
    op.execute("ALTER TABLE web_documents DROP CONSTRAINT fk_source")
    op.execute("DROP INDEX IF EXISTS idx_web_documents_source")
    op.execute("ALTER TABLE web_documents DROP COLUMN source")


def downgrade() -> None:
    op.execute("ALTER TABLE web_documents ADD COLUMN source TEXT")
    op.execute(
        "UPDATE web_documents SET source = s.name"
        " FROM discovery_sources s WHERE web_documents.discovery_source_id = s.id"
    )
    op.execute("CREATE INDEX idx_web_documents_source ON web_documents(source)")
    op.execute("ALTER TABLE web_documents DROP COLUMN discovery_source_id")
    op.execute("ALTER TABLE discovery_sources RENAME TO sources")
    op.execute(
        "ALTER TABLE web_documents ADD CONSTRAINT fk_source"
        " FOREIGN KEY (source) REFERENCES sources(name) ON UPDATE CASCADE"
    )
