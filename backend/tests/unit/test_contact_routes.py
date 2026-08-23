"""Unit tests for the private contact book endpoints (library/contact_routes.py).

Same pattern as test_tool_candidate_routes.py: call view functions directly
inside a bare Flask app.test_request_context(), with get_scoped_session
monkeypatched to a MagicMock session — no real DB, no test_client/blueprint
registration needed.
"""

import datetime as dt
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")

from flask import Flask


def _make_category(id_=1, name="Osoba prywatna"):
    return SimpleNamespace(id=id_, name=name, description=None, is_active=True)


def _make_contact(id_=1, last_name="Wojtysiak", first_name="Adam", category=None, **extra):
    defaults = dict(
        uuid="11111111-1111-1111-1111-111111111111",
        category_id=category.id if category else 1,
        category=category or _make_category(),
        first_name=first_name,
        last_name=last_name,
        phone_number="+48 725 428 453",
        email=None, linkedin_url=None, company=None, position=None,
        address=None, birthday=None, notes=None,
        created_at=dt.datetime(2026, 8, 23, 12, 0),
        updated_at=dt.datetime(2026, 8, 23, 12, 0),
    )
    defaults.update(extra)
    return SimpleNamespace(id=id_, **defaults)


class TestContactsAdd:
    def test_creates_contact_with_default_category(self, monkeypatch):
        from library.contact_routes import contacts_add

        default_category = _make_category()
        session = MagicMock()
        session.execute.return_value.scalars.return_value.first.return_value = default_category
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)

        app = Flask(__name__)
        with app.test_request_context(
            "/contacts", method="POST",
            json={"first_name": "Adam", "last_name": "Wojtysiak", "phone_number": "+48 725 428 453"},
        ):
            response = contacts_add()

        assert response[1] == 200
        session.add.assert_called_once()
        added = session.add.call_args[0][0]
        assert added.last_name == "Wojtysiak"
        assert added.first_name == "Adam"
        assert added.phone_number == "+48 725 428 453"
        assert added.category_id == default_category.id
        session.commit.assert_called_once()

    def test_missing_last_name_is_400(self, monkeypatch):
        from library.contact_routes import contacts_add

        session = MagicMock()
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context("/contacts", method="POST", json={"first_name": "Adam"}):
            response = contacts_add()

        assert response[1] == 400
        session.add.assert_not_called()

    def test_unknown_category_id_is_400(self, monkeypatch):
        from library.contact_routes import contacts_add

        session = MagicMock()
        session.get.return_value = None
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context(
            "/contacts", method="POST", json={"last_name": "Wojtysiak", "category_id": 999},
        ):
            response = contacts_add()

        assert response[1] == 400
        session.add.assert_not_called()


class TestContactsUpdate:
    def test_updates_fields(self, monkeypatch):
        from library.contact_routes import contacts_update

        row = _make_contact()
        session = MagicMock()
        session.get.return_value = row
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context(
            "/contacts/1", method="PATCH", json={"email": "adam@example.com", "company": "Acme"},
        ):
            response = contacts_update(1)

        assert response[1] == 200
        assert row.email == "adam@example.com"
        assert row.company == "Acme"
        session.commit.assert_called_once()

    def test_missing_contact_is_404(self, monkeypatch):
        from library.contact_routes import contacts_update

        session = MagicMock()
        session.get.return_value = None
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context("/contacts/999", method="PATCH", json={"email": "x@y.com"}):
            response = contacts_update(999)

        assert response[1] == 404


class TestContactsDelete:
    def test_deletes_contact(self, monkeypatch):
        from library.contact_routes import contacts_delete

        session = MagicMock()
        session.get.return_value = _make_contact()
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context("/contacts/1", method="DELETE"):
            response = contacts_delete(1)

        assert response[1] == 200
        session.delete.assert_called_once()

    def test_missing_contact_is_404(self, monkeypatch):
        from library.contact_routes import contacts_delete

        session = MagicMock()
        session.get.return_value = None
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context("/contacts/999", method="DELETE"):
            response = contacts_delete(999)

        assert response[1] == 404


