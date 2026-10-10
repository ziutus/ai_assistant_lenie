"""Organization headquarters geocoding and related persons/places, without network or DB."""

from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")

from library.db.models import GeocodeCache, Organization, OrganizationCountry
from library.organization_location import (
    absorb_organization,
    add_country,
    country_suggestions,
    geocode_headquarters,
    related_persons,
    related_places,
    remove_country,
)


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


# --- countries ---------------------------------------------------------------


def _session_with_existing(row):
    session = MagicMock()
    session.execute.return_value.scalars.return_value.first.return_value = row
    return session


def test_add_country_creates_row_for_known_slug():
    session = _session_with_existing(None)
    country, created = add_country(session, 836, " Jemen ", "operates_in", " od 2015 ")
    assert created is True
    assert country["country_slug"] == "jemen" and country["name_pl"] == "Jemen"
    assert country["relation"] == "operates_in" and country["note"] == "od 2015"
    session.add.assert_called_once()
    session.commit.assert_not_called()


def test_add_country_existing_pair_is_idempotent_and_only_updates_note():
    existing = OrganizationCountry(id=5, organization_id=836, country_slug="jemen", relation="operates_in", note="old")
    session = _session_with_existing(existing)
    country, created = add_country(session, 836, "jemen", "operates_in", "new")
    assert created is False and country["id"] == 5 and existing.note == "new"
    session.add.assert_not_called()


def test_add_country_keeps_note_when_none_given():
    existing = OrganizationCountry(id=5, organization_id=836, country_slug="jemen", relation="operates_in", note="keep")
    add_country(_session_with_existing(existing), 836, "jemen", "operates_in")
    assert existing.note == "keep"


@pytest.mark.parametrize("slug,relation", [("atlantyda", "operates_in"), ("", "operates_in"),
                                           (None, "operates_in"), ("jemen", "owns")])
def test_add_country_rejects_unknown_slug_or_relation(slug, relation):
    session = _session_with_existing(None)
    with pytest.raises(ValueError):
        add_country(session, 836, slug, relation)
    session.add.assert_not_called()


def test_remove_country_only_for_own_organization():
    session = MagicMock()
    session.get.return_value = OrganizationCountry(id=5, organization_id=999, country_slug="jemen", relation="linked_to")
    assert remove_country(session, 836, 5) is False
    session.delete.assert_not_called()

    row = OrganizationCountry(id=5, organization_id=836, country_slug="jemen", relation="linked_to")
    session.get.return_value = row
    assert remove_country(session, 836, 5) is True
    session.delete.assert_called_once_with(row)

    session.get.return_value = None
    assert remove_country(session, 836, 6) is False


def test_country_suggestions_count_documents_and_skip_attached():
    session = MagicMock()
    docs_tags = ["kraj-jemen,kraj-jemen,polityka", "kraj-jemen,kraj-zjednoczone-emiraty-arabskie", None,
                 "kraj-polska,kraj-nieistniejacy"]
    attached = ["polska"]
    session.execute.return_value.scalars.return_value.all.side_effect = [docs_tags, attached]

    assert country_suggestions(session, 836) == [
        {"country_slug": "jemen", "name_pl": "Jemen", "documents": 2},
        {"country_slug": "zjednoczone-emiraty-arabskie", "name_pl": "Zjednoczone Emiraty Arabskie", "documents": 1},
    ]


def test_absorb_organization_moves_countries_and_fills_empty_fields():
    source = Organization(id=1, canonical_name="Src", headquarters_address="Aden", latitude=12.8, longitude=45.0,
                          website="https://src.example", obsidian_note_path="n/src.md")
    target = Organization(id=2, canonical_name="Dst", website="https://dst.example")
    moved = OrganizationCountry(id=10, organization_id=1, country_slug="jemen", relation="operates_in")
    dup = OrganizationCountry(id=11, organization_id=1, country_slug="polska", relation="based_in")
    on_target = [MagicMock(country_slug="polska", relation="based_in")]
    session = MagicMock()
    session.execute.return_value.scalars.side_effect = [iter(on_target), MagicMock(all=lambda: [moved, dup])]

    absorb_organization(session, source, target)

    assert moved.organization_id == 2
    session.delete.assert_called_once_with(dup)
    assert target.headquarters_address == "Aden" and float(target.latitude) == 12.8
    assert target.website == "https://dst.example"  # target's own value wins
    assert target.obsidian_note_path == "n/src.md"


def test_absorb_organization_keeps_target_headquarters():
    source = Organization(id=1, canonical_name="Src", headquarters_address="Aden", latitude=12.8, longitude=45.0)
    target = Organization(id=2, canonical_name="Dst", headquarters_address="Warszawa")
    session = MagicMock()
    session.execute.return_value.scalars.side_effect = [iter([]), MagicMock(all=lambda: [])]
    absorb_organization(session, source, target)
    assert target.headquarters_address == "Warszawa" and target.latitude is None
