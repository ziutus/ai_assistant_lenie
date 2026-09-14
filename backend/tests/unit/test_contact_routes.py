"""Unit tests for the private contact book endpoints (library/contact_routes.py).

Same pattern as test_tool_candidate_routes.py: call view functions directly
inside a bare Flask app.test_request_context(), with get_scoped_session
monkeypatched to a MagicMock session — no real DB, no test_client/blueprint
registration needed.
"""

import datetime as dt
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")

from flask import Flask, g


def _make_category(id_=1, name="Osoba prywatna"):
    return SimpleNamespace(id=id_, name=name, description=None, is_active=True)


def _make_contact(id_=1, last_name="Wojtysiak", first_name="Adam", category=None, **extra):
    defaults = dict(
        uuid="11111111-1111-1111-1111-111111111111",
        category_id=category.id if category else 1,
        category=category or _make_category(),
        first_name=first_name,
        last_name=last_name,
        display_label=None,
        phone_number="+48 725 428 453",
        email=None, linkedin_url=None, company=None, position=None,
        address=None, birthday=None, pesel=None, notes=None, private_notes=None, groups=[], whatsapp_profile=None,
        birthday_month=None, birthday_day=None,
        languages=[], nationality=[], photo_storage_key=None, photo_thumbnail_storage_key=None, is_archived=False,
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
        # Two rows added: the Contact itself, plus a contact_change_log entry
        # recording the create (default change_source="manual_edit").
        assert session.add.call_count == 2
        added = session.add.call_args_list[0][0][0]
        assert added.last_name == "Wojtysiak"
        assert added.first_name == "Adam"
        assert added.phone_number == "+48 725 428 453"
        assert added.category_id == default_category.id
        change_log_entry = session.add.call_args_list[1][0][0]
        assert change_log_entry.source == "manual_edit"
        assert set(change_log_entry.changed_fields) == {"last_name", "first_name", "phone_number"}
        session.commit.assert_called_once()

    def test_missing_all_names_is_400(self, monkeypatch):
        from library.contact_routes import contacts_add

        session = MagicMock()
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context("/contacts", method="POST", json={}):
            response = contacts_add()

        assert response[1] == 400
        session.add.assert_not_called()

    def test_creates_unnamed_contact_with_label(self, monkeypatch):
        from library.contact_routes import contacts_add
        session = MagicMock()
        session.execute.return_value.scalars.return_value.first.return_value = _make_category()
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        with Flask(__name__).test_request_context("/contacts", method="POST", json={"display_label": "Dziecko 1"}):
            response, status = contacts_add()
        assert status == 200
        assert response.json["contact"]["display_name"] == "Dziecko 1"
        assert response.json["contact"]["last_name"] is None

    def test_later_name_preserves_contact_id(self, monkeypatch):
        from library.contact_routes import contacts_update
        row = _make_contact(id_=7, first_name=None, last_name=None, display_label="Dziecko 1")
        session = MagicMock()
        session.get.return_value = row
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        with Flask(__name__).test_request_context("/contacts/7", method="PATCH", json={"first_name": "Jan"}):
            response, status = contacts_update(7)
        assert status == 200
        assert response.json["contact"]["id"] == 7
        assert response.json["contact"]["display_name"] == "Jan"
        assert row.display_label == "Dziecko 1"

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

    def test_rejects_invalid_change_source(self, monkeypatch):
        from library.contact_routes import contacts_add

        default_category = _make_category()
        session = MagicMock()
        session.execute.return_value.scalars.return_value.first.return_value = default_category
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)

        app = Flask(__name__)
        with app.test_request_context(
            "/contacts", method="POST",
            json={"last_name": "Wojtysiak", "change_source": "not_a_real_source"},
        ):
            response = contacts_add()

        assert response[1] == 400
        session.add.assert_not_called()

    def test_creates_contact_with_languages(self, monkeypatch):
        from library.contact_routes import contacts_add

        default_category = _make_category()
        session = MagicMock()
        session.execute.return_value.scalars.return_value.first.return_value = default_category
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)

        app = Flask(__name__)
        with app.test_request_context(
            "/contacts", method="POST",
            json={
                "last_name": "Wojtysiak",
                "languages": [{"language": "polski", "native": True}, {"language": "niemiecki", "level": "b2"}],
            },
        ):
            response = contacts_add()

        assert response[1] == 200
        added = session.add.call_args_list[0][0][0]
        assert added.languages == [
            {"language": "polski", "native": True, "level": None},
            {"language": "niemiecki", "native": False, "level": "B2"},
        ]

    def test_creates_contact_with_nationality(self, monkeypatch):
        from library.contact_routes import contacts_add

        default_category = _make_category()
        session = MagicMock()
        session.execute.return_value.scalars.return_value.first.return_value = default_category
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)

        app = Flask(__name__)
        with app.test_request_context(
            "/contacts", method="POST",
            json={"last_name": "Wojtysiak", "nationality": ["polska", "niemiecka"]},
        ):
            response = contacts_add()

        assert response[1] == 200
        added = session.add.call_args_list[0][0][0]
        assert added.nationality == ["polska", "niemiecka"]


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
        session.add.assert_called_once()
        change_log_entry = session.add.call_args[0][0]
        assert change_log_entry.source == "manual_edit"
        assert set(change_log_entry.changed_fields) == {"email", "company"}
        session.commit.assert_called_once()

    def test_no_actual_change_does_not_log(self, monkeypatch):
        from library.contact_routes import contacts_update

        row = _make_contact(email="adam@example.com")
        session = MagicMock()
        session.get.return_value = row
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context(
            "/contacts/1", method="PATCH", json={"email": "adam@example.com"},
        ):
            response = contacts_update(1)

        assert response[1] == 200
        session.add.assert_not_called()

    def test_custom_change_source_and_note_are_recorded(self, monkeypatch):
        from library.contact_routes import contacts_update

        row = _make_contact(phone_number=None)
        session = MagicMock()
        session.get.return_value = row
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context(
            "/contacts/1", method="PATCH",
            json={
                "phone_number": "+48 600 000 000",
                "change_source": "whatsapp_analysis",
                "change_note": "Podany w czacie osiedlowym",
            },
        ):
            response = contacts_update(1)

        assert response[1] == 200
        change_log_entry = session.add.call_args[0][0]
        assert change_log_entry.source == "whatsapp_analysis"
        assert change_log_entry.note == "Podany w czacie osiedlowym"
        assert change_log_entry.changed_fields == ["phone_number"]

    def test_rejects_invalid_change_source(self, monkeypatch):
        from library.contact_routes import contacts_update

        row = _make_contact()
        session = MagicMock()
        session.get.return_value = row
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context(
            "/contacts/1", method="PATCH", json={"email": "x@y.com", "change_source": "bogus"},
        ):
            response = contacts_update(1)

        assert response[1] == 400
        session.add.assert_not_called()

    def test_missing_contact_is_404(self, monkeypatch):
        from library.contact_routes import contacts_update

        session = MagicMock()
        session.get.return_value = None
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context("/contacts/999", method="PATCH", json={"email": "x@y.com"}):
            response = contacts_update(999)

        assert response[1] == 404

    def test_archives_contact(self, monkeypatch):
        from library.contact_routes import contacts_update

        row = _make_contact(is_archived=False)
        session = MagicMock()
        session.get.return_value = row
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context("/contacts/1", method="PATCH", json={"is_archived": True}):
            response = contacts_update(1)

        assert response[1] == 200
        assert row.is_archived is True
        assert response[0].json["contact"]["is_archived"] is True

    def test_unarchives_contact(self, monkeypatch):
        from library.contact_routes import contacts_update

        row = _make_contact(is_archived=True)
        session = MagicMock()
        session.get.return_value = row
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context("/contacts/1", method="PATCH", json={"is_archived": False}):
            response = contacts_update(1)

        assert response[1] == 200
        assert row.is_archived is False

    def test_sets_languages(self, monkeypatch):
        from library.contact_routes import contacts_update

        row = _make_contact()
        session = MagicMock()
        session.get.return_value = row
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context(
            "/contacts/1", method="PATCH",
            json={"languages": [
                {"language": "polski", "native": True},
                {"language": "angielski", "native": False, "level": "c1"},
            ]},
        ):
            response, status = contacts_update(1)

        assert status == 200
        assert row.languages == [
            {"language": "polski", "native": True, "level": None},
            {"language": "angielski", "native": False, "level": "C1"},
        ]
        assert response.json["contact"]["languages"] == row.languages
        change_log_entry = session.add.call_args[0][0]
        assert change_log_entry.changed_fields == ["languages"]

    def test_rejects_invalid_language_level(self, monkeypatch):
        from library.contact_routes import contacts_update

        row = _make_contact()
        session = MagicMock()
        session.get.return_value = row
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context(
            "/contacts/1", method="PATCH",
            json={"languages": [{"language": "angielski", "level": "fluent"}]},
        ):
            response = contacts_update(1)

        assert response[1] == 400
        session.add.assert_not_called()

    def test_rejects_language_entry_without_language_name(self, monkeypatch):
        from library.contact_routes import contacts_update

        row = _make_contact()
        session = MagicMock()
        session.get.return_value = row
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context(
            "/contacts/1", method="PATCH", json={"languages": [{"native": True}]},
        ):
            response = contacts_update(1)

        assert response[1] == 400
        session.add.assert_not_called()

    def test_unchanged_languages_does_not_log(self, monkeypatch):
        from library.contact_routes import contacts_update

        row = _make_contact(languages=[{"language": "polski", "native": True, "level": None}])
        session = MagicMock()
        session.get.return_value = row
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context(
            "/contacts/1", method="PATCH",
            json={"languages": [{"language": "polski", "native": True}]},
        ):
            response = contacts_update(1)

        assert response[1] == 200
        session.add.assert_not_called()

    def test_sets_nationality(self, monkeypatch):
        from library.contact_routes import contacts_update

        row = _make_contact()
        session = MagicMock()
        session.get.return_value = row
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context(
            "/contacts/1", method="PATCH", json={"nationality": ["polska", " niemiecka "]},
        ):
            response, status = contacts_update(1)

        assert status == 200
        assert row.nationality == ["polska", "niemiecka"]
        assert response.json["contact"]["nationality"] == row.nationality
        change_log_entry = session.add.call_args[0][0]
        assert change_log_entry.changed_fields == ["nationality"]

    def test_rejects_non_string_nationality_entry(self, monkeypatch):
        from library.contact_routes import contacts_update

        row = _make_contact()
        session = MagicMock()
        session.get.return_value = row
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context(
            "/contacts/1", method="PATCH", json={"nationality": [123]},
        ):
            response = contacts_update(1)

        assert response[1] == 400
        session.add.assert_not_called()

    def test_unchanged_nationality_does_not_log(self, monkeypatch):
        from library.contact_routes import contacts_update

        row = _make_contact(nationality=["polska"])
        session = MagicMock()
        session.get.return_value = row
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context(
            "/contacts/1", method="PATCH", json={"nationality": ["polska"]},
        ):
            response = contacts_update(1)

        assert response[1] == 200
        session.add.assert_not_called()


