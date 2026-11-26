"""Offline company evidence, resolution and lifecycle contracts."""

from copy import deepcopy
from datetime import date

import pytest
from flask import Flask
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from library import organization_relation_routes as routes
from library import organization_relations as service
from library.company_registry_client import parse_krs
from library.db.models import Organization, OrganizationAlias, OrganizationIdentifier, OrganizationRelation


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("PRAGMA foreign_keys=ON"))
        connection.execute(text("CREATE TABLE persons (id INTEGER PRIMARY KEY)"))
        connection.execute(text("""CREATE TABLE organizations (
            id INTEGER PRIMARY KEY, uuid TEXT, canonical_name TEXT, organization_type TEXT,
            description TEXT, headquarters_address TEXT, latitude NUMERIC, longitude NUMERIC,
            website TEXT, wikipedia_url TEXT, links JSON, obsidian_note_path TEXT,
            primary_note_document_id INTEGER, created_at DATETIME, updated_at DATETIME)"""))
        connection.execute(text("INSERT INTO organizations (id, canonical_name) VALUES (1, 'One'), (2, 'Two'), (3, 'Three')"))
    for model in (OrganizationAlias, OrganizationIdentifier, OrganizationRelation):
        model.__table__.create(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def result(start=None, end=None):
    return {"checked_at": "2026-11-20T10:00:00+00:00", "krs": {"status": "ok", "name": "One",
            "current_shareholders": [{"name": "Two S.A.", "krs": "2", "is_company": True,
                                      "shares": "10 udziałów", "added_at": start, "removed_at": end},
                                     {"name": "Natural Person", "is_company": False}],
            "source_url": "https://example.org/krs"}}


def record(session, data=None, org=1):
    return service.record_company_shareholders(session, session.get(Organization, org), data or result())


def test_evidence_guard_and_idempotency(session):
    org = session.get(Organization, 1)
    assert service.record_company_shareholders(session, org, result(), {"other"})["message"]
    assert service.record_company_shareholders(session, org, {"krs": {"status": "error"}})["added"] == 0
    assert record(session)["added"] == 1
    assert record(session)["added"] == 0
    rows = session.scalars(select(OrganizationRelation)).all()
    assert len(rows) == 1 and rows[0].subject_krs == "0000000002"
    assert rows[0].person_id is None
    duplicate = OrganizationRelation(organization_id=1, subject_name="Two", subject_key="0000000002",
                                     role="shareholder", source="krs")
    with pytest.raises(IntegrityError), session.begin_nested():
        session.add(duplicate)
        session.flush()


def test_history_and_manual_decisions_survive_new_checks(session):
    record(session, result("2020-01-01"))
    row = session.scalar(select(OrganizationRelation))
    row.related_organization_id, row.link_rejected = 3, True
    newer = result("2020-01-01", "2022-01-01")
    newer["checked_at"] = "2026-11-21T10:00:00+00:00"
    record(session, newer)
    record(session, result("2024-01-01"))
    record(session, result("2020-01-01"))  # Older response cannot reopen the closed tenure.
    assert row.valid_to == date(2022, 1, 1)
    assert row.related_organization_id == 3 and row.link_rejected
    assert len(session.scalars(select(OrganizationRelation)).all()) == 2


def test_read_time_krs_manual_rejection_candidates_and_holdings(session):
    record(session)
    row = session.scalar(select(OrganizationRelation))
    view = service.related_companies(session, 1)["shareholders"][0]
    assert view["organization"] is None and view["name_candidates"] == [{"id": 2, "canonical_name": "Two"}]
    session.add(OrganizationIdentifier(organization_id=2, country_code="PL", identifier_type="krs", value="0000000002"))
    view = service.related_companies(session, 1)["shareholders"][0]
    assert view["link_method"] == "krs" and row.related_organization_id is None
    assert service.related_companies(session, 2)["holdings"][0]["holding_organization"]["id"] == 1
    row.related_organization_id = 3
    assert service.related_companies(session, 3)["holdings"][0]["link_method"] == "manual"
    row.related_organization_id, row.link_rejected = None, True
    assert not service.related_companies(session, 2)["holdings"]
    assert service.related_companies(session, 1)["shareholders"][0]["organization"] is None


def test_routes_headers_holdings_scope_and_fixed_errors(session, monkeypatch):
    record(session)
    row = session.scalar(select(OrganizationRelation))
    row.related_organization_id = 2
    monkeypatch.setattr(routes, "get_scoped_session", lambda: session)
    app = Flask(__name__)
    app.register_blueprint(routes.organization_relations_bp)
    client = app.test_client()
    path = f"/organizations/2/relations/{row.id}"
    assert client.options(path).status_code == 200
    assert client.get("/organizations/1/related_companies").json["shareholders"]
    assert client.patch(path.replace('/2/', '/3/'), json={"related_organization_id": None}).status_code == 404
    assert client.patch(path, json={"related_organization_id": 1}).status_code == 400
    assert client.patch(path, json={"related_organization_id": 999}).status_code == 404
    assert client.patch(path, json={"related_organization_id": True}).status_code == 400
    assert client.patch(path, data='{"related_organization_id":null}',
                        content_type="application/x-www-form-urlencoded").status_code == 400
    response = client.patch(path, data='{"related_organization_id":null}', content_type="application/json")
    assert response.status_code == 200 and response.json["holdings"] == []
    assert row.link_rejected
    assert client.patch(f"/organizations/1/relations/{row.id}", json={"related_organization_id": 3}).status_code == 200
    assert row.related_organization_id == 3 and not row.link_rejected
    monkeypatch.setattr(routes, "related_companies", lambda *a: (_ for _ in ()).throw(RuntimeError("secret")))
    response = client.get("/organizations/1/related_companies")
    assert response.status_code == 500 and "secret" not in response.text


def test_merge_collisions_inbound_links_and_self_relations(session):
    record(session, org=1)
    record(session, org=2)
    target = session.scalar(select(OrganizationRelation).where(OrganizationRelation.organization_id == 2))
    target.link_rejected = True
    inbound = OrganizationRelation(organization_id=3, related_organization_id=1, subject_name="One",
                                   subject_key="one", role="shareholder", source="krs")
    self_link = OrganizationRelation(organization_id=1, related_organization_id=2, subject_name="Self",
                                     subject_key="self", role="shareholder", source="krs")
    session.add_all([inbound, self_link])
    session.flush()
    service.absorb_relations(session, 1, 2)
    rows = session.scalars(select(OrganizationRelation)).all()
    assert len(rows) == 2 and target in rows and target.link_rejected
    assert inbound.related_organization_id == 2
    # Database actions keep incoming evidence and remove owned evidence on deletion.
    session.execute(text("DELETE FROM organizations WHERE id=2"))
    session.expire_all()
    assert session.get(OrganizationRelation, inbound.id).related_organization_id is None
    assert len(session.scalars(select(OrganizationRelation)).all()) == 1


@pytest.mark.parametrize("number", ["0000000002", [{"krs": "0000000002", "nrWpisuWprow": 1}]])
def test_parser_tenures_and_krs_history(number):
    payload = {"odpis": {"naglowekP": {"wpis": [
        {"numerWpisu": n, "dataWpisu": f"01.01.202{n}"} for n in range(1, 5)]}, "dane": {"dzial1": {
            "wspolnicySpzoo": [{"nazwa": [
                {"nazwa": "Two", "nrWpisuWprow": 1, "nrWpisuWykr": 2},
                {"nazwa": "Two", "nrWpisuWprow": 3}], "krs": number}]}}}}
    parsed = parse_krs(deepcopy(payload))
    assert parsed["current_shareholders"][0]["added_at"] == "2023-01-01"
    assert parsed["former_shareholders"][0]["removed_at"] == "2022-01-01"
    assert all(r["krs"] == "0000000002" for r in parsed["current_shareholders"] + parsed["former_shareholders"])


def test_sync_and_import_store_company_evidence(session, monkeypatch):
    from library import company_registry_import, organization_identifier_sync

    data = result()
    data["query"] = {"organization_id": 1, "krs": "0000000001"}
    data["krs"]["krs"] = "0000000001"
    monkeypatch.setattr(organization_identifier_sync, "check_company", lambda **kwargs: deepcopy(data))
    monkeypatch.setattr(organization_identifier_sync, "apply_seat", lambda *args: {})
    monkeypatch.setattr(company_registry_import, "apply_seat", lambda *args: {})
    assert organization_identifier_sync.check_and_store(session, 1)["relations"]["added"] == 1
    # Explicit import can attach registry evidence despite a different organization name.
    imported = company_registry_import.store_company(session, data, {"organization_id": 3})
    assert imported["relations"]["added"] == 1
    assert session.scalar(select(OrganizationRelation).where(OrganizationRelation.organization_id == 3))


def test_migration_upgrade_and_downgrade_in_memory_only():
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from alembic.script import ScriptDirectory
    from sqlalchemy import inspect

    script = ScriptDirectory("alembic")
    revision = script.get_revision("d91f7a6b203e")
    assert script.get_heads() == [revision.revision]
    assert revision.down_revision == "c82e6f904ab1"
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            revision.module.upgrade()
            indexes = inspect(connection).get_indexes("organization_relations")
            assert len(indexes) == 5 and sum(index["unique"] for index in indexes) == 2
            revision.module.downgrade()
            assert "organization_relations" not in inspect(connection).get_table_names()
    engine.dispose()
