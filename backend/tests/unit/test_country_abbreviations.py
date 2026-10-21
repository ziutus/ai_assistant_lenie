"""Contextual LLM check of ambiguous country abbreviations (DRK = Kongo vs German Red Cross)."""

import json
from types import SimpleNamespace

import pytest

pytest.importorskip("unidecode")

from library import article_tagging, country_abbreviations, entity_service
from library.country_gazetteer import canonical_country_name, country_tag_for

TEXT = "Podczas gdy DRK, czyli Demokratyczna Republika Kongo, nałożyła limity na kobalt. DRK wstrzymało eksport."


def verdict(**overrides):
    return {"id": 0, "class": "country", "confidence": "high", "rationale": "kobalt"} | overrides


@pytest.fixture
def llm(monkeypatch):
    calls = []

    def fake_ask(prompt, **kwargs):
        calls.append((prompt, kwargs))
        return SimpleNamespace(response_text=json.dumps({"results": [verdict()]}))

    monkeypatch.setattr("library.ai.ai_ask", fake_ask)
    monkeypatch.setattr(country_abbreviations, "_model", lambda: "test-model")
    return calls


def test_every_abbreviation_points_at_a_gazetteer_country():
    for abbreviation, country in country_abbreviations.COUNTRY_ABBREVIATIONS.items():
        assert canonical_country_name(country) == country, abbreviation


def test_candidates_are_case_sensitive_whole_words():
    assert country_abbreviations.find_abbreviation_candidates("drk, DRKi i ADRK") == []
    [candidate] = country_abbreviations.find_abbreviation_candidates(TEXT)
    assert candidate["abbreviation"] == "DRK" and candidate["count"] == 2


def test_no_candidate_means_no_llm_call(llm):
    assert country_abbreviations.classify_country_abbreviations("Nic o skrótach.") == []
    assert llm == []


def test_confident_country_verdict_is_confirmed(llm):
    confirmed = country_abbreviations.confirmed_country_abbreviations(TEXT, "Kobalt", 7)
    assert confirmed == {"DRK": {"country": "Demokratyczna Republika Konga", "count": 2}}
    assert llm[0][1]["document_id"] == 7


@pytest.mark.parametrize("answer", [
    verdict(**{"class": "other"}), verdict(**{"class": "uncertain"}), verdict(confidence="low"),
])
def test_other_verdicts_confirm_nothing(monkeypatch, answer):
    monkeypatch.setattr("library.ai.ai_ask", lambda *a, **k: SimpleNamespace(
        response_text=json.dumps({"results": [answer]})))
    assert country_abbreviations.confirmed_country_abbreviations(TEXT) == {}


@pytest.mark.parametrize("failure", ["not json", RuntimeError("down")])
def test_llm_failure_fails_open(monkeypatch, failure):
    def fake_ask(*args, **kwargs):
        if isinstance(failure, Exception):
            raise failure
        return SimpleNamespace(response_text=failure)

    monkeypatch.setattr("library.ai.ai_ask", fake_ask)
    assert country_abbreviations.confirmed_country_abbreviations(TEXT) == {}


def test_entity_groups_get_the_country_instead_of_the_abbreviation(llm):
    groups = {("orgName", "DRK"): {"count": 1, "variants": ["DRK"], "raw_lemmas": ["DRK"]},
              ("persName", "Kowalski"): {"count": 1, "variants": []}}
    entity_service._apply_country_abbreviations(groups, TEXT, "Kobalt", 7)
    assert ("orgName", "DRK") not in groups and ("persName", "Kowalski") in groups
    assert groups[("placeName", "Demokratyczna Republika Konga")] == {
        "count": 2, "variants": ["DRK"], "raw_lemmas": ["Demokratyczna Republika Konga"]}


def test_abbreviation_folds_into_an_existing_country_group(llm):
    groups = {("placeName", "Demokratyczna Republika Konga"): {"count": 1, "variants": [], "raw_lemmas": []}}
    entity_service._apply_country_abbreviations(groups, TEXT, "", 7)
    group = groups[("placeName", "Demokratyczna Republika Konga")]
    assert group["count"] == 3 and group["variants"] == ["DRK"]


def test_unconfirmed_abbreviation_keeps_ner_group(monkeypatch):
    monkeypatch.setattr("library.ai.ai_ask", lambda *a, **k: SimpleNamespace(
        response_text=json.dumps({"results": [verdict(**{"class": "other"})]})))
    groups = {("orgName", "DRK"): {"count": 1, "variants": ["DRK"]}}
    entity_service._apply_country_abbreviations(groups, "Pomoc DRK dotarła na miejsce.", "", 7)
    assert list(groups) == [("orgName", "DRK")]


def test_hybrid_country_tags_include_confirmed_abbreviation(llm, monkeypatch):
    monkeypatch.setattr(article_tagging, "_extract_countries_from_gazetteer", lambda text, title: ["kraj-polska"])
    tags = article_tagging.extract_countries_hybrid(TEXT, "Kobalt")
    assert tags == ["kraj-polska", country_tag_for("Demokratyczna Republika Konga")]
