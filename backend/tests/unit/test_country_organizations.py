"""Planning of one organization per country, without a DB."""

import pytest

pytest.importorskip("sqlalchemy")

from library.country_organizations import OrgInfo, note_index, plan_country_organizations  # noqa: E402
from library.organization_registry import normalize_alias  # noqa: E402

COUNTRIES = {"iran": "Iran", "rosja": "Rosja", "polska": "Polska"}


def _org(org_id, name, org_type=None, aliases=(), note=None, ties=()):
    return OrgInfo(id=org_id, canonical_name=name, organization_type=org_type, aliases=list(aliases),
                   primary_note_document_id=note, country_ties=set(ties))


NOTES = [
    (10159, "obsidian://02-wiedza/Geopolityka/Kraje/Bliski Wschód/Iran.md"),
    (10200, "obsidian://02-wiedza/Geopolityka/Kraje/Europa/Polska.md"),
]


def _by_slug(actions):
    return {a.slug: a for a in actions}


def test_creates_missing_countries_and_links_notes():
    actions = _by_slug(plan_country_organizations(COUNTRIES, [], NOTES))
    assert actions["iran"].action == "create"
    assert actions["iran"].note_document_id == 10159
    assert actions["polska"].note_document_id == 10200
    assert actions["rosja"].note_issue == "missing"


def test_promotes_existing_untyped_organization():
    actions = _by_slug(plan_country_organizations(COUNTRIES, [_org(21, "Rosja")], NOTES))
    rosja = actions["rosja"]
    assert (rosja.action, rosja.organization_id, rosja.needs_type, rosja.needs_tie) == ("promote", 21, True, True)


def test_already_done_country_needs_nothing():
    done = _org(39, "Iran", "country", note=10159, ties=[("iran", "based_in")])
    iran = _by_slug(plan_country_organizations(COUNTRIES, [done], NOTES))["iran"]
    assert (iran.action, iran.needs_type, iran.needs_tie, iran.note_document_id) == ("promote", False, False, None)


def test_alias_only_match_is_a_conflict_for_a_human_to_resolve():
    organizations = [_org(50, "Islamska Republika Iranu", aliases=["Iran"])]
    iran = _by_slug(plan_country_organizations(COUNTRIES, organizations, NOTES))["iran"]
    assert iran.action == "conflict" and iran.organization_id == 50 and "alias" in iran.reason
    assert iran.note_document_id is None


def test_other_type_is_a_conflict_not_touched():
    iran = _by_slug(plan_country_organizations(COUNTRIES, [_org(7, "Iran", "firma")], NOTES))["iran"]
    assert iran.action == "conflict" and "firma" in iran.reason


def test_several_candidates_conflict():
    organizations = [_org(1, "Polska"), _org(2, "Polska")]
    assert _by_slug(plan_country_organizations(COUNTRIES, organizations, NOTES))["polska"].action == "conflict"


def test_one_organization_cannot_serve_two_countries():
    countries = {"a": "Persja", "b": "Iran"}
    organizations = [_org(5, "Persja", aliases=["Iran"])]
    actions = plan_country_organizations(countries, organizations, [])
    assert sorted(a.action for a in actions) == ["conflict", "promote"]


def test_ambiguous_note_is_reported_not_linked():
    notes = NOTES + [(10999, "obsidian://x/Kraje/Archiwum/Iran.md")]
    iran = _by_slug(plan_country_organizations(COUNTRIES, [], notes))["iran"]
    assert iran.note_document_id is None and iran.note_issue == "ambiguous"


def test_existing_link_is_kept():
    linked = _org(39, "Iran", note=5)
    iran = _by_slug(plan_country_organizations(COUNTRIES, [linked], NOTES))["iran"]
    assert iran.note_document_id is None and iran.note_issue is None


def test_note_index_ignores_case_and_polish_letters_in_file_names():
    index = note_index([(1, "obsidian://x/Kraje/Azja/AZERBEJDŻAN.MD"), (2, "obsidian://x/Kraje/Azja/Azerbejdzan.md")])
    assert index == {normalize_alias("azerbejdzan"): [1, 2]}


def test_country_with_unaccented_note_file_is_linked():
    actions = plan_country_organizations({"azerbejdzan": "Azerbejdżan"}, [], [(7, "obsidian://x/Kraje/Azja/Azerbejdzan.md")])
    assert actions[0].note_document_id == 7
