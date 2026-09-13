"""Create family contacts from explicit user facts, atomically and idempotently."""

from uuid import UUID

from library.contact_change_log import record_contact_change
from library.contact_names import contact_display_name, validate_contact_name
from library.contact_photos import _error, _photo
from library.db.models import Contact, ContactFamilyCreation, ContactGroup, ContactRelationship


def create_family(session, contact_id, body):
    if not isinstance(body, dict):
        return _error("Dane rodziny muszą być obiektem.", 400)
    try:
        request_id = str(UUID(body.get("request_id", "")))
    except (ValueError, TypeError, AttributeError):
        return _error("Wymagany request_id w formacie UUID.", 400)
    # Lock the root before checking the receipt: two retries cannot both create
    # contacts. A saved receipt remains valid even if the photo later changes.
    root = session.get(Contact, contact_id, with_for_update=True)
    if root is None:
        return _error("Nie znaleziono kontaktu.", 404)
    receipt = session.get(ContactFamilyCreation, request_id)
    if receipt is not None:
        matches = receipt.contact_id == contact_id and receipt.request_payload == body
        previous_result = receipt.result
        session.rollback()
        if not matches:
            return _error("Ten request_id dotyczy innej operacji.", 409)
        return {"status": "success", "family": previous_result, "replayed": True}, 200

    children = body.get("children")
    spouse = body.get("spouse")
    if not isinstance(children, list) or not 1 <= len(children) <= 6:
        session.rollback()
        return _error("Podaj od jednego do sześciorga dzieci.", 400)
    if spouse is not None and not isinstance(spouse, dict):
        session.rollback()
        return _error("Dane drugiego rodzica muszą być obiektem.", 400)
    if any(type(body.get(field, False)) is not bool for field in ("twins", "share_photo", "copy_parent_groups")):
        session.rollback()
        return _error("Opcje rodziny muszą być wartościami logicznymi.", 400)
    if body.get("twins") and len(children) != 2:
        session.rollback()
        return _error("Relacja bliźniąt wymaga dokładnie dwojga dzieci.", 400)
    if spouse is not None and body.get("spouse_relationship") not in ("mąż", "żona", "partner", "partnerka"):
        session.rollback()
        return _error("Wybierz relację drugiego rodzica.", 400)
    members = ([spouse] if spouse is not None else []) + children
    for member in members:
        error = validate_contact_name(member)
        if error:
            session.rollback()
            return _error(error, 400)
    source_note = body.get("source_note")
    if not isinstance(source_note, str) or not source_note.strip() or len(source_note) > 12000:
        session.rollback()
        return _error("Podaj własną informację o rodzinie (do 12000 znaków).", 400)

    root, photo, error = _photo(session, contact_id, body, lock=True)
    if error:
        session.rollback()
        return error
    peer_id = body.get("peer_contact_id")
    peer = None
    if peer_id is not None:
        if type(peer_id) is not int or peer_id == contact_id:
            session.rollback()
            return _error("Wybierz kontakt dziecka z tej samej grupy.", 400)
        peer = session.get(Contact, peer_id)
        if peer is None:
            session.rollback()
            return _error("Nie znaleziono wskazanego dziecka z grupy.", 400)
    group = None
    group_id = body.get("children_group_id")
    if group_id is not None:
        if type(group_id) is not int:
            session.rollback()
            return _error("Nieprawidłowa grupa dzieci.", 400)
        group = session.get(ContactGroup, group_id)
        if group is None:
            session.rollback()
            return _error("Nie znaleziono grupy dzieci.", 400)

    source = f"Informacja użytkownika; rodzina kontaktu {contact_id}.\n{source_note.strip()}"
    result = {"spouse": None, "children": [], "twins": body.get("twins", False)}
    try:
        def add_contact(data):
            row = Contact(
                category_id=root.category_id,
                first_name=(data.get("first_name") or "").strip() or None,
                last_name=(data.get("last_name") or "").strip() or None,
                display_label=(data.get("display_label") or "").strip() or None,
                notes=source,
                photo_storage_key=photo.storage_key if body.get("share_photo") else None,
            )
            session.add(row)
            session.flush()
            record_contact_change(session, row, "manual_edit",
                                  ["first_name", "last_name", "display_label", "notes", "photo_storage_key"], source)
            return row

        def link(origin, other, relation):
            session.add(ContactRelationship(contact_id=origin.id, related_contact_id=other.id,
                                            relationship_type=relation, note=source))

        def summary(row):
            return {"id": row.id, "display_name": contact_display_name(row)}

        second_parent = add_contact(spouse) if spouse is not None else None
        if second_parent is not None:
            link(root, second_parent, body["spouse_relationship"])
            if body.get("copy_parent_groups"):
                second_parent.groups = list(root.groups)
                record_contact_change(session, second_parent, "manual_edit", ["groups"])
            result["spouse"] = summary(second_parent)
        child_rows = []
        for child in children:
            row = add_contact(child)
            child_rows.append(row)
            link(root, row, "dziecko")
            if second_parent is not None:
                link(second_parent, row, "dziecko")
            if peer is not None:
                link(row, peer, "ta sama grupa przedszkolna")
            if group is not None:
                row.groups = [group]
                record_contact_change(session, row, "manual_edit", ["groups"])
            result["children"].append(summary(row))
        if body.get("twins"):
            link(child_rows[0], child_rows[1], "bliźnięta")
        record_contact_change(session, root, "manual_edit", ["relationships"], source)
        session.add(ContactFamilyCreation(request_id=request_id, contact_id=contact_id, request_payload=body, result=result))
        session.commit()
    except Exception:
        session.rollback()
        return _error("Nie udało się zapisać rodziny. Żaden częściowy zapis nie został zatwierdzony.", 500)
    return {"status": "success", "family": result, "replayed": False}, 201
