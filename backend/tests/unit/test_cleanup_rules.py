"""Reguły ADR-027 i obie ścieżki czyszczenia bez dostępu do bazy."""

from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")

from library import article_cleaner as cleaner
from library import cleanup_rules as rules
from library.website import website_download_context as website

LONG_PARAGRAPH = (
    "To jest długi akapit właściwej treści artykułu, który ma zdecydowanie ponad "
    "osiemdziesiąt znaków i powinien zostać zachowany po czyszczeniu."
)


def row(pattern="Zajrzyj na nasz profil", match_type="literal_line", scope="global", domain=None):
    return rules.CleanupRuleRow(42, scope, domain, match_type, pattern)


@pytest.fixture(autouse=True)
def isolated_cache():
    rules.bust_cache()
    yield
    rules.bust_cache()


@pytest.mark.parametrize("line", [
    "ZAJRZYJ NA NASZ PROFIL.", " **Zajrzyj na nasz profil:** ", "_Zajrzyj na nasz profil_.",
])
def test_literal_normalization(line):
    assert rules.rule_matches(line, None, row())
    assert not rules.rule_matches("Inna linia", None, row())


def test_contains_guard():
    assert rules.rule_matches("Już teraz ZAJRZYJ NA NASZ PROFIL i zobacz", None, row(match_type="contains"))
    assert not rules.rule_matches("Krótki tekst", None, row("tekst", "contains"))
    with pytest.raises(rules.CleanupRuleValidationError):
        rules.validate_rule(scope="global", domain=None, match_type="contains", pattern="tekst")


@pytest.mark.parametrize("host,expected", [("wiadomosci.onet.pl", True), ("onet.pl", True),
                                         ("interia.pl", False), ("nieonet.pl", False), (None, False)])
def test_domain_scope(host, expected):
    assert rules.rule_matches("Zajrzyj na nasz profil", host, row(scope="domain", domain="www.onet.pl")) is expected
    assert rules.rule_matches("Zajrzyj na nasz profil", host, row())


def test_narrow_domain_does_not_match_siblings():
    assert not rules.rule_matches(
        "Zajrzyj na nasz profil", "sport.onet.pl", row(scope="domain", domain="wiadomosci.onet.pl"),
    )
    assert rules.host_from_url("https://WWW.Onet.PL/artykul") == "onet.pl"
    assert rules.host_from_url("") is None


@pytest.mark.parametrize("domain", [None, "", "https://onet.pl", "bad domain.pl", "-bad.pl"])
def test_invalid_domain(domain):
    with pytest.raises(rules.CleanupRuleValidationError):
        rules.validate_rule(scope="domain", domain=domain, match_type="literal_line", pattern="Fraza")


@pytest.mark.parametrize("pattern", ["reklama", "^.*$", "^[", "^" + "a" * 201])
def test_regex_gate_rejects(pattern):
    with pytest.raises(rules.CleanupRuleValidationError):
        rules.validate_rule(scope="global", domain=None, match_type="regex", pattern=pattern)
    assert not rules.rule_matches("tekst", None, row(pattern, "regex"))


def test_regex_good_corpus_and_safe_pattern():
    assert 15 <= len(rules.load_known_good_corpus()) <= 25
    with pytest.raises(rules.CleanupRuleValidationError, match="akapit 1"):
        rules.validate_rule(scope="global", domain=None, match_type="regex", pattern="^To jest długi")
    rules.validate_rule(scope="global", domain=None, match_type="regex", pattern=r"^Zajrzyj na nasz profil\.$")
    assert rules.rule_matches("Zajrzyj na nasz profil.", None, row(r"^Zajrzyj na nasz profil\.$", "regex"))


def test_regex_timeout_is_no_match(monkeypatch):
    compiled = MagicMock()
    compiled.search.side_effect = TimeoutError
    monkeypatch.setattr(rules, "_validated_regex", lambda pattern: compiled)
    assert not rules.rule_matches("tekst", None, row("^tekst$", "regex"))


def test_cache_ttl_and_bust(monkeypatch):
    clock = [100.0]
    session = MagicMock()
    session.scalars.return_value = [row()]
    factory = MagicMock(return_value=session)
    monkeypatch.setattr(rules, "get_session", factory)
    monkeypatch.setattr(rules.time, "monotonic", lambda: clock[0])
    assert rules.load_active_rules() == [row()]
    assert rules.load_active_rules() == [row()]
    assert factory.call_count == 1
    rules.bust_cache()
    rules.load_active_rules()
    assert factory.call_count == 2
    clock[0] += 61
    rules.load_active_rules()
    assert factory.call_count == 3
    assert session.close.call_count == 3


