"""STT phrase regression and cache/statistics tests without a database."""

from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")

from library import transcript_corrections as rules

PATTERN = "pi\u0119to Achillesa"
REPLACEMENT = "pi\u0119ta Achillesa"
SOURCE = (
    "Chocia\u017c zaznaczam ... on jest t\u0105 pi\u0119to Achillesa do Rosji, "
    "no bo nie ma go za bardzo ani jak zaopatrzy\u0107"
)


def row(pattern=PATTERN, replacement=REPLACEMENT, scope="global", author=None, rule_id=42):
    return rules.TranscriptCorrectionRow(rule_id, scope, author, pattern, replacement)


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    rules.bust_cache()
    monkeypatch.setattr(rules, "get_session", MagicMock(side_effect=AssertionError("No database in unit tests")))
    yield
    rules.bust_cache()


def test_doc_10872_regression(monkeypatch):
    monkeypatch.setattr(rules, "load_active_rules", lambda **kwargs: [row()])
    bump = MagicMock()
    monkeypatch.setattr(rules, "_bump_hit_counts", bump)
    corrected, hits = rules.apply_transcript_corrections(SOURCE)
    assert corrected == SOURCE.replace(PATTERN, REPLACEMENT)
    assert REPLACEMENT in corrected and PATTERN not in corrected
    assert hits == [(42, 1)]
    bump.assert_called_once_with(hits, session=None)
    assert rules.correct_text(SOURCE, None, [])[0] == SOURCE


@pytest.mark.parametrize("text", ["pi\u0119tro", "pi\u0119t\u0119 Achillesa", "pi\u0119ty Achillesa",
                                  "x" + PATTERN, PATTERN + "mi", "_" + PATTERN, PATTERN + "2"])
def test_other_forms_and_word_boundaries_untouched(text):
    assert rules.correct_text(text, None, [row()]) == (text, [])


def test_capitalisation_whitespace_and_counts():
    text = "Pi\u0119to\n\tAchillesa; " + PATTERN + "."
    assert rules.correct_text(text, None, [row()]) == ("Pi\u0119ta Achillesa; " + REPLACEMENT + ".", [(42, 2)])


def test_literal_metacharacters_and_literal_replacement():
    assert rules.correct_text("a+b test", None, [row("a+b test", r"literal \1")]) == (r"literal \1", [(42, 1)])
    assert rules.correct_text("aaab test", None, [row("a+b test", "fixed text")])[1] == []


def test_author_normalization():
    scoped = row(scope="author", author="Na Wschod od Bliskiego Wschodu")
    assert rules.correct_text(PATTERN, "  NA WSCHOD  OD BLISKIEGO WSCHODU  ", [scoped])[1] == [(42, 1)]
    for author in (None, "Other channel"):
        assert rules.correct_text(PATTERN, author, [scoped]) == (PATTERN, [])
    assert rules.correct_text(PATTERN, "Other channel", [row()])[1] == [(42, 1)]


def test_longest_first_and_single_pass():
    assert rules.correct_text("one two three", None, [row("one two", "short text"),
                              row("one two three", "long text", rule_id=43)]) == ("long text", [(43, 1)])
    assert rules.correct_text("one two", None, [row("one two", "one two two")]) == ("one two two", [(42, 1)])


@pytest.mark.parametrize("pattern", ["", "  ", "word", "averylongsingleword", "word!", "... ..."])
def test_reject_single_words_and_empty_patterns(pattern):
    with pytest.raises(rules.TranscriptCorrectionValidationError):
        rules.validate_rule(pattern=pattern, replacement="fixed text")


@pytest.mark.parametrize("values", [
    {"replacement": PATTERN}, {"replacement": None}, {"scope": "other"},
    {"scope": "author"}, {"scope": "author", "author": "  "}, {"author": "channel"}, {"author": 42},
])
def test_invalid_rules(values):
    data = dict(pattern=PATTERN, replacement=REPLACEMENT)
    data.update(values)
    with pytest.raises(rules.TranscriptCorrectionValidationError):
        rules.validate_rule(**data)


def test_valid_phrase_thresholds():
    rules.validate_rule(pattern="a b", replacement="c d")
    rules.validate_rule(pattern="longword-otherword", replacement="c d")


def test_cache_ttl_bust_and_explicit_session(monkeypatch):
    clock = [100.0]
    session = MagicMock()
    session.scalars.return_value = [row()]
    factory = MagicMock(return_value=session)
    monkeypatch.setattr(rules, "get_session", factory)
    monkeypatch.setattr(rules.time, "monotonic", lambda: clock[0])
    assert rules.load_active_rules() == rules.load_active_rules() == [row()]
    assert factory.call_count == 1
    rules.bust_cache()
    rules.load_active_rules()
    clock[0] += 61
    rules.load_active_rules()
    assert factory.call_count == session.close.call_count == 3
    assert rules.load_active_rules(session=session) == [row()]
    assert factory.call_count == 3


@pytest.mark.parametrize("error", [RuntimeError("no DB"), SystemExit(1)])
def test_db_failure_is_cached_noop(monkeypatch, error):
    factory = MagicMock(side_effect=error)
    monkeypatch.setattr(rules, "get_session", factory)
    assert rules.apply_transcript_corrections(SOURCE) == (SOURCE, [])
    assert rules.load_active_rules() == []
    assert factory.call_count == 1
    rules._bump_hit_counts([(42, 1)])


def test_statistics_failure_does_not_lose_corrected_text(monkeypatch):
    session = MagicMock()
    session.scalars.return_value = [row()]
    session.execute.side_effect = RuntimeError("statistics unavailable")
    monkeypatch.setattr(rules, "get_session", lambda: session)
    assert rules.apply_transcript_corrections(PATTERN) == (REPLACEMENT, [(42, 1)])
    session.rollback.assert_called_once()
    assert session.close.call_count == 2


def test_statistics_count_and_caller_session_ownership():
    session = MagicMock()
    rules._bump_hit_counts([(42, 3)], session=session)
    assert session.execute.call_args.args[0].compile().params["hit_count_1"] == 3
    session.commit.assert_not_called()
    session.close.assert_not_called()
