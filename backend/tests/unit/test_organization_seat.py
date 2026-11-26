"""Seat from an official register: only solid evidence, never overwriting."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from library import organization_seat as seat
from library.company_registry_client import parse_krs
from library.country_gazetteer import slug_to_name

ADDRESS = {"street": "UL. FILTROWA", "house": "63", "flat": "43", "postal_code": "02-056", "city": "WARSZAWA",
           "country": "POLSKA"}


def result(**krs):
    return {"krs": {"status": "ok", "name": "ACME SPÓŁKA Z OGRANICZONĄ ODPOWIEDZIALNOŚCIĄ",
                    "legal_form": "SPÓŁKA Z OGRANICZONĄ ODPOWIEDZIALNOŚCIĄ", "address": ADDRESS, **krs}}


def organization(**fields):
    return SimpleNamespace(id=7, **{"headquarters_address": None, "latitude": None, "longitude": None, **fields})


@pytest.fixture
def registry(monkeypatch):
    mocks = SimpleNamespace(countries=[], add=MagicMock(return_value=({}, True)), geocode=MagicMock())
    monkeypatch.setattr(seat, "list_countries", lambda session, org_id: mocks.countries)
    monkeypatch.setattr(seat, "add_country", mocks.add)
    monkeypatch.setattr(seat, "geocode_headquarters", mocks.geocode)
    return mocks


def test_poland_is_a_known_country():
    assert slug_to_name(seat.POLAND)


def test_krs_company_gets_country_and_address(registry):
    org = organization()
    outcome = seat.apply_seat(MagicMock(), org, result(), {"acme"})
    assert outcome == {"country_added": True, "address_added": "ul. Filtrowa 63/43, 02-056 Warszawa", "message": None}
    assert org.headquarters_address == "ul. Filtrowa 63/43, 02-056 Warszawa"
    assert registry.add.call_args.args[1:] == (7, "polska", "based_in", "Z rejestru KRS")
    registry.geocode.assert_called_once()


def test_geocoder_failure_keeps_the_address(registry):
    registry.geocode.side_effect = RuntimeError("down")
    org = organization()
    assert seat.apply_seat(MagicMock(), org, result())["address_added"] == org.headquarters_address


def test_existing_data_is_not_overwritten(registry):
    org = organization(headquarters_address="Inny adres")
    registry.countries = [{"country_slug": "polska", "relation": "based_in"}]
    outcome = seat.apply_seat(MagicMock(), org, result())
    assert outcome["country_added"] is False and outcome["address_added"] is None
    assert org.headquarters_address == "Inny adres"
    registry.add.assert_not_called()


def test_another_seat_country_changes_nothing(registry):
    registry.countries = [{"country_slug": "malta", "relation": "based_in"}]
    org = organization()
    assert "innym kraju" in seat.apply_seat(MagicMock(), org, result())["message"]
    assert org.headquarters_address is None
    registry.add.assert_not_called()


@pytest.mark.parametrize("data,fragment", [
    (result(legal_form="ODDZIAŁ ZAGRANICZNEGO PRZEDSIĘBIORCY"), "zagraniczny"),
    (result(address={**ADDRESS, "country": "MALTA"}), "zagraniczny"),
    (result(name="INNA FIRMA S.A."), "nie pasuje"),
    ({"vat": {"status": "ok"}, "krs": {"status": "skipped"}}, "Sam NIP"),
])
def test_weak_evidence_changes_nothing(registry, data, fragment):
    outcome = seat.apply_seat(MagicMock(), organization(), data, {"acme"})
    assert fragment in outcome["message"]
    registry.add.assert_not_called()


def test_sole_proprietor_gets_the_country_but_no_address(registry):
    org = organization()
    data = {"krs": {"status": "skipped"}, "ceidg": {"status": "ok", "company": {"name": "Jan Test"}}}
    outcome = seat.apply_seat(MagicMock(), org, data)
    assert outcome["country_added"] is True and outcome["address_added"] is None
    assert org.headquarters_address is None


def test_no_answer_is_silent(registry):
    assert seat.apply_seat(MagicMock(), organization(), {})["message"] is None


@pytest.mark.parametrize("address,expected", [
    ({"city": "KOWALE", "house": "12", "postal_code": "80-180"}, "Kowale 12, 80-180 Kowale"),
    ({"city": "GDAŃSK"}, "Gdańsk"),
    ({"street": "UL. X"}, None),
])
def test_format_address(address, expected):
    assert seat.format_address(address) == expected


def test_parser_reads_current_legal_form_and_address():
    payload = {"odpis": {"dane": {"dzial1": {
        "danePodmiotu": {"formaPrawna": [{"formaPrawna": "SPÓŁKA AKCYJNA", "nrWpisuWprow": "1"}]},
        "siedzibaIAdres": {"adres": [
            {"ulica": "UL. STARA", "miejscowosc": "ŁÓDŹ", "nrWpisuWprow": "1", "nrWpisuWykr": "3"},
            {"ulica": "UL. NOWA", "nrDomu": "1", "miejscowosc": "ŁÓDŹ", "kraj": "POLSKA", "nrWpisuWprow": "3"},
        ]}}}}}
    parsed = parse_krs(payload)
    assert parsed["legal_form"] == "SPÓŁKA AKCYJNA"
    assert parsed["address"]["street"] == "UL. NOWA" and parsed["address"]["house"] == "1"
