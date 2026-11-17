"""Countries and geopolitical macro-regions a person is tied to (the person counterpart of
``organization_location``'s country ties).

A tie is ``(kind, slug, relation)``: ``kind`` ``country`` has the slug of the ``kraj-<slug>`` document tag
(``jemen``), ``kind`` ``region`` the slug of the ``miejsce-<slug>`` tag of a macro-region from
``geopolitical_region_gazetteer`` (``bliski-wschod``). That is what makes the ties usable against a document: its
territories are simply its ``kraj-*`` and ``miejsce-<region>`` tags, so ``persons_for_document()`` can answer "who
belongs to this document's countries" — the candidate list for choosing between namesakes and for repairing
speech-to-text slips of a name.

Nothing here commits; the caller owns the transaction.
"""

import datetime
from collections import Counter

from sqlalchemy import select

from library.country_gazetteer import slug_to_name
from library.db.models import Document, DocumentPerson, Person, PersonAlias, PersonTerritory
from library.geopolitical_region_gazetteer import geopolitical_region_name, known_geopolitical_regions

KINDS = ("country", "region")

RELATIONS = {
    "citizen_of": "obywatelstwo",
    "holds_office_in": "pełni funkcję w",
    "active_in": "działa w",
    "linked_to": "powiązanie",
}

COUNTRY_TAG = "kraj-"
REGION_TAG = "miejsce-"


class TerritoryError(ValueError):
    """A tie that cannot be stored. ``code`` is one of ``ERROR_MESSAGES``; the REST layer answers with that fixed
    text, never with the exception's own message."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


ERROR_MESSAGES = {
    "kind": "kind must be country or region",
    "slug": "unknown country or region slug",
    "relation": "relation must be one of citizen_of, holds_office_in, active_in, linked_to",
    "date_format": "valid_from and valid_to must be ISO dates (YYYY-MM-DD)",
    "date_order": "valid_to must not be earlier than valid_from",
}


def territory_name(kind: str, slug: str) -> str | None:
    """The Polish name of a territory, or None when the slug is not a known country / macro-region."""
    if kind == "country":
        return slug_to_name(slug)
    if kind == "region":
        return geopolitical_region_name(slug)
    return None


def territory_tag(kind: str, slug: str) -> str:
    """The document tag that stands for the territory (``kraj-jemen`` / ``miejsce-bliski-wschod``)."""
    return (COUNTRY_TAG if kind == "country" else REGION_TAG) + slug


def _parse_date(value, field: str) -> datetime.date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime.date):
        return value
    try:
        return datetime.date.fromisoformat(str(value))
    except ValueError as exc:
        raise TerritoryError("date_format", f"{field} must be an ISO date (YYYY-MM-DD)") from exc


def _tie_dict(row: PersonTerritory) -> dict:
    return {
        "id": row.id,
        "kind": row.kind,
        "slug": row.slug,
        "name_pl": territory_name(row.kind, row.slug) or row.slug,
        "tag": territory_tag(row.kind, row.slug),
        "relation": row.relation,
        "relation_label": RELATIONS.get(row.relation, row.relation),
        "note": row.note,
        "valid_from": row.valid_from.isoformat() if row.valid_from else None,
        "valid_to": row.valid_to.isoformat() if row.valid_to else None,
    }


def list_territories(session, person_id: int) -> list[dict]:
    rows = session.execute(
        select(PersonTerritory).where(PersonTerritory.person_id == person_id)
        .order_by(PersonTerritory.kind, PersonTerritory.id)
    ).scalars().all()
    return [_tie_dict(row) for row in rows]


def add_territory(session, person_id: int, kind: str, slug: str, relation: str, note: str | None = None,
                  valid_from=None, valid_to=None) -> tuple[dict, bool]:
    """Tie a person to a country or macro-region; returns ``(tie, created)``.

    Re-adding an existing ``(kind, slug, relation)`` is not an error: it refreshes the note and the dates that
    are given. Raises ValueError for an unknown kind / slug / relation or a reversed date range.
    """
    if kind not in KINDS:
        raise TerritoryError("kind", f"kind must be one of {', '.join(KINDS)}")
    slug = (slug or "").strip().lower()
    if territory_name(kind, slug) is None:
        raise TerritoryError("slug", f"unknown {kind} slug: {slug!r}")
    if relation not in RELATIONS:
        raise TerritoryError("relation", f"relation must be one of {', '.join(RELATIONS)}")
    start, end = _parse_date(valid_from, "valid_from"), _parse_date(valid_to, "valid_to")
    if start and end and end < start:
        raise TerritoryError("date_order", "valid_to must not be earlier than valid_from")
    note = (note or "").strip() or None

    row = session.execute(select(PersonTerritory).where(
        PersonTerritory.person_id == person_id, PersonTerritory.kind == kind,
        PersonTerritory.slug == slug, PersonTerritory.relation == relation,
    )).scalars().first()
    created = row is None
    if created:
        row = PersonTerritory(person_id=person_id, kind=kind, slug=slug, relation=relation,
                              note=note, valid_from=start, valid_to=end)
        session.add(row)
        session.flush()
    else:
        if note is not None:
            row.note = note
        if start is not None:
            row.valid_from = start
        if end is not None:
            row.valid_to = end
    return _tie_dict(row), created


def remove_territory(session, person_id: int, row_id: int) -> bool:
    row = session.get(PersonTerritory, row_id)
    if row is None or row.person_id != person_id:
        return False
    session.delete(row)
    return True


def territories_of_tags(tags) -> set[tuple[str, str]]:
    """``{("country", "jemen"), ("region", "bliski-wschod")}`` from a document's tags (list or comma string)."""
    if isinstance(tags, str):
        tags = tags.split(",")
    regions = {region["slug"] for region in known_geopolitical_regions()}
    found: set[tuple[str, str]] = set()
    for tag in tags or []:
        tag = tag.strip().lower() if isinstance(tag, str) else ""
        if tag.startswith(COUNTRY_TAG) and slug_to_name(tag[len(COUNTRY_TAG):]):
            found.add(("country", tag[len(COUNTRY_TAG):]))
        elif tag.startswith(REGION_TAG) and tag[len(REGION_TAG):] in regions:
            found.add(("region", tag[len(REGION_TAG):]))
    return found


