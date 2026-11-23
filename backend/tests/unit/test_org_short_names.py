"""Document #11278: distinguish ICC from ICJ using context, never lexical similarity alone."""

import json
from copy import deepcopy
from unittest.mock import MagicMock, patch

import pytest

from library.org_short_names import find_candidates, merge_confirmed_short_names

SHORT = "Międzynarodowego Trybunału"
ICC = "Międzynarodowy Trybunał Karny"
ICJ = "Międzynarodowy Trybunał Sprawiedliwości"
# Doc #11278: „... jest Haga i Międzynarodowy Trybunał Karny. I tutaj wyraźnie powiedziano,
# żeby ograniczyć działania Międzynarodowego Trybunału, żeby pamiętał o immunitecie głów państw, prawda?”
TEXT = (
    "Jest Haga i Międzynarodowy Trybunał Karny. I tutaj wyraźnie powiedziano, żeby ograniczyć działania "
    "Międzynarodowego Trybunału, żeby pamiętał o immunitecie głów państw, prawda?"
)


def _groups(two=True):
    groups = {
        ("orgName", SHORT): {"count": 1, "variants": [SHORT, SHORT.lower()], "raw_lemmas": [SHORT, "wspólny"]},
        ("orgName", ICC): {"count": 3, "variants": [ICC], "raw_lemmas": [ICC, "wspólny"]},
    }
    if two:
        groups[("orgName", ICJ)] = {"count": 2, "variants": [ICJ], "raw_lemmas": [ICJ]}
    return groups


def _answer(choice=ICC, confidence="high"):
    return MagicMock(response_text=json.dumps({"choice": choice, "confidence": confidence, "rationale": "Kontekst"}))


@pytest.mark.parametrize("two,confidence", [(False, "high"), (True, "high"), (True, "medium")])
def test_confirmed_merge_preserves_counts_variants_lemmas_and_other_organization(two, confidence):
    groups = _groups(two)
    before = deepcopy(groups)
    with patch("library.org_short_names._model", return_value="cheap-model"), patch(
        "library.ai.ai_ask", return_value=_answer(confidence=confidence),
    ) as ask:
        assert merge_confirmed_short_names(groups, TEXT, "Immunitet", 11278) == [(SHORT, ICC)]
    assert ("orgName", SHORT) not in groups
    assert groups[("orgName", ICC)] == {
        "count": 4, "variants": [ICC, SHORT], "raw_lemmas": [ICC, "wspólny", SHORT],
    }
    if two:
        assert groups[("orgName", ICJ)] == before[("orgName", ICJ)]
    ask.assert_called_once()
    payload = json.loads(ask.call_args.args[0].split("\n", 1)[1])
    assert payload["candidates"] == ([ICC, ICJ] if two else [ICC])
    assert payload["title"] == "Immunitet"
    assert "immunitecie głów państw" in payload["context"]
    kwargs = ask.call_args.kwargs
    assert kwargs["operation"] == "ner_org_short_name_verification"
    assert kwargs["document_id"] == 11278
    assert kwargs["model"] == "cheap-model"
    assert kwargs["response_format"]["json_schema"]["schema"]["properties"]["choice"]["enum"] == [
        *payload["candidates"], "none", "uncertain",
    ]


@pytest.mark.parametrize("choice,confidence", [("none", "high"), ("uncertain", "medium"), (ICC, "low"),
                                              ("Invented organization", "high"), (ICC, "invalid")])
def test_unconfirmed_choice_changes_nothing(choice, confidence):
    groups = _groups()
    before = deepcopy(groups)
    with patch("library.org_short_names._model", return_value="m"), patch(
        "library.ai.ai_ask", return_value=_answer(choice, confidence),
    ):
        assert merge_confirmed_short_names(groups, TEXT) == []
    assert groups == before


@pytest.mark.parametrize("response", ["{", "null", "[]", '{"choice": "x"}',
                                    '{"choice": [], "confidence": "high", "rationale": "x"}'])
def test_invalid_json_or_schema_is_fail_open(response):
    groups = _groups()
    before = deepcopy(groups)
    with patch("library.org_short_names._model", return_value="m"), patch(
        "library.ai.ai_ask", return_value=MagicMock(response_text=response),
    ):
        assert merge_confirmed_short_names(groups, TEXT) == []
    assert groups == before


def test_model_failure_is_fail_open():
    groups = _groups()
    before = deepcopy(groups)
    with patch("library.org_short_names._model", return_value="m"), patch(
        "library.ai.ai_ask", side_effect=RuntimeError("offline"),
    ):
        assert merge_confirmed_short_names(groups, TEXT) == []
    assert groups == before


def test_config_backend_exit_is_fail_open():
    groups = _groups()
    before = deepcopy(groups)
    with patch("library.org_short_names._model", side_effect=SystemExit(1)), patch("library.ai.ai_ask") as ask:
        assert merge_confirmed_short_names(groups, TEXT) == []
    assert groups == before
    ask.assert_not_called()


@pytest.mark.parametrize("short,variants", [
    ("trybunał", []), ("Trybunał Konstytucyjny", []), (SHORT, ["Inna Organizacja"]),
    (SHORT, [ICC]), ("Międzynarodowxyzw Trybunału", []),
])
def test_every_form_must_be_a_strict_multiword_prefix(short, variants):
    groups = {("orgName", short): {"count": 1, "variants": variants},
              ("orgName", ICC): {"count": 3, "variants": []}}
    with patch("library.ai.ai_ask") as ask:
        assert merge_confirmed_short_names(groups, short + ". " + ICC) == []
    ask.assert_not_called()


def test_no_target_no_context_and_full_name_only_do_not_call_model():
    with patch("library.ai.ai_ask") as ask:
        assert merge_confirmed_short_names({("orgName", SHORT): {"count": 1}}, TEXT) == []
        assert merge_confirmed_short_names(_groups(), "Brak wzmianek") == []
        groups = _groups()
        groups[("orgName", "Międzynarodowy Trybunał")] = groups.pop(("orgName", SHORT))
        groups[("orgName", "Międzynarodowy Trybunał")]["variants"] = []
        assert merge_confirmed_short_names(groups, ICC) == []
    ask.assert_not_called()


def test_target_variants_and_accent_case_folding():
    groups = {("orgName", "Miedzynarodowego Trybunalu"): {"count": 1},
              ("orgName", "ICC"): {"count": 3, "variants": [ICC]}}
    candidates = find_candidates(groups, "O MIEDZYNARODOWEGO TRYBUNALU mowa.")
    assert len(candidates) == 1
    assert candidates[0]["targets"] == [("orgName", "ICC")]


def test_short_is_another_groups_complete_name():
    groups = _groups()
    groups[("orgName", SHORT.lower())] = {"count": 2}
    with patch("library.ai.ai_ask") as ask:
        assert merge_confirmed_short_names(groups, TEXT) == []
    ask.assert_not_called()
