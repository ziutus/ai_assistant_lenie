"""Region-scoped STT corrections (country tag, optional channel) without a database."""

from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")

from library import transcript_corrections as rules

YEMEN = "kraj-jemen"


def region_row(pattern="Hutni", replacement="Huti", author=None, slug=YEMEN, rule_id=7):
    return rules.TranscriptCorrectionRow(rule_id, "region", author, pattern, replacement, slug)


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    rules.bust_cache()
    monkeypatch.setattr(rules, "get_session", MagicMock(side_effect=AssertionError("No database in unit tests")))
    yield
    rules.bust_cache()


def test_region_rule_allows_single_word_and_needs_country_tag():
    text = "Hutni zaatakowali port."
    rule = region_row()
    assert rules.correct_text(text, None, [rule], {YEMEN}) == ("Huti zaatakowali port.", [(7, 1)])
    # No tag (also what the ingestion hook passes) or another country: the rule stays silent.
    assert rules.correct_text(text, None, [rule]) == (text, [])
    assert rules.correct_text(text, None, [rule], {"kraj-iran"}) == (text, [])


def test_region_rule_narrowed_to_channel():
    text = "Hutni atakuja."
    rule = region_row(author="Kanal Bliski Wschod")
    assert rules.correct_text(text, " KANAL  bliski wschod", [rule], {YEMEN})[1] == [(7, 1)]
    assert rules.correct_text(text, "Inny kanal", [rule], {YEMEN}) == (text, [])
    assert rules.correct_text(text, None, [rule], {YEMEN}) == (text, [])


def test_region_rule_respects_word_boundaries_and_case():
    assert rules.correct_text("hutnicy i Hutni", None, [region_row()], {YEMEN}) == ("hutnicy i Huti", [(7, 1)])


@pytest.mark.parametrize("values", [
    {"scope": "region"},
    {"scope": "region", "country_slug": "jemen"},
    {"scope": "region", "country_slug": "kraj-atlantyda"},
    {"scope": "region", "country_slug": YEMEN, "author": "  "},
    {"scope": "global", "country_slug": YEMEN},
    {"scope": "author", "author": "x", "country_slug": YEMEN},
])
def test_invalid_region_rules(values):
    with pytest.raises(rules.TranscriptCorrectionValidationError):
        rules.validate_rule(pattern="Hutni", replacement="Huti", **values)


@pytest.mark.parametrize("pattern", ["", "12", "ab", "... ..."])
def test_region_rule_rejects_non_words(pattern):
    with pytest.raises(rules.TranscriptCorrectionValidationError):
        rules.validate_rule(pattern=pattern, replacement="Huti", scope="region", country_slug=YEMEN)


def test_valid_region_rules():
    rules.validate_rule(pattern="Hutni", replacement="Huti", scope="region", country_slug=YEMEN)
    rules.validate_rule(pattern="Hutni", replacement="Huti", scope="region", country_slug=" KRAJ-JEMEN ",
                        author="Kanal")


def test_global_single_word_still_rejected():
    with pytest.raises(rules.TranscriptCorrectionValidationError):
        rules.validate_rule(pattern="Hutni", replacement="Huti")


def test_country_slugs_from_tags():
    assert rules.country_slugs_from_tags(["Kraj-Jemen", " kraj-iran ", "miejsce-aden", 5]) == {YEMEN, "kraj-iran"}
    assert rules.country_slugs_from_tags("kraj-jemen, polityka") == {YEMEN}
    assert rules.country_slugs_from_tags(None) == set()


def test_apply_passes_countries(monkeypatch):
    monkeypatch.setattr(rules, "load_active_rules", lambda **kwargs: [region_row()])
    monkeypatch.setattr(rules, "_bump_hit_counts", MagicMock())
    assert rules.apply_transcript_corrections("Hutni", countries={YEMEN}) == ("Huti", [(7, 1)])
    assert rules.apply_transcript_corrections("Hutni") == ("Hutni", [])