def territory_suggestions(session, person_id: int, limit: int = 15) -> list[dict]:
    """Territories of the documents the person appears in, with how many documents carry each.

    Candidates only: sharing a document does not make a person a citizen of the country, so nothing is attached
    automatically. Territories the person already has (any relation) are left out.
    """
    tag_rows = session.execute(
        select(Document.tags).join(DocumentPerson, DocumentPerson.document_id == Document.id)
        .where(DocumentPerson.person_id == person_id)
    ).scalars().all()
    counts: Counter[tuple[str, str]] = Counter()
    for tags in tag_rows:
        counts.update(territories_of_tags(tags))
    attached = {(row.kind, row.slug) for row in session.execute(
        select(PersonTerritory).where(PersonTerritory.person_id == person_id)).scalars()}
    return [
        {"kind": kind, "slug": slug, "name_pl": territory_name(kind, slug) or slug, "documents": n}
        for (kind, slug), n in counts.most_common() if (kind, slug) not in attached
    ][:limit]


def persons_for_territories(session, territories: set[tuple[str, str]], on: datetime.date | None = None) -> list[dict]:
    """People tied to any of the territories, with their aliases.

    ``on`` keeps only ties valid on that date (a missing bound is open); without it every tie counts. A person
    tied to several of the territories appears once, with all matching ties listed.
    """
    if not territories:
        return []
    ties = session.execute(
        select(PersonTerritory, Person)
        .join(Person, Person.id == PersonTerritory.person_id)
        .where(PersonTerritory.kind.in_({kind for kind, _slug in territories}))
        .order_by(Person.canonical_name, PersonTerritory.id)
    ).all()
    people: dict[int, dict] = {}
    for tie, person in ties:
        if (tie.kind, tie.slug) not in territories:
            continue
        if on is not None and ((tie.valid_from and tie.valid_from > on) or (tie.valid_to and tie.valid_to < on)):
            continue
        entry = people.setdefault(person.id, {
            "id": person.id, "canonical_name": person.canonical_name, "role": person.role,
            "kind": person.kind, "ties": [],
        })
        entry["ties"].append(_tie_dict(tie))
    if people:
        for person_id, alias in session.execute(
            select(PersonAlias.person_id, PersonAlias.alias).where(PersonAlias.person_id.in_(people))
        ).all():
            people[person_id].setdefault("aliases", []).append(alias)
    for entry in people.values():
        entry.setdefault("aliases", [])
    return list(people.values())


def persons_for_document(session, document_id: int, on: datetime.date | None = None) -> dict | None:
    """The territories of a document (its ``kraj-*`` / region tags) and the people tied to them; None when the
    document does not exist."""
    document = session.get(Document, document_id)
    if document is None:
        return None
    territories = territories_of_tags(document.tags)
    return {
        "territories": [
            {"kind": kind, "slug": slug, "name_pl": territory_name(kind, slug) or slug, "tag": territory_tag(kind, slug)}
            for kind, slug in sorted(territories)
        ],
        "persons": persons_for_territories(session, territories, on=on),
    }
