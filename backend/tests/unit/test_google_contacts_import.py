import csv
import datetime as dt
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from imports.google_contacts_import import _birthday_patch, _ContactIndex, _name_key, _parse_birthday, _parse_channels, main
from library.db.models import Contact, ContactAlternateName


def contact(id_=1, phones=(), **kwargs):
    return Contact(id=id_, first_name="Jan", last_name="Test", phone_numbers=[{"value": v, "label": None} for v in phones], **kwargs)


@pytest.mark.parametrize("raw,expected", [
    ("--04-29", {"birthday_month": 4, "birthday_day": 29}),
    (" --02-29 ", {"birthday_month": 2, "birthday_day": 29}),
    ("2000-02-29", {"birthday": dt.date(2000, 2, 29)}),
    ("1990-04-29", {"birthday": dt.date(1990, 4, 29)}),
    (None, None), ("", None), ("--02-30", None), ("--13-01", None), ("--00-01", None),
    ("--04-31", None), ("--4-29", None), ("1900-02-29", None), ("0000-04-29", None),
])
def test_parse_birthday(raw, expected):
    assert _parse_birthday(raw) == expected


def test_birthday_fill_preserves_conflicts_and_adds_only_known_information():
    row = contact()
    partial = _parse_birthday("--02-29")
    assert _birthday_patch(row, partial) == (partial, False)
    row.birthday_month, row.birthday_day = 2, 29
    assert _birthday_patch(row, partial) == ({}, False)
    assert _birthday_patch(row, _parse_birthday("--03-01")) == ({}, True)
    assert _birthday_patch(row, _parse_birthday("2000-02-29")) == ({"birthday": dt.date(2000, 2, 29)}, False)
    row.birthday = dt.date(2000, 2, 29)
    assert _birthday_patch(row, partial) == ({}, False)
    assert _birthday_patch(row, _parse_birthday("2004-02-29")) == ({}, True)


def test_csv_deduplicates_country_prefix_variants():
    assert _parse_channels({"Phone 1 - Value": "501234567 ::: +48 501 234 567", "Phone 2 - Value": "0048501234567"}, "Phone", "phone_numbers") == [{"value": "+48501234567", "label": None}]


def test_matching_includes_secondary_numbers_and_normalizes_existing_data():
    row = contact(phones=("502 234 567", "+48 501 234 567"))
    index = _ContactIndex([row])
    assert index.match([{"value": "0048 501234567"}], None) == (row, None)


def test_legacy_scalar_is_indexed_and_short_numbers_are_not():
    row = contact(phone_number="501 234 567")
    short = contact(2, phones=("112",))
    index = _ContactIndex([row, short])
    assert index.match([{"value": "+48501234567"}], None) == (row, None)
    assert index.match([{"value": "112"}], None) == (None, None)


@pytest.mark.parametrize("phones", [("501234567",), ("501234567", "502234567")])
def test_colliding_numbers_are_never_first_wins(phones):
    a = contact(phones=("501234567",))
    b = contact(2, phones=("501234567", "502234567"))
    result, conflict = _ContactIndex([a, b]).match([{"value": p} for p in phones], _name_key(a))
    assert result is None and conflict


def test_conflicting_numbers_names_and_homonyms_need_review():
    a = contact(phones=("501234567",))
    b = contact(2, phones=("502234567",))
    index = _ContactIndex([a, b])
    assert index.match([], _name_key(a))[1]
    assert _ContactIndex([a]).match([{"value": "502234567"}], _name_key(a))[1]
    b.first_name = "Anna"
    assert _ContactIndex([a, b]).match([{"value": "501234567"}], _name_key(b))[1]


