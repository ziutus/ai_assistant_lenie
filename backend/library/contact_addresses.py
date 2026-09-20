"""Idempotent address attachment for contact imports (caller owns the transaction)."""
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from library.address_formatting import imported_address_fields
from library.db.models import Address, ContactAddress


def contact_address_links(session, contact):
    if contact.id is None:
        return []
    return list(session.scalars(
        select(ContactAddress).options(joinedload(ContactAddress.address))
        .where(ContactAddress.contact_id == contact.id)
        .order_by(ContactAddress.is_primary.desc(), ContactAddress.id)
    ))


def attach_imported_address(session, contact, address_text):
    """Add nonblank text once per contact, making only its first address primary."""
    if not (address_text or "").strip():
        return False
    fields = imported_address_fields(address_text)
    links = contact_address_links(session, contact)
    if any(all(getattr(link.address, field) == value for field, value in fields.items()) for link in links):
        return False
    address = Address(**fields)
    session.add(address)
    session.add(ContactAddress(contact=contact, address=address,
                               role="zamieszkania", is_primary=not links))
    session.flush()
    return True
