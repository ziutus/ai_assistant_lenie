"""Offline import contracts against a real, isolated SQLite transaction."""

from copy import deepcopy
from unittest.mock import Mock

import pytest
from flask import Flask
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from library import company_registry_import as service
from library import company_registry_routes as routes
from library import organization_identifiers as identifiers
from library.db.models import Organization, OrganizationAlias, OrganizationIdentifier
from library.organization_registry import add_alias

NIP, KRS, REGON = "5260250995", "0000000123", "012345675"
LEGAL = "ŻÓŁW SPÓŁKA Z OGRANICZONĄ ODPOWIEDZIALNOŚCIĄ"


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("""CREATE TABLE organizations (
            id INTEGER PRIMARY KEY, uuid TEXT, canonical_name TEXT, organization_type TEXT,
            description TEXT, headquarters_address TEXT, latitude NUMERIC, longitude NUMERIC,
            website TEXT, wikipedia_url TEXT, links JSON, obsidian_note_path TEXT,
            primary_note_document_id INTEGER, created_at DATETIME, updated_at DATETIME)"""))
        connection.execute(text("INSERT INTO organizations (id, canonical_name) VALUES (1, 'Żółw'), (2, 'Inna')"))
    OrganizationIdentifier.__table__.create(engine)
    OrganizationAlias.__table__.create(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


@pytest.fixture
def result():
    record = {"name": LEGAL, "nip": NIP, "krs": KRS, "regon": REGON}
    return {"query": {"nip": NIP, "krs": None}, "vat": {"subject": dict(record)},
            "krs": dict(record), "crbr": {"filings": []}, "ceidg": {},
            "source_urls": {"vat": "https://example.org/vat", "krs": "https://example.org/krs"}}


@pytest.fixture
def client(session, result, monkeypatch):
    monkeypatch.setattr(routes, "get_scoped_session", lambda: session)
    monkeypatch.setattr(routes, "check_company", Mock(side_effect=lambda **kw: deepcopy(result)))
    app = Flask(__name__)
    app.register_blueprint(routes.company_registry_bp)
    return app.test_client()


def post(client, **extra):
    return client.post("/company_registry/organizations", json={"nip": NIP, **extra})


def test_read_only_match_and_unchanged_plain_response(client, session, result):
    assert client.get(f"/company_registry/check?nip={NIP}").json == result
    match = client.get(f"/company_registry/check?nip={NIP}&match=1").json["lenie_match"]
    assert match["suggested_name"] == "Żółw"
    assert match["registry_name"] == LEGAL
    assert [c["id"] for c in match["name_candidates"]] == [1]
    assert len(match["identifiers"]) == 3
    assert match["identifiers"][0]["source_url"] == "https://example.org/vat"
    assert not session.scalars(select(OrganizationIdentifier)).all()


def test_alias_candidate_and_owner_exclusion(session, result):
    session.get(Organization, 1).canonical_name = "Marka"
    add_alias(session, session.get(Organization, 1), "Żółw S.A.")
    assert service.match_company(session, result)["name_candidates"][0]["id"] == 1
    identifiers.add_identifier(session, 1, {"country_code": "PL", "identifier_type": "nip", "value": NIP})
    match = service.match_company(session, result)
    assert match["name_candidates"] == []
    assert match["owners"][0]["identifiers"][0]["value"] == NIP


def test_create_and_attach_are_minimal_and_idempotent(client, session):
    response = post(client, canonical_name="  Nowa marka  ", identifiers=[{"value": "evil"}], registry_name="evil")
    assert response.status_code == 201
    org_id = response.json["organization"]["id"]
    org = session.get(Organization, org_id)
    assert org.canonical_name == "Nowa marka" and org.organization_type == "firma"
    assert org.description is None and org.headquarters_address is None
    assert {a.alias for a in org.aliases} == {"Nowa marka", LEGAL}
    assert {n["note"] for n in response.json["identifiers"]} == {"Dodane z rejestru"}
    assert post(client, organization_id=org_id).status_code == 200
    assert len(identifiers.list_identifiers(session, org_id)) == 3
    assert routes.check_company.call_count == 2


@pytest.mark.parametrize("name", [" ŻÓŁW ", "Zajęty alias"])
def test_name_conflict(client, session, name):
    add_alias(session, session.get(Organization, 1), "Zajęty alias")
    session.commit()
    response = post(client, canonical_name=name)
    assert response.status_code == 409
    assert response.json["conflict_organization"]["id"] == 1
    assert len(session.scalars(select(Organization)).all()) == 2


def test_number_conflict_writes_nothing(client, session):
    identifiers.add_identifier(session, 2, {"country_code": "PL", "identifier_type": "regon", "value": REGON})
    session.commit()
    response = post(client, canonical_name="Nowa")
    assert response.status_code == 409 and response.json["conflict_organization"]["id"] == 2
    assert len(session.scalars(select(Organization)).all()) == 2
    assert len(session.scalars(select(OrganizationIdentifier)).all()) == 1


def test_existing_other_number_and_unknown_target(client, session):
    identifiers.add_identifier(session, 1, {"country_code": "PL", "identifier_type": "krs", "value": "999"})
    session.commit()
    assert post(client, organization_id=1).status_code == 409
    assert len(identifiers.list_identifiers(session, 1)) == 1
    assert post(client, organization_id=999).status_code == 404


def test_disagreeing_numbers(client, session, result):
    result["krs"]["regon"] = "123456785"
    match = service.match_company(session, result)
    assert match["disagreeing"] == ["regon"]
    assert {n["identifier_type"] for n in match["identifiers"]} == {"nip", "krs"}
    result["krs"]["nip"] = "7011301944"
    assert post(client, organization_id=1).status_code == 409
    assert identifiers.list_identifiers(session, 1) == []


def test_query_owner_even_when_sources_disagree(client, session, result):
    identifiers.add_identifier(session, 1, {"country_code": "PL", "identifier_type": "nip", "value": NIP})
    result["krs"]["nip"] = "7011301944"
    assert service.match_company(session, result)["owners"][0]["id"] == 1


def test_sole_proprietor_requires_boolean_and_ceidg_fallback(client, result):
    result.update(vat={}, krs={}, ceidg={"company": {"name": "Jan Żółw Usługi"}})
    for confirmation in (None, False, "true"):
        assert post(client, canonical_name="Usługi", confirm_sole_proprietor=confirmation).status_code == 400
    response = post(client, canonical_name="Usługi", confirm_sole_proprietor=True)
    assert response.status_code == 201
    assert response.json["identifiers"][0]["value"] == NIP


def test_alias_conflict_warns_without_overwriting(client, session):
    add_alias(session, session.get(Organization, 2), LEGAL)
    session.commit()
    response = post(client, organization_id=1)
    assert response.status_code == 200 and response.json["warnings"]
    assert session.scalar(select(OrganizationAlias)).organization_id == 2


def test_rollback_after_partial_write_and_fixed_error(client, session, monkeypatch):
    original = identifiers.add_identifier

    def fail(session, org_id, number):
        if number["identifier_type"] == "krs":
            raise RuntimeError("SECRET database password")
        return original(session, org_id, number)

    monkeypatch.setattr(identifiers, "add_identifier", fail)
    response = post(client, canonical_name="Nowa")
    assert response.status_code == 500 and "SECRET" not in response.text
    assert len(session.scalars(select(Organization)).all()) == 2
    assert not session.scalars(select(OrganizationIdentifier)).all()
    assert not session.scalars(select(OrganizationAlias)).all()


def test_unknown_and_input_validation(client, result):
    for body in ([], {}, {"nip": NIP, "krs": KRS}):
        assert client.post("/company_registry/organizations", json=body).status_code == 400
    for name in (None, " ", "a" * 201, 3):
        assert post(client, canonical_name=name).status_code == 400
    result.update(vat={}, krs={}, ceidg={})
    assert post(client, canonical_name="Unknown").status_code == 400
    assert client.post("/company_registry/organizations", data={"nip": NIP}).status_code == 400


@pytest.mark.parametrize("name,expected", [(LEGAL, "Żółw"), ("INVICTI SP. Z O.O.", "Invicti"),
                                         ("ŁĄKA S.A.", "Łąka"), ("iFirma", "iFirma")])
def test_readable_suggestion(name, expected):
    assert service.suggested_name(name) == expected
