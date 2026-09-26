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


def _rows(items):
    """A mocked ``session.execute(...)`` result whose ``.scalars().all()`` yields ``items``."""
    result = MagicMock()
    result.scalars.return_value.all.return_value = items
    return result


class TestContactAddresses:
    @pytest.fixture
    def address_api(self, monkeypatch):
        from library.contact_routes import bp
        from library.db.models import Address, ContactAddress
        session = MagicMock()
        contact = _make_contact(id_=7, first_name="Jan", last_name="Kowalski")
        address = Address(id=20, label="dom", street="Example Street", building_number="1", city="Warsaw")
        link = ContactAddress(id=30, contact_id=7, address_id=20, address=address,
                              role="zamieszkania", is_primary=True)
        rows = {("Contact", 7): contact, ("Address", 20): address, ("ContactAddress", 30): link}
        session.get.side_effect = lambda model, ident: rows.get((model.__name__, ident))
        session.execute.return_value.scalars.return_value.all.return_value = []
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        app.register_blueprint(bp)
        return app.test_client(), session, contact, address, link

    def test_list_and_detail_use_nested_addresses_and_primary_order(self, address_api):
        from library.contact_routes import _contact_dict
        client, session, contact, address, link = address_api
        session.execute.return_value.scalars.return_value.all.return_value = [link]
        response = client.get("/contacts/7/addresses")
        assert response.status_code == 200
        assert response.json["addresses"] == [{
            "id": 30, "role": "zamieszkania", "is_primary": True,
            "valid_from": None, "valid_to": None, "is_archived": False, "shared_with": [],
            "address": {"id": 20, "label": "dom", "street": "Example Street", "building_number": "1", "block_number": None, "apartment_number": None,
                        "postal_code": None, "city": "Warsaw", "country": None, "notes": None,
                        "formatted_address": "Example Street 1, Warsaw",
                        "latitude": None, "longitude": None, "geocoded": False, "verified_at": None},
            "duplicate_of_link_id": None,
        }]
        sql = str(session.execute.call_args_list[0].args[0])  # the address list; the next call finds co-users
        assert ("ORDER BY contact_addresses.is_archived, contact_addresses.is_primary DESC, "
                "contact_addresses.id") in sql
        with client.application.test_request_context():
            detail = _contact_dict(contact)
        assert "address" not in detail
        assert detail["addresses"] == response.json["addresses"]

    def test_list_flags_a_later_link_repeating_an_earlier_place(self, address_api):
        from library.db.models import Address, ContactAddress
        client, session, contact, address, link = address_api
        twin = ContactAddress(id=31, contact_id=7, address_id=21, role=None, is_primary=False,
                              address=Address(id=21, street="example street", building_number="1", city="WARSAW"))
        session.execute.return_value.scalars.return_value.all.return_value = [link, twin]
        addresses = client.get("/contacts/7/addresses").json["addresses"]
        assert [entry["duplicate_of_link_id"] for entry in addresses] == [None, 30]

    def test_post_rejects_an_address_the_contact_already_has(self, address_api):
        client, session, contact, address, link = address_api
        session.execute.return_value.scalars.return_value.all.return_value = [link]
        response = client.post("/contacts/7/addresses",
                               json={"street": "Example Street", "building_number": "1", "city": "Warsaw"})
        assert response.status_code == 409
        assert response.json["code"] == "duplicate_address"
        assert response.json["existing"]["id"] == 30
        session.add.assert_not_called()

    def test_post_maps_the_database_duplicate_guard_to_409(self, address_api):
        from sqlalchemy.exc import IntegrityError
        client, session, contact, address, link = address_api
        session.commit.side_effect = IntegrityError("insert", {}, SimpleNamespace(pgcode="23505"))
        response = client.post("/contacts/7/addresses",
                               json={"street": "Other Street", "building_number": "9", "city": "Warsaw"})
        assert response.status_code == 409
        assert response.json["code"] == "duplicate_address"
        session.rollback.assert_called()

    def test_post_keeps_500_for_other_integrity_errors(self, address_api):
        from sqlalchemy.exc import IntegrityError
        client, session, contact, address, link = address_api
        session.commit.side_effect = IntegrityError("insert", {}, SimpleNamespace(pgcode="23503"))
        response = client.post("/contacts/7/addresses",
                               json={"street": "Other Street", "building_number": "9", "city": "Warsaw"})
        assert response.status_code == 500

    def test_post_rejects_choosing_an_existing_address_row_twice(self, address_api):
        client, session, contact, address, link = address_api
        session.execute.return_value.scalars.return_value.all.return_value = [link]
        response = client.post("/contacts/7/addresses", json={"address_id": 20})
        assert response.status_code == 409
        session.add.assert_not_called()

    def test_link_dict_exposes_period_and_archive_flag(self, address_api):
        import datetime
        client, session, contact, address, link = address_api
        link.valid_from, link.valid_to, link.is_archived = datetime.date(2015, 3, 1), datetime.date(2019, 8, 31), True
        link.is_primary = False
        session.execute.return_value.scalars.return_value.all.return_value = [link]
        entry = client.get("/contacts/7/addresses").json["addresses"][0]
        assert (entry["valid_from"], entry["valid_to"], entry["is_archived"]) == ("2015-03-01", "2019-08-31", True)

    def test_archived_links_are_history_not_duplicates(self, address_api):
        from library.db.models import Address, ContactAddress
        client, session, contact, address, link = address_api
        old = ContactAddress(id=31, contact_id=7, address_id=21, is_archived=True, is_primary=False,
                             address=Address(id=21, street="Example Street", building_number="1", city="Warsaw"))
        session.execute.return_value.scalars.return_value.all.return_value = [link, old]
        addresses = client.get("/contacts/7/addresses").json["addresses"]
        assert [entry["duplicate_of_link_id"] for entry in addresses] == [None, None]

    def test_post_allows_moving_back_to_a_place_that_is_archived(self, address_api):
        client, session, contact, address, link = address_api
        link.is_archived, link.is_primary = True, False
        session.execute.return_value.scalars.return_value.all.return_value = [link]
        response = client.post("/contacts/7/addresses",
                               json={"street": "Example Street", "building_number": "1", "city": "Warsaw"})
        assert response.status_code == 200

    def test_post_allows_a_new_stay_at_the_same_row_when_the_earlier_one_is_archived(self, address_api):
        client, session, contact, address, link = address_api
        link.is_archived, link.is_primary = True, False
        session.execute.return_value.scalars.return_value.all.return_value = [link]
        response = client.post("/contacts/7/addresses", json={"address_id": 20})
        assert response.status_code == 200

    def test_post_with_a_past_end_date_stores_an_archived_stay(self, address_api):
        from library.db.models import ContactAddress
        client, session, contact, address, link = address_api
        response = client.post("/contacts/7/addresses", json={
            "street": "Old Street", "building_number": "2", "city": "Warsaw",
            "valid_from": "2015-03-01", "valid_to": "2019-08-31", "sharing_choice": "separate"})
        assert response.status_code == 200
        stay = next(call.args[0] for call in session.add.call_args_list if isinstance(call.args[0], ContactAddress))
        assert stay.is_archived is True and stay.is_primary is False

    def test_patch_archive_clears_primary_and_stores_period(self, address_api):
        import datetime
        client, session, contact, address, link = address_api
        response = client.patch("/contact_addresses/30", json={
            "is_archived": True, "valid_from": "2015-03-01", "valid_to": "2019-08-31"})
        assert response.status_code == 200
        assert link.is_archived is True and link.is_primary is False
        assert (link.valid_from, link.valid_to) == (datetime.date(2015, 3, 1), datetime.date(2019, 8, 31))

    def test_patch_accepts_year_and_month_precision_and_reports_them_back(self, address_api):
        import datetime
        client, session, contact, address, link = address_api
        link.is_primary = False
        response = client.patch("/contact_addresses/30", json={"valid_from": "2016", "valid_to": "2019-08"})
        assert response.status_code == 200
        assert (link.valid_from, link.valid_from_precision) == (datetime.date(2016, 1, 1), "year")
        assert (link.valid_to, link.valid_to_precision) == (datetime.date(2019, 8, 31), "month")
        assert (response.json["address"]["valid_from"], response.json["address"]["valid_to"]) == ("2016", "2019-08")
        assert link.is_archived is True  # the end (31 Aug 2019) is in the past

    def test_an_end_year_is_not_before_a_start_month_of_the_same_year(self, address_api):
        client, session, contact, address, link = address_api
        link.is_primary = False
        ok = client.patch("/contact_addresses/30", json={"valid_from": "2019-06", "valid_to": "2019"})
        assert ok.status_code == 200
        bad = client.patch("/contact_addresses/30", json={"valid_from": "2020", "valid_to": "2019-12"})
        assert bad.status_code == 400

    def test_clearing_a_date_clears_its_precision(self, address_api):
        import datetime
        client, session, contact, address, link = address_api
        link.is_primary = False
        link.valid_from, link.valid_from_precision = datetime.date(2016, 1, 1), "year"
        assert client.patch("/contact_addresses/30", json={"valid_from": None}).status_code == 200
        assert (link.valid_from, link.valid_from_precision) == (None, None)

    def test_patch_past_end_date_archives_automatically_but_future_does_not(self, address_api):
        client, session, contact, address, link = address_api
        link.is_primary = False
        assert client.patch("/contact_addresses/30", json={"valid_to": "2999-01-01"}).status_code == 200
        assert not link.is_archived
        assert client.patch("/contact_addresses/30", json={"valid_to": "2019-08-31"}).status_code == 200
        assert link.is_archived is True

    def test_patch_explicit_flag_wins_over_the_end_date_rule(self, address_api):
        client, session, contact, address, link = address_api
        link.is_primary = False
        response = client.patch("/contact_addresses/30", json={"valid_to": "2019-08-31", "is_archived": False})
        assert response.status_code == 200
        assert not link.is_archived

    @pytest.mark.parametrize("payload", [
        {"is_archived": True, "is_primary": True},
        {"valid_from": "2020-01-01", "valid_to": "2019-01-01"},
        {"valid_from": "2020-13-45"},
        {"valid_from": "20200101"},
        {"valid_from": "03.2015"},
        {"valid_to": "2020-02-30"},
        {"is_archived": "yes"},
    ])
    def test_patch_rejects_invalid_period_or_archive_state(self, address_api, payload):
        client, session, contact, address, link = address_api
        assert client.patch("/contact_addresses/30", json=payload).status_code == 400
        session.commit.assert_not_called()

    def test_patch_cannot_make_an_archived_link_primary(self, address_api):
        client, session, contact, address, link = address_api
        link.is_archived, link.is_primary = True, False
        response = client.patch("/contact_addresses/30", json={"is_primary": True})
        assert response.status_code == 400
        assert link.is_primary is False

    def test_patch_maps_restore_collision_to_409(self, address_api):
        from sqlalchemy.exc import IntegrityError
        client, session, contact, address, link = address_api
        link.is_archived, link.is_primary = True, False
        session.commit.side_effect = IntegrityError("update", {}, SimpleNamespace(pgcode="23505"))
        response = client.patch("/contact_addresses/30", json={"is_archived": False})
        assert response.status_code == 409
        assert response.json["code"] == "duplicate_address"

    def test_create_address_and_audit(self, address_api):
        from library.db.models import ContactAddress, ContactChangeLog
        client, session, _, _, _ = address_api
        response = client.post("/contacts/7/addresses", json={
            "street": " New Street ", "building_number": "2", "city": " Warsaw ", "label": " summer house ",
            "role": "dowolna rola", "is_primary": True,
        })
        assert response.status_code == 200
        link, audit = [call.args[0] for call in session.add.call_args_list]
        assert isinstance(link, ContactAddress)
        assert link.contact_id == 7
        assert link.address.street == "New Street"
        assert link.address.building_number == "2"
        assert link.address.city == "Warsaw"
        assert link.address.country == "Polska"
        assert link.address.label == "summer house"
        assert link.role == "dowolna rola" and link.is_primary
        assert all(getattr(link.address, field) is None for field in ("latitude", "longitude", "location", "geocode_id"))
        assert isinstance(audit, ContactChangeLog)
        assert audit.contact_id == 7 and audit.changed_fields == ["addresses"]
        assert session.commit.call_count == 2  # Persist the post-commit audit too.
        assert [call[0] for call in session.method_calls if call[0] in ("add", "commit")] == [
            "add", "commit", "add", "commit",
        ]

    @pytest.mark.parametrize("initial", [None, " 31A-32 ", "x" * 20])
    def test_block_number_create_update_and_clear(self, address_api, initial):
        client, session, *_ = address_api
        response = client.post("/contacts/7/addresses", json={
            "street": "Bratysławska", "building_number": "15", "block_number": initial,
            "apartment_number": "26", "city": "Łódź",
        })
        assert response.status_code == 200
        address = session.add.call_args_list[0].args[0].address
        assert address.block_number == response.json["address"]["address"]["block_number"] == (
            (initial or "").strip() or None)
        session.get.side_effect = lambda *_: address
        for value in (" 31 ", "x" * 20, "   ", None):
            response = client.patch("/address/20", json={"block_number": value})
            assert response.status_code == 200
            normalized = (value or "").strip() or None
            assert address.block_number == response.json["address"]["block_number"] == normalized
            block = f" blok {normalized}" if normalized else ""
            assert response.json["address"]["formatted_address"] == f"Bratysławska 15{block}/26, Łódź"
            assert address.building_number == "15" and address.apartment_number == "26"

    @pytest.mark.parametrize("value", [31, [], {}, "x" * 21])
    def test_invalid_block_number_rejected_on_create_and_update(self, address_api, value):
        client, session, *_ = address_api
        for method, path, base in (
            (client.post, "/contacts/7/addresses", {"building_number": "15", "city": "Łódź"}),
            (client.patch, "/address/20", {}),
        ):
            response = method(path, json={**base, "block_number": value})
            assert response.status_code == 400
            assert "block_number" in response.json["message"]
        session.commit.assert_not_called()

    def test_attach_reuses_same_address(self, address_api):
        client, session, _, address, _ = address_api
        response = client.post("/contacts/7/addresses", json={"address_id": 20, "role": "praca"})
        assert response.status_code == 200
        link = session.add.call_args_list[0].args[0]
        assert link.address is address
        assert link.is_primary is False

    @pytest.mark.parametrize("initial", [None, "", "  Domofon: 5869  ", "x" * 1000])
    def test_notes_create_update_and_clear_preserve_coordinates(self, address_api, initial):
        client, session, _, _, _ = address_api
        response = client.post("/contacts/7/addresses", json={
            "city": "Warsaw", "building_number": "1", "notes": initial,
        })
        assert response.status_code == 200
        address = session.add.call_args_list[0].args[0].address
        assert address.notes == response.json["address"]["address"]["notes"] == ((initial or "").strip() or None)
        session.get.side_effect = lambda *_: address
        address.latitude, address.longitude, address.location, address.geocode_id = 52, 21, "point", 42
        for notes in ("  Piętro 2\nDzwonić trzy razy  ", "x" * 1000, "   ", None):
            response = client.patch("/address/20", json={"notes": notes})
            assert response.status_code == 200
            assert address.notes == response.json["address"]["notes"] == ((notes or "").strip() or None)
            assert response.json["address"]["formatted_address"] == "1, Warsaw"
            assert (address.latitude, address.longitude, address.location, address.geocode_id) == (52, 21, "point", 42)

    @pytest.mark.parametrize("notes", [42, [], {}, "x" * 1001])
    def test_invalid_notes_rejected_on_create_and_update(self, address_api, notes):
        client, session, *_ = address_api
        assert client.post("/contacts/7/addresses", json={
            "city": "Warsaw", "building_number": "1", "notes": notes,
        }).status_code == 400
        assert client.patch("/address/20", json={"notes": notes}).status_code == 400
        session.commit.assert_not_called()

    @pytest.mark.parametrize("payload", [
        {}, {"city": "   "}, {"city": None}, {"city": 42},
        {"address_id": 20, "block_number": "31"}, {"address_id": 20, "notes": "unexpected"}, {"address_id": "20"}, {"address_id": 20, "city": "unexpected"},
        {"city": "Street", "role": "x" * 51},
        {"city": "Street", "is_primary": "false"},
    ])
    def test_invalid_create_is_400(self, address_api, payload):
        client, session, *_ = address_api
        assert client.post("/contacts/7/addresses", json=payload).status_code == 400
        session.add.assert_not_called()
        session.commit.assert_not_called()

    @pytest.mark.parametrize("method,path,payload", [
        ("get", "/contacts/999/addresses", None),
        ("post", "/contacts/999/addresses", {"city": "Street"}),
        ("post", "/contacts/7/addresses", {"address_id": 999}),
        ("patch", "/address/999", {"label": "home"}),
        ("post", "/address/999/geocode", None),
        ("post", "/address/999/validate", None),
        ("patch", "/contact_addresses/999", {"role": "home"}),
        ("delete", "/contact_addresses/999", None),
    ])
    def test_missing_rows_are_404(self, address_api, method, path, payload):
        client, session, *_ = address_api
        assert getattr(client, method)(path, json=payload).status_code == 404
        session.commit.assert_not_called()

    def test_search_unaccents_and_lists_each_linked_contact_once(self, address_api):
        client, session, contact, address, _ = address_api
        spouse = _make_contact(id_=8, first_name="Anna", last_name="Kowalska")
        result_addresses, result_links = MagicMock(), MagicMock()
        result_addresses.scalars.return_value.all.return_value = [address]
        result_links.scalars.return_value.all.return_value = [
            SimpleNamespace(address_id=20, contact_id=c.id, contact=c) for c in (contact, spouse, contact)
        ]
        session.execute.side_effect = [result_addresses, result_links]
        response = client.get("/addresses?q=Łódź")
        assert response.status_code == 200
        assert response.json["addresses"][0]["linked_contacts"] == [
            {"id": 7, "display_name": "Jan Kowalski"}, {"id": 8, "display_name": "Anna Kowalska"},
        ]
        from sqlalchemy.dialects import postgresql
        compiled = session.execute.call_args_list[0].args[0].compile(dialect=postgresql.dialect())
        assert "unaccent(addresses.city) ILIKE unaccent(" in str(compiled)
        assert "unaccent(addresses.street) ILIKE unaccent(" in str(compiled)
        assert "unaccent(addresses.postal_code) ILIKE unaccent(" in str(compiled)
        assert " OR " in str(compiled)
        assert "%Łódź%" in compiled.params.values()
        assert 20 in compiled.params.values()

    def test_shared_edit_changes_all_links_and_audits_contacts(self, address_api):
        from library.db.models import ContactAddress
        client, session, contact, address, link = address_api
        second_link = ContactAddress(address=address, contact_id=8)
        second_link.contact = _make_contact(id_=8)
        link.contact = contact
        session.execute.side_effect = [
            _rows([link, second_link]),   # links of the shared address
            _rows([]), _rows([]),         # each contact's other addresses (no clash)
            _rows([contact, _make_contact(id_=8)]),  # audit targets
        ]
        response = client.patch("/address/20", json={
            "street": "Changed Street", "building_number": "3", "label": None, "confirm_shared": True})
        assert response.status_code == 200
        assert link.address.street == second_link.address.street == "Changed Street"
        assert link.address.building_number == "3"
        assert address.label is None
        assert {call.args[0].contact_id for call in session.add.call_args_list} == {7, 8}

    def test_moving_a_shared_address_needs_explicit_confirmation(self, address_api):
        from library.db.models import ContactAddress
        client, session, contact, address, link = address_api
        link.contact = contact
        second = ContactAddress(address=address, contact_id=8)
        second.contact = _make_contact(id_=8, first_name="Ola", last_name="Nowak")
        session.execute.side_effect = [_rows([link, second])]
        response = client.patch("/address/20", json={"street": "Elsewhere"})
        assert response.status_code == 409
        assert response.json["code"] == "shared_address"
        assert {entry["id"] for entry in response.json["contacts"]} == {7, 8}
        assert address.street == "Example Street"
        session.commit.assert_not_called()

    def test_moving_an_unshared_address_or_editing_notes_needs_no_confirmation(self, address_api):
        client, session, contact, address, link = address_api
        link.contact = contact
        session.execute.side_effect = [_rows([link]), _rows([]), _rows([contact]), _rows([contact])]
        assert client.patch("/address/20", json={"street": "Elsewhere"}).status_code == 200
        assert client.patch("/address/20", json={"notes": "domofon"}).status_code == 200

    def test_edit_that_would_duplicate_another_address_of_a_linked_contact_is_refused(self, address_api):
        from library.db.models import Address, ContactAddress
        client, session, contact, address, link = address_api
        link.contact = contact
        target = ContactAddress(id=31, contact_id=7, address_id=21, is_archived=False,
                                address=Address(id=21, street="Elsewhere", building_number="1", city="Warsaw"))
        session.execute.side_effect = [_rows([link]), _rows([link, target])]
        response = client.patch("/address/20", json={"street": "Elsewhere"})
        assert response.status_code == 409
        assert response.json["code"] == "duplicate_address"
        assert address.street == "Example Street"

    def test_list_shows_who_else_uses_the_same_address_row(self, address_api):
        from library.db.models import ContactAddress
        client, session, contact, address, link = address_api
        other = ContactAddress(id=40, contact_id=9, address_id=20, address=address, is_archived=False)
        other.contact = _make_contact(id_=9, first_name="Ola", last_name="Nowak")
        session.execute.side_effect = [_rows([link]), _rows([other])]
        entry = client.get("/contacts/7/addresses").json["addresses"][0]
        assert entry["shared_with"] == [{"contact_id": 9, "display_name": "Ola Nowak", "is_archived": False}]

    def _another_contacts_link(self):
        from library.db.models import Address, ContactAddress
        other = ContactAddress(id=40, contact_id=9, address_id=30, is_archived=False,
                               address=Address(id=30, street="Example Street", building_number="1", city="Warsaw",
                                               notes="secret gate code"))
        other.contact = _make_contact(id_=9, first_name="Ola", last_name="Nowak")
        return other

    def test_post_suggests_an_address_other_contacts_already_use(self, address_api):
        client, session, contact, address, link = address_api
        session.execute.side_effect = [_rows([]), _rows([self._another_contacts_link()])]
        response = client.post("/contacts/7/addresses",
                               json={"street": "example street", "building_number": "1", "city": "WARSAW"})
        assert response.status_code == 409
        assert response.json["code"] == "similar_addresses"
        [candidate] = response.json["candidates"]
        assert candidate["address_id"] == 30 and candidate["has_notes"] is True
        assert candidate["linked_contacts"] == [{"id": 9, "display_name": "Ola Nowak", "is_archived": False}]
        assert "secret" not in response.get_data(as_text=True)  # notes are never exposed in a suggestion
        session.add.assert_not_called()

    def test_post_saves_a_separate_address_when_the_user_insists(self, address_api):
        client, session, contact, address, link = address_api
        session.execute.side_effect = [_rows([])]
        response = client.post("/contacts/7/addresses", json={
            "street": "Example Street", "building_number": "1", "city": "Warsaw", "sharing_choice": "separate"})
        assert response.status_code == 200
        assert session.execute.call_count >= 1

    def test_city_only_addresses_are_never_suggested_and_cost_no_query(self):
        from library.contact_routes import _similar_address_candidates
        from library.db.models import Address
        session = MagicMock()
        assert _similar_address_candidates(session, 7, Address(city="Łódź")) == []
        session.execute.assert_not_called()

    def test_an_apartment_mismatch_is_not_the_same_place(self):
        from library.contact_routes import _similar_address_candidates
        from library.db.models import Address
        session = MagicMock()
        other = self._another_contacts_link()
        other.address.apartment_number = "12"
        session.execute.return_value = _rows([other])
        assert _similar_address_candidates(
            session, 7, Address(street="Example Street", building_number="1", apartment_number="3", city="Warsaw")) == []
        assert len(_similar_address_candidates(
            session, 7, Address(street="Example Street", building_number="1", apartment_number="12", city="Warsaw"))) == 1

    def test_post_with_address_id_shares_the_existing_row_without_suggestions(self, address_api):
        client, session, contact, address, link = address_api
        session.execute.side_effect = [_rows([])]
        response = client.post("/contacts/7/addresses", json={"address_id": 20, "role": "zamieszkania"})
        assert response.status_code == 200

    @pytest.mark.parametrize("payload", [
        {"street": "S", "building_number": "1", "city": "W", "sharing_choice": "merge"},
        {"address_id": 20, "sharing_choice": "separate"},
        {"confirm_shared": "yes"},
    ])
    def test_new_flags_are_validated(self, address_api, payload):
        client, session, contact, address, link = address_api
        url = "/address/20" if "confirm_shared" in payload else "/contacts/7/addresses"
        call = client.patch if "confirm_shared" in payload else client.post
        assert call(url, json=payload).status_code == 400

    def test_geocode_resolved_audits_every_linked_contact(self, address_api, monkeypatch):
        client, session, contact, address, _ = address_api
        session.execute.return_value.scalars.return_value.all.return_value = [contact, _make_contact(id_=8)]

        def resolve(db_session, row):
            assert db_session is session and row is address
            row.latitude, row.longitude = 52.2297, 21.0122
            return True

        geocode = MagicMock(side_effect=resolve)
        monkeypatch.setattr("library.contact_routes.geocode_address", geocode)
        response = client.post("/address/20/geocode")
        assert response.status_code == 200
        assert response.json == {
            "status": "success", "resolved": True,
            "address": {"id": 20, "label": "dom", "street": "Example Street", "building_number": "1", "block_number": None, "apartment_number": None,
                        "postal_code": None, "city": "Warsaw", "country": None, "notes": None,
                        "formatted_address": "Example Street 1, Warsaw",
                        "latitude": 52.2297, "longitude": 21.0122, "geocoded": True, "verified_at": None},
        }
        geocode.assert_called_once_with(session, address)
        audits = [call.args[0] for call in session.add.call_args_list]
        assert {audit.contact_id for audit in audits} == {7, 8}
        assert all(audit.source == "manual_edit" and audit.changed_fields == ["addresses"] for audit in audits)
        assert [call[0] for call in session.method_calls if call[0] in ("add", "commit")] == [
            "add", "add", "commit",
        ]
        query = session.execute.call_args.args[0]
        assert "contact_addresses.address_id" in str(query)
        assert 20 in query.compile().params.values()

    def test_geocode_unresolved_still_succeeds(self, address_api, monkeypatch):
        client, session, contact, address, _ = address_api
        session.execute.return_value.scalars.return_value.all.return_value = [contact]
        geocode = MagicMock(return_value=False)
        monkeypatch.setattr("library.contact_routes.geocode_address", geocode)
        response = client.post("/address/20/geocode")
        assert response.status_code == 200
        assert response.json["status"] == "success"
        assert response.json["resolved"] is False
        assert response.json["address"]["geocoded"] is False
        assert response.json["address"]["latitude"] is None
        assert response.json["address"]["longitude"] is None
        geocode.assert_called_once_with(session, address)
        assert session.add.call_args.args[0].changed_fields == ["addresses"]
        session.commit.assert_called_once()

    def test_geocode_database_error_rolls_back(self, address_api, monkeypatch):
        client, session, *_ = address_api
        monkeypatch.setattr("library.contact_routes.geocode_address", MagicMock(return_value=False))
        session.commit.side_effect = RuntimeError("synthetic failure")
        response = client.post("/address/20/geocode")
        assert response.status_code == 500
        assert response.json == {"status": "error", "message": "DB error"}
        session.rollback.assert_called_once()

    def test_geocode_options_does_not_access_database(self, address_api):
        client, session, *_ = address_api
        assert client.options("/address/20/geocode").status_code == 200
        session.get.assert_not_called()
        session.commit.assert_not_called()

    @pytest.mark.parametrize("outcome", ["confirmed", "not_found"])
    def test_validate_response_and_audit_every_linked_contact(self, address_api, monkeypatch, outcome):
        client, session, contact, address, _ = address_api
        session.execute.return_value.scalars.return_value.all.return_value = [contact, _make_contact(id_=8)]
        verified = dt.datetime(2026, 9, 20, 12, 30)
        result = {"outcome": outcome, "official_postal_code": "50-106" if outcome == "confirmed" else None,
                  "postal_code_matches": True if outcome == "confirmed" else None,
                  "score": 0.98 if outcome == "confirmed" else None}

        def validate(db_session, row):
            assert db_session is session and row is address
            row.verified_at = verified
            return result

        validator = MagicMock(side_effect=validate)
        monkeypatch.setattr("library.contact_routes.validate_address", validator)
        response = client.post("/address/20/validate")
        assert response.status_code == 200
        assert response.json == {
            "status": "success", **result,
            "address": {"id": 20, "label": "dom", "street": "Example Street", "building_number": "1", "block_number": None,
                        "apartment_number": None, "postal_code": None, "city": "Warsaw", "country": None,
                        "notes": None, "formatted_address": "Example Street 1, Warsaw",
                        "latitude": None, "longitude": None, "geocoded": False,
                        "verified_at": verified.isoformat()},
        }
        validator.assert_called_once_with(session, address)
        audits = [call.args[0] for call in session.add.call_args_list]
        assert {audit.contact_id for audit in audits} == {7, 8}
        assert all(audit.source == "manual_edit" and audit.changed_fields == ["addresses"] for audit in audits)
        assert [call[0] for call in session.method_calls if call[0] in ("add", "commit")] == [
            "add", "add", "commit",
        ]
        query = session.execute.call_args.args[0]
        assert "contact_addresses.address_id" in str(query)
        assert 20 in query.compile().params.values()

    @pytest.mark.parametrize("previous", [None, dt.datetime(2026, 1, 2, 3, 4)])
    def test_validate_unavailable_is_200_and_preserves_verified_at(self, address_api, monkeypatch, previous):
        client, session, contact, address, _ = address_api
        address.verified_at = previous
        session.execute.return_value.scalars.return_value.all.return_value = [contact]
        result = {"outcome": "unavailable", "official_postal_code": None,
                  "postal_code_matches": None, "score": None}
        validator = MagicMock(return_value=result)
        monkeypatch.setattr("library.contact_routes.validate_address", validator)
        response = client.post("/address/20/validate")
        assert response.status_code == 200
        assert response.json["status"] == "success"
        assert {key: response.json[key] for key in result} == result
        assert address.verified_at == previous
        assert response.json["address"]["verified_at"] == (previous.isoformat() if previous else None)
        validator.assert_called_once_with(session, address)
        assert session.add.call_args.args[0].changed_fields == ["addresses"]
        session.commit.assert_called_once()

    @pytest.mark.parametrize("outcome", ["confirmed", "not_found", "unavailable"])
    @pytest.mark.parametrize("coordinates", [(None, None), (51.746111, None), (None, 19.418129), (51.746111, 19.418129)])
    def test_validate_osm_gating_through_real_domain(self, address_api, monkeypatch, outcome, coordinates):
        client, _, _, address, _ = address_api
        address.latitude, address.longitude = coordinates
        hit = {"outcome": outcome, "match": {"nr_budynku": "1"}} if outcome != "unavailable" else None
        monkeypatch.setattr("library.address_validation_client.validate_address_external", lambda _: hit)
        supplement = {"found": True, "postal_code": None, "nearby_postal_code": "94-039", "housename": "blok 31",
                      "lat": 51.74869, "lon": 19.4211182, "osm_id": 106305382, "osm_type": "way"}
        osm = MagicMock(return_value=supplement)
        monkeypatch.setattr("library.address_overpass_client.find_osm_building_match", osm)
        response = client.post("/address/20/validate")
        assert response.status_code == 200
        assert response.json["outcome"] == outcome
        if outcome != "confirmed" and all(value is not None for value in coordinates):
            osm.assert_called_once_with(*coordinates, address.street, address.building_number)
            assert response.json["osm_supplement"] == supplement
        else:
            osm.assert_not_called()
            assert response.json.get("osm_supplement") is None

    @pytest.mark.parametrize("outcome", ["not_found", "unavailable"])
    @pytest.mark.parametrize("previous", [None, dt.datetime(2026, 1, 2, 3, 4)])
    @pytest.mark.parametrize("supplement", [
        None, {"found": False, "postal_code": None, "nearby_postal_code": None},
        {"found": False, "postal_code": None, "nearby_postal_code": "94-039"},
        {"found": True, "postal_code": "94-039", "housename": "blok 31"},
    ])
    def test_validate_osm_response_preserves_registry_decision(self, address_api, monkeypatch, outcome, previous, supplement):
        client, _, _, address, _ = address_api
        address.latitude, address.longitude = 51.746111, 19.418129
        address.verified_at = previous
        monkeypatch.setattr("library.address_validation_client.validate_address_external",
                            lambda _: {"outcome": "not_found"} if outcome == "not_found" else None)
        timestamps_at_lookup = []

        def lookup(*args):
            timestamps_at_lookup.append(address.verified_at)
            return supplement

        monkeypatch.setattr("library.address_overpass_client.find_osm_building_match", lookup)
        before = dt.datetime.now()
        response = client.post("/address/20/validate")
        assert response.status_code == 200
        assert response.json["outcome"] == outcome
        assert response.json["osm_supplement"] == supplement
        assert response.json["official_postal_code"] is None
        assert address.verified_at == timestamps_at_lookup[0]
        if outcome == "not_found":
            assert before <= address.verified_at <= dt.datetime.now()
        else:
            assert address.verified_at == previous
        assert response.json["address"]["verified_at"] == (
            address.verified_at.isoformat() if address.verified_at else None
        )
        assert response.json["address"]["postal_code"] is None
        assert (response.json["address"]["latitude"], response.json["address"]["longitude"]) == (51.746111, 19.418129)

    def test_validate_database_error_rolls_back(self, address_api, monkeypatch):
        client, session, *_ = address_api
        monkeypatch.setattr("library.contact_routes.validate_address", MagicMock(return_value={"outcome": "unavailable"}))
        session.commit.side_effect = RuntimeError("synthetic failure")
        response = client.post("/address/20/validate")
        assert response.status_code == 500
        session.rollback.assert_called_once()

    def test_validate_options_does_not_access_database(self, address_api):
        client, session, *_ = address_api
        assert client.options("/address/20/validate").status_code == 200
        session.get.assert_not_called()
        session.commit.assert_not_called()

    @pytest.mark.parametrize("value", ["", "  ", None])
    def test_shared_address_cannot_be_blanked(self, address_api, value):
        client, session, _, address, _ = address_api
        assert client.patch("/address/20", json={"city": value}).status_code == 400
        assert address.city == "Warsaw"
        session.commit.assert_not_called()

    def test_patch_link_does_not_change_shared_address(self, address_api):
        client, session, _, address, link = address_api
        response = client.patch("/contact_addresses/30", json={
            "role": "korespondencyjny", "is_primary": False, "city": "Ignored",
        })
        assert response.status_code == 200
        assert link.role == "korespondencyjny" and not link.is_primary
        assert address.city == "Warsaw"
        assert session.add.call_args.args[0].changed_fields == ["addresses"]

    def test_delete_only_unlinks_and_keeps_address(self, address_api):
        client, session, _, address, link = address_api
        assert client.delete("/contact_addresses/30").status_code == 200
        session.delete.assert_called_once_with(link)
        assert address.city == "Warsaw"
        assert session.add.call_args.args[0].changed_fields == ["addresses"]

    def test_database_error_rolls_back(self, address_api):
        client, session, *_ = address_api
        session.commit.side_effect = RuntimeError("synthetic failure")
        assert client.post("/contacts/7/addresses", json={"address_id": 20}).status_code == 500
        session.rollback.assert_called_once()
        session.add.assert_called_once()  # No audit for an unsuccessful change.

    @pytest.mark.parametrize("postal_code", ["95-054", None, ""])
    def test_create_village_address(self, address_api, postal_code):
        client, session, *_ = address_api
        response = client.post("/contacts/7/addresses", json={
            "city": "Wyczółki", "building_number": "32", "postal_code": postal_code,
        })
        assert response.status_code == 200
        address = response.json["address"]["address"]
        assert address["street"] is None
        assert address["country"] == "Polska"
        assert address["formatted_address"] == ("32, 95-054 Wyczółki" if postal_code else "32, Wyczółki")

    @pytest.mark.parametrize("postal_code", ["95054", "1-234", "AB-CDE", "95-054 Ksawerów", "１２-３４５"])
    def test_malformed_postal_code_rejected_on_create_and_patch(self, address_api, postal_code):
        client, session, *_ = address_api
        for method, path, payload in [
            (client.post, "/contacts/7/addresses", {"city": "Ksawerów", "building_number": "15"}),
            (client.patch, "/address/20", {}),
        ]:
            response = method(path, json={**payload, "postal_code": postal_code})
            assert response.status_code == 400
            assert "postal_code" in response.json["message"]
        session.commit.assert_not_called()

    @pytest.mark.parametrize("field, limit", [
        ("street", 200), ("building_number", 20), ("block_number", 20), ("apartment_number", 20),
        ("postal_code", 10), ("city", 200), ("country", 100), ("notes", 1000),
    ])
    def test_address_fields_validate_type_and_length(self, address_api, field, limit):
        client, session, *_ = address_api
        for value in (42, "x" * (limit + 1)):
            assert client.patch("/address/20", json={field: value}).status_code == 400
        session.commit.assert_not_called()

    def test_building_required_for_creation_but_fallback_can_be_edited(self, address_api):
        client, session, _, address, _ = address_api
        assert client.post("/contacts/7/addresses", json={"city": "Wyczółki"}).status_code == 400
        assert client.patch("/address/20", json={"building_number": None}).status_code == 400
        address.city, address.building_number = "unparsed legacy address", None
        assert client.patch("/address/20", json={"label": "do poprawy"}).status_code == 200
        assert address.city == "unparsed legacy address"

    def test_explicit_null_country_is_not_defaulted(self, address_api):
        client, *_ = address_api
        response = client.post("/contacts/7/addresses", json={"city": "Wyczółki", "building_number": "32", "country": None})
        assert response.status_code == 200
        assert response.json["address"]["address"]["country"] is None

    def test_coordinate_invalidation_only_for_changed_components(self, address_api):
        client, _, _, address, _ = address_api
        address.latitude, address.longitude, address.geocode_id = 52, 21, 1
        assert client.patch("/address/20", json={"label": "home", "street": "Example Street"}).status_code == 200
        assert address.latitude == 52 and address.geocode_id == 1
        assert client.patch("/address/20", json={"postal_code": "00-001"}).status_code == 200
        assert all(getattr(address, field) is None for field in ("latitude", "longitude", "location", "geocode_id"))

    def test_parse_address_success_and_schema(self, address_api, monkeypatch):
        import json
        from library.address_parsing import DEFAULT_ADDRESS_PARSE_MODEL
        client, session, *_ = address_api
        fields = dict(street=None, building_number="32", block_number=None, apartment_number=None,
                      postal_code="08-207", city="Wyczółki", country=None, notes="Domofon: 5869")
        ask = MagicMock(return_value=SimpleNamespace(response_text=json.dumps(fields)))
        monkeypatch.setattr("library.address_parsing.ai_ask", ask)
        monkeypatch.setattr("library.address_parsing.load_config", lambda: {})
        response = client.post("/addresses/parse", json={"text": "Wyczółki 32, 08-207 Wyczółki. Domofon: 5869"})
        assert response.status_code == 200
        assert response.json == {"status": "success", **fields}
        assert ask.call_args.args == ("Wyczółki 32, 08-207 Wyczółki. Domofon: 5869",)
        kwargs = ask.call_args.kwargs
        assert kwargs["model"] == DEFAULT_ADDRESS_PARSE_MODEL
        assert kwargs["temperature"] == 0.0 and kwargs["operation"] == "address_parse"
        assert kwargs["response_format"]["type"] == "json_schema"
        schema = kwargs["response_format"]["json_schema"]["schema"]
        assert set(schema["required"]) == set(fields)
        assert schema["additionalProperties"] is False
        assert all(value["type"] == ["string", "null"] for value in schema["properties"].values())
        session.get.assert_not_called()

    @pytest.mark.parametrize("response_text", [
        "not JSON", '{"city": "Warszawa"}', "null", "[]", None,
        '{"city": 7, "street": null, "building_number": null, "block_number": null, "apartment_number": null, "postal_code": null, "country": null, "notes": null}',
    ])
    def test_parse_malformed_response_is_empty_success(self, address_api, monkeypatch, response_text):
        from library.address_formatting import ADDRESS_FIELD_LIMITS
        client, *_ = address_api
        monkeypatch.setattr("library.address_parsing.ai_ask", MagicMock(return_value=SimpleNamespace(response_text=response_text)))
        monkeypatch.setattr("library.address_parsing.load_config", lambda: {})
        response = client.post("/addresses/parse", json={"text": "test"})
        assert response.status_code == 200
        assert response.json == {"status": "success", **dict.fromkeys((*ADDRESS_FIELD_LIMITS, "notes"))}

    @pytest.mark.parametrize("failure", [RuntimeError("provider unavailable"), SystemExit(1)])
    @pytest.mark.parametrize("target", ["ai_ask", "load_config"])
    def test_parse_exceptions_are_empty_success(self, address_api, monkeypatch, failure, target):
        from library.address_formatting import ADDRESS_FIELD_LIMITS
        client, *_ = address_api
        monkeypatch.setattr("library.address_parsing.load_config", lambda: {})
        monkeypatch.setattr(f"library.address_parsing.{target}", MagicMock(side_effect=failure))
        response = client.post("/addresses/parse", json={"text": "test"})
        assert response.status_code == 200
        assert response.json == {"status": "success", **dict.fromkeys((*ADDRESS_FIELD_LIMITS, "notes"))}

    @pytest.mark.parametrize("payload", [None, [], {}, {"text": None}, {"text": 42}, {"text": " "}])
    def test_empty_parse_input_does_not_call_llm(self, address_api, monkeypatch, payload):
        client, *_ = address_api
        ask = MagicMock()
        monkeypatch.setattr("library.address_parsing.ai_ask", ask)
        assert client.post("/addresses/parse", json=payload).status_code == 200
        ask.assert_not_called()

    def test_parse_model_is_configurable(self, address_api, monkeypatch):
        client, *_ = address_api
        ask = MagicMock(return_value=SimpleNamespace(response_text="{}"))
        monkeypatch.setattr("library.address_parsing.ai_ask", ask)
        monkeypatch.setattr("library.address_parsing.load_config", lambda: {"ADDRESS_PARSE_MODEL": "Bielik-11B-v2.3-Instruct"})
        assert client.post("/addresses/parse", json={"text": "test"}).status_code == 200
        assert ask.call_args.kwargs["model"] == "Bielik-11B-v2.3-Instruct"


