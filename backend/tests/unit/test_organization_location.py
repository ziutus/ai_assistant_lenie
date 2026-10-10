"""Organization headquarters geocoding and related persons/places, without network or DB."""

from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")

from library.db.models import GeocodeCache, Organization
from library.organization_location import geocode_headquarters, related_persons, related_places


def _org(address):
    return Organization(canonical_name="Acme", headquarters_address=address,
                        latitude=1.0, longitude=2.0)


@pytest.mark.parametrize("cached", [False, True])
@pytest.mark.parametrize("resolved", [False, True])
def test_geocode_headquarters_cache_and_coordinates(monkeypatch, cached, resolved):
    session = MagicMock()
    organization = _org("Aleje Jerozolimskie 1, Warszawa")
    hit = {"display_name": "Warszawa, Polska", "lat": "52.2297", "lon": "21.0122",
           "class": "building", "type": "yes", "importance": 0.4} if resolved else None
    row = GeocodeCache(id=7, query=organization.headquarters_address, resolved=resolved,
                       lat=hit["lat"] if hit else None, lon=hit["lon"] if hit else None)
    session.query.return_value.filter.return_value.one_or_none.return_value = row if cached else None
    geocode = MagicMock(return_value=hit)
    monkeypatch.setattr("library.organization_location.locationiq_client.geocode", geocode)

    assert geocode_headquarters(session, organization) is resolved
    if cached:
        geocode.assert_not_called()
        session.add.assert_not_called()
    else:
        geocode.assert_called_once_with("Aleje Jerozolimskie 1, Warszawa")
        created = session.add.call_args.args[0]
        assert created.resolved is resolved and created.raw == hit
    if resolved:
        assert organization.latitude == hit["lat"] and organization.longitude == hit["lon"]
    else:
        # a miss must not leave a stale point from a previous address
        assert organization.latitude is None and organization.longitude is None
    session.commit.assert_not_called()


@pytest.mark.parametrize("address", [None, "", "   "])
def test_geocode_headquarters_blank_address_clears_point_without_lookup(monkeypatch, address):
    session = MagicMock()
    geocode = MagicMock()
    monkeypatch.setattr("library.organization_location.locationiq_client.geocode", geocode)
    organization = _org(address)

    assert geocode_headquarters(session, organization) is False
    assert organization.latitude is None and organization.longitude is None
    geocode.assert_not_called()
    session.query.assert_not_called()


def test_related_persons_shapes_rows():
    session = MagicMock()
    session.execute.return_value.all.return_value = [
        MagicMock(id=3, canonical_name="Jan Kowalski", shared_documents=4),
        MagicMock(id=9, canonical_name="Anna Nowak", shared_documents=1),
    ]
    assert related_persons(session, 836) == [
        {"id": 3, "canonical_name": "Jan Kowalski", "shared_documents": 4},
        {"id": 9, "canonical_name": "Anna Nowak", "shared_documents": 1},
    ]


def test_related_places_shapes_rows_and_casts_coordinates():
    session = MagicMock()
    session.execute.return_value.all.return_value = [
        MagicMock(name_="x", display_name="Kijów, Ukraina", lat="50.45", lon="30.52",
                  shared_documents=2, mentions=None),
    ]
    row = session.execute.return_value.all.return_value[0]
    row.name = "Kijów"

    (place,) = related_places(session, 836)
    assert place == {"name": "Kijów", "display_name": "Kijów, Ukraina", "lat": 50.45, "lon": 30.52,
                     "shared_documents": 2, "mentions": 0}


def test_related_places_query_keeps_only_resolved_geocodes():
    session = MagicMock()
    session.execute.return_value.all.return_value = []
    related_places(session, 836)
    sql = str(session.execute.call_args.args[0])
    assert "geocode_cache.resolved" in sql and "document_entities.entity_type IN" in sql
