"""REST API for the private contact book (personal CRM), independent of the
NER persons registry (library/person_registry.py) — a contact here may
never appear in any document. See docs: contact_categories is a lookup
table managed from the UI (like DiscoverySource); contact_relationships is
directional and single-row (no automatic reciprocal row/label)."""

import datetime
import logging
import re
from pathlib import Path
from uuid import uuid4

from flask import Blueprint, g, jsonify, request
from sqlalchemy import column, false, func, or_, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import aliased, joinedload, selectinload
from werkzeug.utils import secure_filename

from library.address_formatting import ADDRESS_FIELD_LIMITS, format_address
from library.address_parsing import ADDRESS_NOTES_MAX_LENGTH, parse_address_text
from library.address_geocoding import geocode_address
from library.address_validation import validate_address
from library.contact_birthdays import upcoming_birthday_entry
from library.contact_channels import channel_patch, contact_channels
from library.contact_change_log import CONTACT_CHANGE_SOURCES, record_contact_change
from library.contact_names import contact_display_name, validate_contact_name
from library.contact_phones import phone_search_digits
from library.contact_photo_thumbnails import _photo_thumbnail_storage_key, generate_photo_thumbnail
from library.db.engine import get_scoped_session
from library.db.models import (
    Address, ContactAddress, ContactAlternateName,
    ChatConversation, ChatMessage,
    Contact, ContactPhoto, ContactCategory, ContactChangeLog, ContactGroup, ContactGroupEvent, ContactGroupMembership, ContactLink,
    ContactDuplicateDismissal, ContactEducation, ContactInterest, ContactInterestMembership,
    ContactLookupResult, ContactEventParticipant, ContactOrganization, ContactRelationship, Document,
)

bp = Blueprint("contacts", __name__)
logger = logging.getLogger(__name__)