@pytest.mark.parametrize("apply", [False, True])
def test_import_new_yearless_birthday_and_repeat_phone_row(tmp_path, monkeypatch, capsys, apply):
    path = tmp_path / "contacts.csv"
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["First Name", "Last Name", "Phone 1 - Value", "Birthday"])
        writer.writeheader()
        writer.writerows([
            {"First Name": "Jan", "Last Name": "Test", "Phone 1 - Value": "501234567", "Birthday": "--02-29"},
            {"First Name": "Jan", "Last Name": "Test", "Phone 1 - Value": "+48 501 234 567", "Birthday": "2000-02-29"},
        ])
    session = MagicMock()
    session.execute.return_value.scalars.return_value.first.return_value = SimpleNamespace(id=1)
    session.scalars.side_effect = [[], []]
    monkeypatch.setattr("library.db.engine.get_session", lambda: session)
    monkeypatch.setattr("sys.argv", ["import", "--csv", str(path), *(["--apply"] if apply else [])])
    main()
    assert "dopasowanych do istniejących kontaktów: 1, nowych: 1" in capsys.readouterr().out
    if apply:
        row = next(call.args[0] for call in session.add.call_args_list if isinstance(call.args[0], Contact))
        assert row.phone_number == "+48501234567"
        assert (row.birthday_month, row.birthday_day) == (2, 29)
        assert row.birthday == dt.date(2000, 2, 29)
        session.commit.assert_called_once()
    else:
        session.add.assert_not_called()
        session.commit.assert_not_called()


@pytest.mark.parametrize("apply", [False, True])
def test_existing_contact_gets_yearless_date_and_conflicts_are_preserved(tmp_path, monkeypatch, capsys, apply):
    row = contact(phones=("+48 501 234 567",))
    path = tmp_path / "existing.csv"
    path.write_text("First Name,Last Name,Phone 1 - Value,Birthday\nJan,Test,501234567,--04-29\nJan,Test,0048501234567,--04-30\n", encoding="utf-8")
    session = MagicMock()
    session.execute.return_value.scalars.return_value.first.return_value = SimpleNamespace(id=1)
    session.scalars.side_effect = [[row], []]
    monkeypatch.setattr("library.db.engine.get_session", lambda: session)
    monkeypatch.setattr("sys.argv", ["import", "--csv", str(path), *(["--apply"] if apply else [])])
    main()
    output = capsys.readouterr().out
    assert "dopasowanych do istniejących kontaktów: 2, nowych: 0" in output
    assert "Konflikty dat urodzin: zachowano obecne" in output
    assert row.birthday is None
    if apply:
        assert (row.birthday_month, row.birthday_day) == (4, 29)
        assert session.add.call_args_list[0].args[0].changed_fields == ["birthday_month", "birthday_day"]
    else:
        assert row.birthday_month is None and row.birthday_day is None
        session.add.assert_not_called()


@pytest.mark.parametrize("apply", [False, True])
def test_ambiguous_csv_row_is_reported_without_creating_or_updating_contact(tmp_path, monkeypatch, capsys, apply):
    rows = [contact(1, phones=("501234567",)), contact(2, phones=("+48 501 234 567",))]
    path = tmp_path / "ambiguous.csv"
    path.write_text("First Name,Last Name,Phone 1 - Value,Birthday\nJan,Test,501234567,--04-29\n", encoding="utf-8")
    session = MagicMock()
    session.execute.return_value.scalars.return_value.first.return_value = SimpleNamespace(id=1)
    session.scalars.side_effect = [rows, []]
    monkeypatch.setattr("library.db.engine.get_session", lambda: session)
    monkeypatch.setattr("sys.argv", ["import", "--csv", str(path), *(["--apply"] if apply else [])])
    main()
    output = capsys.readouterr().out
    assert "dopasowanych do istniejących kontaktów: 0, nowych: 0" in output
    assert "Niejednoznaczne wiersze pominięte do ręcznego sprawdzenia: 1" in output
    assert all(row.birthday_month is None for row in rows)
    session.add.assert_not_called()


