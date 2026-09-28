"""Resolve sourced contact facts and project the selected values into legacy caches."""
import datetime as dt
import hashlib
import json
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from library.contact_change_log import record_contact_change
from library.db.models import (
    Contact, ContactEducation, ContactFactAssertion, ContactFactAttribute,
    ContactFactSlot, ContactFactSource, ContactFactSourcePolicy,
)


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def _source_priority(session: Session, source_key: str, attribute_key: str) -> int:
    policy = session.get(ContactFactSourcePolicy, (source_key, attribute_key))
    if policy is not None:
        return policy.priority
    source = session.get(ContactFactSource, source_key)
    if source is None:
        raise ValueError(f"Unknown fact source: {source_key}")
    return source.default_priority


def record_assertion(
    session: Session, *, contact_id: int, attribute_key: str, item_key: str,
    source_key: str, value: dict, source_record_key: str, source_url: str | None = None,
    asserted_by: str | None = None, confidence: float | None = None, status: str = "candidate",
) -> ContactFactAssertion:
    attribute = session.get(ContactFactAttribute, attribute_key)
    if attribute is None:
        raise ValueError(f"Unknown fact attribute: {attribute_key}")
    if attribute.cardinality == "single" and item_key != "singleton":
        raise ValueError("Single-valued attributes require item_key='singleton'")
    slot = session.scalar(select(ContactFactSlot).where(
        ContactFactSlot.contact_id == contact_id, ContactFactSlot.attribute_key == attribute_key,
        ContactFactSlot.item_key == item_key,
    ))
    if slot is None:
        slot = ContactFactSlot(contact_id=contact_id, attribute_key=attribute_key,
                               item_key=item_key, resolution_mode="auto")
        session.add(slot)
        session.flush()
    dedup_key = hashlib.sha256(
        f"{slot.id}|{source_key}|{source_record_key}|{json.dumps(value, sort_keys=True)}".encode()
    ).hexdigest()
    assertion = session.scalar(select(ContactFactAssertion).where(ContactFactAssertion.dedup_key == dedup_key))
    now = _now()
    if assertion is not None:
        assertion.last_seen_at = now
        assertion.updated_at = now
        return assertion
    assertion = ContactFactAssertion(
        slot_id=slot.id, source_key=source_key, source_record_key=source_record_key,
        source_url=source_url, asserted_by=asserted_by, value=value, confidence=confidence,
        status="confirmed" if source_key == "user_manual" else status,
        dedup_key=dedup_key, observed_at=now, last_seen_at=now,
    )
    session.add(assertion)
    session.flush()
    if source_key == "user_manual":
        slot.resolution_mode = "pinned"
        slot.selected_assertion_id = assertion.id
        slot.decision_by = asserted_by
        slot.decision_note = None
        slot.resolved_at = now
    else:
        resolve_slot(session, slot)
    slot.updated_at = now
    project_slot_to_cache(session, slot)
    return assertion


def resolve_slot(session: Session, slot: ContactFactSlot) -> None:
    if slot.resolution_mode != "auto":
        return
    attribute = session.get(ContactFactAttribute, slot.attribute_key)
    candidates = []
    for assertion in session.scalars(select(ContactFactAssertion).where(
        ContactFactAssertion.slot_id == slot.id,
        ContactFactAssertion.status.in_(("confirmed", "candidate")),
    )):
        priority = _source_priority(session, assertion.source_key, slot.attribute_key)
        if assertion.status == "confirmed" or priority >= attribute.min_auto_priority:
            candidates.append((priority, assertion.confidence if assertion.confidence is not None else -1,
                               assertion.observed_at, assertion.id))
    slot.selected_assertion_id = max(candidates)[-1] if candidates else None
    slot.resolved_at = slot.updated_at = _now()


