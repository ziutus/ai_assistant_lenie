import json
from pathlib import Path

import pytest

from imports.relation_extraction_eval import main, model_capabilities, read_documents, score_relations, validate_output_path


def relation(**kwargs):
    return {"subject": "Ada Brzask", "relation": "pracownik", "object": "Lunoria", "claim": "fakt", **kwargs}


def test_scoring_alias_alternatives_optional_forbidden_and_unmatched():
    gold = {"relations": [relation(relations=["pracownik", "doradca"]),
                          relation(subject="Iwo Brzask", required=False)],
            "forbidden": [relation(relation="udzialowiec", reason="negated")],
            "aliases": {"Ada Brzask": ["Ady Brzask"]}}
    result = score_relations([relation(subject="Ady Brzask", relation="doradca"),
                              relation(subject="Iwo Brzask"), relation(relation="udzialowiec"),
                              relation(object="Mgloria")], gold)
    assert result["correct"] == 1 and result["recall"] == 1
    assert result["precision"] == 1 / 3 and result["f1"] == 0.5
    assert result["forbidden_hits"] == 1 and result["unmatched_count"] == 1
    assert result["optional_matches"] == 1 and result["claim_type_accuracy"] == 1
    assert score_relations([], gold)["missed"] == [gold["relations"][0]]


def test_direction_symmetry_claim_and_duplicate_scoring():
    reverse = relation(subject="Lunoria", object="Ada Brzask")
    assert score_relations([reverse], {"relations": [relation()]})["wrong_direction_count"] == 1
    reverse["relation"] = "partner"
    assert score_relations([reverse], {"relations": [relation(relation="partner")]})["correct"] == 1
    score = score_relations([relation(claim="anonimowe_zrodlo"), relation()], {"relations": [relation()]})
    assert score["correct"] == 1 and score["claim_type_accuracy"] == 0
    assert score["precision"] == 0.5


def test_output_refuses_repository_and_accepts_external(tmp_path):
    with pytest.raises(ValueError, match="outside"):
        validate_output_path(Path(__file__).resolve().parents[3] / "results")
    assert validate_output_path(tmp_path) == tmp_path.resolve()
    (tmp_path / ".git").mkdir()
    with pytest.raises(ValueError, match="outside"):
        validate_output_path(tmp_path / "nested")


def test_api_reads_only_two_gets(monkeypatch):
    monkeypatch.setenv("LENIE_API_URL", "https://lenie.invalid")
    monkeypatch.setenv("LENIE_API_KEY", "invented-test-key")
    calls = []

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"text": "Tekst.", "entities": {"persName": []}}

    def get(url, **kwargs):
        calls.append((url, kwargs))
        return Response()

    assert read_documents([1], None, get=get)[0]["text"] == "Tekst."
    assert [url for url, _ in calls] == ["https://lenie.invalid/website_get", "https://lenie.invalid/website_entities"]
    assert all(k["params"] == {"id": 1} and k["headers"]["x-api-key"] == "invented-test-key" for _, k in calls)


def test_cli_local_multiple_models_runs_and_no_gold(tmp_path):
    source = tmp_path / "input"
    source.mkdir()
    (source / "1.json").write_text(json.dumps({"id": 1, "text": "Tekst.", "entities": []}), encoding="utf-8")
    out = tmp_path / "out"
    calls = []

    def ask(*args, **kwargs):
        calls.append(kwargs)
        return '{"relations":[]}'

    assert main(["--input", str(source), "--models", "mock/a,mock/b", "--runs", "2", "--out", str(out)],
                ask=ask, capabilities=lambda m: {}) == 0
    assert len(list(out.glob("*.json"))) == 4
    assert len(list(out.glob("*.md"))) == 2 and len(calls) == 4
    assert json.loads(next(out.glob("*.json")).read_text())["metrics"] == {"found": 0}


def test_capability_checks_use_existing_helpers_without_model_calls(monkeypatch):
    from library import ai, entity_description_batch

    monkeypatch.setattr(ai, "_registry_provider", lambda model: "openai")
    monkeypatch.setattr(entity_description_batch, "supports_structured_output", lambda model: model == "mock-structured")
    assert model_capabilities("mock-plain") == {"system_supported": False, "structured_output": False}
    assert model_capabilities("openrouter/mock") == {"system_supported": True, "structured_output": False}
    assert model_capabilities("mock-structured")["structured_output"]


def test_cli_rejects_repo_output_before_reading_input_or_calling_model():
    def unexpected(*args, **kwargs):
        pytest.fail("model/capability lookup must not be reached")

    with pytest.raises(SystemExit) as exc:
        main(["--input", "missing-input", "--models", "mock", "--out", str(Path(__file__).parent)],
             ask=unexpected, capabilities=unexpected)
    assert exc.value.code == 2


def test_cli_with_gold_writes_metrics_and_unknown_cost(tmp_path):
    source = tmp_path / "input"
    source.mkdir()
    gold = tmp_path / "gold"
    gold.mkdir()
    out = tmp_path / "out"
    (source / "1.json").write_text(json.dumps({"id": 1, "text": "Tekst.", "entities": []}), encoding="utf-8")
    (gold / "1.json").write_text(json.dumps({"relations": [relation()]}), encoding="utf-8")
    main(["--input", str(source), "--gold", str(gold), "--models", "mock", "--out", str(out), "--no-verify"],
         ask=lambda *a, **k: '{"relations":[]}', capabilities=lambda m: {})
    result = json.loads(next(out.glob("*.json")).read_text())
    assert result["metrics"]["recall"] == 0
    assert result["metrics"]["missed"] == [relation()]
    assert result["report"]["llm_cost_amount"] is None


def test_inflected_names_match_but_different_names_do_not():
    from imports.relation_extraction_eval import same_name

    assert same_name("lunorii", "lunoria") and same_name("ady brzask", "ada brzaska")
    assert not same_name("ada brzask", "iwo brzask") and not same_name("brzask", "ada brzask")
    assert not same_name("lunoria", "lunapark")


def test_symmetric_gold_entry_and_rescore(tmp_path):
    import json

    from imports.relation_extraction_eval import rescore

    gold = tmp_path / "gold"
    out = tmp_path / "out"
    gold.mkdir()
    out.mkdir()
    (gold / "1.json").write_text(json.dumps({"relations": [
        {"subject": "Lunoria", "relation": "platnosc", "object": "Mokradło", "claim": "fakt", "symmetric": True}]}),
        encoding="utf-8")
    report = {"rejected": {}, "calls": 1, "llm_tokens": 1, "llm_cost_amount": None, "llm_cost_currency": None,
              "elapsed_seconds": 1}
    (out / "1-a-1.json").write_text(json.dumps({"document_id": 1, "run": 1, "model": "m", "report": report, "relations": [
        {"subject": "Mokradło", "relation": "platnosc", "object": "Lunorii", "claim": "fakt"}]}), encoding="utf-8")
    assert rescore(out, gold) == 1
    assert json.loads((out / "1-a-1.json").read_text(encoding="utf-8"))["metrics"]["correct"] == 1
