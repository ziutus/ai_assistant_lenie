"""Multiple channels, legacy compatibility and CSV preservation."""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from flask import Flask
from sqlalchemy import inspect
from sqlalchemy.orm.attributes import instance_state

from library.contact_channels import channel_patch, contact_channels, normalize_channels
from library.db.models import Contact


def entries(*values):
    return [{"value": value, "label": None} for value in values]


@pytest.mark.parametrize("field,legacy,values", [
    ("phone_numbers", "phone_number", ["+48 501 234 567", "+48 502 234 567"]),
    ("email_addresses", "email", ["a@example.com", "b@example.com"]),
])
def test_list_and_legacy_edits_preserve_additional_values(field, legacy, values):
    row = SimpleNamespace(**{field: entries(*values), legacy: values[0]})
    patch = channel_patch({legacy: "replacement"}, row)
    assert patch[field] == entries("replacement", values[1])
    assert patch[legacy] == "replacement"
    cleared = channel_patch({legacy: None}, row)
    assert cleared[field] == entries(values[1])
    assert cleared[legacy] == values[1]
    assert channel_patch({field: []}, row) == {field: [], legacy: None}
    assert channel_patch({}, row) == {}


@pytest.mark.parametrize("payload", [None, "abc", ["abc"], [{"value": ""}],
    [{"value": 123}], [{"value": "x", "label": 123}],
    [{"value": "x", "label": "x" * 101}], [{"value": "x", "is_primary": True}],
    entries("x" * 31), entries("---"), entries("123", "1 23"), entries(*map(str, range(51))),
])
def test_rejects_invalid_phone_lists(payload):
    with pytest.raises(ValueError):
        normalize_channels(payload, "phone_numbers")


def test_normalization_and_email_duplicates():
    assert normalize_channels([{"value": " a@example.com ", "label": " praca "}], "email_addresses") == [
        {"value": "a@example.com", "label": "praca"}]
    with pytest.raises(ValueError, match="duplicate"):
        normalize_channels(entries("A@example.com", "a@example.com"), "email_addresses")
    with pytest.raises(ValueError, match="match"):
        channel_patch({"email": "other@example.com", "email_addresses": entries("a@example.com")})


def test_orm_legacy_insert_and_update_events():
    row = Contact(last_name="Test", phone_number="111", email="a@example.com")
    mapper = inspect(Contact)
    mapper.dispatch.before_insert(mapper, None, instance_state(row))
    assert row.phone_numbers == entries("111")
    assert row.email_addresses == entries("a@example.com")
    # Simulate a persisted state, then an old importer replacing just the scalar.
    row.phone_numbers = entries("111", "222", "333")
    instance_state(row)._commit_all(row.__dict__)
    row.phone_number = None
    mapper.dispatch.before_update(mapper, None, instance_state(row))
    assert row.phone_numbers == entries("222", "333")
    assert row.phone_number == "222"
    instance_state(row)._commit_all(row.__dict__)
    row.phone_numbers = entries("333", "222")
    mapper.dispatch.before_update(mapper, None, instance_state(row))
    assert row.phone_number == "333"


def test_csv_preserves_all_columns_values_and_labels():
    from imports.google_contacts_import import _parse_channels
    row = {"Phone 2 - Value": "222 ::: 333", "Phone 2 - Type": "praca",
           "Phone 1 - Value": "111", "Phone 10 - Value": "444", "Phone 3 - Value": "2 22"}
    assert _parse_channels(row, "Phone", "phone_numbers") == [
        {"value": "111", "label": None}, {"value": "222", "label": "praca"},
        {"value": "333", "label": "praca"}, {"value": "444", "label": None}]


def test_api_create_and_read_multiple_channels(monkeypatch):
    from library.contact_routes import contacts_add
    session = MagicMock()
    session.execute.return_value.scalars.return_value.first.return_value = SimpleNamespace(id=1)
    monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
    with Flask(__name__).test_request_context("/contacts", method="POST", json={
        "last_name": "Test", "phone_numbers": entries("111", "222"),
        "email_addresses": [{"value": "a@example.com", "label": "praca"}, {"value": "b@example.com"}],
    }):
        response, status = contacts_add()
    assert status == 200
    contact = response.json["contact"]
    assert contact["phone_number"] == "111"
    assert contact["phone_numbers"] == entries("111", "222")
    assert contact["email"] == "a@example.com"
    assert len(contact["email_addresses"]) == 2
    assert "phone_numbers" in session.add.call_args_list[-1].args[0].changed_fields


def test_invalid_api_patch_does_not_mutate_contact(monkeypatch):
    from library.contact_routes import contacts_update
    row = Contact(first_name="Jan", last_name="Test", phone_number="111", phone_numbers=entries("111"))
    session = MagicMock()
    session.get.return_value = row
    monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
    with Flask(__name__).test_request_context("/contacts/1", method="PATCH", json={
        "first_name": "Changed", "phone_numbers": entries("222"), "email_addresses": [None],
    }):
        response, status = contacts_update(1)
    assert status == 400
    assert row.first_name == "Jan"
    assert row.phone_numbers == entries("111")
    session.commit.assert_not_called()


def test_api_patch_can_promote_remove_and_clear_channels(monkeypatch):
    from library.contact_routes import contacts_update
    row = Contact(id=1, first_name="Jan", last_name="Test", phone_number="111", phone_numbers=entries("111", "222"))
    session = MagicMock()
    session.get.return_value = row
    monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
    for payload, expected in [({"phone_numbers": entries("222", "111")}, entries("222", "111")),
                              ({"phone_number": None}, entries("111")), ({"phone_numbers": []}, [])]:
        with Flask(__name__).test_request_context("/contacts/1", method="PATCH", json=payload):
            response, status = contacts_update(1)
        assert status == 200
        assert response.json["contact"]["phone_numbers"] == expected
        assert row.phone_number == (expected[0]["value"] if expected else None)


def test_legacy_serialization_fallback():
    assert contact_channels(SimpleNamespace(phone_number="111"), "phone_numbers") == entries("111")
