"""Replace the contact's free-text address with shareable address records."""
from alembic import op
import sqlalchemy as sa

revision = "9bc5a781e204"
down_revision = "d8f2c4a6b901"
branch_labels = None
depends_on = None


def upgrade():
    # PostGIS already exists; keep this migration independent of ORM models.
    op.execute(sa.text("""
        CREATE TABLE addresses (
            id SERIAL PRIMARY KEY,
            label VARCHAR(100), raw_address TEXT NOT NULL,
            latitude NUMERIC(9,6), longitude NUMERIC(9,6),
            location GEOGRAPHY(POINT,4326),
            geocode_id INTEGER REFERENCES geocode_cache(id) ON DELETE SET NULL,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """))
    op.execute(sa.text("""
        CREATE TABLE contact_addresses (
            id SERIAL PRIMARY KEY,
            contact_id INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            address_id INTEGER NOT NULL REFERENCES addresses(id) ON DELETE CASCADE,
            role VARCHAR(50), is_primary BOOLEAN NOT NULL DEFAULT false,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """))
    op.create_index("idx_contact_addresses_contact", "contact_addresses", ["contact_id"])
    # Reserve an address id per source contact, rather than joining by text:
    # different contacts may have identical text but must each get their own row.
    op.execute(sa.text("""
        WITH source AS MATERIALIZED (
            SELECT id AS contact_id, address AS raw_address,
                   nextval(pg_get_serial_sequence('addresses', 'id')) AS address_id
            FROM contacts
            WHERE address IS NOT NULL AND btrim(address) <> ''
        ), inserted AS (
            INSERT INTO addresses (id, raw_address, label)
            SELECT address_id, raw_address, NULL FROM source
            RETURNING id
        )
        INSERT INTO contact_addresses (contact_id, address_id, role, is_primary)
        SELECT source.contact_id, inserted.id, 'zamieszkania', true
        FROM source JOIN inserted ON inserted.id = source.address_id
    """))
    op.drop_column("contacts", "address")


def downgrade():
    op.add_column("contacts", sa.Column("address", sa.Text(), nullable=True))
    # The legacy column can retain only one address; choose deterministically.
    op.execute(sa.text("""
        UPDATE contacts AS c SET address = (
            SELECT a.raw_address
            FROM contact_addresses AS ca JOIN addresses AS a ON a.id = ca.address_id
            WHERE ca.contact_id = c.id
            ORDER BY ca.is_primary DESC, ca.id
            LIMIT 1
        )
    """))
    op.drop_table("contact_addresses")
    op.drop_table("addresses")