class TestContactGroupsAssignment:
    def test_assign_logs_change(self, monkeypatch):
        from library.contact_routes import contact_groups_assign

        group = SimpleNamespace(id=5, name="Sąsiedzi")
        row = _make_contact(groups=[])
        session = MagicMock()
        session.get.side_effect = lambda model, id_: row if id_ == 1 else group
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context("/contacts/1/groups", method="POST", json={"group_id": 5}):
            response = contact_groups_assign(1)

        assert response[1] == 200
        assert group in row.groups
        session.add.assert_called_once()
        change_log_entry = session.add.call_args[0][0]
        assert change_log_entry.source == "manual_edit"
        assert change_log_entry.changed_fields == ["groups"]
        assert "Sąsiedzi" in change_log_entry.note

    def test_assign_again_is_noop(self, monkeypatch):
        from library.contact_routes import contact_groups_assign

        group = SimpleNamespace(id=5, name="Sąsiedzi")
        row = _make_contact(groups=[group])
        session = MagicMock()
        session.get.side_effect = lambda model, id_: row if id_ == 1 else group
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context("/contacts/1/groups", method="POST", json={"group_id": 5}):
            response = contact_groups_assign(1)

        assert response[1] == 200
        session.add.assert_not_called()

    def test_unassign_logs_change(self, monkeypatch):
        from library.contact_routes import contact_groups_unassign

        group = SimpleNamespace(id=5, name="Sąsiedzi")
        row = _make_contact(groups=[group])
        session = MagicMock()
        session.get.side_effect = lambda model, id_: row if id_ == 1 else group
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context("/contacts/1/groups/5", method="DELETE"):
            response = contact_groups_unassign(1, 5)

        assert response[1] == 200
        assert group not in row.groups
        session.add.assert_called_once()
        change_log_entry = session.add.call_args[0][0]
        assert change_log_entry.changed_fields == ["groups"]
        assert "Sąsiedzi" in change_log_entry.note


class TestContactPhotoChangeLog:
    def test_upload_logs_change(self, monkeypatch):
        from library.contact_routes import contact_photo_upload

        row = _make_contact(photo_storage_key=None)
        session = MagicMock()
        session.get.return_value = row
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        storage = MagicMock()
        storage.presigned_get_url.return_value = "http://example.test/photo.jpg"
        monkeypatch.setitem(
            __import__("sys").modules, "library.storage",
            SimpleNamespace(storage_from_config=lambda cfg: storage),
        )
        monkeypatch.setitem(
            __import__("sys").modules, "library.config_loader",
            SimpleNamespace(load_config=lambda: {}),
        )

        app = Flask(__name__)
        data = {"photo": (BytesIO(b"fake-bytes"), "photo.jpg")}
        with app.test_request_context(
            "/contacts/1/photo", method="POST", data=data, content_type="multipart/form-data",
        ):
            response = contact_photo_upload(1)

        assert response[1] == 200
        assert session.add.call_count == 2  # photo metadata plus contact audit
        change_log_entry = session.add.call_args_list[-1][0][0]
        assert change_log_entry.source == "manual_edit"
        assert change_log_entry.changed_fields == ["photo_storage_key", "photo_thumbnail_storage_key"]

    def test_delete_logs_change(self, monkeypatch):
        from library.contact_routes import contact_photo_delete

        row = _make_contact(photo_storage_key="contacts/uuid/photo.jpg")
        session = MagicMock()
        session.get.return_value = row
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context("/contacts/1/photo", method="DELETE"):
            response = contact_photo_delete(1)

        assert response[1] == 200
        assert row.photo_storage_key is None
        session.add.assert_called_once()
        change_log_entry = session.add.call_args[0][0]
        assert change_log_entry.changed_fields == ["photo_storage_key", "photo_thumbnail_storage_key"]


class TestContactsListArchivedFilter:
    def test_relationship_chips_use_placeholder_names(self):
        from library.contact_routes import _load_contact_relationships_summary
        session = MagicMock()
        session.execute.return_value.all.side_effect = [
            [(1, "dziecko", None, None, "Dziecko 1")],
            [(1, "bliźnięta", None, None, "Dziecko 2")],
        ]
        result = _load_contact_relationships_summary(session, [1])
        assert [row["other_name"] for row in result[1]] == ["Dziecko 1", "Dziecko 2"]

    def _run(self, monkeypatch, query_string):
        from library.contact_routes import contacts_list

        session = MagicMock()
        session.execute.return_value.scalar_one.return_value = 0
        session.execute.return_value.scalars.return_value.all.return_value = []
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context(f"/contacts{query_string}"):
            response = contacts_list()
        assert response[1] == 200
        return str(session.execute.call_args_list[0][0][0])

    def test_default_excludes_archived(self, monkeypatch):
        compiled = self._run(monkeypatch, "")
        assert "is_archived" in compiled

    def test_archived_true_filters_to_archived_only(self, monkeypatch):
        compiled = self._run(monkeypatch, "?archived=1")
        assert "is_archived" in compiled

    def test_archived_all_skips_filter(self, monkeypatch):
        compiled = self._run(monkeypatch, "?archived=all")
        assert "is_archived" not in compiled

    def test_filters_to_any_selected_contact_group(self, monkeypatch):
        compiled = self._run(monkeypatch, "?group_ids=3,5")
        assert "contact_groups.id IN" in compiled

    def test_excludes_contacts_in_selected_contact_group(self, monkeypatch):
        compiled = self._run(monkeypatch, "?exclude_group_ids=5")
        assert "NOT" in compiled
        assert "contact_groups.id IN" in compiled


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


def _make_organization(id_=1, contact_id=1, org_type="jdg", organization_name="Vente", status="confirmed", **extra):
    defaults = dict(
        contact_id=contact_id, org_type=org_type, organization_name=organization_name,
        role=None, nip=None, regon=None, address=None,
        is_primary=False, is_current=True, start_date=None, end_date=None,
        status=status, source_url=None, notes=None,
        created_at=dt.datetime(2026, 8, 23, 12, 0),
        updated_at=dt.datetime(2026, 8, 23, 12, 0),
    )
    defaults.update(extra)
    return SimpleNamespace(id=id_, **defaults)


