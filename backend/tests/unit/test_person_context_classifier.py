"""Tests for contextual verification of one-word person candidates."""

import json
from unittest.mock import MagicMock, patch

from library.person_context_classifier import (
    MAX_CANDIDATES_PER_CALL,
    _candidate_payloads,
    classify_single_word_person_candidates,
)


def test_candidate_payloads_only_include_one_word_persons_with_context():
    groups = {
        ("persName", "Pocisków"): {"variants": ["Pocisków"]},
        ("persName", "Donald Tusk"): {"variants": ["Donalda Tuska"]},
        ("placeName", "Warszawa"): {"variants": ["Warszawie"]},
        ("persName", "Nieobecny"): {"variants": []},
    }
    result = _candidate_payloads(
        "Rozpoczęto dostawy Pocisków artyleryjskich.",
        groups,
    )
    assert [item["entity_text"] for item in result] == ["Pocisków"]
    assert "artyleryjskich" in result[0]["context"]


def test_pseudonym_backed_by_an_explicit_cue_is_not_sent_to_the_model():
    """„Kryminał” after „ps.” is a person by the text's own words, not a common noun to second-guess."""
    groups = {
        ("persName", "Kryminał"): {"variants": ["Kryminał"], "pseudonym": True},
        ("persName", "Pocisków"): {"variants": ["Pocisków"]},
    }
    text = 'Andrij Osipow, ps. "Kryminał" oraz dostawy Pocisków artyleryjskich.'
    assert [item["entity_text"] for item in _candidate_payloads(text, groups)] == ["Pocisków"]


def test_high_confidence_not_person_is_marked_for_dropping():
    groups = {("persName", "Pocisków"): {"variants": ["Pocisków"]}}
    response = MagicMock()
    response.response_text = (
        '{"results":[{"id":0,"class":"not_person","confidence":"high",'
        '"rationale":"Rodzaj amunicji."}]}'
    )
    with patch("library.person_context_classifier._model", return_value="Bielik-11B-v3.0-Instruct"), patch(
        "library.ai.ai_ask", return_value=response
    ) as ask:
        result = classify_single_word_person_candidates(
            "Dostawy Pocisków artyleryjskich.", "Tytuł", groups, 8850
        )

    assert result[0]["dropped"] is True
    assert result[0]["predicted_class"] == "not_person"
    assert ask.call_args.kwargs["operation"] == "ner_person_context_verification"
    assert ask.call_args.kwargs["document_id"] == 8850


def test_medium_confidence_not_person_is_retained():
    groups = {("persName", "Pocisków"): {"variants": ["Pocisków"]}}
    response = MagicMock()
    response.response_text = (
        '{"results":[{"id":0,"class":"not_person","confidence":"medium",'
        '"rationale":"Kontekst niepełny."}]}'
    )
    with patch("library.person_context_classifier._model", return_value="Bielik-11B-v3.0-Instruct"), patch(
        "library.ai.ai_ask", return_value=response
    ):
        result = classify_single_word_person_candidates(
            "Wspomniano Pocisków w tekście.", "", groups, 1
        )
    assert result[0]["dropped"] is False


def test_llm_failure_is_fail_open():
    groups = {("persName", "Pocisków"): {"variants": ["Pocisków"]}}
    with patch("library.person_context_classifier._model", return_value="Bielik-11B-v3.0-Instruct"), patch(
        "library.ai.ai_ask", side_effect=RuntimeError("offline")
    ):
        result = classify_single_word_person_candidates(
            "Dostawy Pocisków artyleryjskich.", "", groups, 1
        )
    assert result == []


def _truncating_ai_ask(max_batch):
    """A fake model whose answer is cut off (invalid JSON) when the batch is larger than `max_batch`."""

    def fake(prompt, **_kwargs):
        items = json.loads(prompt.split("DANE JSON:\n")[1])
        if len(items) > max_batch:
            return MagicMock(response_text='{"results": [{"id": 0, "class": "person", "confidence": "hi')
        return MagicMock(response_text=json.dumps({"results": [
            {
                "id": item["id"],
                "class": "not_person" if item["candidate"] == "Konstans" else "person",
                "confidence": "high",
                "rationale": "test",
            }
            for item in items
        ]}))

    return fake


def test_truncated_json_batch_is_split_and_every_candidate_gets_a_verdict():
    """doc 11274: two of three batches of 20 came back cut off, so "Konstans" never got a verdict."""
    names = ["Konstans"] + [f"Osoba{i}" for i in range(29)]
    groups = {("persName", name): {"variants": [name]} for name in names}
    text = " ".join(f"Wypowiedział się {name} w tej sprawie." for name in names)

    assert MAX_CANDIDATES_PER_CALL <= 8
    with patch("library.person_context_classifier._model", return_value="Bielik-11B-v3.0-Instruct"), patch(
        "library.ai.ai_ask", side_effect=_truncating_ai_ask(max_batch=2)
    ):
        results = classify_single_word_person_candidates(text, "Tytuł", groups, 11274)

    assert {result["entity_text"] for result in results} == set(names)
    konstans = next(result for result in results if result["entity_text"] == "Konstans")
    assert konstans["dropped"] is True


