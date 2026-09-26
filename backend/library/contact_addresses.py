"""Idempotent address attachment for contact imports (caller owns the transaction)."""
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from library.address_formatting import addresses_match, imported_address_fields
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
    """Add nonblank text once per contact, making only its first active address primary.

    The same place (however spelled) is never added twice — the database refuses a second active copy
    anyway. An archived stay counts too: re-importing an old source must not move the person back to a
    place they left, so a match with history is skipped rather than resurrected.
    """
    if not (address_text or "").strip():
        return False
    fields = imported_address_fields(address_text)
    links = contact_address_links(session, contact)
    address = Address(**fields)
    if any(addresses_match(link.address, address) for link in links):
        return False
    session.add(address)
    session.add(ContactAddress(contact=contact, address=address, role="zamieszkania",
                               is_primary=not any(not link.is_archived for link in links)))
    session.flush()
    return True
