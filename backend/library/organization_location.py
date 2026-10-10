"""Location and relations of an organization: headquarters geocoding and the
persons/places that co-occur with it in documents."""

from collections import Counter

from sqlalchemy import func, select

from library import locationiq_client
from library.country_gazetteer import slug_to_name
from library.db.models import (
    Document,
    DocumentEntity,
    DocumentOrganization,
    DocumentPerson,
    GeocodeCache,
    Organization,
    OrganizationCountry,
    Person,
)

PLACE_ENTITY_TYPES = ("geogName", "placeName")

COUNTRY_RELATIONS = {
    "based_in": "siedziba w",
    "operates_in": "działa w",
    "linked_to": "powiązana z",
}


def geocode_headquarters(session, organization: Organization) -> bool:
    """Set the organization's coordinates from its headquarters address; never commit.

    Goes through the shared exact-query ``geocode_cache`` (a negative result is
    cached too and never retried). Returns True when the address resolved; on a
    miss the previous coordinates are cleared so a stale point cannot outlive
    the address it belonged to.
    """
    query = (organization.headquarters_address or "").strip()
    if not query:
        organization.latitude = None
        organization.longitude = None
        return False

    row = session.query(GeocodeCache).filter(GeocodeCache.query == query).one_or_none()
    if row is None:
        hit = locationiq_client.geocode(query)
        row = GeocodeCache(
            query=query,
            resolved=hit is not None,
            display_name=hit.get("display_name") if hit else None,
            lat=hit.get("lat") if hit else None,
            lon=hit.get("lon") if hit else None,
            osm_class=hit.get("class") if hit else None,
            osm_type=hit.get("type") if hit else None,
            importance=hit.get("importance") if hit else None,
            raw=hit,
        )
        session.add(row)
        session.flush()

    if row.resolved:
        organization.latitude = row.lat
        organization.longitude = row.lon
    else:
        organization.latitude = None
        organization.longitude = None
    return bool(row.resolved)


def _organization_document_ids(organization_id: int):
    return select(DocumentOrganization.document_id).where(DocumentOrganization.organization_id == organization_id)


def related_persons(session, organization_id: int, limit: int = 30) -> list[dict]:
    """Persons mentioned in the same documents as the organization, most shared documents first."""
    shared = func.count(func.distinct(DocumentPerson.document_id))
    rows = session.execute(
        select(Person.id, Person.canonical_name, shared.label("shared_documents"))
        .join(DocumentPerson, DocumentPerson.person_id == Person.id)
        .where(DocumentPerson.document_id.in_(_organization_document_ids(organization_id)))
        .group_by(Person.id, Person.canonical_name)
        .order_by(shared.desc(), Person.canonical_name)
        .limit(limit)
    ).all()
    return [{"id": r.id, "canonical_name": r.canonical_name, "shared_documents": r.shared_documents} for r in rows]


def related_places(session, organization_id: int, limit: int = 50) -> list[dict]:
    """Geocoded places mentioned in the same documents as the organization.

    Only places the geocoder resolved are returned (they are the ones that can
    be drawn); duplicates sharing one geocode row are folded together.
    """
    shared = func.count(func.distinct(DocumentEntity.document_id))
    mentions = func.sum(DocumentEntity.mention_count)
    rows = session.execute(
        select(
            GeocodeCache.id,
            func.min(DocumentEntity.entity_text).label("name"),
            GeocodeCache.display_name,
            GeocodeCache.lat,
            GeocodeCache.lon,
            shared.label("shared_documents"),
            mentions.label("mentions"),
        )
        .join(GeocodeCache, GeocodeCache.id == DocumentEntity.geocode_id)
        .where(
            DocumentEntity.entity_type.in_(PLACE_ENTITY_TYPES),
            DocumentEntity.document_id.in_(_organization_document_ids(organization_id)),
            GeocodeCache.resolved.is_(True),
            GeocodeCache.lat.is_not(None),
            GeocodeCache.lon.is_not(None),
        )
        .group_by(GeocodeCache.id, GeocodeCache.display_name, GeocodeCache.lat, GeocodeCache.lon)
        .order_by(shared.desc(), mentions.desc())
        .limit(limit)
    ).all()
    return [{
        "name": r.name,
        "display_name": r.display_name,
        "lat": float(r.lat),
        "lon": float(r.lon),
        "shared_documents": r.shared_documents,
        "mentions": int(r.mentions or 0),
    } for r in rows]


