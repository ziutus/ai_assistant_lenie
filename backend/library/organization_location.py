"""Location and relations of an organization: headquarters geocoding and the
persons/places that co-occur with it in documents."""

from sqlalchemy import func, select

from library import locationiq_client
from library.db.models import (
    DocumentEntity,
    DocumentOrganization,
    DocumentPerson,
    GeocodeCache,
    Organization,
    Person,
)

PLACE_ENTITY_TYPES = ("geogName", "placeName")


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
