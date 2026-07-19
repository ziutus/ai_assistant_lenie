from types import SimpleNamespace
from unittest.mock import MagicMock

from library.search.name_resolution import resolve_author_name, resolve_discovery_source_name


def _session(rows):
    session = MagicMock()
    session.scalars.return_value.all.return_value = rows
    return session


def test_empty_names_return_zero_without_database():
    session = MagicMock()
    assert resolve_author_name(session, " ").count == 0
    assert resolve_discovery_source_name(session, None).count == 0
    session.scalars.assert_not_called()


def test_author_zero_one_many_and_no_arbitrary_id():
    assert resolve_author_name(_session([]), "Nikt").count == 0
    one = resolve_author_name(_session([SimpleNamespace(id=3, canonical_name="Jan")]), "jan")
    assert one.count == 1 and one.id == 3
    many = resolve_author_name(_session([
        SimpleNamespace(id=3, canonical_name="Jan"),
        SimpleNamespace(id=8, canonical_name="Jan"),
    ]), "jan")
    assert many.count == 2
    assert many.id is None
    assert [match.id for match in many.matches] == [3, 8]


def test_author_query_includes_alias_and_unaccent():
    session = _session([])
    resolve_author_name(session, "Żaneta")
    sql = str(session.scalars.call_args.args[0].compile(compile_kwargs={"literal_binds": True}))
    assert "person_aliases.alias" in sql
    assert "unaccent(lower(persons.canonical_name))" in sql


def test_discovery_source_zero_one_many_and_case_insensitive_sql():
    rows = [SimpleNamespace(id=1, name="friend"), SimpleNamespace(id=2, name="Friend")]
    session = _session(rows)
    result = resolve_discovery_source_name(session, "FRIEND")
    assert result.count == 2
    assert result.id is None
    sql = str(session.scalars.call_args.args[0].compile(compile_kwargs={"literal_binds": True}))
    assert "FROM discovery_sources" in sql
    assert "information_sources" not in sql
    assert "unaccent(lower(discovery_sources.name))" in sql
