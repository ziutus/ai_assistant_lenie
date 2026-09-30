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


# Statuses an external (non-manual) caller may set. "superseded" is reserved for the service itself.
EXTERNAL_ASSERTION_STATUSES = ("candidate", "confirmed", "rejected")
# Attributes an external source may assert through the REST API. Education is many-valued and
# projects into contact_education rows, so it keeps its own endpoints for now.
EXTERNAL_ASSERTION_ATTRIBUTES = ("birthday", "gender", "current_city", "hometown")
_GENDER_VALUES = ("male", "female", "other")


def validate_assertion_value(attribute_key: str, value) -> dict:
    """Return the normalised value dict for an externally asserted fact, or raise ValueError."""
    if attribute_key not in EXTERNAL_ASSERTION_ATTRIBUTES:
        raise ValueError(f"attribute_key must be one of {EXTERNAL_ASSERTION_ATTRIBUTES}")
    if not isinstance(value, dict):
        raise ValueError("value must be a JSON object")
    if attribute_key == "birthday":
        unknown = set(value) - {"year", "month", "day"}
        if unknown:
            raise ValueError(f"birthday value has unknown keys: {sorted(unknown)}")
        year, month, day = (value.get(key) for key in ("year", "month", "day"))
        for key, item in (("year", year), ("month", month), ("day", day)):
            if item is not None and (type(item) is not int):
                raise ValueError(f"birthday {key} must be an integer or null")
        if year is None and month is None and day is None:
            raise ValueError("birthday value needs at least a year or a month with a day")
        if (month is None) != (day is None):
            raise ValueError("birthday month and day must be provided together")
        if year is not None and not 1900 <= year <= dt.date.today().year:
            raise ValueError(f"birthday year must be between 1900 and {dt.date.today().year}")
        if month is not None:
            try:
                dt.date(year if year is not None else 2000, month, day)  # 2000 is a leap year: allows 29 Feb
            except ValueError as exc:
                raise ValueError(f"invalid birthday date: {exc}") from None
        return {"year": year, "month": month, "day": day}
    if set(value) != {attribute_key}:
        raise ValueError(f"{attribute_key} value must be exactly {{'{attribute_key}': ...}}")
    item = value[attribute_key]
    if not isinstance(item, str) or not item.strip():
        raise ValueError(f"{attribute_key} must be a non-empty string")
    item = item.strip()
    if attribute_key == "gender":
        if item not in _GENDER_VALUES:
            raise ValueError(f"gender must be one of {_GENDER_VALUES}")
    elif len(item) > 200:
        raise ValueError(f"{attribute_key} must be at most 200 characters")
    return {attribute_key: item}


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


def project_slot_to_cache(session: Session, slot: ContactFactSlot, *, clear: bool = False) -> None:
    """Copy the selected assertion into the legacy Contact/ContactEducation columns.

    ``clear=True`` blanks the cache even though the slot is not suppressed. It is only meant for the
    moment a rejection removes the value that the cache was showing: a slot with nothing selected is
    otherwise left alone, because the columns may hold values written before the slot existed.
    """
    suppressed = slot.resolution_mode == "suppressed" or clear
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
        source = "manual_edit" if slot.resolution_mode == "suppressed" or (
            assertion is not None and assertion.source_key == "user_manual") else "other"
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


def require_external_source(session: Session, source_key) -> str:
    """Return a known, non-manual source key or raise ValueError."""
    if not isinstance(source_key, str) or not source_key.strip():
        raise ValueError("source_key is required")
    if source_key == "user_manual":
        raise ValueError("source_key 'user_manual' is reserved for edits made by the owner")
    if session.get(ContactFactSource, source_key) is None:
        raise ValueError(f"Unknown fact source: {source_key}")
    return source_key


def assertion_summary(session: Session, assertion: ContactFactAssertion) -> dict:
    """Small outcome record for an API response: did the assertion end up as the visible value?"""
    slot = session.get(ContactFactSlot, assertion.slot_id)
    return {
        "assertion_id": assertion.id, "slot_id": slot.id, "attribute_key": slot.attribute_key,
        "source_key": assertion.source_key, "status": assertion.status,
        "resolution_mode": slot.resolution_mode, "selected_assertion_id": slot.selected_assertion_id,
        "applied": slot.selected_assertion_id == assertion.id,
    }


def set_assertion_status(
    session: Session, assertion_id: int, status: str, *, by: str, note: str | None = None,
    contact_id: int | None = None,
) -> ContactFactAssertion:
    """Review a non-manual assertion (candidate / confirmed / rejected) and re-resolve its slot.

    Rejecting the assertion that the slot currently shows releases a pin on it and, when nothing else
    qualifies, blanks the legacy cache. Manual (``user_manual``) assertions are the owner's own word
    and are changed only through the manual PATCH endpoints, never through review.
    """
    if status not in EXTERNAL_ASSERTION_STATUSES:
        raise ValueError(f"status must be one of {EXTERNAL_ASSERTION_STATUSES}")
    assertion = session.get(ContactFactAssertion, assertion_id)
    slot = session.get(ContactFactSlot, assertion.slot_id) if assertion is not None else None
    if assertion is None or (contact_id is not None and slot.contact_id != contact_id):
        raise LookupError("Fact assertion not found")
    if assertion.source_key == "user_manual":
        raise PermissionError("Manual assertions cannot be reviewed; edit the contact instead")
    was_shown = slot.selected_assertion_id == assertion.id
    now = _now()
    assertion.status = status
    assertion.reviewed_by, assertion.reviewed_at, assertion.review_note = by, now, note
    assertion.updated_at = now
    if status == "rejected" and was_shown and slot.resolution_mode == "pinned":
        slot.resolution_mode = "auto"
        slot.decision_by = slot.decision_note = None
    session.flush()
    resolve_slot(session, slot)
    slot.updated_at = now
    rejected_shown = status == "rejected" and was_shown and slot.selected_assertion_id is None
    project_slot_to_cache(session, slot, clear=rejected_shown and slot.resolution_mode == "auto")
    return assertion


def reassign_assertion_source(
    session: Session, assertion_id: int, source_key: str, *, unpin: bool = True,
) -> ContactFactAssertion:
    """Correct the provenance of an assertion that was recorded under the wrong source.

    Used to repair Facebook values that were saved through the manual PATCH endpoint and therefore
    look like the owner's own input. The value stays selected and the cache is untouched; only the
    source (and, with ``unpin``, the manual pin on its slot) changes, so later observations from
    better sources can compete with it normally.
    """
    assertion = session.get(ContactFactAssertion, assertion_id)
    if assertion is None:
        raise ValueError("Fact assertion not found")
    if source_key == "user_manual" or session.get(ContactFactSource, source_key) is None:
        raise ValueError("source_key must be an existing non-manual source")
    slot = session.get(ContactFactSlot, assertion.slot_id)
    dedup_key = hashlib.sha256(
        f"{slot.id}|{source_key}|{assertion.source_record_key}|{json.dumps(assertion.value, sort_keys=True)}".encode()
    ).hexdigest()
    clash = session.scalar(select(ContactFactAssertion).where(ContactFactAssertion.dedup_key == dedup_key))
    if clash is not None and clash.id != assertion.id:
        raise ValueError("An assertion with the same source, record and value already exists")
    assertion.source_key, assertion.dedup_key, assertion.updated_at = source_key, dedup_key, _now()
    if unpin and slot.resolution_mode == "pinned" and slot.selected_assertion_id == assertion.id:
        slot.resolution_mode = "auto"
        slot.decision_by = slot.decision_note = None
        slot.updated_at = _now()
    session.flush()
    return assertion


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