def _make_category(id_=1, name="Osoba prywatna"):
    return SimpleNamespace(id=id_, name=name, description=None, is_active=True)


def _make_contact(id_=1, last_name="Wojtysiak", first_name="Adam", category=None, **extra):
    defaults = dict(
        uuid="11111111-1111-1111-1111-111111111111",
        category_id=category.id if category else 1,
        category=category or _make_category(),
        first_name=first_name,
        last_name=last_name,
        gender=None,
        display_label=None,
        phone_number="+48 725 428 453",
        email=None, company=None, position=None,
        current_city=None, hometown=None, birthday=None, pesel=None, notes=None, private_notes=None, groups=[], interests=[], whatsapp_profile=None,
        birthday_month=None, birthday_day=None,
        languages=[], nationality=[], photo_storage_key=None, photo_thumbnail_storage_key=None, is_archived=False,
        created_at=dt.datetime(2026, 8, 23, 12, 0),
        updated_at=dt.datetime(2026, 8, 23, 12, 0),
    )
    defaults.update(extra)
    return SimpleNamespace(id=id_, **defaults)


class TestContactChatConversations:
    def test_returns_conversations_ordered_by_last_message(self):
        from library.contact_routes import _contact_chat_conversations

        session = MagicMock()
        session.execute.return_value.all.return_value = [
            (2, "Tuwima Gardens - Czat ogólny", "whatsapp", 42, dt.datetime(2026, 9, 1, 10, 0)),
        ]
        result = _contact_chat_conversations(session, 380)
        assert result == [{
            "id": 2, "display_name": "Tuwima Gardens - Czat ogólny", "platform": "whatsapp",
            "message_count": 42, "last_message_at": "2026-09-01T10:00:00",
        }]

    def test_no_conversations_returns_empty_list(self):
        from library.contact_routes import _contact_chat_conversations

        session = MagicMock()
        session.execute.return_value.all.return_value = []
        assert _contact_chat_conversations(session, 380) == []


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
        assert added.phone_number == "+48725428453"
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
        row = _make_contact(groups=[], interests=[])
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


