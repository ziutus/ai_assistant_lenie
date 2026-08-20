"""Add curated profiles for physical facilities.

Revision ID: a12b3c4d5e6f
Revises: f01a2b3c4d5e
Create Date: 2026-08-20 00:00:00.000000
"""

from alembic import op


revision = "a12b3c4d5e6f"
down_revision = "f01a2b3c4d5e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE facilities ADD COLUMN description TEXT")
    op.execute("ALTER TABLE facilities ADD COLUMN operator_name TEXT")
    op.execute("ALTER TABLE facilities ADD COLUMN source_url TEXT")
    # Wikidata Q1739407: Gravelines Nuclear Power Station.  Its P625 point is
    # the plant itself, not the nearby settlement's geocoder centroid.
    op.execute("""
        UPDATE facilities
        SET description = 'Elektrownia jądrowa w departamencie Nord we Francji.',
            operator_name = 'EDF',
            source_url = 'https://www.wikidata.org/wiki/Q1739407',
            wikidata_qid = 'Q1739407',
            latitude = 51.013611,
            longitude = 2.136111,
            location = ST_SetSRID(ST_MakePoint(2.136111, 51.013611), 4326)::geography,
            updated_at = NOW()
        WHERE canonical_name = 'Elektrownia jądrowa Gravelines'
          AND facility_type = 'nuclear_power_plant'
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE facilities DROP COLUMN source_url")
    op.execute("ALTER TABLE facilities DROP COLUMN operator_name")
    op.execute("ALTER TABLE facilities DROP COLUMN description")