# --- countries -------------------------------------------------------------


def _country_dict(row: OrganizationCountry) -> dict:
    return {
        "id": row.id,
        "country_slug": row.country_slug,
        "name_pl": slug_to_name(row.country_slug) or row.country_slug,
        "relation": row.relation,
        "relation_label": COUNTRY_RELATIONS.get(row.relation, row.relation),
        "note": row.note,
    }


def list_countries(session, organization_id: int) -> list[dict]:
    rows = session.execute(
        select(OrganizationCountry)
        .where(OrganizationCountry.organization_id == organization_id)
        .order_by(OrganizationCountry.id)
    ).scalars().all()
    return [_country_dict(r) for r in rows]


def add_country(session, organization_id: int, country_slug: str, relation: str,
                note: str | None = None) -> tuple[dict, bool]:
    """Attach a country to an organization; never commits.

    Returns (row, created). Re-adding an existing (country, relation) pair is a
    no-op that only refreshes the note when one is given. Raises ValueError for
    an unknown slug/relation (the slug must be a known ``kraj-<slug>`` country).
    """
    slug = (country_slug or "").strip().lower()
    if slug_to_name(slug) is None:
        raise ValueError(f"unknown country slug: {country_slug!r}")
    if relation not in COUNTRY_RELATIONS:
        raise ValueError(f"relation must be one of {', '.join(COUNTRY_RELATIONS)}")
    note = (note or "").strip() or None

    row = session.execute(
        select(OrganizationCountry).where(
            OrganizationCountry.organization_id == organization_id,
            OrganizationCountry.country_slug == slug,
            OrganizationCountry.relation == relation,
        )
    ).scalars().first()
    created = row is None
    if created:
        row = OrganizationCountry(organization_id=organization_id, country_slug=slug,
                                  relation=relation, note=note)
        session.add(row)
        session.flush()
    elif note is not None:
        row.note = note
    return _country_dict(row), created


def remove_country(session, organization_id: int, row_id: int) -> bool:
    """Delete one country tie of the organization; never commits."""
    row = session.get(OrganizationCountry, row_id)
    if row is None or row.organization_id != organization_id:
        return False
    session.delete(row)
    return True


def country_suggestions(session, organization_id: int, limit: int = 15) -> list[dict]:
    """``kraj-*`` tags of the organization's documents, with how many documents carry each.

    Candidates only — sharing a document does not mean the organization operates
    in the country, so nothing is assigned automatically. Countries already
    attached (with any relation) are left out.
    """
    tag_rows = session.execute(
        select(Document.tags).where(Document.id.in_(_organization_document_ids(organization_id)))
    ).scalars().all()
    counts: Counter[str] = Counter()
    for tags in tag_rows:
        slugs = {t.strip()[len("kraj-"):] for t in (tags or "").split(",") if t.strip().startswith("kraj-")}
        counts.update(slugs)

    attached = set(session.execute(
        select(OrganizationCountry.country_slug).where(OrganizationCountry.organization_id == organization_id)
    ).scalars().all())
    return [
        {"country_slug": slug, "name_pl": slug_to_name(slug) or slug, "documents": n}
        for slug, n in counts.most_common()
        if slug not in attached and slug_to_name(slug) is not None
    ][:limit]


def absorb_organization(session, source: Organization, target: Organization) -> None:
    """Carry location data over when ``source`` is merged into ``target``; never commits.

    Country ties move to the target (dropping pairs it already has) and the
    target's empty headquarters/website/note fields are filled from the source —
    the target's own values always win.
    """
    existing = {
        (c.country_slug, c.relation)
        for c in session.execute(
            select(OrganizationCountry).where(OrganizationCountry.organization_id == target.id)
        ).scalars()
    }
    for row in session.execute(
        select(OrganizationCountry).where(OrganizationCountry.organization_id == source.id)
    ).scalars().all():
        if (row.country_slug, row.relation) in existing:
            session.delete(row)
        else:
            row.organization_id = target.id
            existing.add((row.country_slug, row.relation))

    if target.headquarters_address is None and target.latitude is None and target.longitude is None:
        target.headquarters_address = source.headquarters_address
        target.latitude = source.latitude
        target.longitude = source.longitude
    for field in ("website", "obsidian_note_path"):
        if getattr(target, field) is None:
            setattr(target, field, getattr(source, field))
