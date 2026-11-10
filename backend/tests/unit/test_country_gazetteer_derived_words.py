"""A word merely derived from a country's stem ("Afganistanopodobny") is not a mention of the country."""

import pytest

pytest.importorskip("unidecode")

from library.country_gazetteer import count_country_mentions, detect_countries, mention_snippets


def counts(text):
    return {entry.name_pl: n for entry, n in count_country_mentions(text)}


@pytest.mark.parametrize(
    "text",
    [
        "To jest taki Afganistanopodobny teren.",
        "Chodzi o afganistanizację regionu.",
        "Mówi się o chinizacji gospodarki.",
        "Podejście rosjocentryczne i rosyjskocentryczne.",
    ],
)
def test_derived_words_are_not_mentions(text):
    assert counts(text).get("Afganistan", 0) == 0
    assert counts(text).get("Chiny", 0) == 0
    assert counts(text).get("Rosja", 0) == 0


def test_a_derived_word_does_not_inflate_the_real_count():
    text = "Afganistanopodobny teren. Afganistanopodobny kraj. Afganistan i afgańskie góry."
    assert counts(text) == {"Afganistan": 2}
    assert [entry.name_pl for entry in detect_countries("To Afganistanopodobny teren.")] == []


@pytest.mark.parametrize(
    "text, country",
    [
        ("rozmowy z rosyjskich źródeł", "Rosja"),
        ("władze chińskich prowincji", "Chiny"),
        ("irańskiego prezydenta", "Iran"),
        ("prezydent Kazachstanu", "Kazachstan"),
        ("w Afganistanie i z Afganistanem", "Afganistan"),
        ("afgańsko-pakistańska granica", "Afganistan"),
        ("w Stanach Zjednoczonych", "Stany Zjednoczone"),
        ("Zjednoczonych Emiratów Arabskich", "Zjednoczone Emiraty Arabskie"),
    ],
)
def test_real_inflections_and_adjectives_still_count(text, country):
    assert counts(text).get(country, 0) >= 1


def test_snippets_skip_derived_words():
    text = "To Afganistanopodobny teren, a nie Afganistan."
    found = mention_snippets(text, detect_countries(text))
    assert list(found) == ["Afganistan"]
    assert len(found["Afganistan"]) == 1 and found["Afganistan"][0].endswith("Afganistan.")
