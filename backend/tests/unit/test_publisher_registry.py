from types import SimpleNamespace
from unittest.mock import MagicMock

from library.publisher_registry import normalize_publisher_domain, resolve_publisher


def _session_with(rows):
    session = MagicMock()
    session.scalars.return_value.unique.return_value.all.return_value = rows
    return session


def test_domain_normalization_case_www_and_empty():
    assert normalize_publisher_domain(" WWW.Onet.PL. ") == "onet.pl"
    assert normalize_publisher_domain("  ") is None


def test_empty_criteria_returns_zero_without_query():
    session = MagicMock()
    result = resolve_publisher(session, name="  ")
    assert result.count == 0
    assert result.publisher_id is None
    session.scalars.assert_not_called()


def test_zero_matches_is_explicit():
    result = resolve_publisher(_session_with([]), name="nie istnieje")
    assert result.count == 0
    assert result.matches == ()


def test_one_match_exposes_single_id_and_no_domain_is_allowed():
    row = SimpleNamespace(id=7, canonical_name="Portal bez domeny", domains=[])
    result = resolve_publisher(_session_with([row]), name="Portal bez domeny")
    assert result.count == 1
    assert result.publisher_id == 7
    assert result.matches[0].domains == ()


def test_many_matches_never_selects_arbitrary_id():
    rows = [
        SimpleNamespace(id=2, canonical_name="Gazeta", domains=[SimpleNamespace(domain="b.pl")]),
        SimpleNamespace(id=9, canonical_name="Gazeta", domains=[SimpleNamespace(domain="a.pl")]),
    ]
    result = resolve_publisher(_session_with(rows), name="Gazeta")
    assert result.count == 2
    assert [match.publisher_id for match in result.matches] == [2, 9]
    assert result.publisher_id is None


def test_name_query_is_case_and_diacritic_insensitive_sql():
    session = _session_with([])
    resolve_publisher(session, name="ŻÓŁĆ")
    sql = str(session.scalars.call_args.args[0].compile(compile_kwargs={"literal_binds": True}))
    assert "unaccent(lower(publishers.canonical_name))" in sql
    assert "zołc" in sql or "zolc" in sql


def test_both_name_and_domain_are_anded_in_one_query():
    session = _session_with([])
    resolve_publisher(session, name="Onet", domain="WWW.ONET.PL")
    sql = str(session.scalars.call_args.args[0].compile(compile_kwargs={"literal_binds": True}))
    assert "publishers.canonical_name" in sql
    assert "publisher_domains" in sql
    assert "onet.pl" in sql
