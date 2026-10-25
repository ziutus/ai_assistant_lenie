"""Pure unit tests for grounded compound organization names."""

from copy import deepcopy

import pytest

from library.ner_normalization import strip_content_markers
from library.org_compound_names import merge_compound_org_names

HEAD = "Agencja Unii Europejskiej"
TAIL = "Bezpieczeństwa Lotniczego"
CANONICAL = f"{HEAD} ds. {TAIL} (EASA)"
KEY = ("orgName", CANONICAL)
SENTENCE = (
    "Agencja Unii Europejskiej [link8] ds. Bezpieczeństwa Lotniczego (EASA) "
    "rozszerzyła z kolei w piątek ostrzeżenie."
)


def make_groups(count=1):
    return {
        ("orgName", name): {"count": count, "variants": [name], "raw_lemmas": [name.lower()]}
        for name in (HEAD, TAIL, "EASA")
    }


def test_exact_sentence_after_marker_stripping():
    groups = make_groups()
    assert merge_compound_org_names(strip_content_markers(SENTENCE), groups) == [KEY]
    assert set(groups) == {KEY}
    assert groups[KEY]["count"] == 1
    assert set(groups[KEY]["variants"]) == {
        CANONICAL, f"{HEAD} ds. {TAIL} EASA", f"{HEAD} ds. {TAIL}", "EASA",
    }
    assert groups[KEY]["raw_lemmas"] == [HEAD.lower(), TAIL.lower(), "easa"]


def test_do_spraw_uses_normalized_canonical_and_original_aliases():
    groups = make_groups()
    text = f"{HEAD} do spraw {TAIL} (EASA)"
    assert merge_compound_org_names(text, groups) == [KEY]
    assert f"{HEAD} do spraw {TAIL}" in groups[KEY]["variants"]
    assert f"{HEAD} do spraw {TAIL} EASA" in groups[KEY]["variants"]


def test_standalone_acronym_remains_with_its_own_count():
    groups = make_groups()
    groups[("orgName", "EASA")]["count"] = 2
    merge_compound_org_names(f"{CANONICAL}. EASA ostrzega.", groups)
    # Only the parenthesized occurrence is consumed; standalone EASA stays.
    assert groups[("orgName", "EASA")]["count"] == 1
    assert groups[KEY]["count"] == 1
    assert set(groups) == {KEY, ("orgName", "EASA")}


@pytest.mark.parametrize("text", [f"{HEAD} ds. {TAIL}", f"{HEAD} ds. {TAIL} EASA"])
def test_no_parenthesized_acronym(text):
    groups = make_groups()
    before = deepcopy(groups)
    assert merge_compound_org_names(text, groups) == []
    assert groups == before


@pytest.mark.parametrize("missing", [HEAD, TAIL, "EASA"])
@pytest.mark.parametrize("replacement_type", [None, "persName", "placeName"])
def test_every_component_must_be_an_existing_org(missing, replacement_type):
    groups = make_groups()
    component = groups.pop(("orgName", missing))
    if replacement_type:
        groups[(replacement_type, missing)] = component
    before = deepcopy(groups)
    assert merge_compound_org_names(CANONICAL, groups) == []
    assert groups == before


def test_idempotency_even_when_all_components_have_standalone_mentions():
    groups = make_groups(count=2)
    text = f"{CANONICAL}. {HEAD}. {TAIL}. EASA."
    assert merge_compound_org_names(text, groups) == [KEY]
    before = deepcopy(groups)
    assert merge_compound_org_names(text, groups) == []
    assert groups == before


def test_existing_canonical_group_is_untouched():
    groups = make_groups()
    groups[("orgName", CANONICAL.lower())] = {"count": 3, "variants": [], "raw_lemmas": []}
    before = deepcopy(groups)
    assert merge_compound_org_names(CANONICAL, groups) == []
    assert groups == before


def test_other_groups_are_untouched():
    groups = make_groups()
    others = {
        ("orgName", name): {"count": 2, "variants": [name], "raw_lemmas": [name]}
        for name in ("FAA", "Reuters")
    }
    groups.update(deepcopy(others))
    merge_compound_org_names(f"{CANONICAL}. FAA Reuters.", groups)
    assert {key: groups[key] for key in others} == others


def test_repeated_patterns_count_once_each_and_union_raw_lemmas():
    groups = make_groups(count=2)
    groups[("orgName", HEAD)]["raw_lemmas"].append("shared")
    groups[("orgName", TAIL)]["raw_lemmas"].append("shared")
    assert merge_compound_org_names(f"{CANONICAL}. {HEAD} do spraw {TAIL} (EASA).", groups) == [KEY]
    assert set(groups) == {KEY}
    assert groups[KEY]["count"] == 2
    assert groups[KEY]["raw_lemmas"].count("shared") == 1


def test_variants_case_insensitivity_and_whitespace():
    groups = make_groups()
    groups[("orgName", "lemma head")] = groups.pop(("orgName", HEAD))
    groups[("orgName", "lemma tail")] = groups.pop(("orgName", TAIL))
    groups[("orgName", "easa")] = groups.pop(("orgName", "EASA"))
    text = "AGENCJA  Unii\nEuropejskiej\n do  spraw\nBezpieczeństwa  Lotniczego  ( EASA )"
    result = merge_compound_org_names(text, groups)
    assert result == [("orgName", f"AGENCJA Unii Europejskiej ds. {TAIL} (EASA)")]
    assert len(groups) == 1


def test_equal_head_and_tail_are_not_merged():
    groups = make_groups()
    before = deepcopy(groups)
    assert merge_compound_org_names(f"{HEAD} ds. {HEAD} (EASA)", groups) == []
    assert groups == before


@pytest.mark.parametrize("acronym", ["E", "ABCDEFGHI", "Easa", "EA-SA"])
def test_acronym_format(acronym):
    groups = make_groups()
    groups[("orgName", acronym)] = groups.pop(("orgName", "EASA"))
    before = deepcopy(groups)
    assert merge_compound_org_names(f"{HEAD} ds. {TAIL} ({acronym})", groups) == []
    assert groups == before


@pytest.mark.parametrize("acronym", ["AB", "AB12", "ABCDEFGH"])
def test_short_and_alphanumeric_acronyms(acronym):
    groups = make_groups()
    groups[("orgName", acronym)] = groups.pop(("orgName", "EASA"))
    text = f"{HEAD} ds. {TAIL} ({acronym})"
    assert merge_compound_org_names(text, groups) == [("orgName", text)]
    assert acronym in groups[("orgName", text)]["variants"]


@pytest.mark.parametrize("text", [f"X{CANONICAL}", f"{HEAD} ds. {TAIL}x (EASA)"])
def test_word_boundaries(text):
    groups = make_groups()
    before = deepcopy(groups)
    assert merge_compound_org_names(text, groups) == []
    assert groups == before


def test_ambiguous_component_alias_is_not_merged():
    groups = make_groups()
    groups[("orgName", "Other agency")] = {"count": 1, "variants": [HEAD]}
    before = deepcopy(groups)
    assert merge_compound_org_names(CANONICAL, groups) == []
    assert groups == before