class TestContactCategoriesDelete:
    def test_used_category_is_409(self, monkeypatch):
        from library.contact_routes import contact_categories_delete

        session = MagicMock()
        session.get.return_value = _make_category()
        session.execute.return_value.scalar_one.return_value = 3
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context("/contact_categories/1", method="DELETE"):
            response = contact_categories_delete(1)

        assert response[1] == 409
        session.delete.assert_not_called()

    def test_unused_category_is_deleted(self, monkeypatch):
        from library.contact_routes import contact_categories_delete

        session = MagicMock()
        session.get.return_value = _make_category()
        session.execute.return_value.scalar_one.return_value = 0
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context("/contact_categories/1", method="DELETE"):
            response = contact_categories_delete(1)

        assert response[1] == 200
        session.delete.assert_called_once()


class TestContactRelationships:
    def test_adds_relationship(self, monkeypatch):
        from library.contact_routes import contact_relationships_add

        adam = _make_contact(id_=1, last_name="Wojtysiak")
        zofia = _make_contact(id_=2, last_name="Kowalska", first_name="Zofia")
        session = MagicMock()
        session.get.side_effect = lambda model, id_: {1: adam, 2: zofia}.get(id_)
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context(
            "/contacts/1/relationships", method="POST",
            json={"related_contact_id": 2, "relationship_type": "żona"},
        ):
            response = contact_relationships_add(1)

        assert response[1] == 200
        session.add.assert_called_once()
        added = session.add.call_args[0][0]
        assert added.contact_id == 1
        assert added.related_contact_id == 2
        assert added.relationship_type == "żona"

    def test_self_relationship_is_400(self, monkeypatch):
        from library.contact_routes import contact_relationships_add

        adam = _make_contact(id_=1, last_name="Wojtysiak")
        session = MagicMock()
        session.get.return_value = adam
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context(
            "/contacts/1/relationships", method="POST",
            json={"related_contact_id": 1, "relationship_type": "żona"},
        ):
            response = contact_relationships_add(1)

        assert response[1] == 400
        session.add.assert_not_called()

    def test_missing_related_contact_is_400(self, monkeypatch):
        from library.contact_routes import contact_relationships_add

        adam = _make_contact(id_=1, last_name="Wojtysiak")
        session = MagicMock()
        session.get.side_effect = lambda model, id_: adam if id_ == 1 else None
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context(
            "/contacts/1/relationships", method="POST",
            json={"related_contact_id": 999, "relationship_type": "żona"},
        ):
            response = contact_relationships_add(1)

        assert response[1] == 400
        session.add.assert_not_called()

    def test_deletes_relationship(self, monkeypatch):
        from library.contact_routes import contact_relationships_delete

        session = MagicMock()
        session.get.return_value = SimpleNamespace(id=5)
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context("/contact_relationships/5", method="DELETE"):
            response = contact_relationships_delete(5)

        assert response[1] == 200
        session.delete.assert_called_once()


def _make_lookup_result(id_=1, contact_id=1, lookup_type="phone", status="no_results", **extra):
    defaults = dict(
        contact_id=contact_id, lookup_type=lookup_type, status=status,
        url=None, query_used=None, notes=None,
        searched_at=dt.datetime(2026, 8, 23, 12, 0),
    )
    defaults.update(extra)
    return SimpleNamespace(id=id_, **defaults)


