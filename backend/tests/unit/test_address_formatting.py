"""Pure address formatting/backfill and import preservation contracts."""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from library.address_formatting import (
    ADDRESS_FIELD_LIMITS, format_address, imported_address_fields, parse_address_text_heuristic,
)


@pytest.mark.parametrize("fields, expected", [
    ({"street": "Piękna", "building_number": "15", "postal_code": "95-054", "city": "Ksawerów"},
     "Piękna 15, 95-054 Ksawerów"),
    ({"building_number": "32", "postal_code": "08-207", "city": "Wyczółki", "country": "Polska"},
     "32, 08-207 Wyczółki"),
    ({"street": " Piękna ", "building_number": "15A", "apartment_number": "3", "city": "Łódź"},
     "Piękna 15A/3, Łódź"),
    ({"street": "Hauptstraße", "building_number": "15/17", "city": "Berlin", "country": "Niemcy"},
     "Hauptstraße 15/17, Berlin, Niemcy"),
    ({"city": "tekst\nbez   struktury"}, "tekst bez struktury"),
])
def test_format_address(fields, expected):
    assert format_address(SimpleNamespace(**fields)) == expected


@pytest.mark.parametrize("text, expected", [
    ("ul. Piękna 15/3, 95-054 Ksawerów, Polska",
     dict(street="Piękna", building_number="15", apartment_number="3", postal_code="95-054", city="Ksawerów", country="Polska")),
    ("Piękna 15A, 95-054 Ksawerów", dict(street="Piękna", building_number="15A", postal_code="95-054", city="Ksawerów")),
    ("Wyczółki 32, 08-207 Wyczółki", dict(building_number="32", postal_code="08-207", city="Wyczółki")),
    ("Wyczółki 32", dict(building_number="32", city="Wyczółki")),
    ("32, 08-207 Wyczółki", dict(building_number="32", postal_code="08-207", city="Wyczółki")),
    ("15 Piękna, 95-054 Ksawerów", dict(street="Piękna", building_number="15", postal_code="95-054", city="Ksawerów")),
    ("al. Róż 15A m. 3, 00-001 Warszawa", dict(street="Róż", building_number="15A", apartment_number="3", postal_code="00-001", city="Warszawa")),
])
def test_heuristic(text, expected):
    assert parse_address_text_heuristic(text) == {**dict.fromkeys(ADDRESS_FIELD_LIMITS), **expected}


@pytest.mark.parametrize("text", [
    " gdzieś za stodołą / telefon do sąsiada ??? ",
    "ul. Piękna 15, 95-054 Ksawerów, wejście od podwórza",
    "ul. Piękna 15",
])
def test_unparsed_or_partial_text_is_retained_in_full(text):
    assert parse_address_text_heuristic(text)["city"] is None
    fields = imported_address_fields(text)
    assert fields == {**dict.fromkeys(ADDRESS_FIELD_LIMITS), "city": text}


def test_fallback_does_not_silently_truncate():
    with pytest.raises(ValueError, match="200 characters"):
        imported_address_fields("?" * 201)


def test_import_preserves_fallback_and_does_not_duplicate(monkeypatch):
    from library.contact_addresses import attach_imported_address
    from library.db.models import Contact, ContactAddress
    session = MagicMock()
    links = []
    monkeypatch.setattr("library.contact_addresses.contact_address_links", lambda *_: links)
    contact = Contact(id=1)
    text = "wejście przez zieloną bramę ???"
    assert attach_imported_address(session, contact, text)
    link = session.add.call_args.args[0]
    assert isinstance(link, ContactAddress)
    assert link.address.city == text
    assert link.address.building_number is None
    links.append(link)
    assert not attach_imported_address(session, contact, text)
    assert session.add.call_count == 2
