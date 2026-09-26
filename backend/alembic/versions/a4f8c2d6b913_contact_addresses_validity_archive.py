"""remember when a contact lived at an address: valid period + archived flag

A contact's former addresses stay as history ("lived here 2015-2019") instead
of being deleted. Both live on contact_addresses (the contact's use of an
address), not on addresses, because the address row may be shared.

* valid_from / valid_to — either end may be unknown; valid_to >= valid_from.
* is_archived — explicit "former address"; works with or without dates. An
  archived link is never primary.
* The same-place trigger from c7d3a91e5f42 now ignores archived links on both
  sides: moving back to an old place is a legitimate new active link.

Revision ID: a4f8c2d6b913
Revises: c7d3a91e5f42
Create Date: 2026-09-26 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'a4f8c2d6b913'
down_revision: Union[str, Sequence[str], None] = 'c7d3a91e5f42'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ALIASES = "'pl', 'polska', 'poland', 'rp', 'rzeczpospolita polska'"

# Separators become a single space (not nothing), exactly like library.address_formatting._fold, so
# "1-2" and "12" are different building numbers in SQL and in Python alike.
_FOLD_FUNCTION = """
    CREATE OR REPLACE FUNCTION address_fold(value text) RETURNS text
    LANGUAGE sql STABLE AS $$
        SELECT btrim(regexp_replace(lower(unaccent(coalesce(value, ''))), '[^a-z0-9]+', ' ', 'g'))
    $$
"""

_SAME_PLACE_FUNCTION = """
    CREATE OR REPLACE FUNCTION address_same_place(a addresses, b addresses) RETURNS boolean
    LANGUAGE sql STABLE AS $$
        SELECT address_fold(a.city) <> ''
           AND address_fold(a.city) = address_fold(b.city)
           AND address_fold(a.street) = address_fold(b.street)
           AND address_fold(a.building_number) = address_fold(b.building_number)
           AND address_fold(a.block_number) = address_fold(b.block_number)
           AND address_fold(a.apartment_number) = address_fold(b.apartment_number)
           AND (address_fold(a.postal_code) = '' OR address_fold(b.postal_code) = ''
                OR address_fold(a.postal_code) = address_fold(b.postal_code))
           AND (CASE WHEN address_fold(a.country) IN ('', %(aliases)s) THEN 'pl' ELSE address_fold(a.country) END)
             = (CASE WHEN address_fold(b.country) IN ('', %(aliases)s) THEN 'pl' ELSE address_fold(b.country) END)
    $$
"""

_TRIGGER_FUNCTION = """
    CREATE OR REPLACE FUNCTION contact_addresses_reject_duplicate_place() RETURNS trigger
    LANGUAGE plpgsql AS $$
    DECLARE
        new_address addresses;
    BEGIN
        %(guard)s
        %(lock)s
        SELECT * INTO new_address FROM addresses WHERE id = NEW.address_id;
        IF EXISTS (
            SELECT 1 FROM contact_addresses other
            JOIN addresses oa ON oa.id = other.address_id
            WHERE other.contact_id = NEW.contact_id
              AND other.id <> NEW.id
              %(other_filter)s
              AND address_same_place(oa, new_address)
        ) THEN
            RAISE EXCEPTION 'duplicate_address: contact %% already has this address', NEW.contact_id
                USING ERRCODE = 'unique_violation', CONSTRAINT = 'contact_addresses_same_place';
        END IF;
        RETURN NEW;
    END
    $$
"""


def upgrade() -> None:
    op.execute("ALTER TABLE contact_addresses ADD COLUMN valid_from date, ADD COLUMN valid_to date")
    op.execute("ALTER TABLE contact_addresses ADD COLUMN is_archived boolean NOT NULL DEFAULT false")
    op.execute(
        "ALTER TABLE contact_addresses ADD CONSTRAINT ck_contact_addresses_valid_period "
        "CHECK (valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from)"
    )
    op.execute(
        "ALTER TABLE contact_addresses ADD CONSTRAINT ck_contact_addresses_archived_not_primary "
        "CHECK (NOT (is_archived AND is_primary))"
    )
    # A person can live at the same place twice (moved back), so uniqueness only applies to active stays.
    op.execute("ALTER TABLE contact_addresses DROP CONSTRAINT uq_contact_addresses_contact_address")
    op.execute(
        "CREATE UNIQUE INDEX uq_contact_addresses_active_contact_address "
        "ON contact_addresses (contact_id, address_id) WHERE NOT is_archived"
    )
    op.execute(_FOLD_FUNCTION)
    op.execute(_SAME_PLACE_FUNCTION % {"aliases": _ALIASES})
    op.execute(_TRIGGER_FUNCTION % {
        "guard": "IF NEW.is_archived THEN RETURN NEW; END IF;",
        # Serialize concurrent writers for one contact so two parallel inserts cannot both pass the check.
        "lock": "PERFORM pg_advisory_xact_lock(hashtextextended('contact_addresses:' || NEW.contact_id::text, 0));",
        "other_filter": "AND NOT other.is_archived",
    })
    op.execute("DROP TRIGGER IF EXISTS trg_contact_addresses_reject_duplicate_place ON contact_addresses")
    op.execute(
        """
        CREATE TRIGGER trg_contact_addresses_reject_duplicate_place
            BEFORE INSERT OR UPDATE OF contact_id, address_id, is_archived ON contact_addresses
            FOR EACH ROW EXECUTE FUNCTION contact_addresses_reject_duplicate_place()
        """
    )


def downgrade() -> None:
    op.execute(_TRIGGER_FUNCTION % {"guard": "", "lock": "", "other_filter": ""})
    op.execute(
        """
        CREATE OR REPLACE FUNCTION address_fold(value text) RETURNS text
        LANGUAGE sql STABLE AS $$
            SELECT regexp_replace(lower(unaccent(coalesce(value, ''))), '[^a-z0-9]+', '', 'g')
        $$
        """
    )
    op.execute(_SAME_PLACE_FUNCTION % {"aliases": "'pl', 'polska', 'poland', 'rp', 'rzeczpospolitapolska'"})
    # Restoring the unconditional unique constraint: history rows repeating an (contact, address) pair go first.
    op.execute(
        "DELETE FROM contact_addresses a USING contact_addresses b "
        "WHERE a.contact_id = b.contact_id AND a.address_id = b.address_id AND a.id > b.id"
    )
    op.execute("DROP INDEX IF EXISTS uq_contact_addresses_active_contact_address")
    op.execute(
        "ALTER TABLE contact_addresses "
        "ADD CONSTRAINT uq_contact_addresses_contact_address UNIQUE (contact_id, address_id)"
    )
    op.execute("DROP TRIGGER IF EXISTS trg_contact_addresses_reject_duplicate_place ON contact_addresses")
    op.execute(
        """
        CREATE TRIGGER trg_contact_addresses_reject_duplicate_place
            BEFORE INSERT OR UPDATE OF contact_id, address_id ON contact_addresses
            FOR EACH ROW EXECUTE FUNCTION contact_addresses_reject_duplicate_place()
        """
    )
    op.execute("ALTER TABLE contact_addresses DROP CONSTRAINT IF EXISTS ck_contact_addresses_archived_not_primary")
    op.execute("ALTER TABLE contact_addresses DROP CONSTRAINT IF EXISTS ck_contact_addresses_valid_period")
    op.execute("ALTER TABLE contact_addresses DROP COLUMN IF EXISTS is_archived")
    op.execute("ALTER TABLE contact_addresses DROP COLUMN IF EXISTS valid_to, DROP COLUMN IF EXISTS valid_from")
