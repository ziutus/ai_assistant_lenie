"""Contact ID query parsing and list filters, without a database."""

from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")

from flask import Flask
from sqlalchemy.dialects import postgresql

from library.contact_routes import _parse_contact_id_query, contacts_list


@pytest.mark.parametrize("query, expected", [
    ("", ([], False)),
    ("Jan", ([], False)),
    ("576", ([576], False)),
    ("000576", ([576], False)),
    ("0", ([0], False)),
    ("576,611", ([576, 611], True)),
    ("576 , 611,\t712", ([576, 611, 712], True)),
    ("576,576", ([576, 576], True)),
    ("2147483647", ([2147483647], False)),
    ("2147483648", ([], False)),
    ("576,2147483648", ([576], True)),
    ("2147483648,9999999999", ([], True)),
    ("9" * 5000, ([], False)),
    ("576," + "9" * 5000, ([576], True)),
    ("0" * 5000 + "576", ([576], False)),
    ("576,", ([], False)),
    (",576", ([], False)),
    ("576,,611", ([], False)),
    ("576,Jan", ([], False)),
    ("-576", ([], False)),
    ("+576", ([], False)),
    ("576 611", ([], False)),
    ("501-234-567", ([], False)),
])
def test_parse_contact_id_query(query, expected):
    assert _parse_contact_id_query(query) == expected


def _search_filters(monkeypatch, query):
    session = MagicMock()
    session.execute.return_value.scalar_one.return_value = 0
    session.execute.return_value.scalars.return_value.all.return_value = []
    monkeypatch.setattr("library.contact_routes.get_scoped_session", lambda: session)
    app = Flask(__name__)
    with app.test_request_context("/contacts", query_string={"q": query}):
        response, status = contacts_list()
    assert status == 200
    assert response.get_json()["contacts"] == []
    # Both count and paginated results must apply the same search predicate.
    filters = [str(call.args[0].whereclause.compile(
        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True},
    )) for call in session.execute.call_args_list]
    assert len(filters) == 2
    assert filters[0] == filters[1]
    return filters[0]


@pytest.mark.parametrize("query, ids", [
    ("576,611", "576, 611"),
    (" 576 , 611 ", "576, 611"),
    ("576,2147483648", "576"),
])
def test_id_list_uses_only_id_search(monkeypatch, query, ids):
    sql = _search_filters(monkeypatch, query)
    assert f"contacts.id IN ({ids})" in sql
    assert "unaccent" not in sql
    assert "regexp_replace" not in sql
    assert "contacts.is_archived IS false" in sql


def test_all_out_of_range_ids_match_nothing(monkeypatch):
    sql = _search_filters(monkeypatch, "2147483648,9999999999")
    assert "1 != 1" in sql
    assert "unaccent" not in sql


def test_single_id_also_searches_text_phone_and_pesel(monkeypatch):
    sql = _search_filters(monkeypatch, "576")
    assert " OR contacts.id = 576" in sql
    for field in ("first_name", "last_name", "display_label", "company", "phone_number",
                  "email", "pesel", "phone_numbers", "email_addresses"):
        assert f"contacts.{field}" in sql
    assert "regexp_replace" in sql
    assert "%576%" in sql


@pytest.mark.parametrize("query", ["2147483648", "576,Jan", "576,", "501-234-567", "Jan"])
def test_other_queries_keep_existing_search(monkeypatch, query):
    sql = _search_filters(monkeypatch, query)
    assert "contacts.id" not in sql
    assert "unaccent" in sql
    assert f"%{query}%" in sql
