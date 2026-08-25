"""REST API for the private contact book (personal CRM), independent of the
NER persons registry (library/person_registry.py) — a contact here may
never appear in any document. See docs: contact_categories is a lookup
table managed from the UI (like DiscoverySource); contact_relationships is
directional and single-row (no automatic reciprocal row/label)."""

import datetime
from pathlib import Path

from flask import Blueprint, jsonify, request
from sqlalchemy import func, or_, select
from werkzeug.utils import secure_filename

from library.contact_change_log import CONTACT_CHANGE_SOURCES, record_contact_change
from library.db.engine import get_scoped_session
from library.db.models import (
    Contact, ContactCategory, ContactChangeLog, ContactGroup, ContactGroupMembership, ContactLookupResult,
    ContactOrganization, ContactRelationship,
)

bp = Blueprint("contacts", __name__)

_CONTACT_FIELDS = (
    "first_name", "last_name", "phone_number", "email", "linkedin_url",
    "company", "position", "address", "pesel", "notes",
)

_LOOKUP_TYPES = ("phone", "linkedin", "web")
_LOOKUP_STATUSES = ("no_results", "candidate", "confirmed", "rejected")

_ORG_TYPES = ("employment", "jdg", "board", "ownership", "other")
_ORG_STATUSES = ("candidate", "confirmed", "rejected")
_ORG_FIELDS = ("organization_name", "role", "nip", "regon", "address", "source_url", "notes")

# Same key convention as document_images.py (documents/<uuid>/images/<n>.<ext>),
# except a contact has exactly one photo, so the key is fixed per contact —
# re-uploading with the same extension simply overwrites it in place.
_PHOTO_ALLOWED_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp", ".gif"})


def _photo_storage_key(contact_uuid: str, extension: str) -> str:
    return f"contacts/{contact_uuid}/photo{extension}"


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


def _group_contact_count(session, group_id: int) -> int:
    return session.execute(
        select(func.count()).select_from(ContactGroupMembership).where(
            ContactGroupMembership.group_id == group_id
        )
    ).scalar_one()


