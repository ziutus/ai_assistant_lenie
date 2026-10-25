"""Chapter proposals cannot alter transcript words or sentence indexes."""

import json
import re
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from library import transcript_chapter_suggester as s
from library.transcript_chapter_boundaries import parse_sections


def test_cleaning():
    values = [{"start_sentence": start, "title": title} for start, title in
              [(True, "bad"), (-1, "bad"), (2, " ## Początek\n tekstu "), (2, "duplicate"),
               (1, "descending"), (5, "Dalej"), (100, "outside"), (6, " ")]]
    assert s.clean_chapters(values, 10) == [
        {"start_sentence": 0, "title": "Początek tekstu"}, {"start_sentence": 5, "title": "Dalej"}]
    assert len(s.clean_chapters([{"start_sentence": i, "title": "x"} for i in range(30)], 30)) == 20
    assert s.clean_chapters(None, 10) == []


@pytest.mark.parametrize("text", [
    "  Dr. Kowalski mówi.\n\nTo np. przykład! Dalej?  Koniec bez kropki  ",
    "# Tytuł filmu\n\nPierwsze zdanie. Drugie zdanie.\r\nTrzecie zdanie.\r\n",
])
def test_apply_is_lossless(text):
    chapters = [{"start_sentence": i, "title": f"Temat {i}"} for i in range(len(s.sentences(text)))]
    updated = s.apply_chapters(text, chapters)
    sections = parse_sections(updated)
    assert len(sections) == len(chapters)
    assert [s.sentences(section.body)[0] for section in sections] == s.sentences(text)
    assert re.sub(r"\s", "", "".join(section.body for section in sections)) == re.sub(r"\s", "", text)


def test_apply_rejects_empty_and_existing():
    with pytest.raises(ValueError):
        s.apply_chapters("Zdanie.", [])
    with pytest.raises(ValueError):
        s.apply_chapters("## Istniejący\nZdanie.", [{"start_sentence": 0, "title": "x"}])


def test_windows_overlap_and_cover():
    items = ["Zdanie " + "x" * 60 + "." for _ in range(40)]
    batches = s.windows(items, 400)
    assert len(batches) > 1
    covered = set()
    for offset, batch in batches:
        covered.update(range(offset, offset + len(batch)))
        assert sum(len(item) + len(str(offset + i)) + 4 for i, item in enumerate(batch)) <= 840
    assert covered == set(range(40))
    assert batches[1][0] < len(batches[0][1])
    assert len(s.windows(items, 10000)) == 1
    with pytest.raises(ValueError, match="sentence_exceeds_context"):
        s.windows(["x" * 10000], 400)


@pytest.mark.parametrize("raw", ['{"chapters": []}', '```json\n{"chapters": []}\n```'])
def test_parse_tolerance(raw):
    assert s.parse_answer(raw) == []
    assert s.parse_answer("not JSON") is None
    assert s.parse_answer("[]") is None


@pytest.mark.parametrize("structured", [True, False])
def test_single_call_and_usage(structured):
    response = SimpleNamespace(response_text=json.dumps({"chapters": [
        {"start_sentence": 0, "title": "Początek"}, {"start_sentence": 2, "title": "Koniec"}]}))
    with (
        patch.object(s.llm_model_registry, "model_details", return_value={"context_length": 10000,
                                                                          "max_output_tokens": 900}),
        patch.object(s, "supports_structured_output", return_value=structured),
        patch.object(s, "usage_summary", return_value={"tokens": 10, "cost": "0.01", "currency": "USD"}),
        patch("library.ai.ai_ask", return_value=response) as ask,
    ):
        result = s.suggest_chapters("A. B. C.", model="test", document_id=11172)
    assert result["status"] == "ok"
    assert result["usage"] == {"tokens": 10, "cost": "0.01", "currency": "USD"}
    assert result["model_calls"] == 1
    assert ask.call_args.kwargs["document_id"] == 11172
    assert ask.call_args.kwargs["operation"] == "transcript_chapter_suggestion"
    assert ask.call_args.kwargs["max_token_count"] == 900
    assert bool(ask.call_args.kwargs["response_format"]) == structured
    assert "[0] A." in ask.call_args.args[0]


def test_unusable_answer_is_error():
    with (
        patch.object(s.llm_model_registry, "model_details", return_value={"context_length": 10000}),
        patch.object(s, "supports_structured_output", return_value=False),
        patch.object(s, "usage_summary", return_value={}),
        patch("library.ai.ai_ask", return_value=SimpleNamespace(response_text='{"chapters": []}')),
    ):
        result = s.suggest_chapters("A. B.", model="test", document_id=1)
    assert result["status"] == "error"
    assert result["error_code"] == "unusable_answer"


def test_window_merge_deduplicates():
    def answer(prompt, **kwargs):
        indexes = [int(i) for i in re.findall(r"^\[(\d+)\]", prompt, re.M)]
        return SimpleNamespace(response_text=json.dumps({"chapters": [
            {"start_sentence": i, "title": "Temat"} for i in indexes]}))
    with (
        patch.object(s.llm_model_registry, "model_details", return_value={"context_length": 400}),
        patch.object(s, "supports_structured_output", return_value=False),
        patch.object(s, "usage_summary", return_value={}),
        patch("library.ai.ai_ask", side_effect=answer) as ask,
    ):
        result = s.suggest_chapters("Zdanie " + ("x" * 60 + ". ") * 40, model="test", document_id=1)
    assert result["status"] == "ok"
    assert ask.call_count > 1
    starts = [c["start_sentence"] for c in result["chapters"]]
    assert starts[0] == 0
    assert all(b - a > 1 for a, b in zip(starts, starts[1:]))


def test_unknown_context_never_calls_model():
    with patch.object(s.llm_model_registry, "model_details", return_value={}), patch("library.ai.ai_ask") as ask:
        assert s.suggest_chapters("Zdanie.", model="test", document_id=1)["error_code"] == "unknown_context_length"
    ask.assert_not_called()
    assert s.candidates("Zdanie.", {})["fits_single_call"] is None


@pytest.mark.parametrize("saved, enabled, expected", [
    (None, True, "openrouter/google/gemini-2.5-flash-lite"),
    (None, False, "gpt-4o-mini"),
    ("Bielik-11B-v3.0-Instruct", True, "Bielik-11B-v3.0-Instruct"),
    ("openrouter/google/gemini-2.5-flash-lite", False, "gpt-4o-mini"),
    ("removed-model", True, "openrouter/google/gemini-2.5-flash-lite"),
])
def test_default_model_respects_allowlist(saved, enabled, expected):
    registry = s.llm_model_registry
    with (
        patch.object(s.app_settings, "get_setting", return_value=saved),
        patch.object(registry, "_openrouter_enabled", return_value=enabled),
        patch.object(registry, "selectable_models", side_effect=registry._base_models),
    ):
        assert s.default_model(None) == expected
        assert all(not m["external"] or enabled for m in registry.selectable_models(s.TASK))
