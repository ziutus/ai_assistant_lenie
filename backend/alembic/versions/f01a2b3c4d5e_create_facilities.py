"""Create physical facilities and document mention links.

Revision ID: f01a2b3c4d5e
Revises: 8e7d6c5b4a3f
Create Date: 2026-08-20 00:00:00.000000
"""

from alembic import op


revision = "f01a2b3c4d5e"
down_revision = "8e7d6c5b4a3f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute("""
        CREATE TABLE facilities (
            id SERIAL PRIMARY KEY,
            canonical_name TEXT NOT NULL,
            facility_type VARCHAR(50) NOT NULL,
            place_name TEXT,
            latitude NUMERIC(9,6), longitude NUMERIC(9,6),
            location GEOGRAPHY(POINT,4326),
            geocode_id INTEGER REFERENCES geocode_cache(id) ON DELETE SET NULL,
            wikidata_qid VARCHAR(20) UNIQUE,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(), updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_facilities_identity UNIQUE (canonical_name, facility_type, place_name),
            CONSTRAINT ck_facilities_latitude CHECK (latitude IS NULL OR latitude BETWEEN -90 AND 90),
            CONSTRAINT ck_facilities_longitude CHECK (longitude IS NULL OR longitude BETWEEN -180 AND 180)
        )
    """)
    op.execute("""
        CREATE TABLE document_facilities (
            id SERIAL PRIMARY KEY,
            document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            facility_id INTEGER NOT NULL REFERENCES facilities(id) ON DELETE CASCADE,
            place_entity_id INTEGER REFERENCES document_entities(id) ON DELETE SET NULL,
            raw_mention TEXT NOT NULL, mention_count INTEGER NOT NULL DEFAULT 1,
            confidence VARCHAR(30) NOT NULL DEFAULT 'rule_candidate', created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            UNIQUE (document_id, facility_id)
        )
    """)
    op.execute("CREATE INDEX idx_facilities_location_gist ON facilities USING GIST (location)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS document_facilities")
    op.execute("DROP TABLE IF EXISTS facilities")
    # The extension can already support other data; never drop it here.
