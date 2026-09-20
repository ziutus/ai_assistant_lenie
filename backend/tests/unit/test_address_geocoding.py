"""Full-address geocoding cache and PostGIS coordinate contract, without network."""

from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")

from library.address_geocoding import geocode_address
from library.db.models import Address, GeocodeCache


@pytest.mark.parametrize("cached", [False, True])
@pytest.mark.parametrize("resolved", [False, True])
def test_geocode_address_cache_and_coordinates(monkeypatch, cached, resolved):
    session = MagicMock()
    address = Address(raw_address=" Example Street 1, Warsaw ")
    # A building hit must be accepted even though NER's OSM-class filter rejects it.
    hit = {
        "display_name": "1, Example Street, Warsaw, Poland",
        "lat": "52.229700", "lon": "21.012200", "class": "building",
        "type": "house", "importance": 0.3,
    } if resolved else None
    row = GeocodeCache(id=42, query=address.raw_address, resolved=resolved,
                       lat=hit["lat"] if hit else None, lon=hit["lon"] if hit else None)
    session.query.return_value.filter.return_value.one_or_none.return_value = row if cached else None
    geocode = MagicMock(return_value=hit)
    monkeypatch.setattr("library.address_geocoding.locationiq_client.geocode", geocode)
    session.flush.side_effect = lambda: setattr(session.add.call_args.args[0], "id", 42)

    assert geocode_address(session, address) is resolved
    assert address.geocode_id == 42
    condition = session.query.return_value.filter.call_args.args[0]
    assert condition.right.value == address.raw_address
    if cached:
        geocode.assert_not_called()
        session.add.assert_not_called()
        session.flush.assert_not_called()
    else:
        geocode.assert_called_once_with(address.raw_address)
        session.flush.assert_called_once()
        created = session.add.call_args.args[0]
        assert created.query == address.raw_address
        assert created.resolved is resolved
        assert created.raw == hit
        for field, key in (("display_name", "display_name"), ("lat", "lat"), ("lon", "lon"),
                           ("osm_class", "class"), ("osm_type", "type"), ("importance", "importance")):
            assert getattr(created, field) == (hit[key] if hit else None)
    if resolved:
        assert address.latitude == hit["lat"] and address.longitude == hit["lon"]
        point = address.location.clause.clauses
        coordinates, srid = list(point)
        assert [arg.value for arg in coordinates.clauses] == [hit["lon"], hit["lat"]]
        assert srid.value == 4326
        assert address.location.type is Address.__table__.c.location.type
    else:
        assert address.latitude is None and address.longitude is None and address.location is None
    session.commit.assert_not_called()