def _contact_dict(row: Contact) -> dict:
    return {
        "id": row.id,
        "uuid": row.uuid,
        "category_id": row.category_id,
        "category_name": row.category.name if row.category else None,
        "groups": [{"id": g.id, "name": g.name} for g in row.groups],
        "first_name": row.first_name,
        "last_name": row.last_name,
        "phone_number": row.phone_number,
        "email": row.email,
        "linkedin_url": row.linkedin_url,
        "company": row.company,
        "position": row.position,
        "address": row.address,
        "birthday": row.birthday.isoformat() if row.birthday else None,
        "pesel": row.pesel,
        "notes": row.notes,
        "is_archived": row.is_archived,
        "has_whatsapp_profile": bool(row.whatsapp_profile),
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
        "is_primary": row.is_primary,
        "is_current": row.is_current,
        "start_date": row.start_date.isoformat() if row.start_date else None,
        "end_date": row.end_date.isoformat() if row.end_date else None,
        "status": row.status,
        "source_url": row.source_url,
        "notes": row.notes,
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
        "contact_id": rel.contact_id,
        "related_contact_id": rel.related_contact_id,
        "other_contact": {
            "id": other.id,
            "first_name": other.first_name,
            "last_name": other.last_name,
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

    group_id = request.args.get("group_id", type=int)
    if group_id is not None:
        conditions.append(Contact.groups.any(ContactGroup.id == group_id))

    q = (request.args.get("q") or "").strip()
    if q:
        phrase = func.unaccent(f"%{q}%")
        conditions.append(or_(
            func.unaccent(Contact.first_name).ilike(phrase),
            func.unaccent(Contact.last_name).ilike(phrase),
            func.unaccent(func.coalesce(Contact.phone_number, "")).ilike(phrase),
        ))

    total = session.execute(
        select(func.count()).select_from(Contact).where(*conditions)
    ).scalar_one()

    offset = request.args.get("offset", default=0, type=int)
    limit = min(request.args.get("limit", default=100, type=int), 500)
    query = (
        select(Contact).where(*conditions)
        .order_by(Contact.last_name, Contact.first_name).offset(offset).limit(limit)
    )

    rows = session.execute(query).scalars().all()
    return jsonify({
        "status": "success",
        "contacts": [_contact_dict(row) for row in rows],
        "total": total,
        "offset": offset,
        "limit": limit,
    }), 200


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

    change_log = session.execute(
        select(ContactChangeLog)
        .where(ContactChangeLog.contact_id == contact_id)
        .order_by(ContactChangeLog.created_at.desc())
    ).scalars().all()

    data = _contact_dict(row)
    data["relationships"] = relationships
    data["lookup_results"] = [_lookup_result_dict(lr) for lr in lookup_results]
    data["organizations"] = [_organization_dict(org) for org in organizations]
    data["change_log"] = [_change_log_dict(cl) for cl in change_log]
    data["whatsapp_profile"] = row.whatsapp_profile
    data["photo_url"] = _contact_photo_url(row)
    return jsonify({"status": "success", "contact": data}), 200


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

    contact.photo_storage_key = key
    contact.updated_at = datetime.datetime.now()
    record_contact_change(session, contact, "manual_edit", changed_fields=["photo_storage_key"])
    try:
        session.commit()
    except Exception:
        session.rollback()
        return {"status": "error", "message": "DB error"}, 500

    return jsonify({"status": "success", "photo_url": storage.presigned_get_url(key)}), 200


@bp.route("/contacts/<int:contact_id>/photo", methods=["DELETE", "OPTIONS"])
def contact_photo_delete(contact_id: int):
    if request.method == "OPTIONS":
        return {"status": "OK"}, 200

    session = get_scoped_session()
    contact = session.get(Contact, contact_id)
    if contact is None:
        return {"status": "error", "message": "Contact not found"}, 404

    # The blob itself is left in storage — ObjectStorage has no delete
    # primitive (same tradeoff as document_images.py's replace functions).
    contact.photo_storage_key = None
    contact.updated_at = datetime.datetime.now()
    record_contact_change(session, contact, "manual_edit", changed_fields=["photo_storage_key"])
    try:
        session.commit()
    except Exception:
        session.rollback()
        return {"status": "error", "message": "DB error"}, 500

    return jsonify({"status": "success"}), 200


@bp.route("/contacts", methods=["POST", "OPTIONS"])
def contacts_add():
    if request.method == "OPTIONS":
        return {"status": "OK"}, 200

    data = request.get_json(silent=True) or {}
    last_name = (data.get("last_name") or "").strip()
    if not last_name:
        return {"status": "error", "message": "last_name is required"}, 400

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
    if "birthday" in data:
        row.birthday = data.get("birthday") or None
        changed_fields.append("birthday")

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

    change_source = (data.get("change_source") or "manual_edit").strip()
    if change_source not in CONTACT_CHANGE_SOURCES:
        return {"status": "error", "message": f"change_source must be one of {CONTACT_CHANGE_SOURCES}"}, 400
    change_note = (data.get("change_note") or "").strip() or None
    changed_fields = []

    if "last_name" in data:
        last_name = (data.get("last_name") or "").strip()
        if not last_name:
            return {"status": "error", "message": "last_name cannot be empty"}, 400
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
    if "birthday" in data:
        new_birthday = data.get("birthday") or None
        old_birthday = row.birthday.isoformat() if row.birthday else None
        if old_birthday != new_birthday:
            changed_fields.append("birthday")
        row.birthday = new_birthday
    if "category_id" in data:
        category_id = data.get("category_id")
        if session.get(ContactCategory, category_id) is None:
            return {"status": "error", "message": "category_id not found"}, 400
        if row.category_id != category_id:
            changed_fields.append("category_id")
        row.category_id = category_id
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

    # Confirming a LinkedIn candidate promotes its url onto the contact's
    # single-valued linkedin_url field — this table only tracks the search
    # trail, contacts.linkedin_url remains the one confirmed profile.
    if row.status == "confirmed" and row.lookup_type == "linkedin" and row.url:
        contact = session.get(Contact, row.contact_id)
        if contact is not None and contact.linkedin_url != row.url:
            contact.linkedin_url = row.url
            record_contact_change(
                session, contact, "linkedin_analysis", changed_fields=["linkedin_url"],
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
    if "start_date" in data:
        row.start_date = data.get("start_date") or None
    if "end_date" in data:
        row.end_date = data.get("end_date") or None

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
    if "start_date" in data:
        row.start_date = data.get("start_date") or None
    if "end_date" in data:
        row.end_date = data.get("end_date") or None

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
