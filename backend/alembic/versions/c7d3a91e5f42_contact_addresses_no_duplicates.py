"""forbid duplicate addresses per contact at the database level

Two layers, so direct SQL writes (scripts, AI sessions) are covered too:

* UNIQUE (contact_id, address_id) — the same address row linked twice.
* A BEFORE INSERT/UPDATE trigger on contact_addresses that refuses a link whose
  address is the same *place* as another address the contact already has: equal
  after unaccent + lower + dropping non-alphanumerics, "PL"/"Polska" treated as
  one country, postal code ignored when either side lacks it. It mirrors
  library.address_formatting.addresses_match() except for parsing legacy rows
  whose whole text sits in ``city`` — the backend still handles that case.

The trigger only guards new/changed links; existing rows are not touched.
Violations raise unique_violation (SQLSTATE 23505), which the API maps to 409.

Revision ID: c7d3a91e5f42
Revises: e5a91c3f7b20
Create Date: 2026-09-26 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'c7d3a91e5f42'
down_revision: Union[str, Sequence[str], None] = 'e5a91c3f7b20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE contact_addresses "
        "ADD CONSTRAINT uq_contact_addresses_contact_address UNIQUE (contact_id, address_id)"
    )
    op.execute(
        """
        CREATE FUNCTION address_fold(value text) RETURNS text
        LANGUAGE sql STABLE AS $$
            SELECT regexp_replace(lower(unaccent(coalesce(value, ''))), '[^a-z0-9]+', '', 'g')
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION address_same_place(a addresses, b addresses) RETURNS boolean
        LANGUAGE sql STABLE AS $$
            SELECT address_fold(a.city) <> ''
               AND address_fold(a.city) = address_fold(b.city)
               AND address_fold(a.street) = address_fold(b.street)
               AND address_fold(a.building_number) = address_fold(b.building_number)
               AND address_fold(a.block_number) = address_fold(b.block_number)
               AND address_fold(a.apartment_number) = address_fold(b.apartment_number)
               AND (address_fold(a.postal_code) = '' OR address_fold(b.postal_code) = ''
                    OR address_fold(a.postal_code) = address_fold(b.postal_code))
               AND (CASE WHEN address_fold(a.country) IN ('', 'pl', 'polska', 'poland', 'rp', 'rzeczpospolitapolska')
                         THEN 'pl' ELSE address_fold(a.country) END)
                 = (CASE WHEN address_fold(b.country) IN ('', 'pl', 'polska', 'poland', 'rp', 'rzeczpospolitapolska')
                         THEN 'pl' ELSE address_fold(b.country) END)
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION contact_addresses_reject_duplicate_place() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE
            new_address addresses;
        BEGIN
            SELECT * INTO new_address FROM addresses WHERE id = NEW.address_id;
            IF EXISTS (
                SELECT 1 FROM contact_addresses other
                JOIN addresses oa ON oa.id = other.address_id
                WHERE other.contact_id = NEW.contact_id
                  AND other.id <> NEW.id
                  AND address_same_place(oa, new_address)
            ) THEN
                RAISE EXCEPTION 'duplicate_address: contact % already has this address', NEW.contact_id
                    USING ERRCODE = 'unique_violation', CONSTRAINT = 'contact_addresses_same_place';
            END IF;
            RETURN NEW;
        END
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_contact_addresses_reject_duplicate_place
            BEFORE INSERT OR UPDATE OF contact_id, address_id ON contact_addresses
            FOR EACH ROW EXECUTE FUNCTION contact_addresses_reject_duplicate_place()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_contact_addresses_reject_duplicate_place ON contact_addresses")
    op.execute("DROP FUNCTION IF EXISTS contact_addresses_reject_duplicate_place()")
    op.execute("DROP FUNCTION IF EXISTS address_same_place(addresses, addresses)")
    op.execute("DROP FUNCTION IF EXISTS address_fold(text)")
    op.execute("ALTER TABLE contact_addresses DROP CONSTRAINT IF EXISTS uq_contact_addresses_contact_address")