class TestContactOrganizationsAdd:
    def test_adds_jdg_candidate(self, monkeypatch):
        from library.contact_routes import contact_organizations_add

        session = MagicMock()
        session.get.return_value = _make_contact(id_=1)
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context(
            "/contacts/1/organizations", method="POST",
            json={
                "org_type": "jdg", "organization_name": "Vente Włodzimierz Bartczak",
                "status": "candidate", "nip": "7261038790", "regon": "100950320",
                "address": "ul. Chłopickiego 26, Łódź",
            },
        ):
            response = contact_organizations_add(1)

        assert response[1] == 200
        session.add.assert_called_once()
        added = session.add.call_args[0][0]
        assert added.contact_id == 1
        assert added.org_type == "jdg"
        assert added.organization_name == "Vente Włodzimierz Bartczak"
        assert added.status == "candidate"
        assert added.nip == "7261038790"
        assert added.is_primary is False
        assert added.is_current is True

    def test_defaults_status_to_confirmed(self, monkeypatch):
        from library.contact_routes import contact_organizations_add

        session = MagicMock()
        session.get.return_value = _make_contact(id_=1)
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context(
            "/contacts/1/organizations", method="POST",
            json={"org_type": "employment", "organization_name": "Acme sp. z o.o.", "is_primary": True},
        ):
            response = contact_organizations_add(1)

        assert response[1] == 200
        added = session.add.call_args[0][0]
        assert added.status == "confirmed"
        assert added.is_primary is True

    def test_missing_contact_is_404(self, monkeypatch):
        from library.contact_routes import contact_organizations_add

        session = MagicMock()
        session.get.return_value = None
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context(
            "/contacts/999/organizations", method="POST",
            json={"org_type": "jdg", "organization_name": "Vente"},
        ):
            response = contact_organizations_add(999)

        assert response[1] == 404
        session.add.assert_not_called()

    def test_invalid_org_type_is_400(self, monkeypatch):
        from library.contact_routes import contact_organizations_add

        session = MagicMock()
        session.get.return_value = _make_contact(id_=1)
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context(
            "/contacts/1/organizations", method="POST",
            json={"org_type": "freelance", "organization_name": "Vente"},
        ):
            response = contact_organizations_add(1)

        assert response[1] == 400
        session.add.assert_not_called()

    def test_missing_organization_name_is_400(self, monkeypatch):
        from library.contact_routes import contact_organizations_add

        session = MagicMock()
        session.get.return_value = _make_contact(id_=1)
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context(
            "/contacts/1/organizations", method="POST", json={"org_type": "jdg"},
        ):
            response = contact_organizations_add(1)

        assert response[1] == 400
        session.add.assert_not_called()


class TestContactOrganizationsUpdate:
    def test_promotes_candidate_to_confirmed(self, monkeypatch):
        from library.contact_routes import contact_organizations_update

        row = _make_organization(id_=6, status="candidate")
        session = MagicMock()
        session.get.return_value = row
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context(
            "/contact_organizations/6", method="PATCH",
            json={"status": "confirmed", "nip": "7261038790"},
        ):
            response = contact_organizations_update(6)

        assert response[1] == 200
        assert row.status == "confirmed"
        assert row.nip == "7261038790"
        session.commit.assert_called_once()

    def test_invalid_status_is_400(self, monkeypatch):
        from library.contact_routes import contact_organizations_update

        row = _make_organization(id_=6)
        session = MagicMock()
        session.get.return_value = row
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context(
            "/contact_organizations/6", method="PATCH", json={"status": "maybe"},
        ):
            response = contact_organizations_update(6)

        assert response[1] == 400

    def test_missing_organization_is_404(self, monkeypatch):
        from library.contact_routes import contact_organizations_update

        session = MagicMock()
        session.get.return_value = None
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context(
            "/contact_organizations/999", method="PATCH", json={"status": "confirmed"},
        ):
            response = contact_organizations_update(999)

        assert response[1] == 404


class TestContactPhotoUpload:
    def test_replacement_does_not_overwrite_shared_photo(self, monkeypatch):
        from library.contact_routes import contact_photo_upload
        from library.db.models import ContactPhoto
        old_key = "contacts/shared/photo.jpg"
        contact = _make_contact(photo_storage_key=old_key)
        session = MagicMock()
        session.get.return_value = contact
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        storage = MagicMock()
        storage.presigned_get_url.return_value = "https://example.test/new-photo"
        monkeypatch.setattr("library.config_loader.load_config", lambda: {})
        monkeypatch.setattr("library.storage.storage_from_config", lambda cfg: storage)
        with Flask(__name__).test_request_context("/contacts/1/photo", method="POST",
                data={"photo": (BytesIO(b"image"), "photo.jpg")}, content_type="multipart/form-data"):
            response, status = contact_photo_upload(1)
        assert status == 200
        assert contact.photo_storage_key != old_key
        assert storage.put_bytes.call_args.args[0] != old_key
        created = session.add.call_args_list[0].args[0]
        assert isinstance(created, ContactPhoto)
        assert created.user_description is None and created.ai_descriptions == {}
        session.delete.assert_not_called()

    def test_uploads_photo_and_sets_storage_key(self, monkeypatch):
        from library.contact_routes import contact_photo_upload

        contact = _make_contact(id_=1)
        session = MagicMock()
        session.get.return_value = contact
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)

        fake_storage = MagicMock()
        fake_storage.presigned_get_url.return_value = "https://minio.local/contacts/photo.jpg?sig=1"
        monkeypatch.setattr("library.config_loader.load_config", lambda: {})
        monkeypatch.setattr("library.storage.storage_from_config", lambda cfg: fake_storage)

        app = Flask(__name__)
        with app.test_request_context(
            "/contacts/1/photo", method="POST",
            data={"photo": (BytesIO(b"fake-image-bytes"), "profile.jpg")},
            content_type="multipart/form-data",
        ):
            response = contact_photo_upload(1)

        assert response[1] == 200
        fake_storage.put_bytes.assert_called_once()
        stored_key = fake_storage.put_bytes.call_args[0][0]
        assert stored_key.startswith(f"contacts/{contact.uuid}/photos/")
        assert stored_key.endswith(".jpg")
        assert contact.photo_storage_key == stored_key
        session.commit.assert_called_once()

    def test_missing_contact_is_404(self, monkeypatch):
        from library.contact_routes import contact_photo_upload

        session = MagicMock()
        session.get.return_value = None
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context(
            "/contacts/999/photo", method="POST",
            data={"photo": (BytesIO(b"x"), "a.jpg")}, content_type="multipart/form-data",
        ):
            response = contact_photo_upload(999)

        assert response[1] == 404

    def test_missing_file_is_400(self, monkeypatch):
        from library.contact_routes import contact_photo_upload

        session = MagicMock()
        session.get.return_value = _make_contact(id_=1)
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context("/contacts/1/photo", method="POST", data={}, content_type="multipart/form-data"):
            response = contact_photo_upload(1)

        assert response[1] == 400

    def test_unsupported_extension_is_400(self, monkeypatch):
        from library.contact_routes import contact_photo_upload

        session = MagicMock()
        session.get.return_value = _make_contact(id_=1)
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context(
            "/contacts/1/photo", method="POST",
            data={"photo": (BytesIO(b"x"), "a.pdf")}, content_type="multipart/form-data",
        ):
            response = contact_photo_upload(1)

        assert response[1] == 400
        session.commit.assert_not_called()


class TestContactPhotoDelete:
    def test_clears_storage_key(self, monkeypatch):
        from library.contact_routes import contact_photo_delete

        contact = _make_contact(id_=1, photo_storage_key="contacts/uuid/photo.jpg",
                                photo_thumbnail_storage_key="contacts/uuid/photo_thumb.jpg")
        session = MagicMock()
        session.get.return_value = contact
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context("/contacts/1/photo", method="DELETE"):
            response = contact_photo_delete(1)

        assert response[1] == 200
        assert contact.photo_storage_key is None
        assert contact.photo_thumbnail_storage_key is None
        session.commit.assert_called_once()

    def test_missing_contact_is_404(self, monkeypatch):
        from library.contact_routes import contact_photo_delete

        session = MagicMock()
        session.get.return_value = None
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context("/contacts/999/photo", method="DELETE"):
            response = contact_photo_delete(999)

        assert response[1] == 404