def _scripted_ai_ask(first_pass_drops, second_pass_drops, calls):
    """First call round answers `first_pass_drops` as not_person/high, the next round `second_pass_drops`."""

    def fake(prompt, **_kwargs):
        items = json.loads(prompt.split("DANE JSON:\n")[1])
        calls.append([item["candidate"] for item in items])
        # a pass is over once every distinct candidate has been asked about
        asked = {name for call in calls[:-1] for name in call}
        second_round = len(asked) >= 3 and items[0]["candidate"] in asked
        drops = second_pass_drops if second_round else first_pass_drops
        return MagicMock(response_text=json.dumps({"results": [
            {
                "id": item["id"],
                "class": "not_person" if item["candidate"] in drops else "person",
                "confidence": "high",
                "rationale": "test",
            }
            for item in items
        ]}))

    return fake


def _groups(*names):
    return {("persName", name): {"variants": [name]} for name in names}


def test_drop_needs_a_confirming_second_pass_in_a_different_batch_order():
    """doc 11274: the same mis-heard surname was not_person/high in one batch and person in another."""
    names = ["Besent", "Konstans", "Rubio"]
    text = " ".join(f"Wspomniano {name} tutaj." for name in names)
    calls = []
    with patch("library.person_context_classifier._model", return_value="Bielik-11B-v3.0-Instruct"), patch(
        "library.ai.ai_ask", side_effect=_scripted_ai_ask({"Besent", "Konstans"}, {"Konstans"}, calls)
    ):
        results = classify_single_word_person_candidates(text, "", _groups(*names), 1)

    verdicts = {result["entity_text"]: result for result in results}
    assert verdicts["Konstans"]["dropped"] is True
    assert verdicts["Besent"]["dropped"] is False
    assert "niepotwierdzone" in verdicts["Besent"]["rationale"]
    assert verdicts["Rubio"]["dropped"] is False
    assert len(calls) == 2
    assert calls[0] != calls[1]


def test_no_second_pass_when_the_first_pass_drops_nothing():
    calls = []
    with patch("library.person_context_classifier._model", return_value="Bielik-11B-v3.0-Instruct"), patch(
        "library.ai.ai_ask", side_effect=_scripted_ai_ask(set(), set(), calls)
    ):
        results = classify_single_word_person_candidates("Wspomniano Rubio i Musk.", "", _groups("Rubio", "Musk"), 1)
    assert len(calls) == 1
    assert not any(result["dropped"] for result in results)


def test_failed_second_pass_keeps_the_entity():
    names = ["Konstans", "Rubio"]
    text = "Wspomniano Konstans i Rubio."
    responses = iter([
        MagicMock(response_text=json.dumps({"results": [
            {"id": 0, "class": "not_person", "confidence": "high", "rationale": "rzecz"},
            {"id": 1, "class": "person", "confidence": "high", "rationale": "osoba"},
        ]})),
    ])

    def fake(prompt, **_kwargs):
        try:
            return next(responses)
        except StopIteration as error:
            raise RuntimeError("offline") from error

    with patch("library.person_context_classifier._model", return_value="Bielik-11B-v3.0-Instruct"), patch(
        "library.ai.ai_ask", side_effect=fake
    ):
        results = classify_single_word_person_candidates(text, "", _groups(*names), 1)
    assert {result["entity_text"] for result in results} == set(names)
    assert not any(result["dropped"] for result in results)


def test_fixture_of_real_contexts_is_well_formed():
    from pathlib import Path

    fixture = json.loads(
        (Path(__file__).resolve().parent.parent / "fixtures" / "person_context_cases.json").read_text(encoding="utf-8")
    )
    cases = fixture["cases"]
    assert len(cases) >= 30
    assert {case["expected"] for case in cases} == {"person", "not_person"}
    assert len({case["candidate"] for case in cases}) == len(cases)
    assert all(case["candidate"] and case["context"] for case in cases)


def test_single_candidate_with_unparseable_json_is_retained_without_raising():
    groups = {("persName", "Konstans"): {"variants": ["Konstans"]}}
    with patch("library.person_context_classifier._model", return_value="Bielik-11B-v3.0-Instruct"), patch(
        "library.ai.ai_ask", side_effect=_truncating_ai_ask(max_batch=0)
    ):
        result = classify_single_word_person_candidates("Dodano Konstans do listy.", "", groups, 11274)
    assert result == []
