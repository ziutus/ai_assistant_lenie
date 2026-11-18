"""The Cape Verde starter dictionary on real fragments of doc #11263, without a database."""

from pathlib import Path

import pytest

pytest.importorskip("sqlalchemy")

from imports import seed_region_corrections as seeder
from library import transcript_corrections as rules

DICTIONARY = Path(__file__).resolve().parents[2] / "data" / "region_corrections" / "kraj-republika-zielonego-przyladka.json"
CAPE_VERDE = "kraj-republika-zielonego-przyladka"


def dictionary_rows():
    slug, loaded = seeder.load_dictionary(DICTIONARY)
    assert slug == CAPE_VERDE
    return [rules.TranscriptCorrectionRow(i, "region", r["author"], r["pattern"], r["replacement"], slug)
            for i, r in enumerate(loaded, start=1)]


def fix(text, countries=frozenset({CAPE_VERDE})):
    return rules.correct_text(text, "Na Wschód od Bliskiego Wschodu", dictionary_rows(), set(countries))[0]


@pytest.mark.parametrize("source,expected", [
    ("którzy zmierzą się z prezydentem Hosą Hosem Mario Navesem ubiegającym się o drugą kadencję",
     "którzy zmierzą się z prezydentem José Marią Nevesem ubiegającym się o drugą kadencję"),
    ("burmistrza stolicy, który się nazywa Praja na stanowisko premiera",
     "burmistrza stolicy, który się nazywa Praia na stanowisko premiera"),
    ("mianować Francisco Carvalio, ówczesnego burmistrza", "mianować Francisco Carvalho, ówczesnego burmistrza"),
    ("z diaspory Republiki Zielonego Przyjęcia Przylądka jest zarejestrowanych",
     "z diaspory Republiki Zielonego Przylądka jest zarejestrowanych"),
    ("za granicę z Republiki Zielonego Przylątka za granicę", "za granicę z Republiki Zielonego Przylądka za granicę"),
])
def test_real_fragments(source, expected):
    assert fix(source) == expected


def test_silent_without_the_country_tag():
    text = "z prezydentem Hosą Hosem Mario Navesem"
    assert fix(text, countries=frozenset()) == text
    assert fix(text, countries=frozenset({"kraj-jemen"})) == text


def test_correct_forms_stay_untouched():
    text = "prezydent José Maria Neves z Republiki Zielonego Przylądka, stolica Praia, Carvalho"
    assert fix(text) == text
