"""Tests for contextual verification of geocoded place candidates.

Regression coverage for doc 9267: "Pilica" (mention_count=3) used to be
auto-confirmed by place_verification.AUTO_CONFIRM_MENTIONS and tagged
miejsce-pilica without ever reaching an LLM, even though the mentions were
about the "Wisła-Narew-Pilica" air-defense system, not the town/river.
"""

import json
from unittest.mock import MagicMock, patch

from library.place_context_classifier import (
    _SYSTEM_PROMPT,
    MAX_CANDIDATES_PER_CALL,
    _candidate_payloads,
    classify_place_context_candidates,
)


def test_prompt_distinguishes_western_bloc_from_direction_and_formation_name():
    organization = " ".join(_SYSTEM_PROMPT.split("- organization:")[1].split("- not_place:")[0].split())
    not_place = " ".join(_SYSTEM_PROMPT.split("- not_place:")[1].split("- uncertain:")[0].split())
    for phrase in (
        "Zachód", "Państwa Zachodu", "kraje Zachodu", "blok polityczno-kulturowy",
        "USA", "Kanada", "państwa europejskie", "Australia", "Nowa Zelandia",
        "na Zachodzie", "w krajach Zachodu", "Zachód reaguje", "przywódcy Zachodu",
    ):
        assert phrase in organization
    for phrase in ("na zachodzie kraju", "Polskie Siły Zbrojne na Zachodzie", "Front Zachodni"):
        assert phrase in not_place
    assert "high" in _SYSTEM_PROMPT
    assert "jednoznacznie" in _SYSTEM_PROMPT


def test_snippets_match_whole_words_and_use_actual_variants():
    groups = {"Huta": {"surface": "Huta", "variants": ["huty"]}}
    assert _candidate_payloads("Hutach i huty", groups)[0]["surfaces"] == ["huty"]
    assert _candidate_payloads("Hutach", groups) == []



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
    groups = {"Kreml": {"surface": "Kreml", "variants": ["Kremlu"]}}
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


def test_prompt_marks_place_names_inside_idioms_as_not_place():
    """doc 11137: "odsyła do Jerozolimy niewinnych cywilów" is a channel euphemism for killing."""
    not_place = " ".join(_SYSTEM_PROMPT.split("- not_place:")[1].split("- uncertain:")[0].split())
    for phrase in (
        "związku frazeologicznego", "eufemizmu", "odsyła do Jerozolimy niewinnych cywilów",
        "na drogę do Jerozolimy udało się 22 000 osób", "pielgrzymka do Jerozolimy",
    ):
        assert phrase in not_place


def _truncating_ai_ask(max_batch):
    """ai_ask double: answers with cut-off JSON for batches larger than max_batch."""
    def ask(prompt, **kwargs):
        items = json.loads(prompt.split("DANE JSON:\n")[1])
        response = MagicMock()
        if len(items) > max_batch:
            response.response_text = '{"results":[{"id":0,"class":"place","confidence":"high","rationale":"Mowa o mie'
        else:
            response.response_text = json.dumps({"results": [
                {
                    "id": item["id"],
                    "class": "not_place" if item["candidate"].startswith("Jerozolim") else "place",
                    "confidence": "high",
                    "rationale": "x",
                }
                for item in items
            ]})
        return response
    return ask


def test_truncated_json_batch_is_split_and_every_candidate_gets_a_verdict():
    """doc 11137: the first batch's answer was cut off, so "Jerozolima" never got a verdict."""
    sentence = "każdego dnia odsyła do Jerozolimy niewinnych cywilów."
    groups = {"Jerozolima": {"surface": "Jerozolima", "variants": ["Jerozolimy"]}}
    groups.update({f"Miasto{i}": {"surface": f"Miasto{i}"} for i in range(26)})
    text = sentence + " " + " ".join(f"Miasto{i} jest duże." for i in range(26))

    assert MAX_CANDIDATES_PER_CALL <= 8
    with patch("library.place_context_classifier._model", return_value="Bielik-11B-v3.0-Instruct"), patch(
        "library.ai.ai_ask", side_effect=_truncating_ai_ask(max_batch=2)
    ):
        results = classify_place_context_candidates(text, "Tytuł", groups, 11137)

    assert {result["key"] for result in results} == set(groups)
    jerusalem = next(result for result in results if result["key"] == "Jerozolima")
    assert jerusalem["predicted_class"] == "not_place"
    assert jerusalem["dropped"] is True
    assert sentence in jerusalem["context"]


def test_single_candidate_with_unparseable_json_is_dropped_without_raising():
    groups = {"Jerozolima": {"surface": "Jerozolima", "variants": ["Jerozolimy"]}}
    with patch("library.place_context_classifier._model", return_value="Bielik-11B-v3.0-Instruct"), patch(
        "library.ai.ai_ask", side_effect=_truncating_ai_ask(max_batch=0)
    ):
        result = classify_place_context_candidates("odsyła do Jerozolimy cywilów", "", groups, 11137)
    assert result == []


def test_no_candidates_short_circuits_without_llm_call():
    with patch("library.ai.ai_ask") as ask:
        result = classify_place_context_candidates("tekst bez wzmianek", "", {}, 1)
    assert result == []
    ask.assert_not_called()
