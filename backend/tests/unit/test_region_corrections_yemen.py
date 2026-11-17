"""The Yemen starter dictionary on real fragments of doc #11263, plus the seed script, without a database."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")

from imports import seed_region_corrections as seeder
from library import transcript_corrections as rules

DICTIONARY = Path(__file__).resolve().parents[2] / "data" / "region_corrections" / "kraj-jemen.json"
YEMEN = "kraj-jemen"


def dictionary_rows():
    slug, loaded = seeder.load_dictionary(DICTIONARY)
    assert slug == YEMEN
    return [rules.TranscriptCorrectionRow(i, "region", r["author"], r["pattern"], r["replacement"], slug)
            for i, r in enumerate(loaded, start=1)]


def fix(text):
    return rules.correct_text(text, "Na Wschód od Bliskiego Wschodu", dictionary_rows(), {YEMEN})[0]


@pytest.mark.parametrize("source,expected", [
    ("wielką Wiktorię Hutik, wielką porażkę Saudów", "wielką Wiktorię Huti, wielką porażkę Saudów"),
    ("liczne informacje ze strony Hutin, ale", "liczne informacje ze strony Huti, ale"),
    ("Krótko mówiąc, Chut i tą całą", "Krótko mówiąc, Huti tą całą"),
    ("razem z Hutli wchodzą w skład", "razem z Huti wchodzą w skład"),
    ("prawdopodobnie zostało zajęte przez huti dużo więcej", "prawdopodobnie zostało zajęte przez Huti dużo więcej"),
    ("milicji właśnie Hutich", "milicji właśnie Hutich"),
    ("Huti cały czas jeszcze nie zdobyli Tais. Tais jest oblężone.",
     "Huti cały czas jeszcze nie zdobyli Taiz. Taiz jest oblężone."),
    ("będą jeszcze tylko Mari Tais, prawda?", "będą jeszcze tylko Marib, Taiz, prawda?"),
    ("poprawy wzgórza dookoła Marip przechodzą", "poprawy wzgórza dookoła Marib przechodzą"),
    ("nad cieśniną Bapel Mandep oraz Bappel Mandep i Bappelmande", "nad cieśniną Bab al-Mandab oraz Bab al-Mandab i Bab al-Mandab"),
    ("z wybrzeża zatokiadeńskiej, gdzie", "z wybrzeża Zatoki Adeńskiej, gdzie"),
    ("o marszu na sanę, wielkiej ofensywie", "o marszu na Sanę, wielkiej ofensywie"),
    ("odzyskiwał razem z nimi sane, więc", "odzyskiwał razem z nimi Sanę, więc"),
    ("nad Yemenu", "nad Jemenu"),
    ("nad regionem Medyny, Kuti zaprzeczają ten oskarżeni", "nad regionem Medyny, Huti zaprzeczają ten oskarżeni"),
    ("bo jednak atak na Aden. Aten to jest duże miasto", "bo jednak atak na Aden. Aden to jest duże miasto"),
    ("w tym 41 nalotów na Marib, Aljafi i Taiz", "w tym 41 nalotów na Marib, Al-Dżauf i Taiz"),
    ("w prowincji Lachć w południowo-zachodnim Jemenie", "w prowincji Lahdż w południowo-zachodnim Jemenie"),
    ("do obozu dla uchodźców Haras w prowincji", "do obozu dla uchodźców Al-Charaz w prowincji"),
    ("rzecznik koalicji Turki, almaliki informował", "rzecznik koalicji Turki al-Maliki informował"),
    ("wyspę przy Cieślinie Bab al-Mandab oraz", "wyspę przy Cieśninie Bab al-Mandab oraz"),
    ("nie mówię Janbu albo nie mówię Jan Bu, więc", "nie mówię Janbu albo nie mówię Janbu, więc"),
])
def test_real_fragments(source, expected):
    assert fix(source) == expected


@pytest.mark.parametrize("text", [
    "Huti zajęli Aden i Taiz w Jemenie, a w Sanie rządzi koalicja.",
    "Rząd Arabii Saudyjskiej i Emiratów prowadzi ofensywę.",
    "Mokka i Salecha zostają bez zmian.",
])
def test_correct_text_is_left_alone(text):
    assert fix(text) == text


def test_dictionary_is_ignored_without_the_country_tag():
    text = "Hutik i Tais"
    assert rules.correct_text(text, None, dictionary_rows(), {"kraj-iran"}) == (text, [])
    assert rules.correct_text(text, None, dictionary_rows()) == (text, [])


def test_longest_pattern_wins_over_its_part():
    # "Mari Tais" must be handled before the single word "Tais".
    assert fix("Mari Tais") == "Marib, Taiz"


def test_load_dictionary_reports_every_problem(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"country_slug": "kraj-atlantyda", "rules": [
        {"pattern": "Hutik", "replacement": "Huti"}]}), encoding="utf-8")
    with pytest.raises(ValueError, match="Hutik"):
        seeder.load_dictionary(bad)
    dup = tmp_path / "dup.json"
    dup.write_text(json.dumps({"country_slug": YEMEN, "rules": [
        {"pattern": "Hutik", "replacement": "Huti"}, {"pattern": "hutik", "replacement": "Huti"}]}),
        encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        seeder.load_dictionary(dup)


def test_seed_is_dry_run_by_default_and_skips_existing():
    _, loaded = seeder.load_dictionary(DICTIONARY)
    session = MagicMock()
    session.execute.return_value = [("hutik", None), ("tais", None)]
    result = seeder.seed(session, YEMEN, loaded, apply=False)
    assert result["added"] and "Hutik" in result["skipped_existing"] and "Tais" in result["skipped_existing"]
    assert len(result["added"]) + len(result["skipped_existing"]) == len(loaded)
    session.add.assert_not_called()
    session.commit.assert_not_called()


def test_seed_apply_writes_only_missing_rules(monkeypatch):
    bust = MagicMock()
    monkeypatch.setattr(seeder, "bust_cache", bust)
    _, loaded = seeder.load_dictionary(DICTIONARY)
    session = MagicMock()
    session.execute.return_value = [("hutik", None)]
    result = seeder.seed(session, YEMEN, loaded, apply=True)
    assert session.add.call_count == len(loaded) - 1
    added = session.add.call_args_list[0].args[0]
    assert added.scope == "region" and added.country_slug == YEMEN and added.created_by == seeder.CREATED_BY
    assert "Hutik" not in result["added"]
    session.commit.assert_called_once()
    bust.assert_called_once()
