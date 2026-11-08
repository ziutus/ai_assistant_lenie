from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from library.db.models import Organization, OrganizationAlias
from library.organization_registry import (
    CONFIDENCE_ALIAS_MATCHED,
    CONFIDENCE_CANONICAL_MATCHED,
    find_inflected_base_organization,
    resolve_or_create,
)


def result(rows=(), first=None):
    return MagicMock(**{
        "scalars.return_value.all.return_value": list(rows),
        "scalars.return_value.first.return_value": first,
    })


def session_with(organizations=(), aliases=()):
    session = MagicMock()
    session.execute.side_effect = [result(organizations), result(aliases)]
    return session


@pytest.mark.parametrize("name,base", [
    ("Faktu", "Fakt"), ("Amazone", "Amazon"), ("Onetem", "Onet"),
    ("SpaceXa", "SpaceX"), ("Waszyngtonem", "Waszyngton"), ("rosnieftu", "rosnieft"),
    ("Fiatem", "Fiat"), ("Budomalu", "Budomal"), ("Reutersa", "Reuters"),
])
@pytest.mark.parametrize("via_alias", [False, True])
def test_inflected_names(name, base, via_alias):
    org = Organization(id=1, canonical_name="Other" if via_alias else base)
    alias = SimpleNamespace(alias=base, organization=org)
    session = session_with([], [alias]) if via_alias else session_with([org])
    assert find_inflected_base_organization(session, name) is org
    session.add.assert_not_called()
    session.flush.assert_not_called()


@pytest.mark.parametrize("name,base", [
    ("Nigeria", "Niger"), ("Dominikana", "Dominika"), ("Amerykanów", "Ameryka"),
    ("ABCem", "ABC"), ("Amazon", "Amazon"), ("Foobarem", "Foo.Bar"),
])
def test_nonmatching_bases(name, base):
    assert find_inflected_base_organization(
        session_with([Organization(id=1, canonical_name=base)]), name,
    ) is None


@pytest.mark.parametrize("name", ["Fakt", "", "Faktu Media", "Faktu\tMedia", "Faktu."])
def test_ineligible_names_do_not_query(name):
    session = MagicMock()
    assert find_inflected_base_organization(session, name) is None
    session.execute.assert_not_called()


def test_no_candidates():
    assert find_inflected_base_organization(session_with(), "Faktu") is None


def test_different_organizations_are_ambiguous():
    org = Organization(id=1, canonical_name="Fakt")
    other = Organization(id=2, canonical_name="Other")
    alias = SimpleNamespace(alias="Fakt", organization=other)
    assert find_inflected_base_organization(session_with([org], [alias]), "Faktu") is None


def test_multiple_bases_for_same_organization_are_not_ambiguous():
    org = Organization(id=1, canonical_name="Fakt")
    alias = SimpleNamespace(alias="Fakti", organization=org)
    assert find_inflected_base_organization(session_with([org], [alias]), "Faktiem") is org


def test_case_and_diacritic_normalization():
    org = Organization(id=1, canonical_name="BUDOMAŁ")
    assert find_inflected_base_organization(session_with([org]), "Budomalu") is org


@pytest.mark.parametrize("name,pattern", [("A%_\\a", "A\\%\\_\\\\%"), ("Faktu", "Fakt%")])
def test_queries_restrict_and_escape_prefix(name, pattern):
    session = session_with()
    find_inflected_base_organization(session, name)
    for call in session.execute.call_args_list:
        statement = call.args[0]
        assert list(statement.compile().params.values()) == [pattern]
        assert "ESCAPE" in str(statement)


def test_resolve_inflection_records_name_and_variants_without_creating_organization():
    org = Organization(id=1, canonical_name="Fakt")
    session = MagicMock()
    session.execute.side_effect = [
        result(), result(),  # exact aliases for name and variant
        result(), result([org]), result(), result([org]),  # exact resolution
        result([org]), result(),  # inflection candidates
        result(), result(),  # observing name and variant
    ]
    assert resolve_or_create(session, "Faktu", ["Faktem"]) == (org, CONFIDENCE_ALIAS_MATCHED)
    added = [call.args[0] for call in session.add.call_args_list]
    assert all(isinstance(row, OrganizationAlias) for row in added)
    assert {row.alias for row in added} == {"Faktu", "Faktem"}
    assert {row.normalized_alias for row in added} == {"faktu", "faktem"}
    assert all(row.organization is org for row in added)


def test_exact_canonical_path_unchanged():
    org = Organization(id=1, canonical_name="Fakt")
    session = MagicMock()
    session.execute.side_effect = [result(), result(), result([org])]
    with patch("library.organization_registry.find_inflected_base_organization") as lookup:
        assert resolve_or_create(session, "Fakt") == (org, CONFIDENCE_CANONICAL_MATCHED)
    lookup.assert_not_called()
    session.add.assert_not_called()


def test_exact_variant_alias_takes_priority():
    org = Organization(id=1, canonical_name="Other")
    session = MagicMock()
    session.execute.side_effect = [result(), result(first=SimpleNamespace(organization=org)), result(), result()]
    with patch("library.organization_registry.find_inflected_base_organization") as lookup:
        assert resolve_or_create(session, "Faktu", ["Variant"]) == (org, CONFIDENCE_ALIAS_MATCHED)
    lookup.assert_not_called()


def test_existing_observed_alias_is_not_added_again():
    org = Organization(id=1, canonical_name="Fakt")
    session = MagicMock()
    session.execute.side_effect = [
        result(), result(), result([org]), result(first=SimpleNamespace(organization_id=1)),
    ]
    with patch("library.organization_registry.find_inflected_base_organization", return_value=org):
        assert resolve_or_create(session, "Faktu") == (org, CONFIDENCE_ALIAS_MATCHED)
    session.add.assert_not_called()


def test_lookup_exception_falls_back_to_creation(caplog):
    session = MagicMock()
    session.execute.return_value = result()
    with patch("library.organization_registry.find_inflected_base_organization", side_effect=RuntimeError("failed")):
        org, confidence = resolve_or_create(session, "Faktu")
    assert org.canonical_name == "Faktu"
    assert confidence == CONFIDENCE_CANONICAL_MATCHED
    session.add.assert_called_once_with(org)
    session.flush.assert_called_once()
    assert "organization inflection lookup failed" in caplog.text
