"""On-demand geocoding of full addresses through the shared geocode cache."""

from sqlalchemy import func

from library import locationiq_client
from library.address_formatting import format_address
from library.db.models import Address, GeocodeCache


def geocode_address(session, address: Address) -> bool:
    """Set coordinates from an exact-query cache entry or LocationIQ; never commit.

    Full addresses trust the first hit without NER place-name heuristics.
    Negative cache entries retain provenance and are not retried.
    """
    query = format_address(address)
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

    address.geocode_id = row.id
    if row.resolved:
        address.latitude = row.lat
        address.longitude = row.lon
        address.location = func.ST_SetSRID(
            func.ST_MakePoint(address.longitude, address.latitude), 4326,
        ).cast(Address.__table__.c.location.type)
    return bool(row.resolved)
