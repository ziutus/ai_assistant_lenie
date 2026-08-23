"""Tests for contextual verification of geocoded place candidates.

Regression coverage for doc 9267: "Pilica" (mention_count=3) used to be
auto-confirmed by place_verification.AUTO_CONFIRM_MENTIONS and tagged
miejsce-pilica without ever reaching an LLM, even though the mentions were
about the "Wisła-Narew-Pilica" air-defense system, not the town/river.
"""

from unittest.mock import MagicMock, patch

from library.place_context_classifier import (
    _candidate_payloads,
    classify_place_context_candidates,
)


def test_candidate_payloads_use_surface_form_for_snippet_lookup():
    groups = {
        "Pilica": {"mentions": 3, "surface": "Pilica", "surface_mentions": 3},
        "Bez kontekstu": {"mentions": 1, "surface": "Nigdzie", "surface_mentions": 1},
    }
    result = _candidate_payloads(
        "system obrony powietrznej Wisła-Narew-Pilica", groups,
    )
    assert [item["entity_text"] for item in result] == ["Pilica"]
    assert "Wisła-Narew" in result[0]["context"]
    assert result[0]["key"] == "Pilica"


def test_high_confidence_not_place_is_marked_for_dropping():
    """The doc 9267 case: "Pilica" is part of a weapon-system name, not the town."""
    groups = {"Pilica": {"mentions": 3, "surface": "Pilica", "surface_mentions": 3}}
    response = MagicMock()
    response.response_text = (
        '{"results":[{"id":0,"class":"not_place","confidence":"high",'
        '"rationale":"Część nazwy systemu obrony powietrznej."}]}'
    )
    with patch("library.place_context_classifier._model", return_value="Bielik-11B-v3.0-Instruct"), patch(
        "library.ai.ai_ask", return_value=response
    ) as ask:
        result = classify_place_context_candidates(
            "system obrony powietrznej Wisła-Narew-Pilica", "Tytuł", groups, 9267
        )

    assert result[0]["dropped"] is True
    assert result[0]["predicted_class"] == "not_place"
    assert ask.call_args.kwargs["operation"] == "ner_place_context_verification"
    assert ask.call_args.kwargs["document_id"] == 9267


def test_confirmed_place_is_retained():
    groups = {"Kijów": {"mentions": 2, "surface": "Kijów", "surface_mentions": 2}}
    response = MagicMock()
    response.response_text = (
        '{"results":[{"id":0,"class":"place","confidence":"high",'
        '"rationale":"Mowa o stolicy Ukrainy."}]}'
    )
    with patch("library.place_context_classifier._model", return_value="Bielik-11B-v3.0-Instruct"), patch(
        "library.ai.ai_ask", return_value=response
    ):
        result = classify_place_context_candidates(
            "Prezydent odwiedził Kijów.", "", groups, 1
        )
    assert result[0]["dropped"] is False
    assert result[0]["predicted_class"] == "place"


def test_high_confidence_organization_is_marked_for_dropping_and_routing():
    """doc 9345 regression: "Na Kremlu rozumieją, że dopóki tak jest, to oni
    kontrolują narrację" — metonymic reference to Russia's leadership, not
    the literal building. Must be dropped from place tagging AND flagged for
    organization routing (place_verification._reclassify_as_organization)."""
    groups = {"Kreml": {"surface": "Kreml"}}
    response = MagicMock()
    response.response_text = (
        '{"results":[{"id":0,"class":"organization","confidence":"high",'
        '"rationale":"Podmiotem jest rosyjskie kierownictwo, nie budynek."}]}'
    )
    with patch("library.place_context_classifier._model", return_value="Bielik-11B-v3.0-Instruct"), patch(
        "library.ai.ai_ask", return_value=response
    ):
        result = classify_place_context_candidates(
            "Na Kremlu rozumieją, że dopóki tak jest, to oni kontrolują narrację.", "", groups, 9345,
        )
    assert result[0]["predicted_class"] == "organization"
    assert result[0]["dropped"] is True
    assert result[0]["organization"] is True


def test_literal_visit_is_classified_as_place_not_organization():
    """doc 9394 regression: "wizyta w Białym Domu" is a real physical visit,
    not metonymy — must stay a place candidate, not get routed to
    organization."""
    groups = {"Biały Dom": {"surface": "Białym Domu"}}
    response = MagicMock()
    response.response_text = (
        '{"results":[{"id":0,"class":"place","confidence":"high",'
        '"rationale":"Fizyczna wizyta w budynku."}]}'
    )
    with patch("library.place_context_classifier._model", return_value="Bielik-11B-v3.0-Instruct"), patch(
        "library.ai.ai_ask", return_value=response
    ):
        result = classify_place_context_candidates(
            "Podczas wizyty w Białym Domu książę koronny wezwał Trumpa.", "", groups, 9394,
        )
    assert result[0]["predicted_class"] == "place"
    assert result[0]["dropped"] is False
    assert result[0]["organization"] is False


def test_medium_confidence_not_place_is_retained():
    groups = {"Pilica": {"mentions": 3, "surface": "Pilica", "surface_mentions": 3}}
    response = MagicMock()
    response.response_text = (
        '{"results":[{"id":0,"class":"not_place","confidence":"medium",'
        '"rationale":"Kontekst niepełny."}]}'
    )
    with patch("library.place_context_classifier._model", return_value="Bielik-11B-v3.0-Instruct"), patch(
        "library.ai.ai_ask", return_value=response
    ):
        result = classify_place_context_candidates(
            "Wspomniano Pilica w tekście.", "", groups, 1
        )
    assert result[0]["dropped"] is False


def test_llm_failure_is_fail_open():
    groups = {"Pilica": {"mentions": 3, "surface": "Pilica", "surface_mentions": 3}}
    with patch("library.place_context_classifier._model", return_value="Bielik-11B-v3.0-Instruct"), patch(
        "library.ai.ai_ask", side_effect=RuntimeError("offline")
    ):
        result = classify_place_context_candidates(
            "system Wisła-Narew-Pilica", "", groups, 1
        )
    assert result == []


def test_no_candidates_short_circuits_without_llm_call():
    with patch("library.ai.ai_ask") as ask:
        result = classify_place_context_candidates("tekst bez wzmianek", "", {}, 1)
    assert result == []
    ask.assert_not_called()