def project_slot_to_cache(session: Session, slot: ContactFactSlot) -> None:
    suppressed = slot.resolution_mode == "suppressed"
    if slot.selected_assertion_id is None and not suppressed:
        return
    assertion = session.get(ContactFactAssertion, slot.selected_assertion_id) if not suppressed else None
    if assertion is not None and assertion.slot_id != slot.id:
        raise ValueError("Selected assertion belongs to a different slot")
    value = assertion.value if assertion is not None else {}
    contact = session.get(Contact, slot.contact_id)
    changed = []
    if slot.attribute_key == "education":
        entry = session.scalar(select(ContactEducation).where(ContactEducation.fact_slot_id == slot.id))
        if suppressed:
            if entry is not None:
                session.delete(entry)
                changed.append("education")
        else:
            fields = {key: value.get(key) for key in (
                "institution", "field_of_study", "degree", "start_date", "end_date", "notes",
            )}
            for key in ("start_date", "end_date"):
                if fields[key] is not None:
                    fields[key] = dt.date.fromisoformat(fields[key])
            if entry is None:
                entry = ContactEducation(contact_id=slot.contact_id, fact_slot_id=slot.id, **fields)
                session.add(entry)
                changed.append("education")
            elif any(getattr(entry, key) != val for key, val in fields.items()):
                for key, val in fields.items():
                    setattr(entry, key, val)
                entry.updated_at = _now()
                changed.append("education")
    else:
        if slot.attribute_key == "birthday":
            year, month, day = (value.get(key) for key in ("year", "month", "day"))
            full_date = dt.date(year, month, day) if all(x is not None for x in (year, month, day)) else None
            fields = dict(birthday=full_date, birthday_year=year, birthday_month=month, birthday_day=day)
        else:
            fields = {slot.attribute_key: value.get(slot.attribute_key)}
        for key, val in fields.items():
            if getattr(contact, key) != val:
                setattr(contact, key, val)
                changed.append(key)
    if changed:
        contact.updated_at = _now()
        source = "manual_edit" if suppressed or assertion.source_key == "user_manual" else "other"
        record_contact_change(session, contact, source, changed_fields=changed,
                              note=f"Fact slot {slot.id}; assertion {slot.selected_assertion_id}; {slot.resolution_mode}")


def suppress_slot(session: Session, slot_id: int, *, by: str, note: str | None = None) -> None:
    slot = session.get(ContactFactSlot, slot_id)
    if slot is None:
        raise ValueError("Fact slot not found")
    slot.resolution_mode = "suppressed"
    slot.selected_assertion_id = None
    slot.decision_by, slot.decision_note = by, note
    slot.resolved_at = slot.updated_at = _now()
    project_slot_to_cache(session, slot)


def pin_assertion(session: Session, assertion_id: int, *, by: str, note: str | None = None) -> None:
    assertion = session.get(ContactFactAssertion, assertion_id)
    if assertion is None:
        raise ValueError("Fact assertion not found")
    slot = session.get(ContactFactSlot, assertion.slot_id)
    slot.resolution_mode = "pinned"
    slot.selected_assertion_id = assertion.id
    slot.decision_by, slot.decision_note = by, note
    slot.resolved_at = slot.updated_at = _now()
    project_slot_to_cache(session, slot)


def release_pin(session: Session, slot_id: int) -> None:
    slot = session.get(ContactFactSlot, slot_id)
    if slot is None:
        raise ValueError("Fact slot not found")
    slot.resolution_mode = "auto"
    slot.decision_by = slot.decision_note = None
    resolve_slot(session, slot)
    project_slot_to_cache(session, slot)


def _as_dict(row: ContactFactSlot | ContactFactAssertion) -> dict:
    result = {}
    for column in row.__table__.columns:
        value = getattr(row, column.name)
        if isinstance(value, dt.datetime):
            value = value.isoformat()
        elif isinstance(value, Decimal):
            value = float(value)
        result[column.name] = value
    return result


def get_contact_facts(session: Session, contact_id: int, attribute_key: str | None = None) -> list[dict]:
    query = select(ContactFactSlot).where(ContactFactSlot.contact_id == contact_id)
    if attribute_key is not None:
        query = query.where(ContactFactSlot.attribute_key == attribute_key)
    result = []
    for slot in session.scalars(query.order_by(ContactFactSlot.attribute_key, ContactFactSlot.item_key, ContactFactSlot.id)):
        assertions = session.scalars(select(ContactFactAssertion).where(
            ContactFactAssertion.slot_id == slot.id,
        ).order_by(ContactFactAssertion.observed_at, ContactFactAssertion.id))
        result.append({**_as_dict(slot), "assertions": [_as_dict(row) for row in assertions]})
    return result
