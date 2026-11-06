"""Offline sense classification, provider failover and evaluation regression tests."""

import copy
import datetime as dt
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from library import entity_sense_classifier as sense
from library import fabryka_client as fabryka

CANDIDATE = {"entity_text": "Salvador", "country": "Salwador"}
TEXT = "Salvador wysłał do Haiti ponad 2500 żołnierzy. Prezydent Salvadoru Bukele. W Salvadorze trwa stan wyjątkowy."
RESULT = {"sense": "kraj", "confidence": "high", "provider": "test-model", "rationale": "Prezydent i wojsko"}
REAL_DAILY_CALLS = sense._daily_calls


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    config = {"FABRYKA_API_KEY": "test", "NER_CONTEXT_MODEL": "test-model"}
    monkeypatch.setattr(sense, "load_config", lambda: config)
    monkeypatch.setattr(sense, "_daily_calls", lambda: 0)
    monkeypatch.setattr(sense, "_provider", sense.SenseProvider())
    monkeypatch.setattr(fabryka, "choose", MagicMock(side_effect=AssertionError("unmocked Basal")))
    monkeypatch.setattr(fabryka, "choose_openrouter", MagicMock(side_effect=AssertionError("unmocked decisions")))
    from library import ai
    monkeypatch.setattr(ai, "ai_ask", MagicMock(side_effect=AssertionError("unmocked LLM")))
    return config


def groups():
    return {("persName", "Salvador"): {"count": 3, "variants": ["Salvador", "Salvadoru", "Salvadorze"]}}


@pytest.mark.parametrize("word,expected", [("Salvador", "Salwador"), ("Salvadoru", "Salwador"),
                                         ("Salvadorze", "Salwador"), ("Marek", None), ("Dalí", None),
                                         ("Trump", None), ("Polska", None), ("Polsce", None)])
def test_candidate_selection(word, expected):
    assert sense.candidate_country([word]) == expected


def test_ambiguous_country_is_skipped(monkeypatch):
    monkeypatch.setattr(sense, "_COUNTRY_DATA", [("Salwador", ()), ("Salvadoro", ())])
    assert sense.candidate_country(["Salvador"]) is None


def test_variants_snippets_and_multiword():
    items = groups()
    items[("persName", "Salvador Dalí")] = {"count": 1, "variants": ["Salvador"]}
    candidates = sense._candidate_payloads(TEXT, items)
    assert len(candidates) == 1
    assert candidates[0]["country"] == "Salwador"
    assert len(candidates[0]["context"].split("\n[...]\n")) <= 2
    assert sense._candidate_payloads("brak wzmianki", items) == []
    assert sense.candidate_country(["Xyzzy", "Salvadoru"]) == "Salwador"


def mock_llm(monkeypatch, result=None):
    from library import ai
    call = MagicMock(return_value=SimpleNamespace(response_text=json.dumps(result or RESULT)))
    monkeypatch.setattr(ai, "ai_ask", call)
    return call


def test_basal_unavailable_falls_back_and_opens_circuit(monkeypatch):
    basal = MagicMock(side_effect=fabryka.FabrykaUnavailable("503"))
    monkeypatch.setattr(fabryka, "choose", basal)
    llm = mock_llm(monkeypatch)
    for _ in range(2):
        assert sense.classify_sense(CANDIDATE, TEXT, "Tytuł", 11237) == RESULT
    assert basal.call_count == 1
    assert llm.call_count == 2
    assert llm.call_args.kwargs["response_format"] == sense._RESPONSE_SCHEMA


@pytest.mark.parametrize("error", [fabryka.FabrykaUnexpectedResponse, fabryka.FabrykaError, RuntimeError])
def test_circuit_expires(monkeypatch, error):
    now = [100.0]
    monkeypatch.setattr(sense.time, "monotonic", lambda: now[0])
    basal = MagicMock(side_effect=error("bad response"))
    monkeypatch.setattr(fabryka, "choose", basal)
    mock_llm(monkeypatch)
    sense.classify_sense(CANDIDATE, TEXT, "", 1)
    now[0] += sense.CIRCUIT_SECONDS - 1
    sense.classify_sense(CANDIDATE, TEXT, "", 1)
    assert basal.call_count == 1
    now[0] += 2
    sense.classify_sense(CANDIDATE, TEXT, "", 1)
    assert basal.call_count == 2