class TestContactLookupResultsAdd:
    def test_adds_no_results_phone_lookup(self, monkeypatch):
        from library.contact_routes import contact_lookup_results_add

        session = MagicMock()
        session.get.return_value = _make_contact(id_=1)
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context(
            "/contacts/1/lookup_results", method="POST",
            json={"lookup_type": "phone", "status": "no_results", "query_used": "+48 725 428 453"},
        ):
            response = contact_lookup_results_add(1)

        assert response[1] == 200
        session.add.assert_called_once()
        added = session.add.call_args[0][0]
        assert added.contact_id == 1
        assert added.lookup_type == "phone"
        assert added.status == "no_results"
        assert added.query_used == "+48 725 428 453"

    def test_adds_linkedin_candidate(self, monkeypatch):
        from library.contact_routes import contact_lookup_results_add

        session = MagicMock()
        session.get.return_value = _make_contact(id_=1)
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context(
            "/contacts/1/lookup_results", method="POST",
            json={
                "lookup_type": "linkedin", "status": "candidate",
                "url": "https://www.linkedin.com/in/adam-wojtysiak/",
                "notes": "Superliga sp. z o.o. — miasto/zawód niepotwierdzone",
            },
        ):
            response = contact_lookup_results_add(1)

        assert response[1] == 200
        added = session.add.call_args[0][0]
        assert added.lookup_type == "linkedin"
        assert added.status == "candidate"
        assert added.url == "https://www.linkedin.com/in/adam-wojtysiak/"

    def test_missing_contact_is_404(self, monkeypatch):
        from library.contact_routes import contact_lookup_results_add

        session = MagicMock()
        session.get.return_value = None
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context(
            "/contacts/999/lookup_results", method="POST",
            json={"lookup_type": "phone", "status": "no_results"},
        ):
            response = contact_lookup_results_add(999)

        assert response[1] == 404
        session.add.assert_not_called()

    def test_invalid_lookup_type_is_400(self, monkeypatch):
        from library.contact_routes import contact_lookup_results_add

        session = MagicMock()
        session.get.return_value = _make_contact(id_=1)
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context(
            "/contacts/1/lookup_results", method="POST",
            json={"lookup_type": "facebook", "status": "no_results"},
        ):
            response = contact_lookup_results_add(1)

        assert response[1] == 400
        session.add.assert_not_called()

    def test_invalid_status_is_400(self, monkeypatch):
        from library.contact_routes import contact_lookup_results_add

        session = MagicMock()
        session.get.return_value = _make_contact(id_=1)
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context(
            "/contacts/1/lookup_results", method="POST",
            json={"lookup_type": "phone", "status": "maybe"},
        ):
            response = contact_lookup_results_add(1)

        assert response[1] == 400
        session.add.assert_not_called()


class TestContactLookupResultsUpdate:
    def test_confirming_linkedin_candidate_updates_contact_url(self, monkeypatch):
        from library.contact_routes import contact_lookup_results_update

        contact = _make_contact(id_=1, linkedin_url=None)
        lookup_result = _make_lookup_result(
            id_=7, contact_id=1, lookup_type="linkedin", status="candidate",
            url="https://www.linkedin.com/in/adam-wojtysiak/",
        )
        session = MagicMock()
        session.get.side_effect = lambda model, id_: {
            ("ContactLookupResult", 7): lookup_result,
            ("Contact", 1): contact,
        }.get((model.__name__ if hasattr(model, "__name__") else model, id_))
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context(
            "/contact_lookup_results/7", method="PATCH", json={"status": "confirmed"},
        ):
            response = contact_lookup_results_update(7)

        assert response[1] == 200
        assert lookup_result.status == "confirmed"
        assert contact.linkedin_url == "https://www.linkedin.com/in/adam-wojtysiak/"

    def test_rejecting_candidate_does_not_touch_contact(self, monkeypatch):
        from library.contact_routes import contact_lookup_results_update

        contact = _make_contact(id_=1, linkedin_url=None)
        lookup_result = _make_lookup_result(
            id_=8, contact_id=1, lookup_type="linkedin", status="candidate",
            url="https://www.linkedin.com/in/someone-else/",
        )
        session = MagicMock()
        session.get.side_effect = lambda model, id_: {
            ("ContactLookupResult", 8): lookup_result,
            ("Contact", 1): contact,
        }.get((model.__name__ if hasattr(model, "__name__") else model, id_))
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context(
            "/contact_lookup_results/8", method="PATCH", json={"status": "rejected"},
        ):
            response = contact_lookup_results_update(8)

        assert response[1] == 200
        assert lookup_result.status == "rejected"
        assert contact.linkedin_url is None

    def test_missing_lookup_result_is_404(self, monkeypatch):
        from library.contact_routes import contact_lookup_results_update

        session = MagicMock()
        session.get.return_value = None
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context(
            "/contact_lookup_results/999", method="PATCH", json={"status": "confirmed"},
        ):
            response = contact_lookup_results_update(999)

        assert response[1] == 404


class TestContactLookupResultsDelete:
    def test_deletes_lookup_result(self, monkeypatch):
        from library.contact_routes import contact_lookup_results_delete

        session = MagicMock()
        session.get.return_value = _make_lookup_result(id_=3)
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context("/contact_lookup_results/3", method="DELETE"):
            response = contact_lookup_results_delete(3)

        assert response[1] == 200
        session.delete.assert_called_once()

    def test_missing_lookup_result_is_404(self, monkeypatch):
        from library.contact_routes import contact_lookup_results_delete

        session = MagicMock()
        session.get.return_value = None
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context("/contact_lookup_results/999", method="DELETE"):
            response = contact_lookup_results_delete(999)

        assert response[1] == 404
