"""Tests for contextual verification of one-word person candidates."""

from unittest.mock import MagicMock, patch

from library.person_context_classifier import (
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