class TestContactOrganizationsDelete:
    def test_deletes_organization(self, monkeypatch):
        from library.contact_routes import contact_organizations_delete

        session = MagicMock()
        session.get.return_value = _make_organization(id_=6)
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context("/contact_organizations/6", method="DELETE"):
            response = contact_organizations_delete(6)

        assert response[1] == 200
        session.delete.assert_called_once()

    def test_missing_organization_is_404(self, monkeypatch):
        from library.contact_routes import contact_organizations_delete

        session = MagicMock()
        session.get.return_value = None
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context("/contact_organizations/999", method="DELETE"):
            response = contact_organizations_delete(999)

        assert response[1] == 404


class TestContactThumbnails:
    @pytest.mark.parametrize("bad_image,storage_error", [(False, False), (True, False), (False, True)])
    def test_upload_thumbnail_is_best_effort(self, monkeypatch, bad_image, storage_error):
        from PIL import Image
        from library.contact_routes import contact_photo_upload

        contact = _make_contact(photo_thumbnail_storage_key="old-thumb.jpg")
        session = MagicMock()
        session.get.return_value = contact
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        storage = MagicMock()
        storage.presigned_get_url.return_value = "https://example.test/photo"
        if storage_error:
            storage.put_bytes.side_effect = [None, OSError("storage unavailable")]
        monkeypatch.setattr("library.config_loader.load_config", lambda: {})
        monkeypatch.setattr("library.storage.storage_from_config", lambda cfg: storage)
        output = BytesIO()
        Image.new("RGBA", (800, 400)).save(output, format="PNG")
        data = b"corrupt" if bad_image else output.getvalue()
        with Flask(__name__).test_request_context(
            "/contacts/1/photo", method="POST", content_type="multipart/form-data",
            data={"photo": (BytesIO(data), "profile.png")},
        ):
            response, status = contact_photo_upload(1)
        assert status == 200
        assert contact.photo_storage_key.startswith(f"contacts/{contact.uuid}/photos/")
        assert contact.photo_storage_key.endswith(".png")
        assert storage.put_bytes.call_args_list[0].args[1] == data
        session.commit.assert_called_once()
        if bad_image or storage_error:
            assert contact.photo_thumbnail_storage_key is None
        else:
            assert contact.photo_thumbnail_storage_key == f"{contact.photo_storage_key}.thumb.jpg"
            call = storage.put_bytes.call_args_list[1]
            assert call.kwargs["content_type"] == "image/jpeg"
            with Image.open(BytesIO(call.args[1])) as thumbnail:
                assert thumbnail.size == (256, 128)
                assert thumbnail.format == "JPEG"

    def test_thumbnail_urls_in_list_and_detail(self, monkeypatch):
        from library.contact_routes import contacts_list, contacts_get

        contact = _make_contact(photo_thumbnail_storage_key="contacts/uuid/photo_thumb.jpg")
        session = MagicMock()
        session.get.return_value = contact
        session.execute.return_value.scalar_one.return_value = 1
        session.execute.return_value.scalars.return_value.all.return_value = [contact]
        session.execute.return_value.all.return_value = []
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        monkeypatch.setattr("library.contact_routes._load_contact_relationships_summary", lambda *args: {})
        storage = MagicMock()
        storage.presigned_get_url.return_value = "https://example.test/thumb"
        factory = MagicMock(return_value=storage)
        monkeypatch.setattr("library.config_loader.load_config", lambda: {})
        monkeypatch.setattr("library.storage.storage_from_config", factory)
        with Flask(__name__).test_request_context("/contacts"):
            response, status = contacts_list()
            assert status == 200
            assert response.get_json()["contacts"][0]["photo_thumbnail_url"] == "https://example.test/thumb"
        session.execute.return_value.scalars.return_value.all.return_value = []
        with Flask(__name__).test_request_context("/contacts/1"):
            response, status = contacts_get(1)
            assert status == 200
            assert response.get_json()["contact"]["photo_thumbnail_url"] == "https://example.test/thumb"

    def test_null_thumbnail_needs_no_storage_and_reuses_client(self, monkeypatch):
        from library.contact_routes import _contact_dict

        storage = MagicMock()
        storage.presigned_get_url.return_value = None
        factory = MagicMock(return_value=storage)
        monkeypatch.setattr("library.config_loader.load_config", lambda: {})
        monkeypatch.setattr("library.storage.storage_from_config", factory)
        with Flask(__name__).test_request_context("/contacts"):
            assert _contact_dict(_make_contact())["photo_thumbnail_url"] is None
            factory.assert_not_called()
            for id_ in (1, 2):
                assert _contact_dict(_make_contact(id_=id_, photo_thumbnail_storage_key=f"{id_}.jpg"))["photo_thumbnail_url"] is None
        factory.assert_called_once()
        assert storage.presigned_get_url.call_count == 2


@pytest.mark.parametrize("path,method,helper", [
    ("/contacts/1/photo/description", "PATCH", "library.contact_photos.update_description"),
    ("/contacts/1/photo/describe", "POST", "library.contact_photos.generate_description"),
    ("/contacts/1/family", "POST", "library.contact_families.create_family"),
])
def test_photo_and_family_endpoints_explicitly_serialize_json(monkeypatch, path, method, helper):
    from library.contact_routes import bp
    body = {"text": "<script>alert('untrusted text')</script>"}
    monkeypatch.setattr(helper, lambda *_args: (body, 200))
    monkeypatch.setattr("library.contact_routes.get_scoped_session", MagicMock)
    app = Flask(__name__)
    app.register_blueprint(bp)
    response = app.test_client().open(path, method=method, json={})
    assert response.mimetype == "application/json"
    assert response.get_json() == body


