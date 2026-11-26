"""Document #11287 descriptors and document #11142 relational alliance regression cases."""

import json
from copy import deepcopy
from unittest.mock import MagicMock, patch

import pytest

from library.org_descriptors import find_candidates, is_descriptor, merge_confirmed_descriptors

TEXT_11287 = (
    "Sekretarz generalny Narto Mark Rutte przemawiając w Berlinie powiedział, że sojusz monitoruje sytuację "
    "w Estonii, a także wtargnięcie rosyjskich rakiet na terytorium Polski, dodając, że NATO ma dostępne "
    "opcje reagowania. Sekretarz generalny NATO Mark Rute nazwał wtargnięcie niebezpiecznym incydentem (...). "
    "Sojusz rozważa też rozmieszczenie dodatkowych sił w regionie poinformował rzecznik NATO. "
    "NATO zebrało się w poniedziałek na pilnym spotkaniu, żeby omówić reakcję Zachodniego Sojuszu Wojskowego "
    "na rosyjskie pociski"
)
TEXT_11142 = "Sojusz z USA i trafność działań amerykańskiego prezydenta to dwie różne kwestie."
LONG = "Zachodniego Sojuszu Wojskowego"


def groups():
    return {("orgName", name): {"count": count, "variants": [name], "raw_lemmas": [name]}
            for name, count in [("NATO", 4), ("sojusz", 2), (LONG, 1)]}


@pytest.mark.parametrize("confidence", ["high", "medium"])
def test_doc_11287_two_descriptors_merge_independently(confidence):
    data = groups()
    with patch("library.org_descriptors._model", return_value="m"), patch(
        "library.ai.ai_ask", return_value=MagicMock(response_text=json.dumps({
            "choice": "NATO", "confidence": confidence,
        })),
    ) as ask:
        assert merge_confirmed_descriptors(data, TEXT_11287, "Estonia", 11287) == [(LONG, "NATO"), ("sojusz", "NATO")]
    assert list(data) == [("orgName", "NATO")]
    target = data[("orgName", "NATO")]
    assert target["count"] == 7
    assert set(target["variants"]) == {"NATO", "sojusz", LONG}
    assert target["raw_lemmas"] == ["NATO"]
    assert ask.call_count == 2
    for call in ask.call_args_list:
        assert call.kwargs["operation"] == "ner_org_descriptor_verification"
        assert call.kwargs["document_id"] == 11287
        schema = call.kwargs["response_format"]["json_schema"]["schema"]
        assert set(schema["properties"]) == {"choice", "confidence"}
        assert schema["properties"]["choice"]["enum"] == ["NATO", "none", "uncertain"]


@pytest.mark.parametrize("answer", [
    '{"choice":"none","confidence":"high"}', '{"choice":"uncertain","confidence":"medium"}',
    '{"choice":"NATO","confidence":"low"}', '{"choice":"invented","confidence":"high"}',
    '{', 'null', '[]', '{"choice": [], "confidence":"high"}',
    '{"choice":"NATO","confidence":"high","rationale":"extra"}',
])
def test_unconfirmed_or_invalid_verdict_keeps_groups(answer):
    data = groups()
    before = deepcopy(data)
    with patch("library.org_descriptors._model", return_value="m"), patch(
        "library.ai.ai_ask", return_value=MagicMock(response_text=answer),
    ):
        assert merge_confirmed_descriptors(data, TEXT_11142, document_id=11142) == []
    assert data == before


@pytest.mark.parametrize("error", [RuntimeError("offline"), SystemExit(1)])
def test_errors_fail_open(error):
    data = groups()
    before = deepcopy(data)
    with patch("library.org_descriptors._model", side_effect=error):
        assert merge_confirmed_descriptors(data, TEXT_11287) == []
    assert data == before


@pytest.mark.parametrize("case", ["no_target", "no_descriptor", "manual", "source_manual", "proper", "variant"])
def test_ineligible_groups_never_call_model(case):
    data = groups()
    del data[("orgName", LONG)]
    text = "Sojusz monitoruje sytuację. NATO."
    if case == "no_target":
        del data[("orgName", "NATO")]
    elif case == "no_descriptor":
        del data[("orgName", "sojusz")]
    elif case == "manual":
        data[("orgName", "sojusz")]["manual"] = True
    elif case == "source_manual":
        data[("orgName", "sojusz")]["source"] = "manual"
    elif case == "proper":
        text = "Sojusz Pięciu Oczu i NATO"
    else:
        data[("orgName", "sojusz")]["variants"].append("Sojusz Pięciu Oczu")
    with patch("library.ai.ai_ask") as ask:
        assert merge_confirmed_descriptors(data, text) == []
    ask.assert_not_called()


def test_closed_forms_evidence_limit_unreported_mentions_and_candidate_order():
    data = groups()
    data[("orgName", "sojusz")]["variants"] = ["sojuszu"]
    for index in range(15):
        data[("orgName", f"Org{index}")] = {"count": index, "variants": []}
    candidates = find_candidates(data, "sojusz działa. sojuszu dotyczy. " * 8)
    assert len(candidates) == 1
    assert len(candidates[0]["context"].split("\n[...]\n")) == 6
    assert len(candidates[0]["targets"]) == 12
    assert candidates[0]["targets"][0] == ("orgName", "Org14")
    assert find_candidates(data, "antysojusz sojuszowy") == []
    assert is_descriptor("ŚOJUSZ")
    assert not is_descriptor("sojusze")
    assert not is_descriptor("komisja")


def test_descriptor_metadata_prevents_identity_merge_and_correction():
    from library.ner_corrections import _candidate_keys
    from library.organization_registry import merge_ner_groups

    target = {"count": 3, "variants": ["sojusz", "Nato"], "descriptor_variants": ["sojusz"]}
    assert _candidate_keys("NATO", target) == {"nato"}
    merged = merge_ner_groups({"NATO": target, "Inna": {"count": 1, "variants": ["sojusz"]}})
    assert set(merged) == {"NATO", "Inna"}
    assert merged["NATO"]["descriptor_variants"] == ["sojusz"]