@pytest.mark.parametrize("count", [10, 12, None])
def test_daily_limit_or_unknown_skips_basal(monkeypatch, count):
    monkeypatch.setattr(sense, "_daily_calls", lambda: count)
    mock_llm(monkeypatch)
    assert sense.classify_sense(CANDIDATE, TEXT, "", 1) == RESULT
    fabryka.choose.assert_not_called()


@pytest.mark.parametrize("setting,value", [("FABRYKA_API_KEY", ""), ("FABRYKA_DAILY_LIMIT", 0),
                                         ("FABRYKA_DAILY_LIMIT", "invalid")])
def test_disabled_basal(monkeypatch, offline, setting, value):
    offline[setting] = value
    mock_llm(monkeypatch)
    assert sense.classify_sense(CANDIDATE, TEXT, "", 1) == RESULT
    fabryka.choose.assert_not_called()


def test_rate_limit_resets_next_utc_day(monkeypatch):
    now = [dt.datetime(2026, 11, 6, 23, 59, tzinfo=dt.timezone.utc)]
    monkeypatch.setattr(sense, "_utcnow", lambda: now[0])
    basal = MagicMock(side_effect=fabryka.FabrykaRateLimited("429"))
    monkeypatch.setattr(fabryka, "choose", basal)
    mock_llm(monkeypatch)
    sense.classify_sense(CANDIDATE, TEXT, "", 1)
    sense.classify_sense(CANDIDATE, TEXT, "", 1)
    assert basal.call_count == 1
    now[0] += dt.timedelta(minutes=2)
    sense.classify_sense(CANDIDATE, TEXT, "", 1)
    assert basal.call_count == 2


@pytest.mark.parametrize("score,confidence", [(0.8, "high"), (0.6, "medium"), (0.59, "low"), (None, "low")])
@pytest.mark.parametrize("probabilities", [False, True])
def test_basal_confidence(monkeypatch, score, confidence, probabilities):
    raw = {"probabilities": {"kraj": score}} if probabilities else {"confidence": score}
    monkeypatch.setattr(fabryka, "choose", lambda *a, **kw: ("kraj", raw))
    result = sense.classify_sense(CANDIDATE, TEXT, "", 1)
    assert result["confidence"] == confidence
    assert result["provider"] == "fabryka:basal-1.5-mini"


def test_all_failed_keeps_groups(monkeypatch):
    original = groups()
    current = copy.deepcopy(original)
    assert sense.classify_sense(CANDIDATE, TEXT, "", 1) is None
    assert sense.apply_country_sense(current, TEXT, "", 1) == []
    assert current == original


@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize("counter", ["count", "mention_count"])
def test_move_country_counts_and_variants(monkeypatch, existing, counter):
    current = groups()
    current[("persName", "Salvador")][counter] = current[("persName", "Salvador")].pop("count")
    if existing:
        current[("placeName", "Salwador")] = {"count": 2, "variants": ["Salwador", "Salvadoru"]}
    monkeypatch.setattr(sense, "classify_sense", lambda *args: RESULT)
    events = sense.apply_country_sense(current, TEXT, "", 11237)
    assert ("persName", "Salvador") not in current
    target = current[("placeName", "Salwador")]
    assert target["count"] == (5 if existing else 3)
    if counter == "mention_count":
        assert target[counter] == target["count"]
    assert {"Salvador", "Salvadoru", "Salvadorze"} <= set(target["variants"])
    assert len(target["variants"]) == len(set(target["variants"]))
    assert events[0]["dropped"] is True
    assert events[0]["context"]


