"""Registry-number contract, persistence and lifecycle using an in-memory database only."""

from unittest.mock import MagicMock

import pytest
from flask import Flask
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from library import organization_identifier_routes as routes
from library import organization_identifiers as service
from library.db.models import Organization, OrganizationIdentifier
from library.organization_location import absorb_organization
from library.organization_registry import _delete_organization_if_orphaned


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    # Only the organization columns used here; production migrations are never run.
    with engine.begin() as connection:
        connection.execute(text("""CREATE TABLE organizations (
            id INTEGER PRIMARY KEY, uuid TEXT, canonical_name TEXT, organization_type TEXT,
            description TEXT, headquarters_address TEXT, latitude NUMERIC, longitude NUMERIC,
            website TEXT, wikipedia_url TEXT, links JSON, obsidian_note_path TEXT,
            primary_note_document_id INTEGER, created_at DATETIME, updated_at DATETIME)"""))
        connection.execute(text("INSERT INTO organizations (id, canonical_name, links) VALUES (1, 'One', '[]'), (2, 'Two', '[]')"))
    OrganizationIdentifier.__table__.create(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


@pytest.mark.parametrize("country,kind,value,expected", [
    ("pl", "NIP", "PL 526-025-09-95", "5260250995"),
    ("PL", "krs", "123", "0000000123"),
    ("PL", "regon", "012345675", "012345675"),
    ("PL", "regon", "01234567500008", "01234567500008"),
    ("MT", "company_number", " c   123 ", "C 123"),
    ("XX", "lei", " abc ", "ABC"),
])
def test_normalize(country, kind, value, expected):
    assert service.normalize_identifier(country, kind, value) == (country.upper(), kind.lower(), expected)


@pytest.mark.parametrize("data", [
    ("PL", "nip", "1234567890"), ("PL", "regon", "012345679"), ("PL", "regon", "01234567800009"),
    ("PL", "regon", "123"), ("PL", "pesel", "12345678901"), ("MT", "PESEL", "x"),
    ("ZZ", "custom", "x"), ("PL", "bad type", "x"), ("PL", "a" * 31, "x"),
    ("XX", "lei", ""), ("XX", "lei", "a" * 101), (None, "nip", "1"),
])
def test_invalid(data):
    with pytest.raises(ValueError):
        service.normalize_identifier(*data)


def test_crud_and_conflict(session, monkeypatch):
    monkeypatch.setattr(routes, "get_scoped_session", lambda: session)
    app = Flask(__name__)
    app.register_blueprint(routes.organization_identifiers_bp)
    browser = app.test_client()
    path = "/organizations/1/identifiers"
    data = {"country_code": "PL", "identifier_type": "nip", "value": "5260250995"}
    response = browser.post(path, json=data)
    assert response.status_code == 201
    row = response.json["identifier"]
    assert browser.post(path, json=data).status_code == 200
    response = browser.post("/organizations/2/identifiers", json=data)
    assert response.status_code == 409
    assert response.json["conflict_organization"] == {"id": 1, "canonical_name": "One"}
    assert browser.get(path).json["identifiers"] == [row]
    assert browser.delete(f"/organizations/2/identifiers/{row['id']}").status_code == 404
    assert browser.delete(f"{path}/{row['id']}").status_code == 200
    assert browser.delete(f"{path}/{row['id']}").status_code == 404
    assert browser.get("/organizations/99/identifiers").status_code == 404
    assert browser.post(path, json=[]).status_code == 400
    assert browser.options(path).status_code == 200


@pytest.mark.parametrize("url", ["file:///secret", "javascript:alert(1)", "https://", "https://user:secret@example.com"])
def test_source_url(session, url):
    with pytest.raises(ValueError):
        service.add_identifier(session, 1, dict(country_code="PL", identifier_type="krs", value="1", source_url=url))


def test_merge_moves_relationship_and_orphan_guard(session):
    service.add_identifier(session, 1, dict(country_code="PL", identifier_type="krs", value="1"))
    service.add_identifier(session, 2, dict(country_code="PL", identifier_type="krs", value="2"))
    source, target = session.get(Organization, 1), session.get(Organization, 2)
    mock = MagicMock()
    mock.execute.return_value.scalar.return_value = 0
    mock.get.return_value = source
    assert _delete_organization_if_orphaned(mock, 1) is False
    mock.delete.assert_not_called()
    absorb_organization(mock, source, target)
    session.flush()
    session.expire_all()
    assert service.list_identifiers(session, 1) == []
    assert {row["value"] for row in service.list_identifiers(session, 2)} == {"0000000001", "0000000002"}
    assert _delete_organization_if_orphaned(mock, 1) is True


def test_migration_head_and_model():
    from pathlib import Path
    from alembic.script import ScriptDirectory
    from sqlalchemy import UniqueConstraint
    script = ScriptDirectory(str(Path(__file__).parents[2] / "alembic"))
    assert script.get_heads() == ["d91f7a6b203e"]
    assert script.get_revision("c82e6f904ab1").down_revision == "a7d3c5e9b214"
    table = OrganizationIdentifier.__table__
    assert table.c.organization_id.index
    assert next(iter(table.c.organization_id.foreign_keys)).ondelete == "CASCADE"
    assert any(isinstance(c, UniqueConstraint) and set(c.columns.keys()) == {"country_code", "identifier_type", "value"}
               for c in table.constraints)
