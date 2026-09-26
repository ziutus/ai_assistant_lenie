"""Pure address formatting/backfill and import preservation contracts."""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from library.address_formatting import (
    ADDRESS_FIELD_LIMITS, addresses_match, format_address, imported_address_fields, parse_address_text_heuristic,
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
    assert format_address(SimpleNamespace(**fields, notes="Domofon: 5869; wejście od podwórza")) == expected
    assert format_address(SimpleNamespace(**fields, block_number=None)).encode("utf-8") == expected.encode("utf-8")


@pytest.mark.parametrize("fields, expected", [
    (dict(street="Bratysławska", building_number="15", block_number="31", apartment_number="26",
          postal_code="90-001", city="Łódź"), "Bratysławska 15 blok 31/26, 90-001 Łódź"),
    (dict(street="Bratysławska", building_number="15", block_number=" 31A-32 ", city="Łódź"),
     "Bratysławska 15 blok 31A-32, Łódź"),
    (dict(block_number="31", apartment_number="26", city="Łódź"), "blok 31/26, Łódź"),
    (dict(building_number="15", block_number="   ", city="Łódź"), "15, Łódź"),
])
def test_format_address_with_block(fields, expected):
    assert format_address(SimpleNamespace(**fields)) == expected


def test_bielik_block_number_passes_through(monkeypatch):
    import json
    from library.address_parsing import parse_address_text
    fields = {**dict.fromkeys((*ADDRESS_FIELD_LIMITS, "notes")), "street": "Bratysławska",
              "building_number": "15", "block_number": "31", "apartment_number": "26", "city": "Łódź"}
    ask = MagicMock(return_value=SimpleNamespace(response_text=json.dumps(fields)))
    monkeypatch.setattr("library.address_parsing.load_config", lambda: {})
    monkeypatch.setattr("library.address_parsing.ai_ask", ask)
    assert parse_address_text("Bratysławska 15 m 26 blok 31, Łódź") == fields
    schema = ask.call_args.kwargs["response_format"]["json_schema"]["schema"]
    assert set(schema["properties"]) == set(schema["required"]) == set(fields)
    assert len(schema["required"]) == 8


@pytest.mark.parametrize("notes", [" Domofon: 5869 ", "x" * 1000, None, "   "])
def test_bielik_notes_pass_through(monkeypatch, notes):
    import json
    from library.address_parsing import parse_address_text
    fields = {**dict.fromkeys(ADDRESS_FIELD_LIMITS), "city": "Łódź", "notes": notes}
    monkeypatch.setattr("library.address_parsing.load_config", lambda: {})
    monkeypatch.setattr("library.address_parsing.ai_ask", MagicMock(
        return_value=SimpleNamespace(response_text=json.dumps(fields))))
    assert parse_address_text("Łódź, Domofon: 5869") == {
        **fields, "notes": (notes or "").strip() or None,
    }


@pytest.mark.parametrize("field, value", [
    ("notes", "x" * 1001), ("notes", 42), ("street", "x" * 201),
    ("block_number", "x" * 21), ("block_number", 31),
])
def test_bielik_invalid_field_discards_entire_result(monkeypatch, field, value):
    import json
    from library.address_parsing import parse_address_text
    empty = dict.fromkeys((*ADDRESS_FIELD_LIMITS, "notes"))
    fields = {**empty, "city": "Łódź", field: value}
    monkeypatch.setattr("library.address_parsing.load_config", lambda: {})
    monkeypatch.setattr("library.address_parsing.ai_ask", MagicMock(
        return_value=SimpleNamespace(response_text=json.dumps(fields))))
    assert parse_address_text("test") == empty


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


def _addr(**fields):
    return SimpleNamespace(**{**dict.fromkeys(ADDRESS_FIELD_LIMITS), **fields})


LEGACY_ONE_LINE = _addr(city="Czeremchy 5\n95-073 Tkaczewska Góra\nPL")
STRUCTURED = _addr(street="Czeremchy", building_number="5", postal_code="95-073", city="Tkaczewska Góra", country="PL")


def test_legacy_one_field_address_matches_its_structured_twin():
    assert addresses_match(LEGACY_ONE_LINE, STRUCTURED)
    assert addresses_match(STRUCTURED, LEGACY_ONE_LINE)


@pytest.mark.parametrize("other", [
    _addr(street="olsztyńska", building_number="16", city="ŁÓDŹ", country="Polska"),
    _addr(street="Olsztynska", building_number="16", postal_code="90-001", city="Łódź", country=None),
])
def test_case_accents_country_alias_and_missing_postal_are_ignored(other):
    base = _addr(street="Olsztyńska", building_number="16", city="Łódź", country="Polska")
    assert addresses_match(base, other)


@pytest.mark.parametrize("other", [
    _addr(street="Olsztyńska", building_number="17", city="Łódź"),
    _addr(street="Olsztyńska", building_number="16", apartment_number="3", city="Łódź"),
    _addr(street="Olsztyńska", building_number="16", postal_code="90-001", city="Łódź"),
    _addr(street="Olsztyńska", building_number="16", city="Łódź", country="Niemcy"),
    _addr(street="Olsztyńska", building_number="16", city="Kraków"),
])
def test_different_places_do_not_match(other):
    base = _addr(street="Olsztyńska", building_number="16", postal_code="91-001", city="Łódź")
    assert not addresses_match(base, other)


def test_unparsable_free_text_matches_nothing_else():
    assert not addresses_match(_addr(city="gdzieś nad morzem"), _addr(city="Łódź"))
    assert addresses_match(_addr(city="gdzieś nad morzem"), _addr(city="Gdzies nad morzem"))