class TestContactGroupEvents:
    @pytest.fixture
    def event_session(self, monkeypatch):
        from library.db.models import ContactGroupEvent

        session = MagicMock()
        event = ContactGroupEvent(
            id=7, group_id=3, title="Meeting", event_date=dt.date(2026, 9, 1),
            created_at=dt.datetime(2026, 9, 1), updated_at=dt.datetime(2026, 9, 1),
        )
        session.get.return_value = event
        session.execute.return_value.scalars.return_value.all.return_value = [event]
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        return session, event

    def test_get_group_and_events(self, event_session):
        from library.contact_routes import contact_groups_get, contact_group_events_list

        session, event = event_session
        session.get.return_value = SimpleNamespace(id=3, name="Parents", description=None)
        session.execute.return_value.scalar_one.return_value = 2
        with Flask(__name__).test_request_context():
            response, status = contact_groups_get(3)
            assert status == 200
            assert response.json["contact_group"]["count"] == 2
            assert response.json["contact_group"]["events"][0]["id"] == event.id
            response, status = contact_group_events_list(3)
            assert status == 200
            assert response.json["events"][0]["event_date"] == "2026-09-01"

    def test_post(self, event_session):
        from library.contact_routes import contact_group_events_add
        from library.db.models import ContactGroup, Document

        session, _ = event_session
        document = Document(id=8, title="Journal")
        session.get.side_effect = lambda model, ident: document if model is Document else ContactGroup(id=3, name="Parents")
        with Flask(__name__).test_request_context(method="POST", json={
            "title": " Meeting ", "event_date": "2026-09-13", "summary": "Notes", "source_document_id": 8,
        }):
            response, status = contact_group_events_add(3)
        assert status == 200
        assert response.json["event"]["source_document_title"] == "Journal"
        added = session.add.call_args.args[0]
        assert added.title == "Meeting"
        assert added.group_id == 3
        assert added.event_date == dt.date(2026, 9, 13)
        session.commit.assert_called_once()

    def test_patch_and_delete(self, event_session):
        from library.contact_routes import contact_group_events_update, contact_group_events_delete

        session, event = event_session
        with Flask(__name__).test_request_context(method="PATCH", json={
            "title": "Updated", "event_date": "2026-09-12", "summary": None, "source_document_id": None,
        }):
            response, status = contact_group_events_update(7)
        assert status == 200
        assert response.json["event"]["title"] == "Updated"
        assert event.event_date == dt.date(2026, 9, 12)
        assert event.updated_at > dt.datetime(2026, 9, 1)
        with Flask(__name__).test_request_context(method="DELETE"):
            response, status = contact_group_events_delete(7)
        assert status == 200
        session.delete.assert_called_once_with(event)

    @pytest.mark.parametrize("payload", [
        {}, {"title": ""}, {"title": 4}, {"title": "x" * 256},
        {"title": "OK", "event_date": "2026-02-30"},
        {"title": "OK", "event_date": 123},
        {"title": "OK", "event_date": "2026-09-13", "source_document_id": True},
        {"title": "OK", "event_date": "2026-09-13", "summary": []}, ["invalid"],
    ])
    def test_invalid_post(self, event_session, payload):
        from library.contact_routes import contact_group_events_add

        session, _ = event_session
        with Flask(__name__).test_request_context(method="POST", json=payload):
            assert contact_group_events_add(3)[1] == 400
        session.commit.assert_not_called()

    @pytest.mark.parametrize("payload", [{"title": " "}, {"event_date": None}, {"source_document_id": []}])
    def test_invalid_patch_is_atomic(self, event_session, payload):
        from library.contact_routes import contact_group_events_update

        session, event = event_session
        with Flask(__name__).test_request_context(method="PATCH", json={"summary": "changed", **payload}):
            assert contact_group_events_update(7)[1] == 400
        assert event.summary is None
        session.commit.assert_not_called()

    def test_unknown_document(self, event_session):
        from library.contact_routes import contact_group_events_add
        from library.db.models import Document

        session, _ = event_session
        session.get.side_effect = lambda model, ident: None if model is Document else SimpleNamespace(id=3)
        with Flask(__name__).test_request_context(method="POST", json={
            "title": "OK", "event_date": "2026-09-13", "source_document_id": 999,
        }):
            assert contact_group_events_add(3)[1] == 400

    @pytest.mark.parametrize("name,method", [
        ("contact_groups_get", "GET"), ("contact_group_events_list", "GET"),
        ("contact_group_events_add", "POST"), ("contact_group_events_update", "PATCH"),
        ("contact_group_events_delete", "DELETE"),
    ])
    def test_missing_record(self, event_session, name, method):
        from library import contact_routes

        session, _ = event_session
        session.get.return_value = None
        with Flask(__name__).test_request_context(method=method, json={}):
            assert getattr(contact_routes, name)(999)[1] == 404

    def test_db_failure_rolls_back(self, event_session):
        from library.contact_routes import contact_group_events_delete

        session, _ = event_session
        session.commit.side_effect = RuntimeError("DB failed")
        with Flask(__name__).test_request_context(method="DELETE"):
            assert contact_group_events_delete(7)[1] == 500
        session.rollback.assert_called_once()


    def test_contact_overview_joins_all_groups_and_caps_events(self, event_session):
        from library.contact_routes import contacts_get
        from library.db.models import ContactGroupEvent
        from sqlalchemy.dialects import postgresql

        session, event = event_session
        event.group = None
        # Simple namespaces match the existing endpoint-test convention.
        events = [SimpleNamespace(
            id=index, group_id=index, title="Meeting", event_date=dt.date(2026, 9, index),
            summary=None, source_document_id=None, source_document=None,
            created_at=None, updated_at=None, group=SimpleNamespace(name=f"Group {index}"), participants=[],
        ) for index in (3, 2)]
        session.get.return_value = _make_contact()
        captured = []

        def execute(query):
            result = MagicMock()
            if query.column_descriptions[0].get("entity") is ContactGroupEvent:
                captured.append(str(query.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})))
                result.scalars.return_value.all.return_value = events
            else:
                result.all.return_value = []
                result.scalars.return_value.all.return_value = []
            return result

        session.execute.side_effect = execute
        with Flask(__name__).test_request_context():
            response, status = contacts_get(1)
        assert status == 200
        assert [row["group_name"] for row in response.json["contact"]["events"]] == ["Group 3", "Group 2"]
        assert "contact_group_memberships.contact_id = 1" in captured[0]
        assert "ORDER BY contact_group_events.event_date DESC" in captured[0]
        assert "LIMIT 20" in captured[0]


@pytest.fixture
def photo_history_setup(monkeypatch):
    from library.db.models import Contact

    contact = _make_contact()
    prefix = f"contacts/{contact.uuid}/"
    photo = SimpleNamespace(
        storage_key=prefix + "photo.png", created_at=dt.datetime(2026, 9, 1),
        user_description="Poprzednie zdjęcie", user_description_revision=2,
        ai_descriptions={"model": {"text": "Opis zdjęcia"}},
    )
    session = MagicMock()
    session.get.side_effect = lambda model, key: contact if model is Contact else photo
    monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
    monkeypatch.setattr("library.config_loader.load_config", lambda: {})
    storage = MagicMock()
    storage.presigned_get_url.side_effect = lambda key: f"https://storage.test/{key}"
    storage.exists.return_value = True
    monkeypatch.setattr("library.storage.storage_from_config", lambda cfg: storage)
    return contact, photo, session, storage


class TestContactPhotoHistory:
    def test_history_order_prefix_metadata_and_thumbnails(self, photo_history_setup):
        from library.contact_routes import contact_photo_history, _photo_thumbnail_storage_key
        from library.contact_photos import photo_dict

        contact, legacy, session, storage = photo_history_setup
        newest = SimpleNamespace(**{**vars(legacy), "storage_key": f"contacts/{contact.uuid}/photos/new.png",
                                    "created_at": dt.datetime(2026, 9, 2)})
        contact.photo_storage_key = newest.storage_key
        session.execute.return_value.scalars.return_value.all.return_value = [newest, legacy]
        storage.exists.side_effect = [True, False]
        with Flask(__name__).test_request_context():
            response, status = contact_photo_history(contact.id)
        assert status == 200
        statement = session.execute.call_args.args[0]
        compiled = statement.compile()
        assert list(compiled.params.values()) == [f"contacts/{contact.uuid}/%"]
        assert "contact_photos.storage_key LIKE" in str(compiled)
        assert "ORDER BY contact_photos.created_at DESC" in str(compiled)
        history = response.json["history"]
        assert [item["storage_key"] for item in history] == [newest.storage_key, legacy.storage_key]
        assert [item["is_current"] for item in history] == [True, False]
        assert history[0]["created_at"] == newest.created_at.isoformat()
        for item, photo in zip(history, [newest, legacy]):
            assert {key: item[key] for key in photo_dict(photo)} == photo_dict(photo)
            assert item["photo_url"] == f"https://storage.test/{photo.storage_key}"
        thumb_key = _photo_thumbnail_storage_key(contact.uuid, newest.storage_key)
        assert history[0]["thumbnail_url"] == f"https://storage.test/{thumb_key}"
        assert history[1]["thumbnail_url"] is None
        assert storage.exists.call_count == 2
        storage.get_bytes.assert_not_called()

    def test_empty_history(self, photo_history_setup):
        from library.contact_routes import contact_photo_history

        contact, _, session, _ = photo_history_setup
        session.execute.return_value.scalars.return_value.all.return_value = []
        with Flask(__name__).test_request_context():
            response, status = contact_photo_history(contact.id)
        assert status == 200
        assert response.json == {"status": "success", "history": []}