class TestContactsUpcomingBirthdays:
    def _run(self, monkeypatch, query_string="", rows=()):
        from library import contact_routes

        class FixedDate(dt.date):
            @classmethod
            def today(cls):
                return cls(2026, 12, 15)

        monkeypatch.setattr(contact_routes, "datetime", SimpleNamespace(date=FixedDate))
        session = MagicMock()
        session.execute.return_value.scalars.return_value.all.return_value = rows
        monkeypatch.setattr(contact_routes, "get_scoped_session", lambda: session)
        with Flask(__name__).test_request_context(f"/contacts/upcoming_birthdays{query_string}"):
            response = contact_routes.contacts_upcoming_birthdays()
        assert response.status_code == 200
        assert response.json["status"] == "success"
        statement = session.execute.call_args[0][0]
        return response.json["upcoming_birthdays"], str(statement.whereclause)

    def test_default_window_includes_today_and_day_30_excludes_day_31_and_sorts(self, monkeypatch):
        entries, where = self._run(monkeypatch, rows=[
            _make_contact(id_=1, birthday_month=1, birthday_day=14),
            _make_contact(id_=2, birthday=dt.date(1990, 1, 15)),
            _make_contact(id_=3, birthday_month=12, birthday_day=15),
            _make_contact(id_=4, birthday=dt.date(1990, 12, 20)),
            _make_contact(id_=5),
        ])
        assert [entry["contact_id"] for entry in entries] == [3, 4, 1]
        assert [entry["days_until"] for entry in entries] == [0, 5, 30]
        assert "contacts.birthday IS NOT NULL OR contacts.birthday_month IS NOT NULL AND contacts.birthday_day IS NOT NULL" in where

    @pytest.mark.parametrize("query, predicate", [
        ("", "contacts.is_archived IS false"),
        ("?archived=1", "contacts.is_archived IS true"),
        ("?archived=true", "contacts.is_archived IS true"),
        ("?archived=yes", "contacts.is_archived IS true"),
        ("?archived=%20TRUE%20", "contacts.is_archived IS true"),
        ("?archived=0", "contacts.is_archived IS false"),
        ("?archived=all", None),
    ])
    def test_archived_sql_filter_matches_contacts_list(self, monkeypatch, query, predicate):
        _, where = self._run(monkeypatch, query)
        if predicate is None:
            assert "is_archived" not in where
        else:
            assert predicate in where

    @pytest.mark.parametrize("days, expected", [
        ("0", [1]), ("-10", [1]), ("5", [1, 2]),
        ("invalid", [1, 2]), ("365", [1, 2, 3]), ("999", [1, 2, 3]),
    ])
    def test_days_parsing_and_clamping(self, monkeypatch, days, expected):
        entries, _ = self._run(monkeypatch, f"?days={days}", rows=[
            _make_contact(id_=1, birthday_month=12, birthday_day=16),
            _make_contact(id_=2, birthday_month=12, birthday_day=20),
            _make_contact(id_=3, birthday_month=12, birthday_day=14),
        ])
        assert [entry["contact_id"] for entry in entries] == expected


