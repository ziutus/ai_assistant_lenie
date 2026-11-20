"""A bare "Zatoka" folded into the document's only named "Zatoka Perska" when the text supports it (doc 11274)."""

import json
from unittest.mock import MagicMock, patch

from library.generic_geo_heads import bare_head, find_candidates, merge_confirmed_heads, specific_head
from library.generic_place_names import match_generic_place_name

TEXT = (
    "Rozmawiano o Iranie i Zatoka Perska była w tle. Pomimo tego, że wojna w Zatoce oddziałuje na "
    "chińskie bezpieczeństwo energetyczne, nie padło ani słowo. Wczoraj też o Zatoce mówił analityk."
)


def _groups():
    return {
        ("geogName", "Zatoka"): {"count": 3, "variants": ["Zatoce"], "raw_lemmas": ["Zatoka"]},
        ("geogName", "Zatoka Perska"): {"count": 1, "variants": ["Zatoka Perska"], "raw_lemmas": ["Zatoka Perska"]},
        ("placeName", "Iran"): {"count": 33, "variants": ["Iranie"]},
    }


def _answer(klass, confidence="high"):
    return MagicMock(response_text=json.dumps({"results": [
        {"id": 0, "class": klass, "confidence": confidence, "rationale": "test"},
    ]}))


def test_bare_and_specific_heads():
    assert bare_head(["Zatoka", "Zatoce"]) == "zatoka"
    assert bare_head(["Morze"]) == "morze"
    assert bare_head(["Zatoka", "Morze"]) is None  # two different heads
    assert bare_head(["Zatoka Perska"]) is None
    assert specific_head("Zatoka Perska") == "zatoka"
    assert specific_head("Morze Czerwone") == "morze"
    assert specific_head("Zatoka") is None
    assert specific_head("Iran") is None


def test_a_single_named_feature_makes_the_bare_head_a_candidate():
    candidates = find_candidates(_groups(), TEXT)

    assert len(candidates) == 1
    assert candidates[0]["bare_key"] == ("geogName", "Zatoka")
    assert candidates[0]["target_key"] == ("geogName", "Zatoka Perska")
    assert "wojna w Zatoce" in candidates[0]["context"]


def test_a_head_followed_by_a_capitalised_word_is_part_of_a_name_not_a_bare_mention():
    """doc 11274: "wrócił do zatoki San Francisco" must not count as evidence for the Persian Gulf."""
    groups = {
        ("geogName", "Zatoka"): {"count": 1, "variants": ["zatoki"]},
        ("geogName", "Zatoka Perska"): {"count": 1, "variants": ["Zatoka Perska"]},
    }
    assert find_candidates(groups, "Wrócił do zatoki San Francisco i do Zatoka Perska nie wrócił.") == []

    with_bare = find_candidates(groups, "Wrócił do zatoki San Francisco, a towary nie płyną do zatoki wcale.")
    assert len(with_bare) == 1
    assert "\n[...]\n" not in with_bare[0]["context"]  # one snippet: the "San Francisco" mention is skipped
    assert "towary nie płyną do zatoki wcale" in with_bare[0]["context"]


def test_two_named_features_of_one_kind_make_the_bare_head_ambiguous():
    groups = _groups()
    groups[("geogName", "Zatoka Adeńska")] = {"count": 1, "variants": ["Zatoka Adeńska"]}
    assert find_candidates(groups, TEXT) == []


def test_no_named_feature_no_candidate_and_no_text_evidence_no_candidate():
    only_bare = {("geogName", "Zatoka"): {"count": 3, "variants": ["Zatoce"]}}
    assert find_candidates(only_bare, TEXT) == []
    assert find_candidates(_groups(), "Tekst bez tego słowa.") == []


def test_confirmed_bare_head_is_folded_into_the_named_feature():
    groups = _groups()
    with patch("library.generic_geo_heads._model", return_value="Bielik-11B-v3.0-Instruct"), patch(
        "library.ai.ai_ask", return_value=_answer("specific"),
    ) as ask:
        merged = merge_confirmed_heads(groups, TEXT, "Tytuł", 11274)

    assert merged == [("Zatoka", "Zatoka Perska")]
    assert ("geogName", "Zatoka") not in groups
    target = groups[("geogName", "Zatoka Perska")]
    assert target["count"] == 4
    assert target["variants"] == ["Zatoka Perska", "Zatoka", "Zatoce"]
    assert ask.call_args.kwargs["operation"] == "ner_generic_geo_head_verification"
    assert ask.call_args.kwargs["document_id"] == 11274


def test_other_uncertain_or_low_confidence_leaves_the_groups_alone():
    for klass, confidence in [("other", "high"), ("uncertain", "high"), ("specific", "low")]:
        groups = _groups()
        before = {key: dict(value) for key, value in groups.items()}
        with patch("library.generic_geo_heads._model", return_value="m"), patch(
            "library.ai.ai_ask", return_value=_answer(klass, confidence),
        ):
            assert merge_confirmed_heads(groups, TEXT, "", 1) == []
        assert groups == before


def test_model_failure_or_cut_off_answer_is_fail_open():
    for side_effect in (RuntimeError("offline"), None):
        groups = _groups()
        before = {key: dict(value) for key, value in groups.items()}
        response = MagicMock(response_text='{"results": [{"id": 0, "class": "spec')
        with patch("library.generic_geo_heads._model", return_value="m"), patch(
            "library.ai.ai_ask", side_effect=side_effect, return_value=response,
        ):
            assert merge_confirmed_heads(groups, TEXT, "", 1) == []
        assert groups == before


def test_no_candidates_means_no_llm_call():
    groups = {("placeName", "Iran"): {"count": 3, "variants": ["Iranie"]}}
    with patch("library.ai.ai_ask") as ask:
        assert merge_confirmed_heads(groups, "Iran Iranie", "", 1) == []
    ask.assert_not_called()


def test_a_bare_head_is_held_for_review_but_the_named_feature_with_a_bare_variant_is_not():
    assert match_generic_place_name("Zatoka", ["Zatoce"]).id == "generic_geo_head"
    assert match_generic_place_name("Morzu", None).id == "generic_geo_head"
    assert match_generic_place_name("Zatoka Perska", ["Zatoka Perska", "Zatoka", "Zatoce"]) is None
    assert match_generic_place_name("Morze Czerwone", None) is None
    assert match_generic_place_name("Huty", None).id == "generic_huty"  # the old rules still match variants
    assert match_generic_place_name("Katowice", ["Huta"]).id == "generic_huty"
