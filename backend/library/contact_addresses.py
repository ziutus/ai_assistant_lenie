"""Idempotent address attachment for contact imports (caller owns the transaction)."""
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from library.db.models import Address, ContactAddress


def contact_address_links(session, contact):
    if contact.id is None:
        return []
    return list(session.scalars(
        select(ContactAddress).options(joinedload(ContactAddress.address))
        .where(ContactAddress.contact_id == contact.id)
        .order_by(ContactAddress.is_primary.desc(), ContactAddress.id)
    ))


def attach_imported_address(session, contact, raw_address):
    """Add nonblank text once per contact, making only its first address primary."""
    raw_address = (raw_address or "").strip()
    if not raw_address:
        return False
    links = contact_address_links(session, contact)
    if any(link.address.raw_address == raw_address for link in links):
        return False
    address = Address(raw_address=raw_address)
    session.add(address)
    session.add(ContactAddress(contact=contact, address=address,
                               role="zamieszkania", is_primary=not links))
    session.flush()
    return True