@pytest.mark.parametrize("predicted,confidence", [("osoba", "high"), ("miasto", "medium"),
                                                ("inne", "high"), ("kraj", "low")])
def test_other_senses_audited_without_mutation(monkeypatch, predicted, confidence):
    monkeypatch.setattr(sense, "classify_sense", lambda *a: {**RESULT, "sense": predicted, "confidence": confidence})
    current = groups()
    assert sense.apply_country_sense(current, TEXT, "", 1)[0]["dropped"] is False
    assert current == groups()


@pytest.mark.parametrize("enabled", [False, "false", "0"])
def test_disabled_zero_provider_calls(monkeypatch, offline, enabled):
    offline["ENTITY_SENSE_ENABLED"] = enabled
    call = MagicMock()
    monkeypatch.setattr(sense, "classify_sense", call)
    assert sense.apply_country_sense(groups(), TEXT, "", 1) == []
    call.assert_not_called()
    assert sense._provider.classify_sense(CANDIDATE, TEXT, "", 1) is None
    fabryka.choose.assert_not_called()


def test_no_candidates_does_not_read_config(monkeypatch):
    config = MagicMock(side_effect=AssertionError("config should not load"))
    monkeypatch.setattr(sense, "load_config", config)
    assert sense.apply_country_sense({}, TEXT, "", 1) == []
    config.assert_not_called()


def test_fallback_model_order_and_disabled_router(offline):
    offline["ENTITY_SENSE_FALLBACK_MODELS"] = "openrouter/a,first,second,first"
    assert sense.fallback_models(offline) == ["first", "second", "test-model"]
    offline["OPENROUTER_ENABLED"] = "true"
    assert sense.fallback_models(offline) == ["openrouter/a", "first", "second", "test-model"]
    del offline["ENTITY_SENSE_FALLBACK_MODELS"]
    assert sense.fallback_models(offline) == [sense.DEFAULT_OPENROUTER_MODEL, "test-model"]


def test_sequential_llm_validation_and_failover(monkeypatch, offline):
    offline.update(FABRYKA_DAILY_LIMIT=0, ENTITY_SENSE_FALLBACK_MODELS="first,second")
    call = mock_llm(monkeypatch)
    call.side_effect = [SimpleNamespace(response_text='{"sense": "bogus"}'),
                        SimpleNamespace(response_text=json.dumps(RESULT))]
    result = sense.classify_sense(CANDIDATE, TEXT, "", 1)
    assert result["provider"] == "second"
    assert [c.kwargs["model"] for c in call.call_args_list] == ["first", "second"]


def test_one_candidate_failure_does_not_abort_next(monkeypatch):
    current = groups()
    current[("persName", "Salvadoru")] = {"count": 1, "variants": ["Salvadoru"]}
    monkeypatch.setattr(sense, "classify_sense", MagicMock(side_effect=[RuntimeError("bad"), RESULT]))
    events = sense.apply_country_sense(current, TEXT, "", 1)
    assert len(events) == 1
    assert ("persName", "Salvador") in current
    assert current[("placeName", "Salwador")]["count"] == 1


def test_config_system_exit_is_fail_open(monkeypatch):
    monkeypatch.setattr(sense, "load_config", MagicMock(side_effect=SystemExit(1)))
    assert sense.apply_country_sense(groups(), TEXT, "", 1) == []


@pytest.mark.parametrize("error", [RuntimeError("database down"), SystemExit(1)])
def test_daily_usage_database_failure_is_unknown(monkeypatch, error):
    from library.db import engine

    monkeypatch.setattr(engine, "get_session", MagicMock(side_effect=error))
    assert REAL_DAILY_CALLS() is None


