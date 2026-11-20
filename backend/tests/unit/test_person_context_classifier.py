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


def test_single_candidate_with_unparseable_json_is_retained_without_raising():
    groups = {("persName", "Konstans"): {"variants": ["Konstans"]}}
    with patch("library.person_context_classifier._model", return_value="Bielik-11B-v3.0-Instruct"), patch(
        "library.ai.ai_ask", side_effect=_truncating_ai_ask(max_batch=0)
    ):
        result = classify_single_word_person_candidates("Dodano Konstans do listy.", "", groups, 11274)
    assert result == []