class TestContactsListArchivedFilter:
    def test_relationship_chips_use_placeholder_names(self):
        from library.contact_routes import _load_contact_relationships_summary
        session = MagicMock()
        session.execute.return_value.all.side_effect = [
            [(1, "dziecko", None, None, "Dziecko 1", None)],
            [(1, "bliźnięta", None, None, "Dziecko 2", None)],
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

    def test_search_includes_primary_and_additional_channels(self, monkeypatch):
        compiled = self._run(monkeypatch, "?q=praca")
        assert "contacts.phone_number" in compiled
        assert "contacts.email" in compiled
        assert "jsonb_array_elements(contacts.phone_numbers)" in compiled
        assert "jsonb_array_elements(contacts.email_addresses)" in compiled

    def test_phone_search_ignores_formatting(self, monkeypatch):
        compiled = self._run(monkeypatch, "?q=0048%20501-234-567")
        assert "regexp_replace" in compiled

    def test_search_includes_company(self, monkeypatch):
        compiled = self._run(monkeypatch, "?q=kal")
        assert "contacts.company" in compiled


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

    def test_adds_email_candidate(self, monkeypatch):
        from library.contact_routes import contact_lookup_results_add

        session = MagicMock()
        session.get.return_value = _make_contact(id_=1)
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context(
            "/contacts/1/lookup_results", method="POST",
            json={
                "lookup_type": "email", "status": "candidate",
                "url": "kontakt@example-firma.pl",
                "notes": "Adres znaleziony w CEIDG przy weryfikacji firmy",
            },
        ):
            response = contact_lookup_results_add(1)

        assert response[1] == 200
        added = session.add.call_args[0][0]
        assert added.lookup_type == "email"
        assert added.status == "candidate"
        assert added.url == "kontakt@example-firma.pl"

    def test_adds_facebook_check_record(self, monkeypatch):
        from library.contact_routes import contact_lookup_results_add

        session = MagicMock()
        session.get.return_value = _make_contact(id_=1)
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context(
            "/contacts/1/lookup_results", method="POST",
            json={
                "lookup_type": "facebook", "status": "no_results",
                "url": "https://www.facebook.com/profile.php?id=1",
                "notes": "płeć: tak; miasto: brak; zdjęcie: brak (szara sylwetka)",
            },
        ):
            response = contact_lookup_results_add(1)

        assert response[1] == 200
        added = session.add.call_args[0][0]
        assert added.lookup_type == "facebook"
        assert added.status == "no_results"

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
            json={"lookup_type": "tiktok", "status": "no_results"},
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
    @pytest.mark.parametrize("existing_url", [None, "https://www.linkedin.com/in/old/",
                                               "https://www.linkedin.com/in/adam-wojtysiak/"])
    def test_confirming_linkedin_candidate_updates_contact_link(self, monkeypatch, existing_url):
        from library.contact_routes import contact_lookup_results_update

        from library.db.models import ContactChangeLog, ContactLink

        contact = _make_contact(id_=1)
        lookup_result = _make_lookup_result(
            id_=7, contact_id=1, lookup_type="linkedin", status="candidate",
            url="https://www.linkedin.com/in/adam-wojtysiak/",
        )
        existing = ContactLink(id=42, contact_id=1, link_type="linkedin", url=existing_url) if existing_url else None
        session = MagicMock()
        session.scalars.return_value = [existing] if existing else []
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
        added_links = [call.args[0] for call in session.add.call_args_list if isinstance(call.args[0], ContactLink)]
        if existing_url is None:
            assert len(added_links) == 1
            assert added_links[0].contact_id == 1
            assert added_links[0].link_type == "linkedin"
            assert added_links[0].url == lookup_result.url
        else:
            assert added_links == []
            assert existing.id == 42
            assert existing.url == lookup_result.url
        logs = [call.args[0] for call in session.add.call_args_list if isinstance(call.args[0], ContactChangeLog)]
        if existing_url == lookup_result.url:
            assert logs == []
        else:
            assert len(logs) == 1
            assert logs[0].changed_fields == ["links"]
            assert logs[0].source == "linkedin_analysis"
            assert logs[0].note == "Potwierdzony wynik OSINT (lookup #7)"

    def test_rejecting_candidate_does_not_touch_contact(self, monkeypatch):
        from library.contact_routes import contact_lookup_results_update

        contact = _make_contact(id_=1)
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
        session.scalars.assert_not_called()
        session.add.assert_not_called()

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
        registry=None, role=None, nip=None, regon=None, address=None, correspondence_address=None, website=None,
        is_primary=False, is_current=True, start_date=None, end_date=None,
        suspended_at=None, verified_at=None,
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

    @pytest.mark.parametrize("payload, expected", [
        ({"org_type": "jdg"}, "ceidg"),  # a JDG is by definition a CEIDG entry
        ({"org_type": "jdg", "registry": "krs"}, "krs"),  # explicit value wins over the default
        ({"org_type": "employment"}, None),  # relation to the person says nothing about the register
        ({"org_type": "employment", "registry": "krs"}, "krs"),
        ({"org_type": "employment", "registry": "  KRS "}, "krs"),  # trimmed and lower-cased
        ({"org_type": "employment", "registry": ""}, None),
    ])
    def test_registry_resolution(self, monkeypatch, payload, expected):
        from library.contact_routes import contact_organizations_add

        session = MagicMock()
        session.get.return_value = _make_contact(id_=1)
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context(
            "/contacts/1/organizations", method="POST", json={"organization_name": "Acme", **payload},
        ):
            response = contact_organizations_add(1)

        assert response[1] == 200
        assert session.add.call_args[0][0].registry == expected

    def test_invalid_registry_is_400(self, monkeypatch):
        from library.contact_routes import contact_organizations_add

        session = MagicMock()
        session.get.return_value = _make_contact(id_=1)
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context(
            "/contacts/1/organizations", method="POST",
            json={"org_type": "employment", "organization_name": "Acme", "registry": "regon"},
        ):
            response = contact_organizations_add(1)

        assert response[1] == 400
        session.add.assert_not_called()


class TestContactOrganizationsUpdate:
    def test_sets_registry(self, monkeypatch):
        from library.contact_routes import contact_organizations_update

        row = _make_organization(id_=6, org_type="employment")
        session = MagicMock()
        session.get.return_value = row
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context("/contact_organizations/6", method="PATCH", json={"registry": "krs"}):
            response = contact_organizations_update(6)

        assert response[1] == 200
        assert row.registry == "krs"

    def test_empty_registry_clears_to_unknown(self, monkeypatch):
        from library.contact_routes import contact_organizations_update

        row = _make_organization(id_=6, org_type="employment", registry="krs")
        session = MagicMock()
        session.get.return_value = row
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context("/contact_organizations/6", method="PATCH", json={"registry": ""}):
            response = contact_organizations_update(6)

        assert response[1] == 200
        assert row.registry is None

    def test_registry_untouched_when_not_in_payload(self, monkeypatch):
        from library.contact_routes import contact_organizations_update

        row = _make_organization(id_=6, org_type="employment", registry="krs")
        session = MagicMock()
        session.get.return_value = row
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context("/contact_organizations/6", method="PATCH", json={"status": "confirmed"}):
            response = contact_organizations_update(6)

        assert response[1] == 200
        assert row.registry == "krs"

    def test_invalid_registry_is_400_and_leaves_row_alone(self, monkeypatch):
        from library.contact_routes import contact_organizations_update

        row = _make_organization(id_=6, org_type="employment", registry="krs")
        session = MagicMock()
        session.get.return_value = row
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context("/contact_organizations/6", method="PATCH", json={"registry": "regon"}):
            response = contact_organizations_update(6)

        assert response[1] == 400
        assert row.registry == "krs"

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


class TestContactOrganizationsCeidgLookup:
    def test_creates_new_jdg_from_ceidg_match(self, monkeypatch):
        from library.contact_routes import contact_organizations_ceidg_lookup

        session = MagicMock()
        session.get.return_value = _make_contact(id_=1)
        session.execute.return_value.scalars.return_value.all.return_value = []
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        monkeypatch.setattr(
            "library.ceidg_client.get_company_by_nip",
            lambda nip: {"nazwa": "KRATON", "adresDzialalnosci": {}},
        )
        app = Flask(__name__)
        with app.test_request_context(
            "/contacts/1/organizations/ceidg_lookup", method="POST", json={"nip": "726 175 68 29"},
        ):
            response = contact_organizations_ceidg_lookup(1)

        assert response[1] == 200
        session.add.assert_called_once()
        added = session.add.call_args[0][0]
        assert added.org_type == "jdg"
        assert added.organization_name == "KRATON"
        assert added.nip == "726 175 68 29"
        assert added.registry == "ceidg"

    def test_falls_back_to_existing_jdg_nip(self, monkeypatch):
        from library.contact_routes import contact_organizations_ceidg_lookup

        existing = _make_organization(id_=9, org_type="jdg", nip="7261756829")
        session = MagicMock()
        session.get.return_value = _make_contact(id_=1)
        session.execute.return_value.scalars.return_value.all.return_value = [existing]
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        captured_nip = {}

        def fake_lookup(nip):
            captured_nip["nip"] = nip
            return {"nazwa": "KRATON"}

        monkeypatch.setattr("library.ceidg_client.get_company_by_nip", fake_lookup)
        app = Flask(__name__)
        with app.test_request_context("/contacts/1/organizations/ceidg_lookup", method="POST", json={}):
            response = contact_organizations_ceidg_lookup(1)

        assert response[1] == 200
        assert captured_nip["nip"] == "7261756829"
        session.add.assert_not_called()
        assert existing.organization_name == "KRATON"

    def test_no_nip_available_is_400(self, monkeypatch):
        from library.contact_routes import contact_organizations_ceidg_lookup

        session = MagicMock()
        session.get.return_value = _make_contact(id_=1)
        session.execute.return_value.scalars.return_value.all.return_value = []
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context("/contacts/1/organizations/ceidg_lookup", method="POST", json={}):
            response = contact_organizations_ceidg_lookup(1)

        assert response[1] == 400
        session.add.assert_not_called()

    def test_no_ceidg_match_is_404(self, monkeypatch):
        from library.contact_routes import contact_organizations_ceidg_lookup

        session = MagicMock()
        session.get.return_value = _make_contact(id_=1)
        session.execute.return_value.scalars.return_value.all.return_value = []
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        monkeypatch.setattr("library.ceidg_client.get_company_by_nip", lambda nip: None)
        app = Flask(__name__)
        with app.test_request_context(
            "/contacts/1/organizations/ceidg_lookup", method="POST", json={"nip": "7261756829"},
        ):
            response = contact_organizations_ceidg_lookup(1)

        assert response[1] == 404
        session.add.assert_not_called()

    def test_missing_contact_is_404(self, monkeypatch):
        from library.contact_routes import contact_organizations_ceidg_lookup

        session = MagicMock()
        session.get.return_value = None
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context(
            "/contacts/999/organizations/ceidg_lookup", method="POST", json={"nip": "7261756829"},
        ):
            response = contact_organizations_ceidg_lookup(999)

        assert response[1] == 404

    def test_preserves_old_phone_when_ceidg_omits_it(self, monkeypatch):
        """CEIDG doesn't return telefon for every record; a refresh must not drop
        a phone number already on file from another source (e.g. a business card)."""
        from library.contact_routes import contact_organizations_ceidg_lookup

        existing = _make_organization(
            id_=7, org_type="jdg", nip="7261756829", notes="tel.: +48 600 827 080, e-mail: kraton@kraton.pl",
        )
        session = MagicMock()
        session.get.return_value = _make_contact(id_=1)
        session.execute.return_value.scalars.return_value.all.return_value = [existing]
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        monkeypatch.setattr(
            "library.ceidg_client.get_company_by_nip",
            lambda nip: {"nazwa": "KRATON", "email": "kraton.ak@gmail.com", "www": "www.kraton.pl"},
        )
        app = Flask(__name__)
        with app.test_request_context("/contacts/1/organizations/ceidg_lookup", method="POST", json={}):
            response = contact_organizations_ceidg_lookup(1)

        assert response[1] == 200
        assert "tel.: +48 600 827 080" in existing.notes
        assert "e-mail: kraton.ak@gmail.com" in existing.notes


def _make_link(id_=1, contact_id=1, link_type="facebook", url="https://facebook.com/example", label=None, **extra):
    defaults = dict(
        contact_id=contact_id, link_type=link_type, url=url, label=label,
        created_at=dt.datetime(2026, 9, 16, 12, 0),
        updated_at=dt.datetime(2026, 9, 16, 12, 0),
    )
    defaults.update(extra)
    return SimpleNamespace(id=id_, **defaults)


class TestContactLinksAdd:
    def test_adds_facebook_link(self, monkeypatch):
        from library.contact_routes import contact_links_add

        session = MagicMock()
        session.get.return_value = _make_contact(id_=1)
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context(
            "/contacts/1/links", method="POST",
            json={"link_type": "facebook", "url": "https://facebook.com/example"},
        ):
            response = contact_links_add(1)

        assert response[1] == 200
        session.add.assert_called_once()
        added = session.add.call_args[0][0]
        assert added.contact_id == 1
        assert added.link_type == "facebook"
        assert added.url == "https://facebook.com/example"
        assert added.label is None

    def test_missing_contact_is_404(self, monkeypatch):
        from library.contact_routes import contact_links_add

        session = MagicMock()
        session.get.return_value = None
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context(
            "/contacts/999/links", method="POST",
            json={"link_type": "facebook", "url": "https://facebook.com/example"},
        ):
            response = contact_links_add(999)

        assert response[1] == 404
        session.add.assert_not_called()

    def test_invalid_link_type_is_400(self, monkeypatch):
        from library.contact_routes import contact_links_add

        session = MagicMock()
        session.get.return_value = _make_contact(id_=1)
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context(
            "/contacts/1/links", method="POST",
            json={"link_type": "tiktok", "url": "https://tiktok.com/@example"},
        ):
            response = contact_links_add(1)

        assert response[1] == 400
        session.add.assert_not_called()

    def test_missing_url_is_400(self, monkeypatch):
        from library.contact_routes import contact_links_add

        session = MagicMock()
        session.get.return_value = _make_contact(id_=1)
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context(
            "/contacts/1/links", method="POST", json={"link_type": "website"},
        ):
            response = contact_links_add(1)

        assert response[1] == 400
        session.add.assert_not_called()


class TestContactLinksUpdate:
    def test_updates_url_and_label(self, monkeypatch):
        from library.contact_routes import contact_links_update

        session = MagicMock()
        session.get.return_value = _make_link(id_=6)
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context(
            "/contact_links/6", method="PATCH",
            json={"url": "https://facebook.com/other", "label": "Profil prywatny"},
        ):
            response = contact_links_update(6)

        assert response[1] == 200
        row = session.get.return_value
        assert row.url == "https://facebook.com/other"
        assert row.label == "Profil prywatny"

    def test_invalid_link_type_is_400(self, monkeypatch):
        from library.contact_routes import contact_links_update

        session = MagicMock()
        session.get.return_value = _make_link(id_=6)
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context(
            "/contact_links/6", method="PATCH", json={"link_type": "myspace"},
        ):
            response = contact_links_update(6)

        assert response[1] == 400

    def test_missing_link_is_404(self, monkeypatch):
        from library.contact_routes import contact_links_update

        session = MagicMock()
        session.get.return_value = None
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context(
            "/contact_links/999", method="PATCH", json={"url": "https://example.com"},
        ):
            response = contact_links_update(999)

        assert response[1] == 404


class TestContactLinksDelete:
    def test_deletes_link(self, monkeypatch):
        from library.contact_routes import contact_links_delete

        session = MagicMock()
        session.get.return_value = _make_link(id_=6)
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context("/contact_links/6", method="DELETE"):
            response = contact_links_delete(6)

        assert response[1] == 200
        session.delete.assert_called_once()

    def test_missing_link_is_404(self, monkeypatch):
        from library.contact_routes import contact_links_delete

        session = MagicMock()
        session.get.return_value = None
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)
        with app.test_request_context("/contact_links/999", method="DELETE"):
            response = contact_links_delete(999)

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
        session.scalar.return_value = 0
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
        monkeypatch.setattr("library.contact_routes._contact_addresses", lambda *args: [])
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
        monkeypatch.setattr("library.contact_routes.get_scoped_session", MagicMock())

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
        session.scalar.return_value = 0
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
    session.get.side_effect = lambda model, key, **kw: contact if model is Contact else (
        photo if model.__name__ == "ContactPhoto" else None)
    monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
    monkeypatch.setattr("library.config_loader.load_config", lambda: {})
    storage = MagicMock()
    storage.presigned_get_url.side_effect = lambda key: f"https://storage.test/{key}"
    storage.exists.return_value = True
    monkeypatch.setattr("library.storage.storage_from_config", lambda cfg: storage)
    return contact, photo, session, storage