def _duplicate_summary(row: Contact) -> dict:
    return {
        **{field: getattr(row, field) for field in (
            "id", "uuid", "first_name", "last_name", "company", "phone_number", "email", "current_city", "is_archived",
        )},
        "display_name": contact_display_name(row),
        "category_name": row.category.name if row.category else None,
        "photo_thumbnail_url": _contact_photo_thumbnail_url(row),
        "groups": [{"id": group.id, "name": group.name} for group in row.groups],
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


@bp.route("/contacts/duplicates", methods=["GET", "OPTIONS"])
def contacts_duplicates():
    if request.method == "OPTIONS":
        return {"status": "OK"}, 200
    from library.contact_duplicates import find_duplicate_candidates
    session = get_scoped_session()
    include_archived = request.args.get("include_archived", "").lower() in ("1", "true", "yes")
    pairs = find_duplicate_candidates(session, include_archived=include_archived)
    return jsonify({"status": "success", "duplicates": [
        {**pair, "contact_a": _duplicate_summary(pair["contact_a"]), "contact_b": _duplicate_summary(pair["contact_b"])}
        for pair in pairs
    ]})


@bp.route("/contacts/duplicates/dismiss", methods=["POST", "OPTIONS"])
def contacts_duplicates_dismiss():
    if request.method == "OPTIONS":
        return {"status": "OK"}, 200
    from library.contact_duplicates import dismiss_duplicate_pair
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or any(
        type(data.get(key)) is not int or data[key] <= 0 for key in ("contact_id_a", "contact_id_b")
    ):
        return {"status": "error", "message": "Contact ids must be positive integers"}, 400
    session = get_scoped_session()
    try:
        if any(session.get(Contact, data[key]) is None for key in ("contact_id_a", "contact_id_b")):
            return {"status": "error", "message": "Contact not found"}, 404
        row: ContactDuplicateDismissal = dismiss_duplicate_pair(
            session, data["contact_id_a"], data["contact_id_b"], data.get("note"),
        )
        session.commit()
        return jsonify({"status": "success", "dismissal_id": row.id})
    except ValueError as exc:
        session.rollback()
        return {"status": "error", "message": str(exc)}, 400
    except Exception:
        session.rollback()
        return {"status": "error", "message": "DB error"}, 500


@bp.route("/contacts/merge", methods=["POST", "OPTIONS"])
def contacts_merge():
    if request.method == "OPTIONS":
        return {"status": "OK"}, 200
    from library.contact_merge import merge_contacts
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return {"status": "error", "message": "JSON object required"}, 400
    session = get_scoped_session()
    try:
        row = merge_contacts(
            session, data.get("primary_contact_id"), data.get("duplicate_contact_id"), data.get("field_choices", {}),
        )
        session.commit()
        return jsonify({
            "status": "success", "contact": _contact_dict(row), "deleted_contact_id": data["duplicate_contact_id"],
        })
    except ValueError as exc:
        session.rollback()
        return {"status": "error", "message": str(exc)}, 400
    except Exception:
        session.rollback()
        return {"status": "error", "message": "DB error"}, 500

_CONTACT_FIELDS = (
    "first_name", "last_name", "phone_number", "email",
    "company", "position", "current_city", "hometown", "pesel", "notes", "display_label",
)

_LOOKUP_TYPES = ("phone", "linkedin", "web", "email")
_LOOKUP_STATUSES = ("no_results", "candidate", "confirmed", "rejected")

_ORG_TYPES = ("employment", "jdg", "board", "ownership", "other")
_ORG_STATUSES = ("candidate", "confirmed", "rejected")
_ORG_FIELDS = (
    "organization_name", "role", "nip", "regon", "address", "correspondence_address", "source_url", "notes",
)
_ORG_DATE_FIELDS = ("start_date", "end_date", "suspended_at", "verified_at")

_LINK_TYPES = ("linkedin", "facebook", "instagram", "twitter", "website", "fixly", "other")

_GENDER_VALUES = ("male", "female", "other")

_LANGUAGE_LEVELS = ("A1", "A2", "B1", "B2", "C1", "C2")


def _normalize_languages(value) -> tuple[list[dict] | None, str | None]:
    """Validate/normalize the `languages` payload: a list of
    {"language": str, "native": bool, "level": str|None} entries. `level` is
    a CEFR code and only meaningful when not native (native clears it).
    Returns (normalized, None) on success or (None, error_message) on
    failure — same convention as validate_contact_name — rather than
    raising, so an API error response never carries exception text."""
    if value is None:
        return [], None
    if not isinstance(value, list):
        return None, "languages must be a list"
    normalized = []
    for entry in value:
        if not isinstance(entry, dict):
            return None, "each languages entry must be an object"
        language = (entry.get("language") or "").strip()
        if not language:
            return None, "each languages entry requires a non-empty language"
        native = bool(entry.get("native"))
        level = (entry.get("level") or "").strip().upper() or None
        if level and level not in _LANGUAGE_LEVELS:
            return None, f"level must be one of {_LANGUAGE_LEVELS}"
        if native:
            level = None
        normalized.append({"language": language, "native": native, "level": level})
    return normalized, None


def _normalize_nationality(value) -> tuple[list[str] | None, str | None]:
    """Validate/normalize the `nationality` payload: a list of plain
    strings (dual/multiple citizenship is common, so this is not a single
    value). Returns (normalized, None) or (None, error_message), same
    convention as _normalize_languages."""
    if value is None:
        return [], None
    if not isinstance(value, list):
        return None, "nationality must be a list"
    normalized = []
    for entry in value:
        if not isinstance(entry, str):
            return None, "each nationality entry must be a string"
        entry = entry.strip()
        if not entry:
            return None, "each nationality entry must be non-empty"
        normalized.append(entry)
    return normalized, None

# Immutable keys preserve descriptions and other contacts sharing the old photo.
_PHOTO_ALLOWED_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp", ".gif"})


def _photo_storage_key(contact_uuid: str, extension: str) -> str:
    return f"contacts/{contact_uuid}/photos/{uuid4()}{extension}"


def _category_dict(row: ContactCategory, count: int | None = None) -> dict:
    data = {
        "id": row.id,
        "name": row.name,
        "description": row.description,
        "is_active": row.is_active,
    }
    if count is not None:
        data["count"] = count
    return data


def _category_contact_count(session, category_id: int) -> int:
    return session.execute(
        select(func.count()).select_from(Contact).where(Contact.category_id == category_id)
    ).scalar_one()


def _group_dict(row: ContactGroup, count: int | None = None) -> dict:
    data = {
        "id": row.id,
        "name": row.name,
        "description": row.description,
    }
    if count is not None:
        data["count"] = count
    return data


def _event_dict(row: ContactGroupEvent) -> dict:
    return {
        "id": row.id,
        "group_id": row.group_id,
        "group_name": row.group.name if row.group else None,
        "participants": [{
            "id": contact.id,
            "first_name": contact.first_name,
            "last_name": contact.last_name,
            "display_name": contact_display_name(contact),
        } for contact in row.participants],
        "title": row.title,
        "event_date": row.event_date.isoformat(),
        "summary": row.summary,
        "source_document_id": row.source_document_id,
        "source_document_title": row.source_document.title if row.source_document else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _event_values(session, data, partial=False, row=None) -> dict:
    if not isinstance(data, dict):
        raise ValueError("JSON object required")
    values = {}
    if not partial or "title" in data:
        title = data.get("title")
        if not isinstance(title, str) or not title.strip() or len(title.strip()) > 255:
            raise ValueError("title must be a non-empty string of at most 255 characters")
        values["title"] = title.strip()
    if not partial or "event_date" in data:
        try:
            values["event_date"] = datetime.date.fromisoformat(data.get("event_date"))
        except (ValueError, TypeError):
            raise ValueError("event_date must be a valid ISO date") from None
    if "summary" in data:
        summary = data["summary"]
        if summary is not None and not isinstance(summary, str):
            raise ValueError("summary must be a string or null")
        values["summary"] = summary.strip() or None if summary is not None else None
    if "source_document_id" in data:
        doc_id = data["source_document_id"]
        if doc_id is not None and (type(doc_id) is not int or doc_id <= 0):
            raise ValueError("source_document_id must be a positive integer or null")
        document = session.get(Document, doc_id) if doc_id is not None else None
        if doc_id is not None and document is None:
            raise ValueError("source_document_id not found")
        values["source_document_id"] = doc_id
        values["source_document"] = document
    if "group_id" in data:
        group_id = data["group_id"]
        if group_id is not None and (type(group_id) is not int or group_id <= 0):
            raise ValueError("group_id must be a positive integer or null")
        group = session.get(ContactGroup, group_id) if group_id is not None else None
        if group_id is not None and group is None:
            raise ValueError("group_id not found")
        values["group_id"] = group_id
        values["group"] = group
    if "participant_contact_ids" in data:
        ids = data["participant_contact_ids"]
        if not isinstance(ids, list) or any(type(ident) is not int or ident <= 0 for ident in ids):
            raise ValueError("participant_contact_ids must be a list of positive integers")
        participants = []
        for ident in dict.fromkeys(ids):
            contact = session.get(Contact, ident)
            if contact is None:
                raise ValueError(f"participant_contact_ids: contact {ident} not found")
            participants.append(contact)
        values["participants"] = participants
    group_id = values.get("group_id", row.group_id if partial and row is not None else None)
    participants = values.get("participants", row.participants if partial and row is not None else [])
    if group_id is None and not participants:
        raise ValueError("Wydarzenie musi być powiązane z grupą lub co najmniej jednym kontaktem")
    return values


def _events_query(contact_id=None, group_id=None):
    query = select(ContactGroupEvent).options(
        joinedload(ContactGroupEvent.group), joinedload(ContactGroupEvent.source_document),
        selectinload(ContactGroupEvent.participants),
    )
    if contact_id is not None:
        # Subqueries avoid duplicate events when both forms of membership match.
        query = query.where(or_(
            ContactGroupEvent.group_id.in_(select(ContactGroupMembership.group_id).where(
                ContactGroupMembership.contact_id == contact_id,
            )),
            ContactGroupEvent.id.in_(select(ContactEventParticipant.event_id).where(
                ContactEventParticipant.contact_id == contact_id,
            )),
        ))
    if group_id is not None:
        query = query.where(ContactGroupEvent.group_id == group_id)
    return query.order_by(ContactGroupEvent.event_date.desc(), ContactGroupEvent.id.desc())


def _group_events(session, group_id):
    return session.execute(
        _events_query(group_id=group_id)
    ).scalars().all()


def _group_contact_count(session, group_id: int) -> int:
    return session.execute(
        select(func.count()).select_from(ContactGroupMembership).where(
            ContactGroupMembership.group_id == group_id
        )
    ).scalar_one()


def _channel_search(field, phrase, digits=None):
    # Match individual values/labels, not JSON keys or concatenated phone entries.
    entries = func.jsonb_array_elements(field).table_valued(column("value", JSONB)).alias()
    value = entries.c.value["value"].astext
    conditions = [func.unaccent(value).ilike(phrase), func.unaccent(entries.c.value["label"].astext).ilike(phrase)]
    if digits:
        conditions.append(func.regexp_replace(value, "[^0-9]", "", "g").like(f"%{digits}%"))
    return select(1).select_from(entries).where(or_(*conditions)).exists()


def _contact_dict(row: Contact) -> dict:
    auth = getattr(g, "auth", None)
    return {
        "id": row.id,
        "uuid": row.uuid,
        "category_id": row.category_id,
        "category_name": row.category.name if row.category else None,
        "groups": [{"id": g.id, "name": g.name} for g in row.groups],
        "interests": [{"id": i.id, "name": i.name} for i in row.interests],
        "first_name": row.first_name,
        "last_name": row.last_name,
        "gender": row.gender,
        "display_label": row.display_label,
        "display_name": contact_display_name(row),
        "phone_number": row.phone_number,
        "email": row.email,
        "phone_numbers": contact_channels(row, "phone_numbers"),
        "email_addresses": contact_channels(row, "email_addresses"),
        "company": row.company,
        "position": row.position,
        "addresses": [_contact_address_dict(link) for link in _contact_addresses(get_scoped_session(), row.id)],
        "current_city": row.current_city,
        "hometown": row.hometown,
        "birthday": row.birthday.isoformat() if row.birthday else None,
        "birthday_month": row.birthday_month,
        "birthday_day": row.birthday_day,
        "pesel": row.pesel,
        "notes": row.notes,
        "private_notes": row.private_notes if auth and auth.kind == "service" else None,
        "languages": row.languages or [],
        "nationality": row.nationality or [],
        "is_archived": row.is_archived,
        "has_whatsapp_profile": bool(row.whatsapp_profile),
        "photo_thumbnail_url": _contact_photo_thumbnail_url(row),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _lookup_result_dict(row: ContactLookupResult) -> dict:
    return {
        "id": row.id,
        "contact_id": row.contact_id,
        "lookup_type": row.lookup_type,
        "status": row.status,
        "url": row.url,
        "query_used": row.query_used,
        "notes": row.notes,
        "searched_at": row.searched_at.isoformat() if row.searched_at else None,
    }


def _address_dict(row: Address) -> dict:
    return {
        "id": row.id, "label": row.label,
        **{field: getattr(row, field) for field in ADDRESS_FIELD_LIMITS},
        "formatted_address": format_address(row),
        "notes": row.notes,
        "latitude": float(row.latitude) if row.latitude is not None else None,
        "longitude": float(row.longitude) if row.longitude is not None else None,
        "geocoded": row.latitude is not None,
        "verified_at": row.verified_at.isoformat() if row.verified_at else None,
    }


def _contact_address_dict(row: ContactAddress) -> dict:
    return {
        "id": row.id, "role": row.role, "is_primary": row.is_primary,
        "address": _address_dict(row.address),
    }


def _contact_addresses(session, contact_id):
    return session.execute(
        select(ContactAddress).options(joinedload(ContactAddress.address))
        .where(ContactAddress.contact_id == contact_id)
        .order_by(ContactAddress.is_primary.desc(), ContactAddress.id)
    ).scalars().all()


def _organization_dict(row: ContactOrganization) -> dict:
    return {
        "id": row.id,
        "contact_id": row.contact_id,
        "org_type": row.org_type,
        "organization_name": row.organization_name,
        "role": row.role,
        "nip": row.nip,
        "regon": row.regon,
        "address": row.address,
        "correspondence_address": row.correspondence_address,
        "is_primary": row.is_primary,
        "is_current": row.is_current,
        "start_date": row.start_date.isoformat() if row.start_date else None,
        "end_date": row.end_date.isoformat() if row.end_date else None,
        "suspended_at": row.suspended_at.isoformat() if row.suspended_at else None,
        "verified_at": row.verified_at.isoformat() if row.verified_at else None,
        "status": row.status,
        "source_url": row.source_url,
        "notes": row.notes,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _link_dict(row: ContactLink) -> dict:
    return {
        "id": row.id,
        "contact_id": row.contact_id,
        "link_type": row.link_type,
        "url": row.url,
        "label": row.label,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _change_log_dict(row: ContactChangeLog) -> dict:
    return {
        "id": row.id,
        "contact_id": row.contact_id,
        "source": row.source,
        "changed_fields": row.changed_fields or [],
        "note": row.note,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _relationship_dict(rel: ContactRelationship, other: Contact, direction: str) -> dict:
    return {
        "id": rel.id,
        "direction": direction,  # "outgoing" (this contact -> other) or "incoming" (other -> this contact)
        "relationship_type": rel.relationship_type,
        "note": rel.note,
        "start_date": rel.start_date.isoformat() if rel.start_date else None,
        "end_date": rel.end_date.isoformat() if rel.end_date else None,
        "contact_id": rel.contact_id,
        "related_contact_id": rel.related_contact_id,
        "other_contact": {
            "id": other.id,
            "first_name": other.first_name,
            "last_name": other.last_name,
            "display_name": contact_display_name(other),
        },
    }


# --- categories --------------------------------------------------------

@bp.get("/contact_categories")
def contact_categories_list():
    session = get_scoped_session()
    query = select(ContactCategory)
    if request.args.get("active") in ("1", "true", "yes"):
        query = query.where(ContactCategory.is_active.is_(True))
    rows = session.execute(query.order_by(ContactCategory.name)).scalars().all()
    return jsonify({
        "status": "success",
        "contact_categories": [_category_dict(row, _category_contact_count(session, row.id)) for row in rows],
    }), 200


@bp.route("/contact_categories", methods=["POST", "OPTIONS"])
def contact_categories_add():
    if request.method == "OPTIONS":
        return {"status": "OK"}, 200

    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return {"status": "error", "message": "name is required"}, 400

    session = get_scoped_session()
    row = ContactCategory(
        name=name,
        description=(data.get("description") or "").strip() or None,
        is_active=bool(data.get("is_active", True)),
    )
    session.add(row)
    try:
        session.commit()
    except Exception:
        session.rollback()
        return {"status": "error", "message": "DB error (duplicate name?)"}, 409

    return jsonify({"status": "success", "contact_category": _category_dict(row, 0)}), 200


@bp.route("/contact_categories/<int:category_id>", methods=["PATCH", "OPTIONS"])
def contact_categories_update(category_id: int):
    if request.method == "OPTIONS":
        return {"status": "OK"}, 200

    data = request.get_json(silent=True) or {}
    session = get_scoped_session()
    row = session.get(ContactCategory, category_id)
    if row is None:
        return {"status": "error", "message": "Category not found"}, 404

    if "name" in data:
        name = (data.get("name") or "").strip()
        if not name:
            return {"status": "error", "message": "name cannot be empty"}, 400
        row.name = name
    if "description" in data:
        row.description = (data.get("description") or "").strip() or None
    if "is_active" in data:
        row.is_active = bool(data.get("is_active"))

    try:
        session.commit()
    except Exception:
        session.rollback()
        return {"status": "error", "message": "DB error (duplicate name?)"}, 409

    return jsonify({
        "status": "success",
        "contact_category": _category_dict(row, _category_contact_count(session, row.id)),
    }), 200


@bp.route("/contact_categories/<int:category_id>", methods=["DELETE", "OPTIONS"])
def contact_categories_delete(category_id: int):
    if request.method == "OPTIONS":
        return {"status": "OK"}, 200

    session = get_scoped_session()
    row = session.get(ContactCategory, category_id)
    if row is None:
        return {"status": "error", "message": "Category not found"}, 404
    used_by = _category_contact_count(session, row.id)
    if used_by > 0:
        return jsonify({
            "status": "error",
            "message": f"Category is used by {used_by} contacts — deactivate it instead",
        }), 409
    try:
        session.delete(row)
        session.commit()
    except Exception:
        session.rollback()
        return {"status": "error", "message": "DB error"}, 500
    return jsonify({"status": "success", "deleted_id": category_id}), 200


# --- groups (many-to-many, distinct from the single-value category) -----

@bp.get("/contact_groups")
def contact_groups_list():
    session = get_scoped_session()
    rows = session.execute(select(ContactGroup).order_by(ContactGroup.name)).scalars().all()
    return jsonify({
        "status": "success",
        "contact_groups": [_group_dict(row, _group_contact_count(session, row.id)) for row in rows],
    }), 200


@bp.get("/contact_groups/<int:group_id>")
def contact_groups_get(group_id: int):
    session = get_scoped_session()
    row = session.get(ContactGroup, group_id)
    if row is None:
        return {"status": "error", "message": "Group not found"}, 404
    data = _group_dict(row, _group_contact_count(session, group_id))
    data["events"] = [_event_dict(event) for event in _group_events(session, group_id)]
    return jsonify({"status": "success", "contact_group": data}), 200


@bp.get("/contact_groups/<int:group_id>/events")
def contact_group_events_list(group_id: int):
    session = get_scoped_session()
    if session.get(ContactGroup, group_id) is None:
        return {"status": "error", "message": "Group not found"}, 404
    return jsonify({"status": "success", "events": [
        _event_dict(event) for event in _group_events(session, group_id)
    ]}), 200


@bp.get("/contact_events")
def contact_events_list():
    filters = {}
    for name in ("contact_id", "group_id"):
        if name in request.args:
            try:
                filters[name] = int(request.args[name])
                if filters[name] <= 0:
                    raise ValueError
            except ValueError:
                return {"status": "error", "message": f"{name} must be a positive integer"}, 400
    session = get_scoped_session()
    rows = session.execute(_events_query(**filters)).scalars().all()
    return jsonify({"status": "success", "events": [_event_dict(row) for row in rows]}), 200


@bp.route("/contact_events", methods=["POST", "OPTIONS"])
@bp.route("/contact_groups/<int:group_id>/events", methods=["POST", "OPTIONS"])
def contact_group_events_add(group_id: int | None = None):
    if request.method == "OPTIONS":
        return {"status": "OK"}, 200
    session = get_scoped_session()
    if group_id is not None and session.get(ContactGroup, group_id) is None:
        return {"status": "error", "message": "Group not found"}, 404
    try:
        data = request.get_json(silent=True)
        if group_id is not None and isinstance(data, dict):
            data = {**data, "group_id": group_id}
        values = _event_values(session, data)
    except ValueError as exc:
        return {"status": "error", "message": str(exc)}, 400
    row = ContactGroupEvent(**values)
    session.add(row)
    try:
        session.commit()
    except Exception:
        session.rollback()
        return {"status": "error", "message": "DB error"}, 500
    return jsonify({"status": "success", "event": _event_dict(row)}), 200


@bp.route("/contact_group_events/<int:event_id>", methods=["PATCH", "OPTIONS"])
def contact_group_events_update(event_id: int):
    if request.method == "OPTIONS":
        return {"status": "OK"}, 200
    session = get_scoped_session()
    row = session.get(ContactGroupEvent, event_id)
    if row is None:
        return {"status": "error", "message": "Event not found"}, 404
    try:
        values = _event_values(session, request.get_json(silent=True), partial=True, row=row)
    except ValueError as exc:
        return {"status": "error", "message": str(exc)}, 400
    for key, value in values.items():
        setattr(row, key, value)
    row.updated_at = datetime.datetime.now()
    try:
        session.commit()
    except Exception:
        session.rollback()
        return {"status": "error", "message": "DB error"}, 500
    return jsonify({"status": "success", "event": _event_dict(row)}), 200


@bp.route("/contact_group_events/<int:event_id>", methods=["DELETE", "OPTIONS"])
def contact_group_events_delete(event_id: int):
    if request.method == "OPTIONS":
        return {"status": "OK"}, 200
    session = get_scoped_session()
    row = session.get(ContactGroupEvent, event_id)
    if row is None:
        return {"status": "error", "message": "Event not found"}, 404
    try:
        session.delete(row)
        session.commit()
    except Exception:
        session.rollback()
        return {"status": "error", "message": "DB error"}, 500
    return jsonify({"status": "success", "deleted_id": event_id}), 200


@bp.route("/contact_groups", methods=["POST", "OPTIONS"])
def contact_groups_add():
    if request.method == "OPTIONS":
        return {"status": "OK"}, 200

    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return {"status": "error", "message": "name is required"}, 400

    session = get_scoped_session()
    row = ContactGroup(name=name, description=(data.get("description") or "").strip() or None)
    session.add(row)
    try:
        session.commit()
    except Exception:
        session.rollback()
        return {"status": "error", "message": "DB error (duplicate name?)"}, 409

    return jsonify({"status": "success", "contact_group": _group_dict(row, 0)}), 200


@bp.route("/contact_groups/<int:group_id>", methods=["PATCH", "OPTIONS"])
def contact_groups_update(group_id: int):
    if request.method == "OPTIONS":
        return {"status": "OK"}, 200

    data = request.get_json(silent=True) or {}
    session = get_scoped_session()
    row = session.get(ContactGroup, group_id)
    if row is None:
        return {"status": "error", "message": "Group not found"}, 404

    if "name" in data:
        name = (data.get("name") or "").strip()
        if not name:
            return {"status": "error", "message": "name cannot be empty"}, 400
        row.name = name
    if "description" in data:
        row.description = (data.get("description") or "").strip() or None

    try:
        session.commit()
    except Exception:
        session.rollback()
        return {"status": "error", "message": "DB error (duplicate name?)"}, 409

    return jsonify({
        "status": "success",
        "contact_group": _group_dict(row, _group_contact_count(session, row.id)),
    }), 200


@bp.route("/contact_groups/<int:group_id>", methods=["DELETE", "OPTIONS"])
def contact_groups_delete(group_id: int):
    if request.method == "OPTIONS":
        return {"status": "OK"}, 200

    session = get_scoped_session()
    row = session.get(ContactGroup, group_id)
    if row is None:
        return {"status": "error", "message": "Group not found"}, 404
    used_by = _group_contact_count(session, row.id)
    if used_by > 0:
        return jsonify({
            "status": "error",
            "message": f"Group is used by {used_by} contacts — remove them from it first",
        }), 409
    try:
        session.delete(row)
        session.commit()
    except Exception:
        session.rollback()
        return {"status": "error", "message": "DB error"}, 500
    return jsonify({"status": "success", "deleted_id": group_id}), 200


@bp.route("/contacts/<int:contact_id>/groups", methods=["POST", "OPTIONS"])
def contact_groups_assign(contact_id: int):
    if request.method == "OPTIONS":
        return {"status": "OK"}, 200

    data = request.get_json(silent=True) or {}
    session = get_scoped_session()
    contact = session.get(Contact, contact_id)
    if contact is None:
        return {"status": "error", "message": "Contact not found"}, 404

    group_id = data.get("group_id")
    group = session.get(ContactGroup, group_id) if group_id is not None else None
    if group is None:
        return {"status": "error", "message": "group_id not found"}, 400

    if group not in contact.groups:
        contact.groups.append(group)
        record_contact_change(
            session, contact, "manual_edit", changed_fields=["groups"],
            note=f"Dodano do grupy „{group.name}”",
        )
        try:
            session.commit()
        except Exception:
            session.rollback()
            return {"status": "error", "message": "DB error"}, 500

    return jsonify({"status": "success", "contact": _contact_dict(contact)}), 200


@bp.route("/contacts/<int:contact_id>/groups/<int:group_id>", methods=["DELETE", "OPTIONS"])
def contact_groups_unassign(contact_id: int, group_id: int):
    if request.method == "OPTIONS":
        return {"status": "OK"}, 200

    session = get_scoped_session()
    contact = session.get(Contact, contact_id)
    if contact is None:
        return {"status": "error", "message": "Contact not found"}, 404
    group = session.get(ContactGroup, group_id)
    if group is not None and group in contact.groups:
        contact.groups.remove(group)
        record_contact_change(
            session, contact, "manual_edit", changed_fields=["groups"],
            note=f"Usunięto z grupy „{group.name}”",
        )
        try:
            session.commit()
        except Exception:
            session.rollback()
            return {"status": "error", "message": "DB error"}, 500

    return jsonify({"status": "success", "contact": _contact_dict(contact)}), 200


# --- contacts ------------------------------------------------------------

@bp.get("/contacts/upcoming_birthdays")
def contacts_upcoming_birthdays():
    session = get_scoped_session()
    days = max(1, min(request.args.get("days", default=30, type=int), 365))
    conditions = [or_(
        Contact.birthday.is_not(None),
        Contact.birthday_month.is_not(None) & Contact.birthday_day.is_not(None),
    )]
    archived_filter = (request.args.get("archived") or "").strip().lower()
    if archived_filter in ("1", "true", "yes"):
        conditions.append(Contact.is_archived.is_(True))
    elif archived_filter != "all":
        conditions.append(Contact.is_archived.is_(False))

    rows = session.execute(select(Contact).where(*conditions)).scalars().all()
    today = datetime.date.today()
    entries = []
    for row in rows:
        entry = upcoming_birthday_entry(row, today)
        if entry is not None and 0 <= entry["days_until"] <= days:
            entries.append(entry)
    entries.sort(key=lambda entry: entry["days_until"])
    return jsonify({"status": "success", "upcoming_birthdays": entries})


@bp.get("/contacts")
def contacts_list():
    session = get_scoped_session()

    conditions = []
    archived_filter = (request.args.get("archived") or "").strip().lower()
    if archived_filter in ("1", "true", "yes"):
        conditions.append(Contact.is_archived.is_(True))
    elif archived_filter != "all":
        conditions.append(Contact.is_archived.is_(False))

    category_id = request.args.get("category_id", type=int)
    if category_id is not None:
        conditions.append(Contact.category_id == category_id)

    # `group_id` remains supported for links saved before group multi-filtering
    # was introduced.  The group_filter mode mirrors spreadsheet filtering:
    # selected group IDs and the optional include_ungrouped value form one
    # inclusive list.  A contact with no group is the equivalent of a blank.
    group_id = request.args.get("group_id", type=int)
    group_ids = _parse_contact_group_ids(request.args.get("group_ids"))
    excluded_group_ids = _parse_contact_group_ids(request.args.get("exclude_group_ids"))
    interest_ids = _parse_contact_group_ids(request.args.get("interest_ids"))
    excluded_interest_ids = _parse_contact_group_ids(request.args.get("exclude_interest_ids"))
    if interest_ids:
        conditions.append(Contact.interests.any(ContactInterest.id.in_(interest_ids)))
    if excluded_interest_ids:
        conditions.append(~Contact.interests.any(ContactInterest.id.in_(excluded_interest_ids)))
    group_filter_active = (request.args.get("group_filter") or "").strip().lower() in ("1", "true", "yes")
    include_ungrouped = (request.args.get("include_ungrouped") or "").strip().lower() in ("1", "true", "yes")
    if group_filter_active:
        selected_group_conditions = []
        if group_ids:
            selected_group_conditions.append(Contact.groups.any(ContactGroup.id.in_(group_ids)))
        if include_ungrouped:
            selected_group_conditions.append(~Contact.groups.any())
        conditions.append(or_(*selected_group_conditions) if selected_group_conditions else false())
    elif group_id is not None or group_ids:
        if group_id is not None:
            group_ids.append(group_id)
        group_ids = list(dict.fromkeys(group_ids))
        conditions.append(Contact.groups.any(ContactGroup.id.in_(group_ids)))
    if excluded_group_ids:
        conditions.append(~Contact.groups.any(ContactGroup.id.in_(excluded_group_ids)))

    q = (request.args.get("q") or "").strip()
    if q:
        phrase = func.unaccent(f"%{q}%")
        digits = phone_search_digits(q)
        search_conditions = [
            func.unaccent(Contact.first_name).ilike(phrase),
            func.unaccent(Contact.last_name).ilike(phrase),
            func.unaccent(Contact.display_label).ilike(phrase),
            func.unaccent(func.coalesce(Contact.company, "")).ilike(phrase),
            func.unaccent(func.coalesce(Contact.phone_number, "")).ilike(phrase),
            func.unaccent(func.coalesce(Contact.email, "")).ilike(phrase),
            func.coalesce(Contact.pesel, "").ilike(phrase),
            _channel_search(Contact.phone_numbers, phrase, digits),
            _channel_search(Contact.email_addresses, phrase),
        ]
        if digits:
            search_conditions.append(func.regexp_replace(Contact.phone_number, "[^0-9]", "", "g").like(f"%{digits}%"))
        conditions.append(or_(*search_conditions))

    total = session.execute(
        select(func.count()).select_from(Contact).where(*conditions)
    ).scalar_one()

    offset = request.args.get("offset", default=0, type=int)
    limit = min(request.args.get("limit", default=100, type=int), 500)
    query = (
        select(Contact).where(*conditions)
        .order_by(func.coalesce(Contact.last_name, Contact.first_name, Contact.display_label),
                  Contact.first_name, Contact.id).offset(offset).limit(limit)
    )

    rows = session.execute(query).scalars().all()
    relationships_by_contact = _load_contact_relationships_summary(session, [row.id for row in rows])
    contacts_out = []
    for row in rows:
        data = _contact_dict(row)
        data["relationships"] = relationships_by_contact.get(row.id, [])
        contacts_out.append(data)

    return jsonify({
        "status": "success",
        "contacts": contacts_out,
        "total": total,
        "offset": offset,
        "limit": limit,
    }), 200


def _load_contact_relationships_summary(session, contact_ids: list[int]) -> dict[int, list[dict]]:
    """Lightweight per-contact relationships for the /contacts list view — just
    enough to render a chip (type + other person's name), unlike
    _relationship_dict's full nested contact object used by the detail page."""
    if not contact_ids:
        return {}

    result: dict[int, list[dict]] = {cid: [] for cid in contact_ids}
    other = aliased(Contact)

    outgoing = session.execute(
        select(ContactRelationship.contact_id, ContactRelationship.relationship_type,
               other.first_name, other.last_name, other.display_label, other.company)
        .join(other, other.id == ContactRelationship.related_contact_id)
        .where(ContactRelationship.contact_id.in_(contact_ids))
    ).all()
    for contact_id, relationship_type, first_name, last_name, display_label, company in outgoing:
        result[contact_id].append({
            "relationship_type": relationship_type,
            "direction": "outgoing",
            "other_name": " ".join(filter(None, [first_name, last_name])) or display_label or company or "Kontakt bez nazwy",
        })

    incoming = session.execute(
        select(ContactRelationship.related_contact_id, ContactRelationship.relationship_type,
               other.first_name, other.last_name, other.display_label, other.company)
        .join(other, other.id == ContactRelationship.contact_id)
        .where(ContactRelationship.related_contact_id.in_(contact_ids))
    ).all()
    for contact_id, relationship_type, first_name, last_name, display_label, company in incoming:
        result[contact_id].append({
            "relationship_type": relationship_type,
            "direction": "incoming",
            "other_name": " ".join(filter(None, [first_name, last_name])) or display_label or company or "Kontakt bez nazwy",
        })

    return result


def _parse_contact_group_ids(raw: str | None) -> list[int]:
    """Return unique positive IDs from a comma-separated query parameter."""
    if not raw:
        return []
    ids = []
    for value in raw.split(","):
        try:
            group_id = int(value)
        except ValueError:
            continue
        if group_id > 0 and group_id not in ids:
            ids.append(group_id)
    return ids


def _contact_chat_conversations(session, contact_id: int) -> list[dict]:
    """Conversations (chat_conversations, currently WhatsApp only — see
    library/chat_routes.py) this contact has at least one resolved message in,
    most recently active first. Read-only summary for the contact overview;
    the full thread is opened via /chats/:id."""
    rows = session.execute(
        select(
            ChatConversation.id,
            ChatConversation.display_name,
            ChatConversation.platform,
            func.count(ChatMessage.id),
            func.max(ChatMessage.sent_at),
        )
        .join(ChatMessage, ChatMessage.conversation_id == ChatConversation.id)
        .where(ChatMessage.contact_id == contact_id)
        .group_by(ChatConversation.id)
        .order_by(func.max(ChatMessage.sent_at).desc())
    ).all()
    return [
        {
            "id": conv_id,
            "display_name": display_name,
            "platform": platform,
            "message_count": message_count,
            "last_message_at": last_message_at.isoformat() if last_message_at else None,
        }
        for conv_id, display_name, platform, message_count, last_message_at in rows
    ]


@bp.get("/contacts/<int:contact_id>")
def contacts_get(contact_id: int):
    session = get_scoped_session()
    row = session.get(Contact, contact_id)
    if row is None:
        return {"status": "error", "message": "Contact not found"}, 404

    outgoing = session.execute(
        select(ContactRelationship, Contact)
        .join(Contact, Contact.id == ContactRelationship.related_contact_id)
        .where(ContactRelationship.contact_id == contact_id)
    ).all()
    incoming = session.execute(
        select(ContactRelationship, Contact)
        .join(Contact, Contact.id == ContactRelationship.contact_id)
        .where(ContactRelationship.related_contact_id == contact_id)
    ).all()

    relationships = [
        _relationship_dict(rel, other, "outgoing") for rel, other in outgoing
    ] + [
        _relationship_dict(rel, other, "incoming") for rel, other in incoming
    ]

    lookup_results = session.execute(
        select(ContactLookupResult)
        .where(ContactLookupResult.contact_id == contact_id)
        .order_by(ContactLookupResult.searched_at.desc())
    ).scalars().all()

    organizations = session.execute(
        select(ContactOrganization)
        .where(ContactOrganization.contact_id == contact_id)
        .order_by(ContactOrganization.is_current.desc(), ContactOrganization.is_primary.desc())
    ).scalars().all()

    links = session.execute(
        select(ContactLink)
        .where(ContactLink.contact_id == contact_id)
        .order_by(ContactLink.created_at.asc())
    ).scalars().all()

    change_log = session.execute(
        select(ContactChangeLog)
        .where(ContactChangeLog.contact_id == contact_id)
        .order_by(ContactChangeLog.created_at.desc())
    ).scalars().all()

    data = _contact_dict(row)
    data["photo_storage_key"] = row.photo_storage_key
    data["photo_thumbnail_storage_key"] = row.photo_thumbnail_storage_key
    data["merge_counts"] = {
        name: session.scalar(select(func.count()).select_from(model).where(model.contact_id == contact_id))
        for name, model in (("events", ContactEventParticipant), ("education", ContactEducation))
    }
    # Cap group and participant events at 20 to keep the contact overview compact;
    # the standalone events list exposes the complete history.
    events = session.execute(_events_query(contact_id=contact_id).limit(20)).scalars().all()
    data["events"] = [_event_dict(event) for event in events]
    data["alternate_names"] = [_alternate_name_dict(item) for item in getattr(row, "alternate_names", [])]
    data["relationships"] = relationships
    data["lookup_results"] = [_lookup_result_dict(lr) for lr in lookup_results]
    data["organizations"] = [_organization_dict(org) for org in organizations]
    data["links"] = [_link_dict(link) for link in links]
    data["change_log"] = [_change_log_dict(cl) for cl in change_log]
    data["whatsapp_profile"] = row.whatsapp_profile
    data["chat_conversations"] = _contact_chat_conversations(session, contact_id)
    data["photo_url"] = _contact_photo_url(row)
    from library.contact_photos import photo_dict
    data["photo"] = photo_dict(session.get(ContactPhoto, row.photo_storage_key)) if row.photo_storage_key else None
    return jsonify({"status": "success", "contact": data}), 200


def _contact_photo_thumbnail_url(row: Contact) -> str | None:
    if not row.photo_thumbnail_storage_key:
        return None
    from library.config_loader import load_config
    from library.storage import storage_from_config

    # Reuse the signing client across up to 500 contacts in this request.
    if "contact_photo_storage" not in g:
        g.contact_photo_storage = storage_from_config(load_config())
    return g.contact_photo_storage.presigned_get_url(row.photo_thumbnail_storage_key)


def _contact_photo_url(row: Contact) -> str | None:
    if not row.photo_storage_key:
        return None
    from library.config_loader import load_config
    from library.storage import storage_from_config

    return storage_from_config(load_config()).presigned_get_url(row.photo_storage_key)


@bp.route("/contacts/<int:contact_id>/photo", methods=["POST", "OPTIONS"])
def contact_photo_upload(contact_id: int):
    if request.method == "OPTIONS":
        return {"status": "OK"}, 200

    session = get_scoped_session()
    contact = session.get(Contact, contact_id)
    if contact is None:
        return {"status": "error", "message": "Contact not found"}, 404

    uploaded = request.files.get("photo")
    if uploaded is None or not uploaded.filename:
        return {"status": "error", "message": "multipart field 'photo' is required"}, 400

    safe_name = secure_filename(uploaded.filename)
    extension = Path(safe_name).suffix.lower()
    if extension not in _PHOTO_ALLOWED_EXTENSIONS:
        formats = ", ".join(sorted(ext.removeprefix(".").upper() for ext in _PHOTO_ALLOWED_EXTENSIONS))
        return {"status": "error", "message": f"Unsupported file type; allowed: {formats}"}, 400

    data = uploaded.read()
    if not data:
        return {"status": "error", "message": "file is empty"}, 400

    from library.config_loader import load_config
    from library.storage import storage_from_config

    key = _photo_storage_key(contact.uuid, extension)
    storage = storage_from_config(load_config())
    storage.put_bytes(key, data, content_type=uploaded.content_type)

    photo = ContactPhoto(storage_key=key, user_description_revision=0, ai_descriptions={})
    thumbnail_key = None
    try:
        thumbnail = generate_photo_thumbnail(data)
        thumbnail_key = _photo_thumbnail_storage_key(contact.uuid, key)
        storage.put_bytes(thumbnail_key, thumbnail, content_type="image/jpeg")
    except Exception:
        thumbnail_key = None
        logger.warning("Could not generate/store photo thumbnail for contact %s", contact_id, exc_info=True)
    try:
        session.add(photo)
        session.flush()
        contact.photo_storage_key = key
        contact.photo_thumbnail_storage_key = thumbnail_key
        contact.updated_at = datetime.datetime.now()
        record_contact_change(session, contact, "manual_edit", changed_fields=["photo_storage_key", "photo_thumbnail_storage_key"])
        session.commit()
    except Exception:
        session.rollback()
        return {"status": "error", "message": "DB error"}, 500

    from library.contact_photos import photo_dict
    return jsonify({"status": "success", "photo_url": storage.presigned_get_url(key), "photo": photo_dict(photo)}), 200


@bp.route("/contacts/<int:contact_id>/photo/regenerate_thumbnail", methods=["POST", "OPTIONS"])
def contact_photo_regenerate_thumbnail(contact_id: int):
    """Re-encode the thumbnail for the contact's CURRENT photo in place —
    same deterministic storage key, no new immutable photo version. Useful
    after an improvement to generate_photo_thumbnail() (e.g. face-aware
    cropping) that should apply to an already-uploaded photo without
    re-uploading identical pixels as a spurious new history entry."""
    if request.method == "OPTIONS":
        return {"status": "OK"}, 200

    session = get_scoped_session()
    contact = session.get(Contact, contact_id)
    if contact is None:
        return {"status": "error", "message": "Contact not found"}, 404
    if not contact.photo_storage_key:
        return {"status": "error", "message": "Kontakt nie ma zdjęcia."}, 404

    from library.config_loader import load_config
    from library.storage import storage_from_config

    storage = storage_from_config(load_config())
    try:
        photo_bytes = storage.get_bytes(contact.photo_storage_key)
        thumbnail = generate_photo_thumbnail(photo_bytes)
    except Exception:
        logger.warning("Could not regenerate thumbnail for contact %s", contact_id, exc_info=True)
        return {"status": "error", "message": "Nie udało się przetworzyć zdjęcia."}, 502

    thumb_key = _photo_thumbnail_storage_key(contact.uuid, contact.photo_storage_key)
    storage.put_bytes(thumb_key, thumbnail, content_type="image/jpeg")
    if contact.photo_thumbnail_storage_key != thumb_key:
        contact.photo_thumbnail_storage_key = thumb_key
        contact.updated_at = datetime.datetime.now()
        try:
            session.commit()
        except Exception:
            session.rollback()
            return {"status": "error", "message": "DB error"}, 500
    else:
        session.rollback()

    return jsonify({"status": "success", "photo_thumbnail_url": storage.presigned_get_url(thumb_key)}), 200


@bp.route("/contacts/<int:contact_id>/photo/history", methods=["GET", "OPTIONS"])
def contact_photo_history(contact_id: int):
    if request.method == "OPTIONS":
        return {"status": "OK"}, 200

    session = get_scoped_session()
    contact = session.get(Contact, contact_id)
    if contact is None:
        return {"status": "error", "message": "Contact not found"}, 404

    from library.config_loader import load_config
    from library.contact_photos import photo_dict
    from library.storage import storage_from_config

    storage = storage_from_config(load_config())
    rows = session.execute(
        select(ContactPhoto).where(ContactPhoto.storage_key.like(f"contacts/{contact.uuid}/%"))
        .order_by(ContactPhoto.created_at.desc())
    ).scalars().all()
    history = []
    for row in rows:
        thumb_key = _photo_thumbnail_storage_key(contact.uuid, row.storage_key)
        history.append({
            **photo_dict(row),
            "created_at": row.created_at.isoformat(),
            "is_current": row.storage_key == contact.photo_storage_key,
            "photo_url": storage.presigned_get_url(row.storage_key),
            "thumbnail_url": storage.presigned_get_url(thumb_key) if storage.exists(thumb_key) else None,
        })
    return jsonify({"status": "success", "history": history}), 200


@bp.route("/contacts/<int:contact_id>/photo/restore", methods=["POST", "OPTIONS"])
def contact_photo_restore(contact_id: int):
    if request.method == "OPTIONS":
        return {"status": "OK"}, 200

    session = get_scoped_session()
    contact = session.get(Contact, contact_id)
    if contact is None:
        return {"status": "error", "message": "Contact not found"}, 404

    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get("storage_key"), str):
        return {"status": "error", "message": "storage_key is required and must be a string"}, 400
    key = data["storage_key"]
    if not key.startswith(f"contacts/{contact.uuid}/"):
        return {"status": "error", "message": "Photo does not belong to this contact"}, 400
    photo = session.get(ContactPhoto, key)
    if photo is None:
        return {"status": "error", "message": "Photo not found"}, 404

    from library.config_loader import load_config
    from library.contact_photos import photo_dict
    from library.storage import storage_from_config

    storage = storage_from_config(load_config())
    if key != contact.photo_storage_key:
        thumb_key = _photo_thumbnail_storage_key(contact.uuid, key)
        try:
            if not storage.exists(thumb_key):
                photo_bytes = storage.get_bytes(key)
                thumb_bytes = generate_photo_thumbnail(photo_bytes)
                storage.put_bytes(thumb_key, thumb_bytes, content_type="image/jpeg")
        except Exception:
            thumb_key = None
            logger.warning("Could not generate/store photo thumbnail for contact %s", contact_id, exc_info=True)
        try:
            contact.photo_storage_key = key
            contact.photo_thumbnail_storage_key = thumb_key
            contact.updated_at = datetime.datetime.now()
            record_contact_change(
                session, contact, "manual_edit", changed_fields=["photo_storage_key", "photo_thumbnail_storage_key"],
                note="Przywrócono poprzednie zdjęcie z historii.",
            )
            session.commit()
        except Exception:
            session.rollback()
            return {"status": "error", "message": "DB error"}, 500

    return jsonify({"status": "success", "photo_url": storage.presigned_get_url(key), "photo": photo_dict(photo)}), 200


@bp.route("/contacts/<int:contact_id>/photo", methods=["DELETE", "OPTIONS"])
def contact_photo_delete(contact_id: int):
    if request.method == "OPTIONS":
        return {"status": "OK"}, 200

    session = get_scoped_session()
    contact = session.get(Contact, contact_id)
    if contact is None:
        return {"status": "error", "message": "Contact not found"}, 404

    # The blob itself is left in storage — ObjectStorage has no delete
    # primitive. Shared photo metadata and the file remain for other contacts.
    contact.photo_storage_key = None
    contact.photo_thumbnail_storage_key = None
    contact.updated_at = datetime.datetime.now()
    record_contact_change(session, contact, "manual_edit",
                          changed_fields=["photo_storage_key", "photo_thumbnail_storage_key"])
    try:
        session.commit()
    except Exception:
        session.rollback()
        return {"status": "error", "message": "DB error"}, 500

    return jsonify({"status": "success"}), 200


def _validate_birthday_pair(data, row=None):
    fields = ("birthday_month", "birthday_day")
    if not any(field in data for field in fields):
        return None
    pair_error = "birthday_month and birthday_day must be provided together"
    if any(field not in data and getattr(row, field, None) is None for field in fields):
        return pair_error
    month = data.get("birthday_month", getattr(row, "birthday_month", None))
    day = data.get("birthday_day", getattr(row, "birthday_day", None))
    if month is None and day is None:
        return None
    if month is None or day is None:
        return pair_error
    if type(month) is not int or not 1 <= month <= 12:
        return "birthday_month must be an integer between 1 and 12"
    max_day = 29 if month == 2 else 30 if month in (4, 6, 9, 11) else 31
    if type(day) is not int or not 1 <= day <= max_day:
        return f"birthday_day must be an integer between 1 and {max_day} for month {month}"
    return None


def _validate_gender(data) -> str | None:
    if "gender" not in data:
        return None
    gender = data.get("gender")
    if gender is not None and gender not in _GENDER_VALUES:
        return f"gender must be one of {_GENDER_VALUES} or null"
    return None


@bp.route("/contacts", methods=["POST", "OPTIONS"])
def contacts_add():
    if request.method == "OPTIONS":
        return {"status": "OK"}, 200

    data = request.get_json(silent=True) or {}
    name_error = validate_contact_name(data)
    if name_error:
        return {"status": "error", "message": name_error}, 400
    last_name = (data.get("last_name") or "").strip() or None

    birthday_error = _validate_birthday_pair(data)
    if birthday_error:
        return {"status": "error", "message": birthday_error}, 400

    try:
        channels = channel_patch(data)
    except ValueError as error:
        return {"status": "error", "message": str(error)}, 400

    gender_error = _validate_gender(data)
    if gender_error:
        return {"status": "error", "message": gender_error}, 400

    category_id = data.get("category_id")
    session = get_scoped_session()
    if category_id is None:
        default_category = session.execute(
            select(ContactCategory).where(ContactCategory.name == "Osoba prywatna")
        ).scalars().first()
        if default_category is None:
            return {"status": "error", "message": "category_id is required"}, 400
        category_id = default_category.id
    elif session.get(ContactCategory, category_id) is None:
        return {"status": "error", "message": "category_id not found"}, 400

    change_source = (data.get("change_source") or "manual_edit").strip()
    if change_source not in CONTACT_CHANGE_SOURCES:
        return {"status": "error", "message": f"change_source must be one of {CONTACT_CHANGE_SOURCES}"}, 400
    change_note = (data.get("change_note") or "").strip() or None

    row = Contact(category_id=category_id, last_name=last_name)
    changed_fields = ["last_name"]
    for field in _CONTACT_FIELDS:
        if field == "last_name":
            continue
        if field in data:
            setattr(row, field, (data.get(field) or "").strip() or None)
            changed_fields.append(field)
    for field, value in channels.items():
        if field in data and getattr(row, field, None) != value and field not in changed_fields:
            changed_fields.append(field)
        setattr(row, field, value)
    auth = getattr(g, "auth", None)
    if "private_notes" in data and auth and auth.kind == "service":
        row.private_notes = (data.get("private_notes") or "").strip() or None
        changed_fields.append("private_notes")
    if "birthday" in data:
        row.birthday = data.get("birthday") or None
        changed_fields.append("birthday")
    for field in ("birthday_month", "birthday_day"):
        if field in data:
            setattr(row, field, data[field])
            changed_fields.append(field)
    if "gender" in data:
        row.gender = data.get("gender")
        changed_fields.append("gender")
    if "languages" in data:
        new_languages, error = _normalize_languages(data.get("languages"))
        if error:
            return {"status": "error", "message": error}, 400
        row.languages = new_languages
        changed_fields.append("languages")
    if "nationality" in data:
        new_nationality, error = _normalize_nationality(data.get("nationality"))
        if error:
            return {"status": "error", "message": error}, 400
        row.nationality = new_nationality
        changed_fields.append("nationality")

    session.add(row)
    session.flush()
    record_contact_change(session, row, change_source, changed_fields=changed_fields, note=change_note)
    try:
        session.commit()
    except Exception:
        session.rollback()
        return {"status": "error", "message": "DB error"}, 500

    return jsonify({"status": "success", "contact": _contact_dict(row)}), 200


@bp.route("/contacts/<int:contact_id>", methods=["PATCH", "OPTIONS"])
def contacts_update(contact_id: int):
    if request.method == "OPTIONS":
        return {"status": "OK"}, 200

    data = request.get_json(silent=True) or {}
    session = get_scoped_session()
    row = session.get(Contact, contact_id)
    if row is None:
        return {"status": "error", "message": "Contact not found"}, 404

    name_error = validate_contact_name(data, row)
    if name_error:
        return {"status": "error", "message": name_error}, 400

    birthday_error = _validate_birthday_pair(data, row)
    if birthday_error:
        return {"status": "error", "message": birthday_error}, 400

    try:
        channels = channel_patch(data, row)
    except ValueError as error:
        return {"status": "error", "message": str(error)}, 400

    gender_error = _validate_gender(data)
    if gender_error:
        return {"status": "error", "message": gender_error}, 400

    change_source = (data.get("change_source") or "manual_edit").strip()
    if change_source not in CONTACT_CHANGE_SOURCES:
        return {"status": "error", "message": f"change_source must be one of {CONTACT_CHANGE_SOURCES}"}, 400
    change_note = (data.get("change_note") or "").strip() or None
    changed_fields = []

    if "last_name" in data:
        last_name = (data.get("last_name") or "").strip() or None
        if row.last_name != last_name:
            changed_fields.append("last_name")
        row.last_name = last_name
    for field in _CONTACT_FIELDS:
        if field == "last_name":
            continue
        if field in data:
            new_value = (data.get(field) or "").strip() or None
            if getattr(row, field) != new_value:
                changed_fields.append(field)
            setattr(row, field, new_value)
    for field, value in channels.items():
        if field in data and getattr(row, field, None) != value and field not in changed_fields:
            changed_fields.append(field)
        setattr(row, field, value)
    auth = getattr(g, "auth", None)
    if "private_notes" in data and auth and auth.kind == "service":
        new_private_notes = (data.get("private_notes") or "").strip() or None
        if row.private_notes != new_private_notes:
            changed_fields.append("private_notes")
        row.private_notes = new_private_notes
    if "birthday" in data:
        new_birthday = data.get("birthday") or None
        old_birthday = row.birthday.isoformat() if row.birthday else None
        if old_birthday != new_birthday:
            changed_fields.append("birthday")
        row.birthday = new_birthday
    for field in ("birthday_month", "birthday_day"):
        if field in data:
            if getattr(row, field) != data[field]:
                changed_fields.append(field)
            setattr(row, field, data[field])
    if "gender" in data:
        new_gender = data.get("gender")
        if row.gender != new_gender:
            changed_fields.append("gender")
        row.gender = new_gender
    if "category_id" in data:
        category_id = data.get("category_id")
        if session.get(ContactCategory, category_id) is None:
            return {"status": "error", "message": "category_id not found"}, 400
        if row.category_id != category_id:
            changed_fields.append("category_id")
        row.category_id = category_id
    if "languages" in data:
        new_languages, error = _normalize_languages(data.get("languages"))
        if error:
            return {"status": "error", "message": error}, 400
        if (row.languages or []) != new_languages:
            changed_fields.append("languages")
        row.languages = new_languages
    if "nationality" in data:
        new_nationality, error = _normalize_nationality(data.get("nationality"))
        if error:
            return {"status": "error", "message": error}, 400
        if (row.nationality or []) != new_nationality:
            changed_fields.append("nationality")
        row.nationality = new_nationality
    if "is_archived" in data:
        new_is_archived = bool(data.get("is_archived"))
        if row.is_archived != new_is_archived:
            changed_fields.append("is_archived")
        row.is_archived = new_is_archived

    row.updated_at = datetime.datetime.now()
    record_contact_change(session, row, change_source, changed_fields=changed_fields, note=change_note)
    try:
        session.commit()
    except Exception:
        session.rollback()
        return {"status": "error", "message": "DB error"}, 500

    return jsonify({"status": "success", "contact": _contact_dict(row)}), 200


@bp.route("/contacts/<int:contact_id>", methods=["DELETE", "OPTIONS"])
def contacts_delete(contact_id: int):
    if request.method == "OPTIONS":
        return {"status": "OK"}, 200

    session = get_scoped_session()
    row = session.get(Contact, contact_id)
    if row is None:
        return {"status": "error", "message": "Contact not found"}, 404
    try:
        session.delete(row)
        session.commit()
    except Exception:
        session.rollback()
        return {"status": "error", "message": "DB error"}, 500
    return jsonify({"status": "success", "deleted_id": contact_id}), 200


# --- relationships ---------------------------------------------------------

@bp.route("/contacts/<int:contact_id>/photo/description", methods=["PATCH", "OPTIONS"])
def contact_photo_description_update(contact_id: int):
    if request.method == "OPTIONS":
        return {"status": "OK"}, 200
    from library.contact_photos import update_description
    payload, status = update_description(get_scoped_session(), contact_id, request.get_json(silent=True))
    return jsonify(payload), status


@bp.route("/contacts/<int:contact_id>/photo/describe", methods=["POST", "OPTIONS"])
def contact_photo_describe(contact_id: int):
    if request.method == "OPTIONS":
        return {"status": "OK"}, 200
    from library.contact_photos import generate_description
    payload, status = generate_description(get_scoped_session(), contact_id, request.get_json(silent=True))
    return jsonify(payload), status


@bp.route("/contacts/<int:contact_id>/family", methods=["POST", "OPTIONS"])
def contact_family_create(contact_id: int):
    if request.method == "OPTIONS":
        return {"status": "OK"}, 200
    from library.contact_families import create_family
    payload, status = create_family(get_scoped_session(), contact_id, request.get_json(silent=True))
    return jsonify(payload), status


@bp.route("/contacts/<int:contact_id>/relationships", methods=["POST", "OPTIONS"])
def contact_relationships_add(contact_id: int):
    if request.method == "OPTIONS":
        return {"status": "OK"}, 200

    data = request.get_json(silent=True) or {}
    session = get_scoped_session()
    contact = session.get(Contact, contact_id)
    if contact is None:
        return {"status": "error", "message": "Contact not found"}, 404

    related_contact_id = data.get("related_contact_id")
    related = session.get(Contact, related_contact_id) if related_contact_id is not None else None
    if related is None:
        return {"status": "error", "message": "related_contact_id not found"}, 400
    if related.id == contact_id:
        return {"status": "error", "message": "A contact cannot be related to itself"}, 400

    relationship_type = (data.get("relationship_type") or "").strip()
    if not relationship_type:
        return {"status": "error", "message": "relationship_type is required"}, 400

    row = ContactRelationship(
        contact_id=contact_id,
        related_contact_id=related.id,
        relationship_type=relationship_type,
        note=(data.get("note") or "").strip() or None,
        start_date=data.get("start_date") or None,
        end_date=data.get("end_date") or None,
    )
    session.add(row)
    try:
        session.commit()
    except Exception:
        session.rollback()
        return {"status": "error", "message": "DB error (duplicate relationship?)"}, 409

    return jsonify({
        "status": "success",
        "relationship": _relationship_dict(row, related, "outgoing"),
    }), 200


@bp.route("/contact_relationships/<int:relationship_id>", methods=["PATCH", "OPTIONS"])
def contact_relationships_update(relationship_id: int):
    if request.method == "OPTIONS":
        return {"status": "OK"}, 200

    data = request.get_json(silent=True) or {}
    session = get_scoped_session()
    row = session.get(ContactRelationship, relationship_id)
    if row is None:
        return {"status": "error", "message": "Relationship not found"}, 404

    if "relationship_type" in data:
        relationship_type = (data.get("relationship_type") or "").strip()
        if not relationship_type:
            return {"status": "error", "message": "relationship_type cannot be empty"}, 400
        row.relationship_type = relationship_type
    if "note" in data:
        row.note = (data.get("note") or "").strip() or None
    if "start_date" in data:
        row.start_date = data.get("start_date") or None
    if "end_date" in data:
        row.end_date = data.get("end_date") or None

    try:
        session.commit()
    except Exception:
        session.rollback()
        return {"status": "error", "message": "DB error (duplicate relationship?)"}, 409

    other = session.get(Contact, row.related_contact_id)
    return jsonify({
        "status": "success",
        "relationship": _relationship_dict(row, other, "outgoing"),
    }), 200


@bp.route("/contact_relationships/<int:relationship_id>", methods=["DELETE", "OPTIONS"])
def contact_relationships_delete(relationship_id: int):
    if request.method == "OPTIONS":
        return {"status": "OK"}, 200

    session = get_scoped_session()
    row = session.get(ContactRelationship, relationship_id)
    if row is None:
        return {"status": "error", "message": "Relationship not found"}, 404
    try:
        session.delete(row)
        session.commit()
    except Exception:
        session.rollback()
        return {"status": "error", "message": "DB error"}, 500
    return jsonify({"status": "success", "deleted_id": relationship_id}), 200


# --- lookup results (OSINT search trail, e.g. /lenie-person-lookup) -------

@bp.route("/contacts/<int:contact_id>/lookup_results", methods=["POST", "OPTIONS"])
def contact_lookup_results_add(contact_id: int):
    if request.method == "OPTIONS":
        return {"status": "OK"}, 200

    data = request.get_json(silent=True) or {}
    session = get_scoped_session()
    contact = session.get(Contact, contact_id)
    if contact is None:
        return {"status": "error", "message": "Contact not found"}, 404

    lookup_type = (data.get("lookup_type") or "").strip()
    if lookup_type not in _LOOKUP_TYPES:
        return {"status": "error", "message": f"lookup_type must be one of {_LOOKUP_TYPES}"}, 400

    status = (data.get("status") or "").strip()
    if status not in _LOOKUP_STATUSES:
        return {"status": "error", "message": f"status must be one of {_LOOKUP_STATUSES}"}, 400

    row = ContactLookupResult(
        contact_id=contact_id,
        lookup_type=lookup_type,
        status=status,
        url=(data.get("url") or "").strip() or None,
        query_used=(data.get("query_used") or "").strip() or None,
        notes=(data.get("notes") or "").strip() or None,
    )
    session.add(row)
    try:
        session.commit()
    except Exception:
        session.rollback()
        return {"status": "error", "message": "DB error"}, 500

    return jsonify({"status": "success", "lookup_result": _lookup_result_dict(row)}), 200


@bp.route("/contact_lookup_results/<int:lookup_result_id>", methods=["PATCH", "OPTIONS"])
def contact_lookup_results_update(lookup_result_id: int):
    if request.method == "OPTIONS":
        return {"status": "OK"}, 200

    data = request.get_json(silent=True) or {}
    session = get_scoped_session()
    row = session.get(ContactLookupResult, lookup_result_id)
    if row is None:
        return {"status": "error", "message": "Lookup result not found"}, 404

    if "status" in data:
        status = (data.get("status") or "").strip()
        if status not in _LOOKUP_STATUSES:
            return {"status": "error", "message": f"status must be one of {_LOOKUP_STATUSES}"}, 400
        row.status = status
    if "notes" in data:
        row.notes = (data.get("notes") or "").strip() or None

    # Confirmed profiles live in generic links; lookup rows retain the search trail.
    if row.status == "confirmed" and row.lookup_type == "linkedin" and row.url:
        contact = session.get(Contact, row.contact_id)
        if contact is not None:
            links = list(session.scalars(select(ContactLink).where(
                ContactLink.contact_id == contact.id, ContactLink.link_type == "linkedin",
            ).order_by(ContactLink.id)))
            if not any(link.url == row.url for link in links):
                if links:
                    links[0].url = row.url
                else:
                    session.add(ContactLink(contact_id=contact.id, link_type="linkedin", url=row.url))
                record_contact_change(
                    session, contact, "linkedin_analysis", changed_fields=["links"],
                    note=f"Potwierdzony wynik OSINT (lookup #{row.id})",
                )

    try:
        session.commit()
    except Exception:
        session.rollback()
        return {"status": "error", "message": "DB error"}, 500

    return jsonify({"status": "success", "lookup_result": _lookup_result_dict(row)}), 200


@bp.route("/contact_lookup_results/<int:lookup_result_id>", methods=["DELETE", "OPTIONS"])
def contact_lookup_results_delete(lookup_result_id: int):
    if request.method == "OPTIONS":
        return {"status": "OK"}, 200

    session = get_scoped_session()
    row = session.get(ContactLookupResult, lookup_result_id)
    if row is None:
        return {"status": "error", "message": "Lookup result not found"}, 404
    try:
        session.delete(row)
        session.commit()
    except Exception:
        session.rollback()
        return {"status": "error", "message": "DB error"}, 500
    return jsonify({"status": "success", "deleted_id": lookup_result_id}), 200


# --- addresses (multiple, shareable addresses per contact) ---

@bp.route("/addresses/parse", methods=["POST", "OPTIONS"])
def addresses_parse():
    data = request.get_json(silent=True)
    fields = parse_address_text(data.get("text") if isinstance(data, dict) else None)
    return jsonify({"status": "success", **fields}), 200


@bp.route("/addresses", methods=["GET"])
def addresses_list():
    session = get_scoped_session()
    query = select(Address)
    q = (request.args.get("q") or "").strip()
    if q:
        query = query.where(or_(
            *(func.unaccent(field).ilike(func.unaccent(f"%{q}%"))
              for field in (Address.city, Address.street, Address.postal_code))
        ))
    addresses = session.execute(query.order_by(Address.id).limit(20)).scalars().all()
    contacts_by_address = {}
    if addresses:
        links = session.execute(
            select(ContactAddress).options(joinedload(ContactAddress.contact))
            .where(ContactAddress.address_id.in_([address.id for address in addresses]))
            .order_by(ContactAddress.id)
        ).scalars().all()
        for link in links:
            contacts_by_address.setdefault(link.address_id, {})[link.contact_id] = {
                "id": link.contact_id, "display_name": contact_display_name(link.contact),
            }
    return jsonify({"status": "success", "addresses": [
        {**_address_dict(address),
         "linked_contacts": list(contacts_by_address.get(address.id, {}).values())}
        for address in addresses
    ]}), 200


@bp.route("/contacts/<int:contact_id>/addresses", methods=["GET", "POST", "OPTIONS"])
def contact_addresses(contact_id: int):
    if request.method == "OPTIONS":
        return {"status": "OK"}, 200
    session = get_scoped_session()
    contact = session.get(Contact, contact_id)
    if contact is None:
        return {"status": "error", "message": "Contact not found"}, 404
    if request.method == "GET":
        return jsonify({"status": "success", "addresses": [
            _contact_address_dict(link) for link in _contact_addresses(session, contact_id)
        ]}), 200

    data = request.get_json(silent=True) or {}
    error = _validate_address_payload(data)
    if error:
        return {"status": "error", "message": error}, 400
    if "address_id" in data:
        if type(data["address_id"]) is not int or data["address_id"] <= 0:
            return {"status": "error", "message": "address_id must be a positive integer"}, 400
        if any(field in data for field in (*ADDRESS_FIELD_LIMITS, "label", "notes")):
            return {"status": "error", "message": "Choose address_id or a new address"}, 400
        address = session.get(Address, data["address_id"])
        if address is None:
            return {"status": "error", "message": "Address not found"}, 404
    else:
        error = _validate_address_payload(data, creating=True)
        if error:
            return {"status": "error", "message": error}, 400
        fields = {field: (data.get(field) or "").strip() or None for field in ADDRESS_FIELD_LIMITS}
        if "country" not in data:
            fields["country"] = "Polska"
        address = Address(**fields, label=(data.get("label") or "").strip() or None,
                          notes=(data.get("notes") or "").strip() or None)
    row = ContactAddress(contact_id=contact_id, address=address,
                         role=(data.get("role") or "").strip() or None,
                         is_primary=data.get("is_primary", False))
    try:
        session.add(row)
        session.commit()
        record_contact_change(session, contact, "manual_edit", changed_fields=["addresses"])
        session.commit()
    except Exception:
        session.rollback()
        return {"status": "error", "message": "DB error"}, 500
    return jsonify({"status": "success", "address": _contact_address_dict(row)}), 200


def _validate_address_payload(data, *, creating=False):
    if not isinstance(data, dict):
        return "JSON object required"
    for field, limit in (("label", 100), ("role", 50), ("notes", ADDRESS_NOTES_MAX_LENGTH), *ADDRESS_FIELD_LIMITS.items()):
        if field in data:
            value = data[field]
            if value is not None and not isinstance(value, str):
                return f"{field} must be a string or null"
            if limit and value and len(value.strip()) > limit:
                return f"{field} must be at most {limit} characters"
    for field in ("city", "building_number"):
        if (creating or field in data) and not (data.get(field) or "").strip():
            return f"{field} is required and cannot be empty"
    postal_code = (data.get("postal_code") or "").strip()
    if postal_code and not re.fullmatch(r"[0-9]{2}-[0-9]{3}", postal_code):
        return "postal_code must use Polish format NN-NNN (e.g. 95-054)"
    if "is_primary" in data and type(data["is_primary"]) is not bool:
        return "is_primary must be a boolean"
    return None


@bp.route("/address/<int:address_id>", methods=["PATCH", "OPTIONS"])
def addresses_update(address_id: int):
    if request.method == "OPTIONS":
        return {"status": "OK"}, 200
    session = get_scoped_session()
    row = session.get(Address, address_id)
    if row is None:
        return {"status": "error", "message": "Address not found"}, 404
    data = request.get_json(silent=True) or {}
    error = _validate_address_payload(data)
    if error:
        return {"status": "error", "message": error}, 400
    changed_location = any(
        field in data and (data[field] or "").strip() != (getattr(row, field) or "")
        for field in ADDRESS_FIELD_LIMITS
    )
    for field in ("label", "notes", *ADDRESS_FIELD_LIMITS):
        if field in data:
            setattr(row, field, (data[field] or "").strip() or None)
    if changed_location:
        row.latitude = row.longitude = row.location = row.geocode_id = None
    row.updated_at = datetime.datetime.now()
    try:
        # A shared edit belongs in every affected contact's history.
        contacts = session.execute(select(Contact).where(Contact.id.in_(
            select(ContactAddress.contact_id).where(ContactAddress.address_id == address_id)
        ))).scalars().all()
        for contact in contacts:
            record_contact_change(session, contact, "manual_edit", changed_fields=["addresses"])
        session.commit()
    except Exception:
        session.rollback()
        return {"status": "error", "message": "DB error"}, 500
    return jsonify({"status": "success", "address": _address_dict(row)}), 200


@bp.route("/contact_addresses/<int:link_id>", methods=["PATCH", "OPTIONS"])
def contact_addresses_update(link_id: int):
    if request.method == "OPTIONS":
        return {"status": "OK"}, 200
    session = get_scoped_session()
    row = session.get(ContactAddress, link_id)
    if row is None:
        return {"status": "error", "message": "Address link not found"}, 404
    data = request.get_json(silent=True) or {}
    error = _validate_address_payload(data)
    if error:
        return {"status": "error", "message": error}, 400
    if "role" in data:
        row.role = (data["role"] or "").strip() or None
    if "is_primary" in data:
        row.is_primary = data["is_primary"]
    try:
        contact = session.get(Contact, row.contact_id)
        session.commit()
        record_contact_change(session, contact, "manual_edit", changed_fields=["addresses"])
        session.commit()
    except Exception:
        session.rollback()
        return {"status": "error", "message": "DB error"}, 500
    return jsonify({"status": "success", "address": _contact_address_dict(row)}), 200


@bp.route("/contact_addresses/<int:link_id>", methods=["DELETE", "OPTIONS"])
def contact_addresses_delete(link_id: int):
    if request.method == "OPTIONS":
        return {"status": "OK"}, 200
    session = get_scoped_session()
    row = session.get(ContactAddress, link_id)
    if row is None:
        return {"status": "error", "message": "Address link not found"}, 404
    try:
        contact = session.get(Contact, row.contact_id)
        session.delete(row)
        session.commit()
        record_contact_change(session, contact, "manual_edit", changed_fields=["addresses"])
        session.commit()
    except Exception:
        session.rollback()
        return {"status": "error", "message": "DB error"}, 500
    return jsonify({"status": "success", "deleted_id": link_id}), 200


@bp.route("/address/<int:address_id>/geocode", methods=["POST", "OPTIONS"])
def addresses_geocode(address_id: int):
    if request.method == "OPTIONS":
        return {"status": "OK"}, 200
    session = get_scoped_session()
    try:
        row = session.get(Address, address_id)
        if row is None:
            return {"status": "error", "message": "Address not found"}, 404
        resolved = geocode_address(session, row)
        row.updated_at = datetime.datetime.now()
        contacts = session.execute(select(Contact).where(Contact.id.in_(
            select(ContactAddress.contact_id).where(ContactAddress.address_id == address_id)
        ))).scalars().all()
        for contact in contacts:
            record_contact_change(session, contact, "manual_edit", changed_fields=["addresses"])
        session.commit()
        return jsonify({"status": "success", "address": _address_dict(row), "resolved": resolved}), 200
    except Exception:
        session.rollback()
        return {"status": "error", "message": "DB error"}, 500


@bp.route("/address/<int:address_id>/validate", methods=["POST", "OPTIONS"])
def addresses_validate(address_id: int):
    if request.method == "OPTIONS":
        return {"status": "OK"}, 200
    session = get_scoped_session()
    try:
        row = session.get(Address, address_id)
        if row is None:
            return {"status": "error", "message": "Address not found"}, 404
        result = validate_address(session, row)
        row.updated_at = datetime.datetime.now()
        contacts = session.execute(select(Contact).where(Contact.id.in_(
            select(ContactAddress.contact_id).where(ContactAddress.address_id == address_id)
        ))).scalars().all()
        for contact in contacts:
            record_contact_change(session, contact, "manual_edit", changed_fields=["addresses"])
        session.commit()
        return jsonify({"status": "success", **result, "address": _address_dict(row)}), 200
    except Exception:
        session.rollback()
        return {"status": "error", "message": "DB error"}, 500


# --- organizations (multiple affiliations per contact — JDG, etat, board seat, ...) ---

@bp.route("/contacts/<int:contact_id>/organizations", methods=["POST", "OPTIONS"])
def contact_organizations_add(contact_id: int):
    if request.method == "OPTIONS":
        return {"status": "OK"}, 200

    data = request.get_json(silent=True) or {}
    session = get_scoped_session()
    contact = session.get(Contact, contact_id)
    if contact is None:
        return {"status": "error", "message": "Contact not found"}, 404

    org_type = (data.get("org_type") or "").strip()
    if org_type not in _ORG_TYPES:
        return {"status": "error", "message": f"org_type must be one of {_ORG_TYPES}"}, 400

    organization_name = (data.get("organization_name") or "").strip()
    if not organization_name:
        return {"status": "error", "message": "organization_name is required"}, 400

    status = (data.get("status") or "confirmed").strip()
    if status not in _ORG_STATUSES:
        return {"status": "error", "message": f"status must be one of {_ORG_STATUSES}"}, 400

    row = ContactOrganization(
        contact_id=contact_id,
        org_type=org_type,
        organization_name=organization_name,
        status=status,
        is_primary=bool(data.get("is_primary", False)),
        is_current=bool(data.get("is_current", True)),
    )
    for field in _ORG_FIELDS:
        if field == "organization_name":
            continue
        if field in data:
            setattr(row, field, (data.get(field) or "").strip() or None)
    for field in _ORG_DATE_FIELDS:
        if field in data:
            setattr(row, field, data.get(field) or None)

    session.add(row)
    try:
        session.commit()
    except Exception:
        session.rollback()
        return {"status": "error", "message": "DB error"}, 500

    return jsonify({"status": "success", "organization": _organization_dict(row)}), 200


@bp.route("/contact_organizations/<int:organization_id>", methods=["PATCH", "OPTIONS"])
def contact_organizations_update(organization_id: int):
    if request.method == "OPTIONS":
        return {"status": "OK"}, 200

    data = request.get_json(silent=True) or {}
    session = get_scoped_session()
    row = session.get(ContactOrganization, organization_id)
    if row is None:
        return {"status": "error", "message": "Organization not found"}, 404

    if "org_type" in data:
        org_type = (data.get("org_type") or "").strip()
        if org_type not in _ORG_TYPES:
            return {"status": "error", "message": f"org_type must be one of {_ORG_TYPES}"}, 400
        row.org_type = org_type
    if "organization_name" in data:
        organization_name = (data.get("organization_name") or "").strip()
        if not organization_name:
            return {"status": "error", "message": "organization_name cannot be empty"}, 400
        row.organization_name = organization_name
    if "status" in data:
        status = (data.get("status") or "").strip()
        if status not in _ORG_STATUSES:
            return {"status": "error", "message": f"status must be one of {_ORG_STATUSES}"}, 400
        row.status = status
    for field in _ORG_FIELDS:
        if field == "organization_name":
            continue
        if field in data:
            setattr(row, field, (data.get(field) or "").strip() or None)
    if "is_primary" in data:
        row.is_primary = bool(data.get("is_primary"))
    if "is_current" in data:
        row.is_current = bool(data.get("is_current"))
    for field in _ORG_DATE_FIELDS:
        if field in data:
            setattr(row, field, data.get(field) or None)

    row.updated_at = datetime.datetime.now()
    try:
        session.commit()
    except Exception:
        session.rollback()
        return {"status": "error", "message": "DB error"}, 500

    return jsonify({"status": "success", "organization": _organization_dict(row)}), 200


@bp.route("/contact_organizations/<int:organization_id>", methods=["DELETE", "OPTIONS"])
def contact_organizations_delete(organization_id: int):
    if request.method == "OPTIONS":
        return {"status": "OK"}, 200

    session = get_scoped_session()
    row = session.get(ContactOrganization, organization_id)
    if row is None:
        return {"status": "error", "message": "Organization not found"}, 404
    try:
        session.delete(row)
        session.commit()
    except Exception:
        session.rollback()
        return {"status": "error", "message": "DB error"}, 500
    return jsonify({"status": "success", "deleted_id": organization_id}), 200


# --- links (multiple social/profile URLs per contact — Facebook, Instagram, ...) ---

@bp.route("/contacts/<int:contact_id>/links", methods=["POST", "OPTIONS"])
def contact_links_add(contact_id: int):
    if request.method == "OPTIONS":
        return {"status": "OK"}, 200

    data = request.get_json(silent=True) or {}
    session = get_scoped_session()
    contact = session.get(Contact, contact_id)
    if contact is None:
        return {"status": "error", "message": "Contact not found"}, 404

    link_type = (data.get("link_type") or "").strip()
    if link_type not in _LINK_TYPES:
        return {"status": "error", "message": f"link_type must be one of {_LINK_TYPES}"}, 400

    url = (data.get("url") or "").strip()
    if not url:
        return {"status": "error", "message": "url is required"}, 400

    row = ContactLink(
        contact_id=contact_id,
        link_type=link_type,
        url=url,
        label=(data.get("label") or "").strip() or None,
    )
    session.add(row)
    try:
        session.commit()
    except Exception:
        session.rollback()
        return {"status": "error", "message": "DB error"}, 500

    return jsonify({"status": "success", "link": _link_dict(row)}), 200


@bp.route("/contact_links/<int:link_id>", methods=["PATCH", "OPTIONS"])
def contact_links_update(link_id: int):
    if request.method == "OPTIONS":
        return {"status": "OK"}, 200

    data = request.get_json(silent=True) or {}
    session = get_scoped_session()
    row = session.get(ContactLink, link_id)
    if row is None:
        return {"status": "error", "message": "Link not found"}, 404

    if "link_type" in data:
        link_type = (data.get("link_type") or "").strip()
        if link_type not in _LINK_TYPES:
            return {"status": "error", "message": f"link_type must be one of {_LINK_TYPES}"}, 400
        row.link_type = link_type
    if "url" in data:
        url = (data.get("url") or "").strip()
        if not url:
            return {"status": "error", "message": "url cannot be empty"}, 400
        row.url = url
    if "label" in data:
        row.label = (data.get("label") or "").strip() or None

    row.updated_at = datetime.datetime.now()
    try:
        session.commit()
    except Exception:
        session.rollback()
        return {"status": "error", "message": "DB error"}, 500

    return jsonify({"status": "success", "link": _link_dict(row)}), 200


@bp.route("/contact_links/<int:link_id>", methods=["DELETE", "OPTIONS"])
def contact_links_delete(link_id: int):
    if request.method == "OPTIONS":
        return {"status": "OK"}, 200

    session = get_scoped_session()
    row = session.get(ContactLink, link_id)
    if row is None:
        return {"status": "error", "message": "Link not found"}, 404
    try:
        session.delete(row)
        session.commit()
    except Exception:
        session.rollback()
        return {"status": "error", "message": "DB error"}, 500
    return jsonify({"status": "success", "deleted_id": link_id}), 200


def _interest_dict(row: ContactInterest, count: int | None = None) -> dict:
    data = {
        "id": row.id,
        "name": row.name,
        "description": row.description,
    }
    if count is not None:
        data["count"] = count
    return data




def _interest_contact_count(session, interest_id: int) -> int:
    return session.execute(
        select(func.count()).select_from(ContactInterestMembership).where(
            ContactInterestMembership.interest_id == interest_id
        )
    ).scalar_one()




@bp.get("/contact_interests")
def contact_interests_list():
    session = get_scoped_session()
    rows = session.execute(select(ContactInterest).order_by(ContactInterest.name)).scalars().all()
    return jsonify({
        "status": "success",
        "contact_interests": [_interest_dict(row, _interest_contact_count(session, row.id)) for row in rows],
    }), 200




@bp.route("/contact_interests", methods=["POST", "OPTIONS"])
def contact_interests_add():
    if request.method == "OPTIONS":
        return {"status": "OK"}, 200

    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return {"status": "error", "message": "name is required"}, 400

    session = get_scoped_session()
    row = ContactInterest(name=name, description=(data.get("description") or "").strip() or None)
    session.add(row)
    try:
        session.commit()
    except Exception:
        session.rollback()
        return {"status": "error", "message": "DB error (duplicate name?)"}, 409

    return jsonify({"status": "success", "contact_interest": _interest_dict(row, 0)}), 200


@bp.route("/contact_interests/<int:interest_id>", methods=["PATCH", "OPTIONS"])
def contact_interests_update(interest_id: int):
    if request.method == "OPTIONS":
        return {"status": "OK"}, 200

    data = request.get_json(silent=True) or {}
    session = get_scoped_session()
    row = session.get(ContactInterest, interest_id)
    if row is None:
        return {"status": "error", "message": "Interest not found"}, 404

    if "name" in data:
        name = (data.get("name") or "").strip()
        if not name:
            return {"status": "error", "message": "name cannot be empty"}, 400
        row.name = name
    if "description" in data:
        row.description = (data.get("description") or "").strip() or None

    try:
        session.commit()
    except Exception:
        session.rollback()
        return {"status": "error", "message": "DB error (duplicate name?)"}, 409

    return jsonify({
        "status": "success",
        "contact_interest": _interest_dict(row, _interest_contact_count(session, row.id)),
    }), 200


@bp.route("/contact_interests/<int:interest_id>", methods=["DELETE", "OPTIONS"])
def contact_interests_delete(interest_id: int):
    if request.method == "OPTIONS":
        return {"status": "OK"}, 200

    session = get_scoped_session()
    row = session.get(ContactInterest, interest_id)
    if row is None:
        return {"status": "error", "message": "Interest not found"}, 404
    used_by = _interest_contact_count(session, row.id)
    if used_by > 0:
        return jsonify({
            "status": "error",
            "message": f"Interest is used by {used_by} contacts — remove them from it first",
        }), 409
    try:
        session.delete(row)
        session.commit()
    except Exception:
        session.rollback()
        return {"status": "error", "message": "DB error"}, 500
    return jsonify({"status": "success", "deleted_id": interest_id}), 200


@bp.route("/contacts/<int:contact_id>/interests", methods=["POST", "OPTIONS"])
def contact_interests_assign(contact_id: int):
    if request.method == "OPTIONS":
        return {"status": "OK"}, 200

    data = request.get_json(silent=True) or {}
    session = get_scoped_session()
    contact = session.get(Contact, contact_id)
    if contact is None:
        return {"status": "error", "message": "Contact not found"}, 404

    interest_id = data.get("interest_id")
    interest = session.get(ContactInterest, interest_id) if interest_id is not None else None
    if interest is None:
        return {"status": "error", "message": "interest_id not found"}, 400

    if interest not in contact.interests:
        contact.interests.append(interest)
        record_contact_change(
            session, contact, "manual_edit", changed_fields=["interests"],
            note=f"Dodano zainteresowanie „{interest.name}”",
        )
        try:
            session.commit()
        except Exception:
            session.rollback()
            return {"status": "error", "message": "DB error"}, 500

    return jsonify({"status": "success", "contact": _contact_dict(contact)}), 200


@bp.route("/contacts/<int:contact_id>/interests/<int:interest_id>", methods=["DELETE", "OPTIONS"])
def contact_interests_unassign(contact_id: int, interest_id: int):
    if request.method == "OPTIONS":
        return {"status": "OK"}, 200

    session = get_scoped_session()
    contact = session.get(Contact, contact_id)
    if contact is None:
        return {"status": "error", "message": "Contact not found"}, 404
    interest = session.get(ContactInterest, interest_id)
    if interest is not None and interest in contact.interests:
        contact.interests.remove(interest)
        record_contact_change(
            session, contact, "manual_edit", changed_fields=["interests"],
            note=f"Usunięto zainteresowanie „{interest.name}”",
        )
        try:
            session.commit()
        except Exception:
            session.rollback()
            return {"status": "error", "message": "DB error"}, 500

    return jsonify({"status": "success", "contact": _contact_dict(contact)}), 200




@bp.get("/contact_interests/<int:interest_id>")
def contact_interests_get(interest_id: int):
    session = get_scoped_session()
    row = session.get(ContactInterest, interest_id)
    if row is None:
        return {"status": "error", "message": "Interest not found"}, 404
    return jsonify({"status": "success", "contact_interest":
                    _interest_dict(row, _interest_contact_count(session, interest_id))}), 200


def _education_dict(row):
    data = {key: getattr(row, key) for key in
            ("id", "contact_id", "institution", "field_of_study", "degree", "notes")}
    for key in ("start_date", "end_date", "created_at", "updated_at"):
        value = getattr(row, key)
        data[key] = value.isoformat() if value else None
    return data


def _education_values(data, row=None):
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object")
    values = {}
    for key, limit in (("institution", 255), ("field_of_study", 255), ("degree", 20), ("notes", None)):
        value = data.get(key, getattr(row, key, None))
        if value is not None and not isinstance(value, str):
            raise ValueError(f"{key} must be a string")
        value = value.strip() or None if value is not None else None
        if limit and value and len(value) > limit:
            raise ValueError(f"{key} must be at most {limit} characters")
        values[key] = value
    if not values["institution"]:
        raise ValueError("institution is required")
    if values["degree"] not in (None, "bachelor", "engineer", "master", "doctor", "other"):
        raise ValueError("Invalid degree")
    for key in ("start_date", "end_date"):
        value = data.get(key, getattr(row, key, None))
        if value is not None and value != "" and not isinstance(value, datetime.date):
            try:
                if not isinstance(value, str) or len(value) != 10:
                    raise ValueError()
                value = datetime.date.fromisoformat(value)
            except (TypeError, ValueError):
                raise ValueError(f"{key} must be YYYY-MM-DD") from None
        values[key] = value or None
    if values["start_date"] and values["end_date"] and values["end_date"] < values["start_date"]:
        raise ValueError("end_date must not precede start_date")
    return values


@bp.route("/contacts/<int:contact_id>/education", methods=["GET", "POST", "OPTIONS"])
@bp.route("/contacts/<int:contact_id>/education/<int:education_id>", methods=["GET", "PATCH", "DELETE", "OPTIONS"])
def contact_education(contact_id: int, education_id: int | None = None):
    if request.method == "OPTIONS":
        return {"status": "OK"}, 200
    session = get_scoped_session()
    contact = session.get(Contact, contact_id)
    if contact is None:
        return {"status": "error", "message": "Contact not found"}, 404
    row = None
    if education_id is not None:
        row = session.get(ContactEducation, education_id)
        if row is None or row.contact_id != contact_id:
            return {"status": "error", "message": "Education not found"}, 404
    if request.method == "GET":
        if row is not None:
            return jsonify({"status": "success", "education": _education_dict(row)}), 200
        rows = session.scalars(select(ContactEducation).where(ContactEducation.contact_id == contact_id)
                               .order_by(ContactEducation.start_date.desc().nullslast(), ContactEducation.id)).all()
        return jsonify({"status": "success", "education": [_education_dict(item) for item in rows]}), 200
    if request.method in ("POST", "PATCH"):
        try:
            values = _education_values(request.get_json(silent=True), row)
        except ValueError as exc:
            return {"status": "error", "message": str(exc)}, 400
        if row is None:
            row = ContactEducation(contact_id=contact_id, **values)
            session.add(row)
        else:
            for key, value in values.items():
                setattr(row, key, value)
            row.updated_at = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    else:
        session.delete(row)
    record_contact_change(session, contact, "manual_edit", changed_fields=["education"],
                          note=f"Wykształcenie: {row.institution} ({request.method})")
    try:
        session.commit()
    except Exception:
        session.rollback()
        return {"status": "error", "message": "DB error"}, 500
    if request.method == "DELETE":
        return jsonify({"status": "success", "deleted_id": education_id}), 200
    return jsonify({"status": "success", "education": _education_dict(row)}), 200


def _alternate_name_dict(row):
    data = {key: getattr(row, key) for key in
            ("id", "contact_id", "name", "normalized_name", "name_kind", "note")}
    for key in ("start_date", "end_date", "created_at"):
        value = getattr(row, key)
        data[key] = value.isoformat() if value else None
    return data


def _alternate_name_values(data, row=None):
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object")
    values = {}
    for key, limit in (("name", None), ("name_kind", 20), ("note", None)):
        value = data.get(key, getattr(row, key, "former_name" if key == "name_kind" else None))
        if value is not None and not isinstance(value, str):
            raise ValueError(f"{key} must be a string")
        value = value.strip() or None if value is not None else None
        if limit and value and len(value) > limit:
            raise ValueError(f"{key} must be at most {limit} characters")
        values[key] = value
    if not values["name"]:
        raise ValueError("name is required")
    if values["name_kind"] not in ("maiden_name", "former_name", "other"):
        raise ValueError("Invalid name_kind")
    for key in ("start_date", "end_date"):
        value = data.get(key, getattr(row, key, None))
        if value is not None and value != "" and not isinstance(value, datetime.date):
            try:
                if not isinstance(value, str) or len(value) != 10:
                    raise ValueError()
                value = datetime.date.fromisoformat(value)
            except (TypeError, ValueError):
                raise ValueError(f"{key} must be YYYY-MM-DD") from None
        values[key] = value or None
    if values["start_date"] and values["end_date"] and values["end_date"] < values["start_date"]:
        raise ValueError("end_date must not precede start_date")
    from library.whatsapp_parser import normalize_name

    values["normalized_name"] = " ".join(sorted(normalize_name(values["name"])))
    return values


@bp.route("/contacts/<int:contact_id>/alternate_names", methods=["GET", "POST", "OPTIONS"])
@bp.route("/contacts/<int:contact_id>/alternate_names/<int:alternate_name_id>", methods=["GET", "PATCH", "DELETE", "OPTIONS"])
def contact_alternate_names(contact_id: int, alternate_name_id: int | None = None):
    if request.method == "OPTIONS":
        return {"status": "OK"}, 200
    session = get_scoped_session()
    contact = session.get(Contact, contact_id)
    if contact is None:
        return {"status": "error", "message": "Contact not found"}, 404
    row = None
    if alternate_name_id is not None:
        row = session.get(ContactAlternateName, alternate_name_id)
        if row is None or row.contact_id != contact_id:
            return {"status": "error", "message": "Alternate name not found"}, 404
    if request.method == "GET":
        if row is not None:
            return jsonify({"status": "success", "alternate_name": _alternate_name_dict(row)}), 200
        rows = session.scalars(select(ContactAlternateName).where(ContactAlternateName.contact_id == contact_id)
                               .order_by(ContactAlternateName.start_date.desc().nullslast(), ContactAlternateName.id)).all()
        return jsonify({"status": "success", "alternate_names": [_alternate_name_dict(item) for item in rows]}), 200
    if request.method in ("POST", "PATCH"):
        try:
            values = _alternate_name_values(request.get_json(silent=True), row)
        except ValueError as exc:
            return {"status": "error", "message": str(exc)}, 400
        if row is None:
            row = ContactAlternateName(contact_id=contact_id, **values)
            session.add(row)
        else:
            for key, value in values.items():
                setattr(row, key, value)
    else:
        session.delete(row)
    record_contact_change(session, contact, "manual_edit", changed_fields=["alternate_names"],
                          note=f"Alternatywne nazwisko: {row.name} ({request.method})")
    try:
        session.commit()
    except Exception:
        session.rollback()
        return {"status": "error", "message": "DB error"}, 500
    if request.method == "DELETE":
        return jsonify({"status": "success", "deleted_id": alternate_name_id}), 200
    return jsonify({"status": "success", "alternate_name": _alternate_name_dict(row)}), 200
