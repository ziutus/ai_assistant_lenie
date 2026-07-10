"""create geocode_cache + document_entities.geocode_id

Revision ID: a3b4c5d6e7f8
Revises: f2a3b4c5d6e7
Create Date: 2026-07-10 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a3b4c5d6e7f8"
down_revision: Union[str, None] = "f2a3b4c5d6e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # IF NOT EXISTS: the same objects may already have been created by the
    # Docker init script 22-create-geocode-cache.sql on a fresh database.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS geocode_cache (
            id           SERIAL PRIMARY KEY,
            query        TEXT NOT NULL UNIQUE,
            resolved     BOOLEAN NOT NULL,
            display_name TEXT,
            lat          NUMERIC(9,6),
            lon          NUMERIC(9,6),
            osm_class    VARCHAR(50),
            osm_type     VARCHAR(50),
            importance   REAL,
            raw          JSONB,
            provider     VARCHAR(20) NOT NULL DEFAULT 'locationiq',
            created_at   TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "ALTER TABLE document_entities "
        "ADD COLUMN IF NOT EXISTS geocode_id INTEGER REFERENCES geocode_cache(id) ON DELETE SET NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_document_entities_geocode_id ON document_entities(geocode_id)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE document_entities DROP COLUMN IF EXISTS geocode_id")
    op.execute("DROP TABLE IF EXISTS geocode_cache")