class TestContactPhotoHistory:
    def test_history_query_includes_inherited_but_not_unrelated_photos(self, photo_history_setup):
        from sqlalchemy import Column, DateTime, Integer, MetaData, Table, Text, create_engine
        from library.contact_routes import contact_photo_history
        from library.db.models import ContactPhoto

        contact, legacy, session, _ = photo_history_setup
        metadata = MetaData()
        photos = Table("contact_photos", metadata, Column("storage_key", Text), Column("created_at", DateTime))
        links = Table("contact_photo_links", metadata, Column("contact_id", Integer), Column("storage_key", Text))
        engine = create_engine("sqlite://")
        metadata.create_all(engine)
        inherited = "contacts/parent/photos/shared.png"
        with engine.begin() as connection:
            connection.execute(photos.insert(), [
                {"storage_key": key, "created_at": dt.datetime(2026, 9, day)}
                for key, day in [(legacy.storage_key, 1), (inherited, 2), ("contacts/unrelated/photo.png", 3)]
            ])
            connection.execute(links.insert(), [{"contact_id": contact.id, "storage_key": inherited}])
            session.execute.return_value.scalars.return_value.all.return_value = []
            with Flask(__name__).test_request_context():
                assert contact_photo_history(contact.id)[1] == 200
            query = session.execute.call_args.args[0].with_only_columns(ContactPhoto.storage_key)
            assert connection.execute(query).scalars().all() == [inherited, legacy.storage_key]

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
        assert list(compiled.params.values()) == [f"contacts/{contact.uuid}/%", contact.id]
        assert "contact_photo_links" in str(compiled)
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
    def test_restores_inherited_photo_and_keeps_link(self, photo_history_setup):
        from library.contact_routes import contact_photo_restore
        from library.db.models import Contact, ContactPhoto, ContactPhotoLink

        contact, photo, session, _ = photo_history_setup
        photo.storage_key = "contacts/parent/photos/shared.png"
        link = ContactPhotoLink(contact_id=contact.id, storage_key=photo.storage_key, revision=2,
                                depicts_contact=False)
        session.get.side_effect = lambda model, key, **kw: {
            Contact: contact, ContactPhoto: photo, ContactPhotoLink: link,
        }.get(model)
        with Flask(__name__).test_request_context(method="POST", json={"storage_key": photo.storage_key}):
            response, status = contact_photo_restore(contact.id)
        assert status == 200
        assert response.json["photo"]["storage_key"] == photo.storage_key
        assert contact.photo_storage_key == photo.storage_key
        assert link.depicts_contact is False
        assert link.revision == 2
        session.commit.assert_called_once()

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
        assert session.get.call_count == 2
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
    def test_dict_birthday_pair_is_public(self, kind, month, day, monkeypatch):
        from library.contact_routes import _contact_dict
        monkeypatch.setattr("library.contact_routes.get_scoped_session", MagicMock())

        row = _make_contact(birthday_month=month, birthday_day=day, private_notes="vault note")
        with Flask(__name__).test_request_context():
            if kind is not None:
                g.auth = SimpleNamespace(kind=kind)
            result = _contact_dict(row)
        assert result["birthday_month"] == month
        assert result["birthday_day"] == day
        assert result["private_notes"] == ("vault note" if kind == "service" else None)


