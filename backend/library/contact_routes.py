"""REST API for the private contact book (personal CRM), independent of the
NER persons registry (library/person_registry.py) — a contact here may
never appear in any document. See docs: contact_categories is a lookup
table managed from the UI (like DiscoverySource); contact_relationships is
directional and single-row (no automatic reciprocal row/label)."""

import datetime

from flask import Blueprint, jsonify, request
from sqlalchemy import func, or_, select

from library.db.engine import get_scoped_session
from library.db.models import Contact, ContactCategory, ContactRelationship

bp = Blueprint("contacts", __name__)

_CONTACT_FIELDS = (
    "first_name", "last_name", "phone_number", "email", "linkedin_url",
    "company", "position", "address", "notes",
)


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


def _contact_dict(row: Contact) -> dict:
    return {
        "id": row.id,
        "uuid": row.uuid,
        "category_id": row.category_id,
        "category_name": row.category.name if row.category else None,
        "first_name": row.first_name,
        "last_name": row.last_name,
        "phone_number": row.phone_number,
        "email": row.email,
        "linkedin_url": row.linkedin_url,
        "company": row.company,
        "position": row.position,
        "address": row.address,
        "birthday": row.birthday.isoformat() if row.birthday else None,
        "notes": row.notes,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
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


# --- contacts ------------------------------------------------------------

@bp.get("/contacts")
def contacts_list():
    session = get_scoped_session()
    query = select(Contact)

    category_id = request.args.get("category_id", type=int)
    if category_id is not None:
        query = query.where(Contact.category_id == category_id)

    q = (request.args.get("q") or "").strip()
    if q:
        phrase = func.unaccent(f"%{q}%")
        query = query.where(or_(
            func.unaccent(Contact.first_name).ilike(phrase),
            func.unaccent(Contact.last_name).ilike(phrase),
            func.unaccent(func.coalesce(Contact.phone_number, "")).ilike(phrase),
        ))

    offset = request.args.get("offset", default=0, type=int)
    limit = min(request.args.get("limit", default=100, type=int), 500)
    query = query.order_by(Contact.last_name, Contact.first_name).offset(offset).limit(limit)

    rows = session.execute(query).scalars().all()
    return jsonify({"status": "success", "contacts": [_contact_dict(row) for row in rows]}), 200


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

    data = _contact_dict(row)
    data["relationships"] = relationships
    return jsonify({"status": "success", "contact": data}), 200


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

    row = Contact(category_id=category_id, last_name=last_name)
    for field in _CONTACT_FIELDS:
        if field == "last_name":
            continue
        if field in data:
            setattr(row, field, (data.get(field) or "").strip() or None)
    if "birthday" in data:
        row.birthday = data.get("birthday") or None

    session.add(row)
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

    if "last_name" in data:
        last_name = (data.get("last_name") or "").strip()
        if not last_name:
            return {"status": "error", "message": "last_name cannot be empty"}, 400
        row.last_name = last_name
    for field in _CONTACT_FIELDS:
        if field == "last_name":
            continue
        if field in data:
            setattr(row, field, (data.get(field) or "").strip() or None)
    if "birthday" in data:
        row.birthday = data.get("birthday") or None
    if "category_id" in data:
        category_id = data.get("category_id")
        if session.get(ContactCategory, category_id) is None:
            return {"status": "error", "message": "category_id not found"}, 400
        row.category_id = category_id

    row.updated_at = datetime.datetime.now()
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
