"""Name-based duplicate suggestions and persistent dismissal of canonical pairs."""

from sqlalchemy import func, select
from sqlalchemy.orm import aliased, joinedload, selectinload

from library.db.models import Contact, ContactDuplicateDismissal

NAME_SIMILARITY_THRESHOLD = 0.5
CORROBORATION_BONUS = 0.05


def _normalized_name(contact):
    return func.unaccent(func.lower(func.trim(func.concat(
        func.coalesce(contact.first_name, ""), " ", func.coalesce(contact.last_name, ""),
    ))))


def find_duplicate_candidates(session, *, include_archived: bool = False) -> list[dict]:
    """Return ORM pairs; the route owns serialization and signed photo URLs."""
    a, b = aliased(Contact), aliased(Contact)
    name_a, name_b = _normalized_name(a), _normalized_name(b)
    similarity = func.similarity(name_a, name_b)
    dismissed = select(ContactDuplicateDismissal.id).where(
        ContactDuplicateDismissal.contact_id_a == a.id,
        ContactDuplicateDismissal.contact_id_b == b.id,
    ).exists()
    query = select(a, b, similarity).join(b, a.id < b.id).where(
        name_a != "", name_b != "", similarity >= NAME_SIMILARITY_THRESHOLD, ~dismissed,
    ).options(joinedload(a.category), joinedload(b.category), selectinload(a.groups), selectinload(b.groups))
    if not include_archived:
        query = query.where(a.is_archived.is_(False), b.is_archived.is_(False))
    candidates = []
    for first, second, name_score in session.execute(query):
        reasons = []
        if first.phone_number and first.phone_number == second.phone_number:
            reasons.append("ten sam numer telefonu")
        if first.email and first.email == second.email:
            reasons.append("ten sam adres e-mail")
        if (first.birthday and first.birthday == second.birthday) or (
            first.birthday_month and first.birthday_day
            and (first.birthday_month, first.birthday_day) == (second.birthday_month, second.birthday_day)
        ):
            reasons.append("ta sama data urodzenia")
        if {group.id for group in first.groups} & {group.id for group in second.groups}:
            reasons.append("wspólna grupa")
        candidates.append({
            "contact_a": first, "contact_b": second,
            "score": min(1.0, float(name_score) + CORROBORATION_BONUS * len(reasons)), "reasons": reasons,
        })
    return sorted(candidates, key=lambda pair: (-pair["score"], pair["contact_a"].id, pair["contact_b"].id))


def dismiss_duplicate_pair(
    session, contact_id_a: int, contact_id_b: int, note: str | None,
) -> ContactDuplicateDismissal:
    if any(type(value) is not int or value <= 0 for value in (contact_id_a, contact_id_b)):
        raise ValueError("Contact ids must be positive integers")
    if contact_id_a == contact_id_b:
        raise ValueError("Two different contacts are required")
    if note is not None and not isinstance(note, str):
        raise ValueError("note must be text or null")
    a, b = sorted((contact_id_a, contact_id_b))
    row = session.scalar(select(ContactDuplicateDismissal).where(
        ContactDuplicateDismissal.contact_id_a == a, ContactDuplicateDismissal.contact_id_b == b,
    ))
    if row is None:
        row = ContactDuplicateDismissal(contact_id_a=a, contact_id_b=b)
        session.add(row)
    row.note = note
    row.dismissed_at = func.now()
    return row