class TestContactGender:
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

    @pytest.mark.parametrize("value", ["male", "female", "other"])
    def test_valid_value_accepted(self, birthday_request, value):
        send, session, _ = birthday_request
        response, status = send({"gender": value})
        assert status == 200
        assert response.json["contact"]["gender"] == value
        change = session.add.call_args_list[-1][0][0]
        assert "gender" in change.changed_fields
        session.commit.assert_called_once()

    def test_null_clears_value(self, birthday_request):
        send, session, row = birthday_request
        row.gender = "male"
        response, status = send({"gender": None})
        assert status == 200
        assert response.json["contact"]["gender"] is None
        change = session.add.call_args_list[-1][0][0]
        assert "gender" in change.changed_fields
        session.commit.assert_called_once()

    def test_invalid_value_rejected(self, birthday_request):
        send, session, row = birthday_request
        response, status = send({"gender": "unknown"})
        assert status == 400
        assert response["status"] == "error"
        assert "gender" in response["message"]
        session.add.assert_not_called()
        session.commit.assert_not_called()

    def test_omitted_field_leaves_value_untouched_on_update(self, monkeypatch):
        from library.contact_routes import contacts_update

        row = _make_contact(gender="female")
        session = MagicMock()
        session.get.return_value = row
        monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
        with Flask(__name__).test_request_context("/contacts/1", method="PATCH", json={}):
            response, status = contacts_update(1)
        assert status == 200
        assert row.gender == "female"
        session.add.assert_not_called()


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
        session.scalar.return_value = 0
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
        session.scalar.return_value = 0
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
