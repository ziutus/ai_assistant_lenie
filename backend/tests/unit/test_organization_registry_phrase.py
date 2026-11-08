from types import SimpleNamespace
from unittest.mock import MagicMock

from library.organization_registry import find_organization_by_phrase


def session_with(organizations=(), aliases=()):
    session = MagicMock()
    session.execute.side_effect = [
        MagicMock(**{"scalars.return_value.all.return_value": list(rows)})
        for rows in (organizations, aliases)
    ]
    return session


def test_typo_matches_canonical_without_writes():
    org = SimpleNamespace(id=1239, canonical_name="Cambridge Analytica")
    session = session_with([org])
    assert find_organization_by_phrase(session, "Cambridge Analitica") is org
    session.add.assert_not_called()
    session.flush.assert_not_called()


def test_unrelated_phrase_and_empty_candidates():
    org = SimpleNamespace(id=1, canonical_name="Cambridge University")
    assert find_organization_by_phrase(session_with([org]), "Cambridge Analitica") is None
    assert find_organization_by_phrase(session_with(), "Cambridge Analitica") is None


def test_tie_between_different_organizations_is_ambiguous():
    org = SimpleNamespace(id=1, canonical_name="Cambridge Analytica")
    other = SimpleNamespace(id=2, canonical_name="Other Organization")
    alias = SimpleNamespace(alias=org.canonical_name, organization=other)
    assert find_organization_by_phrase(session_with([org], [alias]), "Cambridge Analitica") is None


def test_alias_and_canonical_of_same_organization_are_not_a_tie():
    org = SimpleNamespace(id=1, canonical_name="Cambridge Analytica")
    alias = SimpleNamespace(alias=org.canonical_name, organization=org)
    assert find_organization_by_phrase(session_with([org], [alias]), "Cambridge Analitica") is org


def test_single_word_does_not_query():
    session = MagicMock()
    assert find_organization_by_phrase(session, "Cambridge") is None
    session.execute.assert_not_called()


def test_alias_normalization():
    org = SimpleNamespace(id=1, canonical_name="Other Organization")
    alias = SimpleNamespace(alias="Łódź Alpha-Beta", organization=org)
    assert find_organization_by_phrase(session_with([], [alias]), "Łódź  Alpha Beta") is org
