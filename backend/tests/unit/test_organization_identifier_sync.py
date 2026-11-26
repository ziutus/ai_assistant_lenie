"""Automatic KRS/REGON saving: only when the registers and the organization agree."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from library import organization_identifier_sync as sync
from library import organization_identifiers as identifiers

NIP, KRS, REGON = "5260250995", "0000000123", "012345675"
LEGAL = "ACME SPÓŁKA Z OGRANICZONĄ ODPOWIEDZIALNOŚCIĄ"


def check_result(name=LEGAL, krs_regon=REGON, krs_nip=NIP):
    return {
        "query": {"nip": NIP, "krs": None, "organization_id": 7},
        "vat": {"subject": {"name": name, "nip": NIP, "krs": KRS, "regon": REGON}},
        "krs": {"name": name, "nip": krs_nip, "krs": KRS, "regon": krs_regon},
        "crbr": {"filings": [{"name": name, "nip": NIP, "krs": KRS, "is_current": True}]},
        "suggested_identifiers": [
            {"country_code": "PL", "identifier_type": kind, "value": value, "source_url": "https://example.org"}
            for kind, value in (("krs", KRS), ("regon", REGON))],
    }


def run(monkeypatch, result, stored=(), aliases=(), add=None):
    organization = SimpleNamespace(canonical_name="Acme", aliases=[SimpleNamespace(alias=a) for a in aliases])
    session = MagicMock()
    session.get.return_value = organization
    add = add or MagicMock(side_effect=lambda s, i, data: (data, True))
    monkeypatch.setattr(sync, "check_company", lambda **kw: result)
    monkeypatch.setattr(identifiers, "list_identifiers", lambda s, i: list(stored))
    monkeypatch.setattr(identifiers, "add_identifier", add)
    return sync.check_and_store(session, "7"), add


def reasons(result):
    return {row["identifier_type"]: row["reason"] for row in result["suggested_identifiers"]}


def test_saves_matching_numbers_with_a_note(monkeypatch):
    result, add = run(monkeypatch, check_result())
    assert [row["identifier_type"] for row in result["identifier_sync"]["added"]] == ["krs", "regon"]
    assert result["suggested_identifiers"] == []
    assert add.call_args.args[2]["note"] == "Dodane automatycznie z rejestru"


def test_alias_counts_as_the_organization_name(monkeypatch):
    result, _ = run(monkeypatch, check_result(name="Zupełnie Inna S.A."), aliases=["Zupełnie Inna"])
    assert len(result["identifier_sync"]["added"]) == 2


@pytest.mark.parametrize("name", ["ACME CONSULTING SP. Z O.O.", ""])
def test_other_name_needs_confirmation(monkeypatch, name):
    result, add = run(monkeypatch, check_result(name=name))
    assert reasons(result) == {"krs": "name_mismatch", "regon": "name_mismatch"}
    add.assert_not_called()


def test_disagreeing_registers(monkeypatch):
    result, _ = run(monkeypatch, check_result(krs_regon="123456785"))
    assert reasons(result) == {"regon": "sources_disagree"}
    result, add = run(monkeypatch, check_result(krs_nip="7011301944"))
    assert reasons(result) == {"krs": "sources_disagree", "regon": "sources_disagree"}
    add.assert_not_called()


def test_existing_other_number(monkeypatch):
    stored = [{"country_code": "PL", "identifier_type": "krs", "value": "0000000999"}]
    result, _ = run(monkeypatch, check_result(), stored=stored)
    assert reasons(result) == {"krs": "has_other"}


def test_number_of_another_organization(monkeypatch):
    conflict = identifiers.IdentifierConflict(SimpleNamespace(id=9, canonical_name="Inna"))
    result, _ = run(monkeypatch, check_result(), add=MagicMock(side_effect=conflict))
    assert reasons(result) == {"krs": "owned_by_other", "regon": "owned_by_other"}
    assert result["suggested_identifiers"][0]["conflict_organization"] == {"id": 9, "canonical_name": "Inna"}


def test_nip_is_never_saved_automatically(monkeypatch):
    data = check_result()
    data["suggested_identifiers"] = [{"country_code": "PL", "identifier_type": "nip", "value": NIP}]
    result, add = run(monkeypatch, data)
    assert reasons(result) == {"nip": "manual"}
    add.assert_not_called()
