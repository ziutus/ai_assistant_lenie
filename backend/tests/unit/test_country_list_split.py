"""A mention that is only a list of countries is split into one group per country (doc 11274)."""

import pytest

pytest.importorskip("sqlalchemy")

from library.entity_service import _split_country_lists, country_split_parts  # noqa: E402


def test_country_split_parts_keeps_the_words_as_written():
    assert country_split_parts("Stanów Zjednoczonych Rosji") == [
        ("Stany Zjednoczone", "Stanów Zjednoczonych"),
        ("Rosja", "Rosji"),
    ]
    assert country_split_parts("Korea Południowa Japonia") == [
        ("Korea Południowa", "Korea Południowa"),
        ("Japonia", "Japonia"),
    ]
    assert country_split_parts("Iran, Irak i Syria") == [("Iran", "Iran"), ("Irak", "Irak"), ("Syria", "Syria")]


@pytest.mark.parametrize("form", [
    "Stany Zjednoczone",  # one two-word country
    "Polska",
    "Unia Europejska",
    "Kijów Lwów",  # not countries
    "Trump Putin",  # persons
    "Polska Kijów",  # one word is not a country
])
def test_country_split_parts_ignores_everything_but_a_list_of_countries(form):
    assert country_split_parts(form) is None


def test_glued_organization_is_added_to_the_existing_country_groups():
    groups = {
        ("orgName", "Stanów Zjednoczonych Rosji"): {"count": 1, "variants": ["Stanów Zjednoczonych Rosji"]},
        ("placeName", "Stany Zjednoczone"): {"count": 51, "variants": ["USA"], "raw_lemmas": ["Stany Zjednoczone"]},
        ("placeName", "Rosja"): {"count": 16, "variants": ["Rosji"], "raw_lemmas": ["Rosja"]},
    }

    split = _split_country_lists(groups)

    assert split == ["Stanów Zjednoczonych Rosji"]
    assert ("orgName", "Stanów Zjednoczonych Rosji") not in groups
    assert groups[("placeName", "Stany Zjednoczone")]["count"] == 52
    assert groups[("placeName", "Stany Zjednoczone")]["variants"] == ["USA", "Stanów Zjednoczonych"]
    assert groups[("placeName", "Rosja")]["count"] == 17
    assert groups[("placeName", "Rosja")]["variants"] == ["Rosji"]  # the spelling is already known


def test_missing_country_groups_are_created_and_counts_follow_the_mentions():
    groups = {("placeName", "Iran Irak"): {"count": 3, "variants": ["Iran Irak", "Iranem Irakiem"]}}

    assert _split_country_lists(groups) == ["Iran Irak"]

    assert set(groups) == {("placeName", "Iran"), ("placeName", "Irak")}
    assert groups[("placeName", "Iran")]["count"] == 3
    assert groups[("placeName", "Iran")]["variants"] == ["Iran", "Iranem"]
    assert groups[("placeName", "Irak")]["variants"] == ["Irak", "Irakiem"]


def test_other_groups_and_single_countries_are_untouched():
    groups = {
        ("persName", "Trump Putin"): {"count": 2, "variants": ["Trump Putin"]},
        ("orgName", "Unia Europejska"): {"count": 4, "variants": []},
        ("placeName", "Stany Zjednoczone"): {"count": 51, "variants": ["USA"]},
    }
    before = {key: dict(value) for key, value in groups.items()}

    assert _split_country_lists(groups) == []
    assert groups == before
