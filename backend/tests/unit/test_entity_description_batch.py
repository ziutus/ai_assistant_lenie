"""Group descriptions of a chapter's organizations and persons: one prompt, one quotation, one JSON answer."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("sqlalchemy")
flask = pytest.importorskip("flask")

from library import chunk_review_routes as cr  # noqa: E402
from library import entity_description_batch as batch_module  # noqa: E402
from library.db.models import Document  # noqa: E402
from library.entity_description_batch import (  # noqa: E402
    Candidate, build_prompt, candidates_for_chapter, describe_batch, describe_candidates, parse_answer,
    response_schema,
)
from library.transcript_chapter_boundaries import describe_sections  # noqa: E402

CHAPTER = {
    "orgName": [
        {"id": 1, "text": "Bank Światowy", "count": 4, "organization_id": 10, "organization_description": None},
        {"id": 2, "text": "NATO", "count": 9, "organization_id": 11, "organization_description": "Sojusz wojskowy."},
        {"id": 3, "text": "Rumunia", "count": 6, "organization_id": 12, "is_country": True},
        {"id": 4, "text": "Gazprom", "count": 2},  # not resolved to the registry
        {"id": 5, "text": "Banku Światowego", "count": 1, "organization_id": 10},  # same registry entry as id 1
        {"id": 6, "text": "Orlen", "count": 7, "organization_id": 13, "organization_description": "  "},
    ],
    "persName": [
        {"id": 7, "text": "Nikulesku", "canonical_name": "Luka Nikulesku", "count": 7, "person_id": 20,
         "person_description": None},
        {"id": 8, "text": "Ciolacu", "count": 3, "person_id": 21, "person_description": "Premier."},
        {"id": 9, "text": "Ktoś", "count": 1},  # not resolved
    ],
    "geogName": [{"id": 10, "text": "Bukareszt", "count": 3}],
}


def _candidates():
    return candidates_for_chapter(CHAPTER)


def test_candidates_are_undescribed_resolved_non_country_and_deduplicated():
    found = _candidates()
    assert [(c.key, c.kind, c.registry_id, c.name) for c in found] == [
        ("o1", "organization", 13, "Orlen"),          # most mentioned first, blank description counts as none
        ("o2", "organization", 10, "Bank Światowy"),
        ("p1", "person", 20, "Luka Nikulesku"),       # canonical name preferred
    ]
    assert candidates_for_chapter({}) == []


def test_prompt_lists_every_key_and_quotes_the_chapter_once():
    prompt = build_prompt(_candidates(), "Rumunia", "Treść rozdziału. " * 400, "Dokument")
    for line in ("[o1] Orlen", "[o2] Bank Światowy", "[p1] Luka Nikulesku", "o1, o2, p1"):
        assert line in prompt
    assert prompt.count("ROZDZIAŁ:") == 1 and "TYTUŁ ROZDZIAŁU: Rumunia" in prompt
    assert len(prompt) < 3500 + 1800  # chapter capped at MAX_CHAPTER_CHARS, the rest is the fixed instruction


def test_schema_requires_exactly_the_candidate_keys():
    schema = response_schema(_candidates())["json_schema"]["schema"]
    assert set(schema["properties"]) == set(schema["required"]) == {"o1", "o2", "p1"}
    assert schema["additionalProperties"] is False
    assert schema["properties"]["o1"]["type"] == ["string", "null"]


def test_parse_answer_handles_fences_nulls_brak_and_invented_keys():
    batch = _candidates()
    raw = '```json\n{"o1": " Polski koncern. ", "o2": null, "p1": "BRAK", "zzz": "wymyślone"}\n```'
    assert parse_answer(raw, batch) == {"o1": "Polski koncern.", "o2": None, "p1": None}
    assert parse_answer('{"o1": "x"}', batch) == {"o1": "x", "o2": None, "p1": None}  # missing key = no description
    assert parse_answer('{"o1": 5, "o2": "", "p1": ["a"]}', batch) == {"o1": None, "o2": None, "p1": None}
    assert len(parse_answer(json.dumps({"o1": "a" * 900}), batch)["o1"]) == batch_module.MAX_DESCRIPTION_CHARS


@pytest.mark.parametrize("raw", [None, "", "nie json", "[1, 2]", '{"o1": "ucięte', "{bad}"])
def test_parse_answer_rejects_unusable_text(raw):
    assert parse_answer(raw, _candidates()) is None


def _reply(text):
    return SimpleNamespace(response_text=text, usage=None)


def test_unparseable_answer_splits_the_batch_and_retries_each_half():
    calls = []

    def fake(prompt, batch, model):
        calls.append([c.key for c in batch])
        if len(batch) > 1:
            return _reply("ucięte {")
        return _reply(json.dumps({batch[0].key: f"opis {batch[0].key}"}))

    with patch.object(batch_module, "_call_model", side_effect=fake):
        result = describe_batch(_candidates(), "T", "tekst", "D", "Bielik-11B-v3.0-Instruct")
    assert result["answers"] == {"o1": "opis o1", "o2": "opis o2", "p1": "opis p1"} and result["errors"] == {}
    assert calls == [["o1", "o2", "p1"], ["o1"], ["o2", "p1"], ["o2"], ["p1"]]


def test_a_single_unparseable_candidate_is_an_error_not_a_missing_description():
    with patch.object(batch_module, "_call_model", return_value=_reply("???")):
        result = describe_batch(_candidates()[:1], "T", "tekst", "D", "m")
    assert result["errors"] == {"o1": "UnparseableAnswer"} and result["answers"] == {}


def test_model_failure_marks_every_candidate_as_error():
    with patch.object(batch_module, "_call_model", side_effect=OSError("down")):
        result = describe_batch(_candidates(), "T", "tekst", "D", "m")
    assert result["errors"] == {"o1": "OSError", "o2": "OSError", "p1": "OSError"}


def test_describe_candidates_makes_one_call_per_six_entities_and_classifies_each():
    many = [Candidate(f"o{i}", "organization", i, 100 + i, f"Org {i}", 1) for i in range(1, 8)]

    def fake(prompt, batch, model):
        return _reply(json.dumps({c.key: (None if c.key == "o2" else f"opis {c.key}") for c in batch}))

    with patch.object(batch_module, "_call_model", side_effect=fake) as call:
        result = describe_candidates(many, "T", "tekst", "D", model="Bielik-11B-v3.0-Instruct")
    assert call.call_count == 2 and result["model_calls"] == 2
    by_key = {p["key"]: p for p in result["proposals"]}
    assert by_key["o1"]["status"] == "ok" and by_key["o1"]["description"] == "opis o1"
    assert by_key["o2"]["status"] == "insufficient_context" and by_key["o2"]["description"] is None
    assert by_key["o7"]["registry_id"] == 107


def test_usage_is_summed_only_when_every_call_is_known():
    usage = batch_module._sum_usage([{"tokens": 10, "cost": "0.001", "currency": "USD"},
                                     {"tokens": 5, "cost": "0.002", "currency": "USD"}])
    assert usage == {"tokens": 15, "cost": "0.003", "currency": "USD"}
    assert batch_module._sum_usage([{"tokens": 10, "cost": None, "currency": None}])["cost"] is None
    assert batch_module._sum_usage([]) == {"tokens": None, "cost": None, "currency": None}


def test_structured_output_support_follows_provider_and_catalog():
    from library.api.openrouter import openrouter_catalog as catalog

    info = catalog.OpenRouterModelInfo("a/b", 1000, 500, None, None, True)
    plain = catalog.OpenRouterModelInfo("c/d", 1000, 500, None, None, False)
    with patch.object(catalog, "get_model_info", side_effect=lambda mid: {"a/b": info, "c/d": plain}.get(mid)):
        assert batch_module.supports_structured_output("Bielik-11B-v3.0-Instruct")
        assert batch_module.supports_structured_output("openrouter/a/b")
        assert not batch_module.supports_structured_output("openrouter/c/d")
        assert not batch_module.supports_structured_output("openrouter/x/unknown")
        assert not batch_module.supports_structured_output("gpt-4o-mini")


def test_answer_budget_grows_with_the_batch_and_respects_the_model_limit():
    with patch("library.llm_model_registry.model_details", return_value=None):
        assert batch_module.max_tokens_for(1, "m") == 220 and batch_module.max_tokens_for(6, "m") == 820
    with patch("library.llm_model_registry.model_details", return_value={"max_output_tokens": 300}):
        assert batch_module.max_tokens_for(6, "m") == 300


# --- endpoint -------------------------------------------------------------------------------------------

TEXT = "## Rumunia\n\nBank Światowy wspiera Rumunię. Luka Nikulesku mówił o tym głośno.\n\n## Reklama\n\nKup teraz."


@pytest.fixture
def client(monkeypatch):
    doc = MagicMock(spec=Document)
    doc.text, doc.chapter_types, doc.title = TEXT, ["TEMAT", "REKLAMA"], "Dokument"
    session = MagicMock()
    session.get.return_value = doc
    monkeypatch.setattr(cr, "get_scoped_session", lambda: session)
    grouped = {
        "orgName": [{"id": 1, "text": "Bank Światowy", "count": 1, "variants": [], "organization_id": 10,
                     "organization_description": None}],
        "persName": [{"id": 2, "text": "Luka Nikulesku", "count": 1, "variants": [], "person_id": 20,
                      "person_description": None}],
        "geogName": [], "placeName": [],
    }
    monkeypatch.setattr("library.entity_service.get_document_entities", lambda session, doc_id: grouped)
    app = flask.Flask(__name__)
    app.register_blueprint(cr.bp)
    app.testing = True
    return app.test_client()


def _first_position():
    return describe_sections(TEXT, stored_types=["TEMAT", "REKLAMA"])[0]["position"]


def test_endpoint_dry_run_lists_candidates_and_prompt_without_calling_a_model(client):
    with patch.object(batch_module, "_call_model", side_effect=AssertionError("model")):
        response = client.post(f"/document/42/chapter/{_first_position()}/describe_entities", json={"dry_run": True})
    assert response.status_code == 200
    assert [c["name"] for c in response.json["candidates"]] == ["Bank Światowy", "Luka Nikulesku"]
    assert "[o1] Bank Światowy" in response.json["prompt"] and "[p1] Luka Nikulesku" in response.json["prompt"]
    assert response.json["default_model"] and isinstance(response.json["models"], list)


def test_endpoint_returns_proposals_from_one_model_call(client):
    reply = _reply(json.dumps({"o1": "Instytucja finansowa.", "p1": None}))
    with patch.object(batch_module, "_call_model", return_value=reply) as call:
        response = client.post(f"/document/42/chapter/{_first_position()}/describe_entities", json={})
    assert response.status_code == 200 and call.call_count == 1
    proposals = {p["name"]: p for p in response.json["proposals"]}
    assert proposals["Bank Światowy"]["description"] == "Instytucja finansowa."
    assert proposals["Bank Światowy"]["registry_id"] == 10 and proposals["Bank Światowy"]["kind"] == "organization"
    assert proposals["Luka Nikulesku"]["status"] == "insufficient_context"
    assert response.json["chapter_title"] == "Rumunia"


def test_endpoint_with_nothing_to_describe_makes_no_call(client, monkeypatch):
    monkeypatch.setattr("library.entity_service.get_document_entities",
                        lambda session, doc_id: {"orgName": [], "persName": []})
    with patch.object(batch_module, "_call_model", side_effect=AssertionError("model")):
        response = client.post(f"/document/42/chapter/{_first_position()}/describe_entities", json={})
    assert response.status_code == 200 and response.json["proposals"] == [] and response.json["model_calls"] == 0


def test_endpoint_rejects_unknown_model_unknown_chapter_and_non_content_chapter(client):
    position = _first_position()
    assert client.post(f"/document/42/chapter/{position}/describe_entities",
                       json={"model": "gpt-99-evil"}).status_code == 400
    assert client.post("/document/42/chapter/99/describe_entities", json={}).status_code == 404
    assert client.post(f"/document/42/chapter/{position + 1}/describe_entities", json={}).status_code == 400
