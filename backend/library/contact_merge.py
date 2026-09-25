"""Transactional contact merge; commit and rollback belong to the caller."""

from sqlalchemy import func, or_, select, update

from library.contact_channels import CHANNEL_FIELDS, channel_key, contact_channels
from library.contact_change_log import record_contact_change
from library.contact_names import contact_display_name
from library.contact_photos import ensure_photo_link
from library.db.models import (
    ChatMessage, Contact, ContactAddress, ContactChangeLog, ContactEducation, ContactEventParticipant,
    ContactFamilyCreation, ContactGroupMembership, ContactInterestMembership, ContactLink, ContactLookupResult,
    ContactOrganization, ContactPhotoLink, ContactRelationship,
)

MERGE_FIELDS = (
    "first_name", "last_name", "gender", "display_label", "phone_number", "email", "company", "position",
    "current_city", "hometown", "birthday", "birthday_month", "birthday_day", "pesel", "notes", "private_notes",
    "category_id", "languages", "nationality", "photo_storage_key", "photo_thumbnail_storage_key",
)


def merge_contacts(session, primary_id: int, duplicate_id: int, field_choices: dict[str, str]) -> Contact:
    if any(type(value) is not int or value <= 0 for value in (primary_id, duplicate_id)):
        raise ValueError("Contact ids must be positive integers")
    if primary_id == duplicate_id:
        raise ValueError("Two different contacts are required")
    if not isinstance(field_choices, dict) or any(
        field not in MERGE_FIELDS or choice not in ("primary", "duplicate")
        for field, choice in field_choices.items()
    ):
        raise ValueError("Invalid field_choices")
    rows = session.scalars(select(Contact).where(Contact.id.in_((primary_id, duplicate_id)))
                           .order_by(Contact.id).with_for_update()).all()
    by_id = {row.id: row for row in rows}
    if len(by_id) != 2:
        raise ValueError("Contact not found")
    primary, duplicate = by_id[primary_id], by_id[duplicate_id]
    duplicate_name = contact_display_name(duplicate)
    values = {
        field: getattr(duplicate, field) for field, choice in field_choices.items()
        if choice == "duplicate" and getattr(primary, field) != getattr(duplicate, field)
    }
    changed_fields = list(values)
    for field, (legacy, _) in CHANNEL_FIELDS.items():
        entries, seen = [], set()
        original = contact_channels(primary, field)
        for entry in original + contact_channels(duplicate, field):
            key = channel_key(entry["value"], field)
            if key not in seen:
                entries.append(dict(entry))
                seen.add(key)
        selected = values.get(legacy, getattr(primary, legacy))
        if selected:
            selected_key = channel_key(selected, field)
            entries.sort(key=lambda entry: channel_key(entry["value"], field) != selected_key)
        if entries != original:
            values[field] = entries
            if seen - {channel_key(entry["value"], field) for entry in original}:
                changed_fields.append(field)
    if values.get("pesel"):
        session.execute(update(Contact).where(Contact.id == duplicate_id).values(pesel=None))
    # The channel mapper hook replaces primary entries and caps lists at 50; a merge
    # must preserve every channel, including when the selected scalar is empty.
    session.execute(update(Contact).where(Contact.id == primary_id).values(**values, updated_at=func.now()))
    photo_links = session.execute(select(ContactPhotoLink).where(
        ContactPhotoLink.contact_id == duplicate_id,
    )).scalars().all()
    for link in photo_links:
        if session.get(ContactPhotoLink, (primary_id, link.storage_key)) is None:
            session.add(ContactPhotoLink(contact_id=primary_id, storage_key=link.storage_key,
                                         depicts_contact=link.depicts_contact))
    photo_key = values.get("photo_storage_key", primary.photo_storage_key)
    if photo_key:
        ensure_photo_link(session, primary_id, photo_key)
    for model, key, marker in (
        (ContactGroupMembership, "group_id", "groups"),
        (ContactInterestMembership, "interest_id", "interests"),
        (ContactEventParticipant, "event_id", "events"),
    ):
        column = getattr(model, key)
        existing = set(session.scalars(select(column).where(model.contact_id == primary_id)))
        incoming = set(session.scalars(select(column).where(model.contact_id == duplicate_id)))
        for ident in incoming - existing:
            session.add(model(contact_id=primary_id, **{key: ident}))
        if incoming - existing:
            changed_fields.append(marker)
    for model in (
        ContactLink, ContactLookupResult, ContactAddress, ContactOrganization, ContactEducation,
        ContactFamilyCreation, ChatMessage, ContactChangeLog,
    ):
        session.execute(update(model).where(model.contact_id == duplicate_id).values(contact_id=primary_id))
    relationships = session.scalars(select(ContactRelationship).where(or_(
        ContactRelationship.contact_id == duplicate_id, ContactRelationship.related_contact_id == duplicate_id,
    )).order_by(ContactRelationship.id)).all()
    for relation in relationships:
        left = primary_id if relation.contact_id == duplicate_id else relation.contact_id
        right = primary_id if relation.related_contact_id == duplicate_id else relation.related_contact_id
        conflict = session.scalar(select(ContactRelationship.id).where(
            ContactRelationship.contact_id == left, ContactRelationship.related_contact_id == right,
            ContactRelationship.relationship_type == relation.relationship_type,
            ContactRelationship.id != relation.id,
        ))
        if left == right or conflict is not None:
            session.delete(relation)
        else:
            relation.contact_id, relation.related_contact_id = left, right
        session.flush()
    record_contact_change(
        session, primary, source="other", changed_fields=changed_fields,
        note=f"Scalono z kontaktem #{duplicate_id} ({duplicate_name})",
    )
    session.delete(duplicate)
    session.flush()
    session.expire(primary)
    return primary