def test_daily_usage_query_bounds_all_outcomes_and_closes_session(monkeypatch):
    from library.db import engine

    session = MagicMock()
    session.scalar.return_value = 4
    monkeypatch.setattr(engine, "get_session", lambda: session)
    monkeypatch.setattr(sense, "_utcnow", lambda: dt.datetime(2026, 11, 6, 13, tzinfo=dt.timezone.utc))
    assert REAL_DAILY_CALLS() == 4
    query = session.scalar.call_args.args[0]
    compiled = query.compile()
    assert "success" not in str(query)
    assert "fabryka" in compiled.params.values()
    assert "systemone" in compiled.params.values()
    assert dt.datetime(2026, 11, 6) in compiled.params.values()
    assert dt.datetime(2026, 11, 7) in compiled.params.values()
    session.close.assert_called_once()
    session.commit.assert_not_called()
    session.scalar.side_effect = RuntimeError("query failed")
    assert REAL_DAILY_CALLS() is None
    assert session.close.call_count == 2


def test_refresh_country_sense_precedes_person_drop_and_audits(monkeypatch):
    from test_entity_service import _session_with_exclusions

    from library import entity_service, person_context_classifier
    from library.db.models import NerContextClassification

    session = _session_with_exclusions([])
    session.get.return_value.title = "Haiti"
    raw = [{"text": "Salvador", "label": "persName", "lemma": "Salvador"}]
    monkeypatch.setattr(entity_service, "extract_entities", lambda text: raw)
    monkeypatch.setattr(entity_service, "_add_place_mentions", lambda *a: None)
    monkeypatch.setattr(entity_service, "_apply_country_abbreviations", lambda *a: None)
    monkeypatch.setattr(person_context_classifier, "classify_single_word_person_candidates", lambda *a: [{
        "key": ("persName", "Salvador"), "entity_text": "Salvador", "predicted_class": "not_person",
        "confidence": "high", "rationale": "Państwo", "context": TEXT, "model": "person-model", "dropped": True,
    }])
    monkeypatch.setattr(sense, "classify_sense", lambda *a: {**RESULT, "provider": "x" * 110})
    rows = entity_service.refresh_document_entities(session, 11237, TEXT)
    assert any(row.entity_type == "placeName" and row.entity_text == "Salwador" for row in rows)
    assert not any(row.entity_type == "persName" for row in rows)
    audit = [row for call in session.add_all.call_args_list for row in call.args[0]
             if isinstance(row, NerContextClassification) and row.predicted_class == "country"]
    assert len(audit) == 1
    assert audit[0].dropped is True
    assert audit[0].entity_type == "persName"
    assert len(audit[0].model) == 100


def test_evaluation_independent_providers_budget_and_no_writes(monkeypatch, offline):
    from imports import evaluate_entity_sense as evaluation
    from library import ai, external_service_events

    cases = [{"word": "Salvador", "context": TEXT, "expected": "kraj"}] * 3
    monkeypatch.setattr(evaluation, "_daily_calls", lambda: 9)
    writes = MagicMock(side_effect=AssertionError("database write"))
    monkeypatch.setattr(ai, "_record_usage", writes)
    monkeypatch.setattr(external_service_events, "record_external_service_event", writes)

    def basal(*a, **kw):
        external_service_events.record_external_service_event()
        return "kraj", {"confidence": 0.9}

    monkeypatch.setattr(fabryka, "choose", MagicMock(side_effect=basal))
    llm = mock_llm(monkeypatch)
    report = evaluation.evaluate(cases, ["fabryka", "test-model"], offline)
    assert fabryka.choose.call_count == 1
    assert llm.call_count == 3
    assert report["fabryka"]["no_answer"] == 2
    assert report["test-model"]["accuracy"] == 1
    assert report["test-model"]["confusion_matrix"]["kraj"]["kraj"] == 3
    writes.assert_not_called()


