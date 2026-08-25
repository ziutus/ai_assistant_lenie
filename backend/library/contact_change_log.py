"""Shared helper for recording Contact audit-trail events (`contact_change_log`
table, see `backend/alembic/versions/bc9846bcce94_create_contact_change_log.py`
for the source vocabulary and rationale). Used both by the REST API
(`contact_routes.py`) and by scripts that write `Contact` rows directly via
the ORM (`imports/google_contacts_import.py`, `imports/whatsapp_neighbor_profiles.py`)."""

from library.db.models import Contact, ContactChangeLog

CONTACT_CHANGE_SOURCES = (
    "manual_edit", "google_import", "linkedin_analysis",
    "whatsapp_analysis", "osint_lookup", "other",
)


def record_contact_change(
    session, contact: Contact, source: str, changed_fields: list[str] | None = None, note: str | None = None,
) -> ContactChangeLog | None:
    """Append one contact_change_log row. No-op (returns None) when there is
    nothing to record — no changed fields and no note."""
    if source not in CONTACT_CHANGE_SOURCES:
        raise ValueError(f"source must be one of {CONTACT_CHANGE_SOURCES}")
    changed_fields = changed_fields or []
    if not changed_fields and not note:
        return None
    row = ContactChangeLog(contact_id=contact.id, source=source, changed_fields=changed_fields, note=note or None)
    session.add(row)
    return row