class TestContactPhotoRestore:
    @pytest.mark.parametrize("body", [{}, {"storage_key": None}, {"storage_key": 123}, [], None])
    def test_invalid_body(self, photo_history_setup, body):
        from library.contact_routes import contact_photo_restore

        contact, _, session, _ = photo_history_setup
        with Flask(__name__).test_request_context(method="POST", json=body):
            assert contact_photo_restore(contact.id)[1] == 400
        session.commit.assert_not_called()

    def test_rejects_other_contact_prefix(self, photo_history_setup):
        from library.contact_routes import contact_photo_restore

        contact, _, session, storage = photo_history_setup
        with Flask(__name__).test_request_context(method="POST", json={
            "storage_key": "contacts/22222222-2222-2222-2222-222222222222/photos/other.png",
        }):
            assert contact_photo_restore(contact.id)[1] == 400
        assert session.get.call_count == 1
        session.commit.assert_not_called()
        storage.exists.assert_not_called()

    def test_unknown_photo(self, photo_history_setup):
        from library.contact_routes import contact_photo_restore
        from library.db.models import Contact

        contact, _, session, _ = photo_history_setup
        session.get.side_effect = lambda model, key: contact if model is Contact else None
        with Flask(__name__).test_request_context(method="POST", json={
            "storage_key": f"contacts/{contact.uuid}/photos/missing.png",
        }):
            assert contact_photo_restore(contact.id)[1] == 404
        session.commit.assert_not_called()

    @pytest.mark.parametrize("thumbnail", ["existing", "regenerate", "failure"])
    def test_restore_updates_contact_and_records_change(self, photo_history_setup, thumbnail):
        from PIL import Image
        from library.contact_routes import contact_photo_restore, _photo_thumbnail_storage_key
        from library.contact_photos import photo_dict
        from library.db.models import ContactChangeLog

        contact, photo, session, storage = photo_history_setup
        previous_updated = contact.updated_at
        storage.exists.return_value = thumbnail == "existing"
        original = BytesIO()
        Image.new("RGB", (32, 24), "white").save(original, format="PNG")
        storage.get_bytes.return_value = original.getvalue()
        if thumbnail == "failure":
            storage.get_bytes.side_effect = RuntimeError("Storage unavailable")
        with Flask(__name__).test_request_context(method="POST", json={"storage_key": photo.storage_key}):
            response, status = contact_photo_restore(contact.id)
        assert status == 200
        assert response.json == {"status": "success", "photo_url": f"https://storage.test/{photo.storage_key}",
                                 "photo": photo_dict(photo)}
        assert contact.photo_storage_key == photo.storage_key
        thumb_key = _photo_thumbnail_storage_key(contact.uuid, photo.storage_key)
        assert contact.photo_thumbnail_storage_key == (None if thumbnail == "failure" else thumb_key)
        assert contact.updated_at > previous_updated
        change = session.add.call_args.args[0]
        assert isinstance(change, ContactChangeLog)
        assert change.contact_id == contact.id
        assert change.source == "manual_edit"
        assert change.changed_fields == ["photo_storage_key", "photo_thumbnail_storage_key"]
        assert change.note == "Przywrócono poprzednie zdjęcie z historii."
        session.commit.assert_called_once()
        if thumbnail == "existing":
            storage.get_bytes.assert_not_called()
            storage.put_bytes.assert_not_called()
        elif thumbnail == "regenerate":
            storage.get_bytes.assert_called_once_with(photo.storage_key)
            assert storage.put_bytes.call_args.args[0] == thumb_key
            assert storage.put_bytes.call_args.kwargs == {"content_type": "image/jpeg"}
            with Image.open(BytesIO(storage.put_bytes.call_args.args[1])) as image:
                assert image.format == "JPEG"

    def test_current_photo_is_noop(self, photo_history_setup):
        from library.contact_routes import contact_photo_restore

        contact, photo, session, storage = photo_history_setup
        contact.photo_storage_key = photo.storage_key
        previous_updated = contact.updated_at
        with Flask(__name__).test_request_context(method="POST", json={"storage_key": photo.storage_key}):
            response, status = contact_photo_restore(contact.id)
        assert status == 200
        assert response.json["photo"]["storage_key"] == photo.storage_key
        assert contact.updated_at == previous_updated
        session.add.assert_not_called()
        session.commit.assert_not_called()
        storage.exists.assert_not_called()

    def test_db_failure_rolls_back(self, photo_history_setup):
        from library.contact_routes import contact_photo_restore

        contact, photo, session, _ = photo_history_setup
        session.commit.side_effect = RuntimeError("DB unavailable")
        with Flask(__name__).test_request_context(method="POST", json={"storage_key": photo.storage_key}):
            response, status = contact_photo_restore(contact.id)
        assert (response, status) == ({"status": "error", "message": "DB error"}, 500)
        session.rollback.assert_called_once()


class TestContactPhotoRegenerateThumbnail:
    def test_no_photo_returns_404(self, photo_history_setup):
        from library.contact_routes import contact_photo_regenerate_thumbnail

        contact, _, session, _ = photo_history_setup
        contact.photo_storage_key = None
        with Flask(__name__).test_request_context(method="POST"):
            response, status = contact_photo_regenerate_thumbnail(contact.id)
        assert status == 404
        session.commit.assert_not_called()

    def test_regenerates_in_place_and_updates_key_when_missing(self, photo_history_setup, monkeypatch):
        from library.contact_routes import contact_photo_regenerate_thumbnail, _photo_thumbnail_storage_key

        contact, photo, session, storage = photo_history_setup
        contact.photo_storage_key = photo.storage_key
        contact.photo_thumbnail_storage_key = None
        previous_updated = contact.updated_at
        storage.get_bytes.return_value = b"original-photo-bytes"
        monkeypatch.setattr("library.contact_routes.generate_photo_thumbnail", lambda data: b"new-thumb-bytes")
        with Flask(__name__).test_request_context(method="POST"):
            response, status = contact_photo_regenerate_thumbnail(contact.id)
        assert status == 200
        thumb_key = _photo_thumbnail_storage_key(contact.uuid, photo.storage_key)
        assert response.json == {"status": "success", "photo_thumbnail_url": f"https://storage.test/{thumb_key}"}
        storage.get_bytes.assert_called_once_with(photo.storage_key)
        storage.put_bytes.assert_called_once_with(thumb_key, b"new-thumb-bytes", content_type="image/jpeg")
        assert contact.photo_thumbnail_storage_key == thumb_key
        assert contact.updated_at > previous_updated
        session.commit.assert_called_once()

    def test_no_db_write_when_key_already_current(self, photo_history_setup, monkeypatch):
        from library.contact_routes import contact_photo_regenerate_thumbnail, _photo_thumbnail_storage_key

        contact, photo, session, storage = photo_history_setup
        contact.photo_storage_key = photo.storage_key
        contact.photo_thumbnail_storage_key = _photo_thumbnail_storage_key(contact.uuid, photo.storage_key)
        previous_updated = contact.updated_at
        storage.get_bytes.return_value = b"original-photo-bytes"
        monkeypatch.setattr("library.contact_routes.generate_photo_thumbnail", lambda data: b"new-thumb-bytes")
        with Flask(__name__).test_request_context(method="POST"):
            response, status = contact_photo_regenerate_thumbnail(contact.id)
        assert status == 200
        storage.put_bytes.assert_called_once()
        assert contact.updated_at == previous_updated
        session.commit.assert_not_called()

    def test_processing_failure_returns_502(self, photo_history_setup, monkeypatch):
        from library.contact_routes import contact_photo_regenerate_thumbnail

        contact, photo, session, storage = photo_history_setup
        contact.photo_storage_key = photo.storage_key
        storage.get_bytes.side_effect = RuntimeError("storage unavailable")
        with Flask(__name__).test_request_context(method="POST"):
            response, status = contact_photo_regenerate_thumbnail(contact.id)
        assert status == 502
        storage.put_bytes.assert_not_called()
        session.commit.assert_not_called()


@pytest.mark.parametrize(
    "route_name", ["contact_photo_history", "contact_photo_restore", "contact_photo_regenerate_thumbnail"],
)
def test_photo_history_routes_missing_contact_and_options(monkeypatch, route_name):
    from library import contact_routes

    session = MagicMock()
    session.get.return_value = None
    monkeypatch.setattr(contact_routes, "get_scoped_session", lambda: session)
    route = getattr(contact_routes, route_name)
    with Flask(__name__).test_request_context(method="OPTIONS"):
        assert route(999) == ({"status": "OK"}, 200)
    session.get.assert_not_called()
    with Flask(__name__).test_request_context():
        assert route(999) == ({"status": "error", "message": "Contact not found"}, 404)