@pytest.mark.parametrize("error", [RuntimeError("brak DB"), SystemExit(1)])
def test_db_failure_is_noop(monkeypatch, error):
    factory = MagicMock(side_effect=error)
    monkeypatch.setattr(rules, "get_session", factory)
    assert rules.load_active_rules() == []
    assert rules.load_active_rules() == []
    assert factory.call_count == 1
    rules._bump_hit_counts({42})


def test_bump_batch_and_rollback(monkeypatch):
    session = MagicMock()
    monkeypatch.setattr(rules, "get_session", lambda: session)
    rules._bump_hit_counts({42, 43})
    session.execute.assert_called_once()
    assert session.execute.call_args.args[1] == {"ids": [42, 43]}
    session.commit.assert_called_once()
    session.close.assert_called_once()
    session.execute.side_effect = RuntimeError("brak DB")
    rules._bump_hit_counts({42})
    session.rollback.assert_called_once()


@pytest.mark.parametrize("url", ["", "https://onet.pl/a", "https://forbes.pl/a", "https://wp.pl/a", "https://money.pl/a",
                                 "https://gazeta.pl/a", "https://bankier.pl/a", "https://interia.pl/a", "https://ithardware.pl/a"])
def test_article_rule_and_no_db_behavior(monkeypatch, url):
    text = f"{LONG_PARAGRAPH}\n\nZajrzyj na nasz profil\n\nZajrzyj na nasz profil"
    monkeypatch.setattr(cleaner, "load_active_rules", lambda: [])
    bump = MagicMock()
    monkeypatch.setattr(cleaner, "_bump_hit_counts", bump)
    baseline = cleaner.clean_article_text(text, url)
    assert baseline["text"] == text
    bump.assert_not_called()
    monkeypatch.setattr(cleaner, "load_active_rules", lambda: [row()])
    result = cleaner.clean_article_text(text, url)
    assert result["text"] == LONG_PARAGRAPH
    bump.assert_called_once_with({42})
    assert {k: v for k, v in result.items() if k != "text"} == {k: v for k, v in baseline.items() if k != "text"}


@pytest.mark.parametrize("url", ["https://onet.pl/a", "https://forbes.pl/a"])
def test_onet_forbes_row_records_hit_before_legacy_rule(monkeypatch, url):
    phrase = "Dalsza część tekstu pod materiałem wideo."
    monkeypatch.setattr(cleaner, "load_active_rules", lambda: [row(phrase)])
    bump = MagicMock()
    monkeypatch.setattr(cleaner, "_bump_hit_counts", bump)
    assert cleaner.clean_article_text(f"{LONG_PARAGRAPH}\n\n*{phrase}*", url)["text"] == LONG_PARAGRAPH
    bump.assert_called_once_with({42})


@pytest.mark.parametrize("portal", ["onet", "money", "wp", "gazeta", "bankier", "interia", "ithardware"])
def test_direct_portal_cleaners(portal):
    hits = set()
    result = getattr(cleaner, f"_clean_lines_{portal}")([LONG_PARAGRAPH, row().pattern], [row()], None, hits)
    assert result == [LONG_PARAGRAPH]
    assert hits == {42}


def test_website_rules_after_site_rules(monkeypatch):
    monkeypatch.setattr(website, "load_config", lambda: {})
    monkeypatch.setattr(website, "load_site_rules", lambda path: {"_global": {"remove_string": ["prefix:"]}})
    monkeypatch.setattr(website, "load_active_rules", lambda: [row()])
    bump = MagicMock()
    monkeypatch.setattr(website, "_bump_hit_counts", bump)
    text = f"{LONG_PARAGRAPH}\n\nprefix:Zajrzyj na nasz profil\n"
    assert website.webpage_text_clean("https://onet.pl", text) == LONG_PARAGRAPH
    bump.assert_called_once_with({42})
    monkeypatch.setattr(website, "load_active_rules", lambda: [])
    assert website.webpage_text_clean("https://onet.pl", text) == text.replace("prefix:", "").strip("\n")