@pytest.mark.parametrize("existing_contact", [False, True])
@pytest.mark.parametrize("apply", [False, True])
def test_import_addresses_adds_once_and_keeps_existing_addresses(tmp_path, monkeypatch, existing_contact, apply):
    from library.db.models import Address, ContactAddress, ContactCategory, ContactChangeLog, ContactGroup
    row = contact(phones=("501234567",))
    links = [ContactAddress(contact_id=1, address=Address(city="Old Street"), is_primary=True)] if existing_contact else []
    session = MagicMock()
    session.execute.return_value.scalars.return_value.first.return_value = ContactCategory(id=1)
    added = []

    def add(value):
        added.append(value)
        if isinstance(value, Contact):
            value.id = 1  # Simulate the subsequent flush assigning the PK.
        elif isinstance(value, ContactAddress):
            links.append(value)

    def scalars(statement):
        entity = statement.column_descriptions[0]["entity"]
        return {Contact: [row] if existing_contact else [], ContactGroup: [], ContactAddress: links}[entity]

    session.add.side_effect = add
    session.scalars.side_effect = scalars
    path = tmp_path / "addresses.csv"
    path.write_text("First Name,Last Name,Phone 1 - Value,Address 1 - Formatted\n"
                    "Jan,Test,501234567,New Street\nJan,Test,501234567,New Street\n", encoding="utf-8")
    monkeypatch.setattr("library.db.engine.get_session", lambda: session)
    monkeypatch.setattr("sys.argv", ["import", "--csv", str(path), *(["--apply"] if apply else [])])
    main()
    if not apply:
        session.add.assert_not_called()
        session.commit.assert_not_called()
        return
    new_addresses = [value for value in added if isinstance(value, Address)]
    new_links = [value for value in added if isinstance(value, ContactAddress)]
    audits = [value for value in added if isinstance(value, ContactChangeLog)]
    assert len(new_addresses) == len(new_links) == 1
    assert new_addresses[0].city == "New Street"
    assert new_links[0].is_primary == (not existing_contact)
    assert new_links[0].role == "zamieszkania"
    assert "addresses" in audits[0].changed_fields
    assert len(links) == (2 if existing_contact else 1)


@pytest.mark.parametrize("alternate", ["Jan Żółć", "Żółć Jan", "Żółć"])
def test_alternate_names_match_full_names_but_never_surnames(alternate):
    row = contact(alternate_names=[ContactAlternateName(name=alternate)])
    index = _ContactIndex([row])
    assert index.match([], "jan zolc") == (row, None)
    assert index.match([], "zolc") == (None, None)
    assert index.match([], _name_key(row)) == (row, None)


@pytest.mark.parametrize("first_name,alternate", [(None, "Żółć"), ("", "Żółć"), ("123", "Żółć"),
                                                      ("Jan", "123"), ("Jan", "Żółć 123")])
def test_alternate_names_require_first_and_last_name(first_name, alternate):
    row = Contact(first_name=first_name, alternate_names=[ContactAlternateName(name=alternate)])
    assert _ContactIndex([row]).names == {}


def test_alternate_name_collisions_are_preserved_and_reindexing_is_idempotent():
    a = contact(alternate_names=[ContactAlternateName(name="Jan Żółć"), ContactAlternateName(name="Żółć")])
    b = contact(2, alternate_names=[ContactAlternateName(name="Żółć")])
    index = _ContactIndex([a])
    index.add(a, include_name=True)
    assert index.match([], "jan zolc") == (a, None)
    index.add(b, include_name=True)
    result, conflict = index.match([], "jan zolc")
    assert result is None and conflict


def test_alternate_names_are_not_indexed_without_include_name():
    row = contact(alternate_names=[ContactAlternateName(name="Żółć")])
    index = _ContactIndex([])
    index.add(row)
    assert index.names == {}


@pytest.mark.parametrize("apply", [False, True])
def test_import_matches_alternate_names_including_dry_run(tmp_path, monkeypatch, capsys, apply):
    row = contact(alternate_names=[ContactAlternateName(name="Żółć")])
    path = tmp_path / "alternate.csv"
    path.write_text("First Name,Last Name\nJan,Żółć\n", encoding="utf-8")
    session = MagicMock()
    session.execute.return_value.scalars.return_value.first.return_value = SimpleNamespace(id=1)
    session.scalars.side_effect = [[row], []]
    monkeypatch.setattr("library.db.engine.get_session", lambda: session)
    monkeypatch.setattr("sys.argv", ["import", "--csv", str(path), *(["--apply"] if apply else [])])
    main()
    assert "dopasowanych do istniejących kontaktów: 1, nowych: 0" in capsys.readouterr().out