class TestContactBirthdayPair:
    @pytest.fixture(params=["POST", "PATCH"])
    def birthday_request(self, monkeypatch, request):
        from library.contact_routes import contacts_add, contacts_update

        row = _make_contact()
        session = MagicMock()
        session.get.return_value = row
        session.execute.return_value.scalars.return_value.first.return_value = _make_category()
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)

        def send(data):
            with Flask(__name__).test_request_context(
                "/contacts" if request.param == "POST" else "/contacts/1",
                method=request.param, json={"last_name": row.last_name, **data},
            ):
                return contacts_add() if request.param == "POST" else contacts_update(1)

        return send, session, row

    @pytest.mark.parametrize("month, day", [(1, 31), (2, 29), (4, 30), (6, 30), (9, 30), (11, 30), (12, 31)])
    def test_valid_pair(self, birthday_request, month, day):
        send, session, _ = birthday_request
        response, status = send({"birthday_month": month, "birthday_day": day})
        assert status == 200
        assert response.json["contact"]["birthday_month"] == month
        assert response.json["contact"]["birthday_day"] == day
        assert response.json["contact"]["birthday"] is None
        change = session.add.call_args_list[-1][0][0]
        assert {"birthday_month", "birthday_day"} <= set(change.changed_fields)
        session.commit.assert_called_once()

    @pytest.mark.parametrize("data", [
        {"birthday_month": 4}, {"birthday_day": 20},
        {"birthday_month": None}, {"birthday_day": None},
        {"birthday_month": 4, "birthday_day": None},
        {"birthday_month": None, "birthday_day": 20},
    ])
    def test_incomplete_pair_rejected(self, birthday_request, data):
        send, session, row = birthday_request
        assert send(data) == ({
            "status": "error", "message": "birthday_month and birthday_day must be provided together",
        }, 400)
        assert row.birthday_month is None and row.birthday_day is None
        session.add.assert_not_called()
        session.commit.assert_not_called()

    @pytest.mark.parametrize("month, day, field", [
        (0, 1, "birthday_month"), (13, 1, "birthday_month"),
        (1, 0, "birthday_day"), (1, 32, "birthday_day"),
        (4, 31, "birthday_day"), (6, 31, "birthday_day"),
        (9, 31, "birthday_day"), (11, 31, "birthday_day"), (2, 30, "birthday_day"),
        ("4", 1, "birthday_month"), (True, 1, "birthday_month"), (1.5, 1, "birthday_month"),
        (1, "2", "birthday_day"), (1, False, "birthday_day"), (1, 2.5, "birthday_day"),
    ])
    def test_invalid_pair_rejected(self, birthday_request, month, day, field):
        send, session, _ = birthday_request
        response, status = send({"birthday_month": month, "birthday_day": day})
        assert status == 400
        assert response["status"] == "error"
        assert field in response["message"]
        session.add.assert_not_called()
        session.commit.assert_not_called()

    def test_null_pair(self, birthday_request):
        send, session, row = birthday_request
        row.birthday_month, row.birthday_day = 2, 29
        response, status = send({"birthday_month": None, "birthday_day": None})
        assert status == 200
        assert response.json["contact"]["birthday_month"] is None
        assert response.json["contact"]["birthday_day"] is None
        change = session.add.call_args_list[-1][0][0]
        assert {"birthday_month", "birthday_day"} <= set(change.changed_fields)
        session.commit.assert_called_once()

    @pytest.mark.parametrize("data, expected, changed", [
        ({"birthday_month": 3}, (3, 29), ["birthday_month"]),
        ({"birthday_day": 28}, (2, 28), ["birthday_day"]),
        ({"birthday_month": 2, "birthday_day": 29}, (2, 29), []),
        ({}, (2, 29), []),
    ])
    def test_update_existing_pair(self, monkeypatch, data, expected, changed):
        from library.contact_routes import contacts_update

        row = _make_contact(birthday_month=2, birthday_day=29, birthday=dt.date(2000, 2, 29))
        session = MagicMock()
        session.get.return_value = row
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        with Flask(__name__).test_request_context("/contacts/1", method="PATCH", json=data):
            response, status = contacts_update(1)
        assert status == 200
        assert (row.birthday_month, row.birthday_day) == expected
        assert response.json["contact"]["birthday"] == "2000-02-29"
        if changed:
            assert session.add.call_args[0][0].changed_fields == changed
        else:
            session.add.assert_not_called()

    @pytest.mark.parametrize("data", [
        {"birthday_month": 4}, {"birthday_month": None}, {"birthday_day": None},
    ])
    def test_update_validates_merged_pair(self, monkeypatch, data):
        from library.contact_routes import contacts_update

        row = _make_contact(birthday_month=1, birthday_day=31)
        session = MagicMock()
        session.get.return_value = row
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        with Flask(__name__).test_request_context("/contacts/1", method="PATCH", json=data):
            response, status = contacts_update(1)
        assert status == 400
        assert response["status"] == "error"
        assert (row.birthday_month, row.birthday_day) == (1, 31)
        session.commit.assert_not_called()

    @pytest.mark.parametrize("kind", ["service", "user", "read_only", None])
    @pytest.mark.parametrize("month, day", [(2, 29), (None, None)])
    def test_dict_birthday_pair_is_public(self, kind, month, day):
        from library.contact_routes import _contact_dict

        row = _make_contact(birthday_month=month, birthday_day=day, private_notes="vault note")
        with Flask(__name__).test_request_context():
            if kind is not None:
                g.auth = SimpleNamespace(kind=kind)
            result = _contact_dict(row)
        assert result["birthday_month"] == month
        assert result["birthday_day"] == day
        assert result["private_notes"] == ("vault note" if kind == "service" else None)


class TestContactPrivateNotes:
    @pytest.mark.parametrize("kind", ["service", "user", "read_only", None])
    @pytest.mark.parametrize("value, normalized", [("  vault note  ", "vault note"), ("  ", None), (None, None)])
    def test_post_private_notes_permissions(self, monkeypatch, kind, value, normalized):
        from library.contact_routes import contacts_add

        session = MagicMock()
        session.execute.return_value.scalars.return_value.first.return_value = _make_category()
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        with Flask(__name__).test_request_context(
            "/contacts", method="POST",
            json={"last_name": "Example", "notes": "public note", "private_notes": value},
        ):
            if kind is not None:
                g.auth = SimpleNamespace(kind=kind)
            response, status = contacts_add()

        assert status == 200
        row = session.add.call_args_list[0][0][0]
        expected = normalized if kind == "service" else None
        assert row.private_notes == expected
        assert response.json["contact"]["private_notes"] == expected
        assert row.notes == "public note"
        change = session.add.call_args_list[1][0][0]
        assert ("private_notes" in change.changed_fields) == (kind == "service")
        session.commit.assert_called_once()

    @pytest.mark.parametrize("kind", ["service", "user", "read_only", None])
    def test_get_private_notes_permissions(self, monkeypatch, kind):
        from library.contact_routes import contacts_get

        row = _make_contact(private_notes="vault note")
        session = MagicMock()
        session.get.return_value = row
        session.execute.return_value.all.return_value = []
        session.execute.return_value.scalars.return_value.all.return_value = []
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        with Flask(__name__).test_request_context("/contacts/1"):
            if kind is not None:
                g.auth = SimpleNamespace(kind=kind)
            response, status = contacts_get(1)

        assert status == 200
        assert response.json["contact"]["private_notes"] == ("vault note" if kind == "service" else None)
        assert row.private_notes == "vault note"

    @pytest.mark.parametrize("kind", ["service", "user", "read_only", None])
    @pytest.mark.parametrize("value, normalized", [
        ("  updated note  ", "updated note"), ("  ", None), (None, None), ("  vault note  ", "vault note"),
    ])
    def test_patch_private_notes_permissions(self, monkeypatch, kind, value, normalized):
        from library.contact_routes import contacts_update

        row = _make_contact(private_notes="vault note")
        session = MagicMock()
        session.get.return_value = row
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        with Flask(__name__).test_request_context(
            "/contacts/1", method="PATCH", json={"private_notes": value, "notes": "public update"},
        ):
            if kind is not None:
                g.auth = SimpleNamespace(kind=kind)
            response, status = contacts_update(1)

        assert status == 200
        assert row.private_notes == (normalized if kind == "service" else "vault note")
        assert response.json["contact"]["private_notes"] == (normalized if kind == "service" else None)
        assert row.notes == response.json["contact"]["notes"] == "public update"
        change = session.add.call_args[0][0]
        expected_fields = {"notes"}
        if kind == "service" and normalized != "vault note":
            expected_fields.add("private_notes")
        assert set(change.changed_fields) == expected_fields
        session.commit.assert_called_once()
