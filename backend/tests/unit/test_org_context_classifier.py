"""Context checks for suspicious organization mentions."""

import json
from unittest.mock import MagicMock, patch

import pytest

from library.org_context_classifier import (
    MAX_CANDIDATES_PER_CALL,
    _candidate_payloads,
    classify_suspicious_org_candidates,
)

TEXT = (
    "Sinaloa odnotowano rekordowy wzrost liczby przestępstw, zresztą głównie brutalnych. "
    "Aresztowania zapoczątkowały walkę o kontrolę nad kartelem, w której zresztą "
    "przeciwstawne grupy regularnie blokują ulice."
)


def groups(*names):
    return {("orgName", name): {"variants": [name]} for name in names}


@pytest.fixture(autouse=True)
def dependencies():
    with patch("library.organization_registry.resolve_alias", return_value=None), patch(
        "library.organization_registry.resolve_or_create"
    ) as create, patch("library.org_context_classifier._model", return_value="test-model"):
        yield
        create.assert_not_called()


def response(kind="common_noun", confidence="high"):
    return MagicMock(response_text=json.dumps({"results": [
        {"id": 0, "class": kind, "confidence": confidence, "rationale": "Kontekst."},
    ]}))


def classify():
    return classify_suspicious_org_candidates(MagicMock(), TEXT, "Tytuł", groups("Aresztowania"), 11284)


def test_candidate_selection():
    names = ["Aresztowania", "baobabu", "demokrata", "AFP", "NATO", "ISW", "Radio Zet", "Reuters", "Interii"]
    candidates = groups(*names, "Nieobecny", "Ręczne", "Źródło", "Pseudonim")
    candidates[("orgName", "Interii")]["variants"] = ["Interia"]
    candidates[("orgName", "Ręczne")]["manual"] = True
    candidates[("orgName", "Źródło")]["source"] = "manual"
    candidates[("orgName", "Pseudonim")]["pseudonym"] = True
    candidates[("persName", "Osoba")] = {}
    with patch("library.organization_registry.resolve_alias", side_effect=lambda s, n: (
        object() if n in {"Reuters", "Interia"} else None
    )):
        result = _candidate_payloads(MagicMock(), " ".join(names) + " Ręczne Źródło Pseudonim Osoba", candidates)
    assert [item["entity_text"] for item in result] == ["Aresztowania", "baobabu", "demokrata"]


@pytest.mark.parametrize("name,text", [
    ("demokrata", "Każdy demokrata w Kongresie głosował przeciw."),
    ("nato", "W tekście zapisano nato małymi literami."),
])
def test_lowercase_candidate_bypasses_known_registry_alias(name, text):
    # Lowercase 'nato' is an ordinary one-word candidate; only uppercase NATO is excluded.
    with patch("library.organization_registry.resolve_alias", return_value=object()) as resolve:
        result = _candidate_payloads(MagicMock(), text, groups(name))
    assert [item["entity_text"] for item in result] == [name]
    assert result[0]["context"] == text
    resolve.assert_not_called()


def test_capitalized_candidate_with_known_registry_alias_is_skipped():
    session = MagicMock()
    with patch("library.organization_registry.resolve_alias", return_value=object()) as resolve:
        assert _candidate_payloads(session, "Reuters podał wiadomość.", groups("Reuters")) == []
    resolve.assert_called_once_with(session, "Reuters")


def test_lowercase_multiword_candidate_is_skipped():
    # Starting lowercase does not bypass the single-word requirement.
    with patch("library.organization_registry.resolve_alias", return_value=object()) as resolve:
        assert _candidate_payloads(MagicMock(), "radio zet podało wiadomość.", groups("radio zet")) == []
    resolve.assert_not_called()


def test_doc_11284_common_noun_requires_two_confirmations():
    with patch("library.ai.ai_ask", return_value=response()) as ask:
        result = classify()
    assert result[0]["dropped"] is True
    assert result[0]["key"] == ("orgName", "Aresztowania")
    assert ask.call_count == 2
    assert ask.call_args.kwargs["operation"] == "ner_org_context_verification"
    assert ask.call_args.kwargs["document_id"] == 11284
    assert ask.call_args.kwargs["response_format"]["type"] == "json_schema"
    assert TEXT in ask.call_args.args[0]


@pytest.mark.parametrize("kind,confidence", [
    ("organization", "high"), ("other_entity", "high"), ("uncertain", "high"),
    ("common_noun", "medium"), ("common_noun", "low"),
])
def test_non_dropping_verdicts(kind, confidence):
    with patch("library.ai.ai_ask", return_value=response(kind, confidence)) as ask:
        assert classify()[0]["dropped"] is False
    assert ask.call_count == 1


@pytest.mark.parametrize("second", [response("organization"), response("other_entity"),
                                   response("uncertain"), response(confidence="medium"),
                                   RuntimeError("offline"), MagicMock(response_text='{"results":[]}')])
def test_unconfirmed_drop_retains_entity(second):
    with patch("library.ai.ai_ask", side_effect=[response(), second]):
        assert classify()[0]["dropped"] is False


@pytest.mark.parametrize("failure", [RuntimeError("offline"), MagicMock(response_text="{"),
                                    MagicMock(response_text="null")])
def test_failure_retains_entity(failure):
    with patch("library.ai.ai_ask", side_effect=[failure]):
        assert classify() == []


def test_registry_and_configuration_failures_retain_entities():
    with patch("library.organization_registry.resolve_alias", side_effect=RuntimeError("db")):
        assert classify() == []
    with patch("library.org_context_classifier._model", side_effect=RuntimeError("config")):
        assert classify() == []


def test_split_truncated_batches_and_reorder_second_pass():
    names = ["Aresztowania"] + [f"Nazwa{i}" for i in range(18)]
    calls = []

    def ask(prompt, **kwargs):
        items = json.loads(prompt.split("DANE JSON:\n")[1])
        calls.append([item["candidate"] for item in items])
        if len(items) > 2:
            return MagicMock(response_text='{"results":[')
        return MagicMock(response_text=json.dumps({"results": [
            {"id": item["id"], "class": "common_noun", "confidence": "high", "rationale": "test"}
            for item in items
        ]}))

    with patch("library.ai.ai_ask", side_effect=ask):
        result = classify_suspicious_org_candidates(MagicMock(), " ".join(names), "", groups(*names), 1)
    assert len(result) == len(names)
    assert all(item["dropped"] for item in result)
    assert MAX_CANDIDATES_PER_CALL == 8
    assert max(map(len, calls)) == 8
    completed = [name for batch in calls if len(batch) <= 2 for name in batch]
    assert completed[:len(names)] == names
    assert completed[len(names):] != names
    assert set(completed[len(names):]) == set(names)
