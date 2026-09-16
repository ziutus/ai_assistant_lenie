"""Contact interests and education REST tests; mocked sessions, no live database."""
import datetime as dt
from unittest.mock import MagicMock

import pytest
from flask import Flask
from library import contact_routes as routes
from library.db.models import Contact, ContactEducation, ContactInterest
from test_contact_routes import _make_contact


@pytest.fixture
def setup(monkeypatch):
    session = MagicMock()
    contact = _make_contact()
    entry = ContactEducation(id=3, contact_id=1, institution="School", degree="master",
                             start_date=dt.date(2010, 1, 1), end_date=dt.date(2015, 1, 1))
    interest = ContactInterest(id=2, name="Music", description="Listening")
    session.get.side_effect = lambda model, key: {
        (Contact, 1): contact, (ContactEducation, 3): entry, (ContactInterest, 2): interest,
    }.get((model, key))
    session.execute.return_value.scalar_one.return_value = 0
    monkeypatch.setattr(routes, "get_scoped_session", lambda: session)
    app = Flask(__name__)
    app.register_blueprint(routes.bp)
    return app.test_client(), session, contact, entry, interest


def test_interest_dictionary_crud(setup):
    client, session, _, _, interest = setup
    session.execute.return_value.scalars.return_value.all.return_value = [interest]
    assert client.get("/contact_interests").json["contact_interests"][0]["name"] == "Music"
    assert client.get("/contact_interests/2").json["contact_interest"]["id"] == 2
    response = client.post("/contact_interests", json={"name": " Hiking ", "description": " Outdoors "})
    assert response.status_code == 200
    assert response.json["contact_interest"]["name"] == "Hiking"
    assert response.json["contact_interest"]["description"] == "Outdoors"
    response = client.patch("/contact_interests/2", json={"name": " Jazz ", "description": None})
    assert response.status_code == 200
    assert interest.name == "Jazz" and interest.description is None
    assert client.delete("/contact_interests/2").status_code == 200
    session.delete.assert_called_once_with(interest)


@pytest.mark.parametrize("method,path,payload,status", [
    ("post", "/contact_interests", {"name": " "}, 400),
    ("patch", "/contact_interests/2", {"name": ""}, 400),
    ("patch", "/contact_interests/99", {}, 404),
    ("get", "/contact_interests/99", None, 404),
    ("delete", "/contact_interests/99", None, 404),
    ("post", "/contacts/99/interests", {"interest_id": 2}, 404),
    ("post", "/contacts/1/interests", {"interest_id": 99}, 400),
    ("delete", "/contacts/99/interests/2", None, 404),
])
def test_interest_errors(setup, method, path, payload, status):
    client, session, *_ = setup
    assert getattr(client, method)(path, json=payload).status_code == status
    session.commit.assert_not_called()


def test_interest_in_use_and_duplicate(setup):
    client, session, *_ = setup
    session.execute.return_value.scalar_one.return_value = 1
    assert client.delete("/contact_interests/2").status_code == 409
    session.delete.assert_not_called()
    session.commit.side_effect = RuntimeError("duplicate")
    assert client.post("/contact_interests", json={"name": "Music"}).status_code == 409
    session.rollback.assert_called_once()


def test_assignment_is_idempotent_and_audited(setup):
    client, session, contact, _, interest = setup
    for _ in range(2):
        response = client.post("/contacts/1/interests", json={"interest_id": 2})
        assert response.status_code == 200
        assert response.json["contact"]["interests"] == [{"id": 2, "name": "Music"}]
    assert contact.interests == [interest]
    session.commit.assert_called_once()
    assert session.add.call_args.args[0].changed_fields == ["interests"]
    for _ in range(2):
        assert client.delete("/contacts/1/interests/2").status_code == 200
    assert contact.interests == []
    assert session.commit.call_count == 2


@pytest.mark.parametrize("query,expected", [
    ("interest_ids=2,3", "contact_interests.id IN (2, 3)"),
    ("exclude_interest_ids=4,5", "contact_interests.id IN (4, 5)"),
    ("interest_ids=2&exclude_interest_ids=4&group_ids=7", "contact_groups.id IN (7)"),
])
def test_interest_filters(setup, query, expected):
    client, session, *_ = setup
    session.execute.return_value.scalars.return_value.all.return_value = []
    session.execute.return_value.all.return_value = []
    assert client.get(f"/contacts?{query}").status_code == 200
    sql = " ".join(str(call.args[0].compile(compile_kwargs={"literal_binds": True}))
                   for call in session.execute.call_args_list)
    assert expected in sql
    if "exclude_interest_ids" in query:
        assert "NOT (EXISTS" in sql


def test_education_crud(setup):
    client, session, _, entry, _ = setup
    session.scalars.return_value.all.return_value = [entry]
    assert client.get("/contacts/1/education").json["education"][0]["id"] == 3
    assert client.get("/contacts/1/education/3").json["education"]["degree"] == "master"
    response = client.post("/contacts/1/education", json={"institution": " University ", "degree": "engineer",
                                                        "start_date": "2000-09-01"})
    assert response.status_code == 200
    assert response.json["education"]["institution"] == "University"
    assert response.json["education"]["start_date"] == "2000-09-01"
    assert session.add.call_args.args[0].changed_fields == ["education"]
    response = client.patch("/contacts/1/education/3", json={"degree": None, "notes": " note "})
    assert response.status_code == 200
    assert entry.degree is None and entry.notes == "note" and entry.institution == "School"
    assert client.delete("/contacts/1/education/3").json["deleted_id"] == 3
    session.delete.assert_called_once_with(entry)


@pytest.mark.parametrize("payload", [
    {}, [], {"institution": " "}, {"institution": 12}, {"institution": "x" * 256},
    {"institution": "School", "degree": "unknown"}, {"institution": "School", "field_of_study": []},
    {"institution": "School", "start_date": "2020"}, {"institution": "School", "start_date": True},
    {"institution": "School", "start_date": "2020-02-30"},
    {"institution": "School", "start_date": "2021-01-01", "end_date": "2020-01-01"},
])
def test_education_validation(setup, payload):
    client, session, *_ = setup
    assert client.post("/contacts/1/education", json=payload).status_code == 400
    session.commit.assert_not_called()


def test_patch_validates_merged_dates_without_mutation(setup):
    client, session, _, entry, _ = setup
    assert client.patch("/contacts/1/education/3", json={"institution": "Changed", "end_date": "2009-01-01"}).status_code == 400
    assert entry.institution == "School"
    session.commit.assert_not_called()


@pytest.mark.parametrize("method", ["get", "patch", "delete"])
def test_education_ownership(setup, method):
    client, session, _, entry, _ = setup
    entry.contact_id = 9
    assert getattr(client, method)("/contacts/1/education/3", json={}).status_code == 404
    assert getattr(client, method)("/contacts/1/education/99", json={}).status_code == 404
    assert getattr(client, method)("/contacts/99/education/3", json={}).status_code == 404
    session.commit.assert_not_called()


def test_education_rollback_and_options(setup):
    client, session, *_ = setup
    assert client.options("/contacts/1/education/3").status_code == 200
    session.get.assert_not_called()
    session.commit.side_effect = RuntimeError("database unavailable")
    assert client.delete("/contacts/1/education/3").status_code == 500
    session.rollback.assert_called_once()