class TestContactEventParticipants:
    @pytest.fixture
    def event_client(self, monkeypatch):
        from library.contact_routes import bp
        from library.db.models import Contact, ContactGroup, ContactGroupEvent

        contacts = {
            1: Contact(id=1, first_name="Anna", last_name="Nowak"),
            2: Contact(id=2, first_name=None, last_name=None, display_label="Dziecko 1"),
            3: Contact(id=3, first_name="Jan", last_name="Nowak"),
        }
        group = ContactGroup(id=3, name="Rodzina")
        event = ContactGroupEvent(id=7, group_id=3, group=group, title="Urodziny",
                                  event_date=dt.date(2026, 9, 13), participants=[contacts[1]])
        session = MagicMock()
        records = {Contact: contacts, ContactGroup: {3: group}, ContactGroupEvent: {7: event}}
        session.get.side_effect = lambda model, ident: records.get(model, {}).get(ident)
        session.execute.return_value.scalars.return_value.all.return_value = [event]
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        app.register_blueprint(bp)
        return app.test_client(), session, event, contacts

    def test_create_participant_only_deduplicates_and_uses_display_name(self, event_client):
        client, session, _, contacts = event_client
        response = client.post("/contact_events", json={
            "title": " Urodziny ", "event_date": "2026-09-13", "participant_contact_ids": [2, 2, 1],
        })
        assert response.status_code == 200
        event = response.json["event"]
        assert event["group_id"] is None
        assert event["group_name"] is None
        assert event["participants"] == [
            {"id": 2, "first_name": None, "last_name": None, "display_name": "Dziecko 1"},
            {"id": 1, "first_name": "Anna", "last_name": "Nowak", "display_name": "Anna Nowak"},
        ]
        added = session.add.call_args.args[0]
        assert added.participants == [contacts[2], contacts[1]]
        assert added in contacts[2].events
        session.commit.assert_called_once()

    @pytest.mark.parametrize("payload", [{}, {"group_id": None}, {"participant_contact_ids": []},
                                         {"group_id": None, "participant_contact_ids": []}])
    def test_create_requires_group_or_participant(self, event_client, payload):
        client, session, _, _ = event_client
        response = client.post("/contact_events", json={"title": "Urodziny", "event_date": "2026-09-13", **payload})
        assert response.status_code == 400
        assert "co najmniej jednym kontaktem" in response.json["message"]
        session.add.assert_not_called()
        session.commit.assert_not_called()

    @pytest.mark.parametrize("path", ["/contact_events", "/contact_groups/3/events"])
    def test_create_with_group_and_participants(self, event_client, path):
        client, session, _, _ = event_client
        response = client.post(path, json={
            "title": "Urodziny", "event_date": "2026-09-13", "group_id": 3, "participant_contact_ids": [1, 2],
        })
        assert response.status_code == 200
        assert response.json["event"]["group_name"] == "Rodzina"
        assert [c["id"] for c in response.json["event"]["participants"]] == [1, 2]
        session.commit.assert_called_once()

    def test_group_url_takes_precedence(self, event_client):
        client, _, _, _ = event_client
        response = client.post("/contact_groups/3/events", json={
            "title": "Urodziny", "event_date": "2026-09-13", "group_id": None,
        })
        assert response.status_code == 200
        assert response.json["event"]["group_id"] == 3

    def test_list_includes_group_and_participant_summaries(self, event_client):
        client, _, _, _ = event_client
        response = client.get("/contact_events")
        assert response.status_code == 200
        assert response.json["events"][0]["group_name"] == "Rodzina"
        assert response.json["events"][0]["participants"][0]["display_name"] == "Anna Nowak"

    def test_patch_replaces_participants_and_detaches_group(self, event_client):
        client, session, event, contacts = event_client
        response = client.patch("/contact_group_events/7", json={"group_id": None, "participant_contact_ids": [2, 3, 2]})
        assert response.status_code == 200
        assert response.json["event"]["group_id"] is None
        assert response.json["event"]["group_name"] is None
        assert event.participants == [contacts[2], contacts[3]]
        assert event.title == "Urodziny"
        session.commit.assert_called_once()

    @pytest.mark.parametrize("initial_group,initial_participants,payload", [
        (3, [1], {"group_id": None, "participant_contact_ids": []}),
        (3, [], {"group_id": None}),
        (None, [1], {"participant_contact_ids": []}),
    ])
    def test_patch_cannot_remove_last_scope(self, event_client, initial_group, initial_participants, payload):
        client, session, event, contacts = event_client
        event.group_id = initial_group
        event.participants = [contacts[ident] for ident in initial_participants]
        response = client.patch("/contact_group_events/7", json={"title": "Changed", **payload})
        assert response.status_code == 400
        assert "co najmniej jednym kontaktem" in response.json["message"]
        assert event.title == "Urodziny"
        assert event.group_id == initial_group
        assert [contact.id for contact in event.participants] == initial_participants
        session.commit.assert_not_called()

    @pytest.mark.parametrize("payload", [{"group_id": None}, {"participant_contact_ids": []}, {"summary": "Notes"}])
    def test_patch_preserves_omitted_scope(self, event_client, payload):
        client, _, event, _ = event_client
        response = client.patch("/contact_group_events/7", json=payload)
        assert response.status_code == 200
        assert event.group_id == payload.get("group_id", 3)
        assert [contact.id for contact in event.participants] == payload.get("participant_contact_ids", [1])

    @pytest.mark.parametrize("payload", [
        {"group_id": True}, {"group_id": "3"}, {"group_id": 999}, {"group_id": 0},
        {"participant_contact_ids": None}, {"participant_contact_ids": "1"},
        {"participant_contact_ids": [True]}, {"participant_contact_ids": [1.5]},
        {"participant_contact_ids": [0]}, {"participant_contact_ids": [1, 999]},
    ])
    @pytest.mark.parametrize("method", ["post", "patch"])
    def test_rejects_invalid_scope_atomically(self, event_client, payload, method):
        client, session, event, contacts = event_client
        path = "/contact_events" if method == "post" else "/contact_group_events/7"
        response = getattr(client, method)(path, json={"title": "Changed", "event_date": "2026-09-13", **payload})
        assert response.status_code == 400
        assert event.title == "Urodziny"
        assert event.participants == [contacts[1]]
        session.commit.assert_not_called()

    @pytest.mark.parametrize("query", ["contact_id=bad", "group_id=0", "contact_id=", "group_id=1.5"])
    def test_invalid_list_filter(self, event_client, query):
        client, session, _, _ = event_client
        assert client.get(f"/contact_events?{query}").status_code == 400
        session.execute.assert_not_called()

    @pytest.mark.parametrize("extra_events", [0, 25])
    def test_contact_event_union_order_limit_and_list_filters(self, event_client, extra_events):
        from sqlalchemy import Column, Date, Integer, MetaData, Table, create_engine
        from library.db.models import ContactGroupEvent

        client, session, _, _ = event_client
        # Execute the endpoint's actual filtering/ordering/limit against a small
        # SQLite fixture; unrelated contact detail queries still use the mock.
        engine = create_engine("sqlite://")
        metadata = MetaData()
        event_table = Table("contact_group_events", metadata, Column("id", Integer, primary_key=True),
                            Column("group_id", Integer), Column("event_date", Date))
        memberships = Table("contact_group_memberships", metadata, Column("contact_id", Integer), Column("group_id", Integer))
        participants = Table("contact_event_participants", metadata, Column("event_id", Integer), Column("contact_id", Integer))
        metadata.create_all(engine)
        # 1: group only; 2: participant only; 3: both; 4: unrelated.
        rows = [dict(id=ident, group_id=group_id, event_date=dt.date(2026, 9, 13))
                for ident, group_id in [(1, 3), (2, None), (3, 3), (4, 4)]]
        rows += [dict(id=ident, group_id=3, event_date=dt.date(2026, 9, 12)) for ident in range(5, 5 + extra_events)]
        events = {row["id"]: ContactGroupEvent(**row, title="Meeting") for row in rows}
        session.get.side_effect = None
        session.get.return_value = _make_contact()
        with engine.begin() as connection:
            connection.execute(event_table.insert(), rows)
            connection.execute(memberships.insert(), [{"contact_id": 1, "group_id": 3}])
            connection.execute(participants.insert(), [{"event_id": ident, "contact_id": 1} for ident in (2, 3)])

            def execute(query):
                result = MagicMock()
                if query.column_descriptions[0].get("entity") is ContactGroupEvent:
                    ids = connection.execute(query.with_only_columns(ContactGroupEvent.id)).scalars().all()
                    result.scalars.return_value.all.return_value = [events[ident] for ident in ids]
                else:
                    result.all.return_value = []
                    result.scalars.return_value.all.return_value = []
                return result

            session.execute.side_effect = execute
            expected = [3, 2, 1] + list(reversed(range(5, 5 + extra_events)))
            response = client.get("/contacts/1")
            assert response.status_code == 200
            assert "group_events" not in response.json["contact"]
            assert [event["id"] for event in response.json["contact"]["events"]] == expected[:20]
            assert [event["id"] for event in client.get("/contact_events?contact_id=1").json["events"]] == expected
            assert [event["id"] for event in client.get("/contact_events?contact_id=1&group_id=3").json["events"]] == [
                ident for ident in expected if ident != 2
            ]
            assert [event["id"] for event in client.get("/contact_events?group_id=4").json["events"]] == [4]
            assert [event["id"] for event in client.get("/contact_events").json["events"]] == [4] + expected
        engine.dispose()

    def test_participant_association_schema(self):
        from library.db.models import ContactEventParticipant, ContactGroupEvent

        table = ContactEventParticipant.__table__
        assert set(table.primary_key.columns.keys()) == {"event_id", "contact_id"}
        assert {fk.ondelete for fk in table.foreign_keys} == {"CASCADE"}
        assert any([column.name for column in index.columns] == ["contact_id"] for index in table.indexes)
        assert not table.c.created_at.nullable
        assert table.c.created_at.server_default is not None
        assert ContactGroupEvent.__table__.c.group_id.nullable
