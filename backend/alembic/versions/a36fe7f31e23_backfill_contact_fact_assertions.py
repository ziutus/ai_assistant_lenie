"""Preserve existing birthday and education values as pinned legacy assertions.

Revision ID: a36fe7f31e23
Revises: 1915e3243ed6
"""
import hashlib
import json

from alembic import op
import sqlalchemy as sa

revision = "a36fe7f31e23"
down_revision = "1915e3243ed6"
branch_labels = None
depends_on = None


def _backfill(bind, contact_id, attribute, item, record, value, observed):
    slot_id = bind.execute(sa.text("""
        INSERT INTO contact_fact_slots (contact_id, attribute_key, item_key, resolution_mode, resolved_at)
        VALUES (:contact, :attribute, :item, 'pinned', now())
        ON CONFLICT (contact_id, attribute_key, item_key) DO NOTHING RETURNING id
    """), dict(contact=contact_id, attribute=attribute, item=item)).scalar_one_or_none()
    if slot_id is None:
        return None
    payload = json.dumps(value, sort_keys=True)
    dedup = hashlib.sha256(f"{slot_id}|legacy_unknown|{record}|{payload}".encode()).hexdigest()
    assertion_id = bind.execute(sa.text("""
        INSERT INTO contact_fact_assertions
            (slot_id, source_key, source_record_key, value, status, observed_at, last_seen_at, dedup_key)
        VALUES (:slot, 'legacy_unknown', :record, CAST(:value AS jsonb), 'confirmed', :observed, :observed, :dedup)
        RETURNING id
    """), dict(slot=slot_id, record=record, value=payload, observed=observed, dedup=dedup)).scalar_one()
    bind.execute(sa.text("UPDATE contact_fact_slots SET selected_assertion_id=:assertion WHERE id=:slot"),
                 dict(assertion=assertion_id, slot=slot_id))
    return slot_id


def upgrade() -> None:
    bind = op.get_bind()
    for contact in bind.execute(sa.text("""
        SELECT id, birthday, birthday_month, birthday_day, birthday_year, updated_at FROM contacts
        WHERE birthday IS NOT NULL OR birthday_month IS NOT NULL OR birthday_day IS NOT NULL OR birthday_year IS NOT NULL
    """)).mappings():
        birthday = contact["birthday"]
        value = dict(month=contact["birthday_month"], day=contact["birthday_day"])
        if birthday:
            value = dict(year=birthday.year, month=birthday.month, day=birthday.day)
        elif contact["birthday_year"] is not None:
            value["year"] = contact["birthday_year"]
        _backfill(bind, contact["id"], "birthday", "singleton", f"legacy:contact:{contact['id']}", value, contact["updated_at"])
    for entry in bind.execute(sa.text("SELECT * FROM contact_education WHERE fact_slot_id IS NULL")).mappings():
        value = {key: entry[key] for key in ("institution", "field_of_study", "degree", "start_date", "end_date", "notes")}
        for key in ("start_date", "end_date"):
            if value[key] is not None:
                value[key] = value[key].isoformat()
        slot_id = _backfill(bind, entry["contact_id"], "education", f"legacy:{entry['id']}",
                            f"legacy:education:{entry['id']}", value, entry["updated_at"])
        if slot_id is not None:
            bind.execute(sa.text("UPDATE contact_education SET fact_slot_id=:slot WHERE id=:id"), dict(slot=slot_id, id=entry["id"]))


def downgrade() -> None:
    # Break the selected-assertion cycle before deleting the backfilled assertions.
    # Preserve later assertions in a backfilled slot, if any.
    op.execute("""
        UPDATE contact_education SET fact_slot_id=NULL WHERE fact_slot_id IN (
            SELECT slot_id FROM contact_fact_assertions WHERE source_key='legacy_unknown'
        )
    """)
    op.execute("""
        UPDATE contact_fact_slots SET selected_assertion_id=NULL WHERE selected_assertion_id IN (
            SELECT id FROM contact_fact_assertions WHERE source_key='legacy_unknown'
        )
    """)
    op.execute("""
        DELETE FROM contact_fact_slots s WHERE EXISTS (
            SELECT 1 FROM contact_fact_assertions a WHERE a.slot_id=s.id AND a.source_key='legacy_unknown'
        ) AND NOT EXISTS (
            SELECT 1 FROM contact_fact_assertions a WHERE a.slot_id=s.id AND a.source_key<>'legacy_unknown'
        )
    """)
    op.execute("DELETE FROM contact_fact_assertions WHERE source_key='legacy_unknown'")