def test_evaluation_fixture_and_cli_json(monkeypatch, capsys):
    from imports import evaluate_entity_sense as evaluation

    cases = json.loads(evaluation.DEFAULT_FIXTURE.read_text(encoding="utf-8"))
    assert len(cases) >= 18
    assert {case["expected"] for case in cases} == set(sense.SENSES)
    monkeypatch.setattr(evaluation, "evaluate", lambda *a: {"test-model": {"cases": len(cases)}})
    assert evaluation.main(["--providers", "test-model", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["test-model"]["cases"] == len(cases)


@pytest.mark.parametrize("used,cap", [(None, 8), (0, 0), (10, 8)])
def test_evaluation_unknown_or_zero_budget_skips_basal(monkeypatch, offline, used, cap):
    from imports import evaluate_entity_sense as evaluation

    monkeypatch.setattr(evaluation, "_daily_calls", lambda: used)
    report = evaluation.evaluate([{"word": "Salvador", "context": TEXT, "expected": "kraj"}],
                                 ["fabryka"], offline, cap)
    assert report["fabryka"]["no_answer"] == 1
    fabryka.choose.assert_not_called()


def test_evaluation_no_failover_and_disabled_openrouter(monkeypatch, offline):
    from imports import evaluate_entity_sense as evaluation

    call = mock_llm(monkeypatch)
    call.side_effect = RuntimeError("unavailable")
    report = evaluation.evaluate([{"word": "Salvador", "context": TEXT, "expected": "kraj"}],
                                 ["first", "openrouter:some/model"], offline)
    assert report["first"]["no_answer"] == 1
    assert report["openrouter/some/model"]["no_answer"] == 1
    assert call.call_count == 1


@pytest.fixture
def router(offline):
    offline.update(OPENROUTER_ENABLED=True, OPENROUTER_API_KEY="test-router")
    return offline


@pytest.mark.parametrize("exhausted", [False, True])
def test_basal_failure_or_quota_falls_back_to_jev(monkeypatch, router, exhausted):
    basal = MagicMock(side_effect=fabryka.FabrykaUnavailable("503"))
    monkeypatch.setattr(fabryka, "choose", basal)
    monkeypatch.setattr(sense, "_daily_calls", lambda: 10 if exhausted else 0)
    decisions = MagicMock(return_value=("kraj", {"confidence": 1}))
    monkeypatch.setattr(fabryka, "choose_openrouter", decisions)
    llm = mock_llm(monkeypatch)
    result = sense.classify_sense(CANDIDATE, TEXT, "", 1)
    assert result["provider"] == "openrouter-decisions:typesafe/jev-1.13"
    assert result["confidence"] == "high"
    assert basal.call_count == (0 if exhausted else 1)
    decisions.assert_called_once()
    assert "pa\u0144stwo Salwador" in decisions.call_args.args[2]["kraj"]
    llm.assert_not_called()


def test_decisions_rate_limit_is_per_model_until_next_utc_day(monkeypatch, router):
    router["FABRYKA_DAILY_LIMIT"] = 0
    now = [dt.datetime(2026, 11, 6, 23, 59, tzinfo=dt.timezone.utc)]
    monkeypatch.setattr(sense, "_utcnow", lambda: now[0])

    def choose(*args, model):
        if model == "typesafe/jev-1.13":
            raise fabryka.FabrykaRateLimited("429")
        return "osoba", {"probabilities": {"osoba": 0.9}}

    call = MagicMock(side_effect=choose)
    monkeypatch.setattr(fabryka, "choose_openrouter", call)
    for _ in range(2):
        result = sense.classify_sense(CANDIDATE, TEXT, "", 1)
        assert result["provider"] == "openrouter-decisions:microsoft/microsoft-decision-1"
        assert result["confidence"] == "high"
    assert [c.kwargs["model"] for c in call.call_args_list] == [
        "typesafe/jev-1.13", "microsoft/microsoft-decision-1", "microsoft/microsoft-decision-1"]
    now[0] += dt.timedelta(minutes=2)
    sense.classify_sense(CANDIDATE, TEXT, "", 1)
    assert call.call_count == 5


@pytest.mark.parametrize("error", [fabryka.FabrykaUnavailable, fabryka.FabrykaUnexpectedResponse,
                                  fabryka.FabrykaError, RuntimeError])
def test_all_decisions_fail_to_llm_and_circuits_expire(monkeypatch, router, error):
    router.update(FABRYKA_DAILY_LIMIT=0, ENTITY_SENSE_FALLBACK_MODELS="test-model")
    now = [100.0]
    monkeypatch.setattr(sense.time, "monotonic", lambda: now[0])
    call = MagicMock(side_effect=error("failed"))
    monkeypatch.setattr(fabryka, "choose_openrouter", call)
    llm = mock_llm(monkeypatch)
    for _ in range(2):
        assert sense.classify_sense(CANDIDATE, TEXT, "", 1) == RESULT
    assert call.call_count == 2
    now[0] += sense.CIRCUIT_SECONDS
    assert sense.classify_sense(CANDIDATE, TEXT, "", 1) == RESULT
    assert call.call_count == 4
    assert llm.call_count == 3


@pytest.mark.parametrize("enabled,key", [(False, "test"), ("false", "test"), ("0", "test"), (True, "")])
def test_router_disabled_or_key_missing_skips_decisions(monkeypatch, offline, enabled, key):
    offline.update(OPENROUTER_ENABLED=enabled, OPENROUTER_API_KEY=key,
                   FABRYKA_DAILY_LIMIT=0, ENTITY_SENSE_FALLBACK_MODELS="test-model")
    mock_llm(monkeypatch)
    assert sense.classify_sense(CANDIDATE, TEXT, "", 1) == RESULT
    fabryka.choose_openrouter.assert_not_called()


def test_decision_models_config_order_and_deduplication(router):
    router["ENTITY_SENSE_DECISION_MODELS"] = " second, first,second, ,third "
    assert sense.decision_models(router) == ["second", "first", "third"]
    router["ENTITY_SENSE_DECISION_MODELS"] = ""
    assert sense.decision_models(router) == []


def test_evaluation_decisions_cost_and_explicit_llm(monkeypatch, router):
    from imports import evaluate_entity_sense as evaluation

    router["FABRYKA_DAILY_LIMIT"] = 0
    call = MagicMock(return_value=("kraj", {"confidence": 0.91, "usage": {"cost": 0.00002}}))
    monkeypatch.setattr(fabryka, "choose_openrouter", call)
    llm = mock_llm(monkeypatch)
    providers = evaluation.provider_names(router)
    assert providers == ["fabryka", "decisions:typesafe/jev-1.13",
                         "decisions:microsoft/microsoft-decision-1", f"llm:{sense.DEFAULT_OPENROUTER_MODEL}"]
    report = evaluation.evaluate([{"word": "Salvador", "context": TEXT, "expected": "kraj"}] * 3,
                                 providers, router)
    assert call.call_count == 6
    assert llm.call_count == 3
    for provider in providers[1:3]:
        assert report[provider]["total_cost_usd"] == pytest.approx(0.00006)
        assert report[provider]["accuracy"] == 1
    assert report["fabryka"]["no_answer"] == 3
    assert report[providers[-1]]["total_cost_usd"] == 0


def test_evaluation_decisions_no_failover_and_disabled(monkeypatch, router):
    from imports import evaluate_entity_sense as evaluation

    call = MagicMock(side_effect=fabryka.FabrykaUnavailable("503"))
    monkeypatch.setattr(fabryka, "choose_openrouter", call)
    cases = [{"word": "Salvador", "context": TEXT, "expected": "kraj"}] * 2
    report = evaluation.evaluate(cases, ["decisions:custom"], router)
    assert report["decisions:custom"]["no_answer"] == 2
    assert call.call_count == 1
    router["OPENROUTER_ENABLED"] = False
    evaluation.evaluate(cases, ["decisions:custom", "llm:openrouter/custom"], router)
    assert call.call_count == 1


@pytest.mark.parametrize("cost", [None, True, -1, "0.1", float("nan"), float("inf")])
def test_evaluation_ignores_invalid_reported_cost(cost):
    from imports import evaluate_entity_sense as evaluation

    assert evaluation._reported_cost({"usage": {"cost": cost}}) == 0
