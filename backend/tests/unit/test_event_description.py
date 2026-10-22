"""LLM description of a hand-added event entity (doc #10872: "Galanbard 2026")."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("sqlalchemy")

from library.event_description import context_sentences, describe_event  # noqa: E402

TEXT = ("Wczoraj była konferencja. Spośród nich wyróżniają się wspólne litewsko-polsko-francuskie ćwiczenia "
        "wojskowe Galanbard 2026, wymierzone w rosyjską enklawę Kaliningradu. Nic więcej. "
        "Galanbard 2026 ma trwać tydzień.")


def test_context_sentences_picks_the_sentences_with_the_name_or_a_variant():
    sentences = context_sentences(TEXT, ["Galanbard 2026"])
    assert len(sentences) == 2
    assert sentences[0].startswith("Spośród nich") and sentences[1] == "Galanbard 2026 ma trwać tydzień."
    assert context_sentences(TEXT, ["galanbardu"]) == []
    assert context_sentences("", ["x"]) == [] and context_sentences(TEXT, []) == []


def test_a_lowercase_continuation_after_a_speech_to_text_full_stop_is_kept():
    text = "Ćwiczenia Galanbard 2026. wymierzone w rosyjską enklawę. Potem była przerwa."
    assert context_sentences(text, ["Galanbard 2026"]) == ["Ćwiczenia Galanbard 2026. wymierzone w rosyjską enklawę."]


def test_context_sentences_is_limited():
    assert len(context_sentences("Galanbard raz. " * 10, ["Galanbard"], limit=3)) == 1  # identical sentences collapse
    assert len(context_sentences(" ".join(f"Galanbard {i}." for i in range(10)), ["Galanbard"], limit=3)) == 3


def ask_returning(text):
    return patch("library.ai.ai_ask", return_value=SimpleNamespace(response_text=text))


def test_describe_event_returns_the_model_text_and_only_sends_the_given_sentences():
    with ask_returning("  Wspólne ćwiczenia wojskowe Litwy, Polski i Francji.  ") as ask:
        description = describe_event("Galanbard 2026", ["Zdanie o ćwiczeniach."], "Film")
    assert description == "Wspólne ćwiczenia wojskowe Litwy, Polski i Francji."
    prompt = ask.call_args.args[0]
    assert "Galanbard 2026" in prompt and "- Zdanie o ćwiczeniach." in prompt
    assert ask.call_args.kwargs["operation"] == "event_description"


@pytest.mark.parametrize("answer", ["", "BRAK", "brak informacji"])
def test_describe_event_none_when_the_text_does_not_say_enough(answer):
    with ask_returning(answer):
        assert describe_event("Galanbard 2026", ["Zdanie."]) is None


def test_describe_event_none_without_sentences_or_when_the_model_fails():
    assert describe_event("Galanbard 2026", []) is None
    with patch("library.ai.ai_ask", side_effect=RuntimeError("down")):
        assert describe_event("Galanbard 2026", ["Zdanie."]) is None


def test_replay_restores_the_approved_description():
    from library.entity_overrides import replay_manual_added_entities
    added = SimpleNamespace(id=1, decision="entity_added", entity_text="Galanbard 2026", entity_type="eventName",
                            details={"surface": "Galanbard 2026", "name": "Galanbard 2026", "count": 2})
    described = SimpleNamespace(id=2, decision="entity_described", entity_text="galanbard 2026", entity_type="eventName",
                                details={"description": "Wspólne ćwiczenia."})
    session = MagicMock()
    session.scalars.return_value.all.side_effect = [[added], [], [described]]
    assert replay_manual_added_entities(session, 1) == {"entity_added": 1}
    (created,) = [call.args[0] for call in session.add.call_args_list]
    assert created.description == "Wspólne ćwiczenia."


CHAPTERS = ("## Wstęp\n\nPowitanie widzów.\n\n## Energetyka\n\nEDF to francuski operator. EDF zarządza elektrowniami. "
            "Rząd rozmawia z EDF.\n\n## Koniec\n\nEDF wspomniane raz.\n")


def test_best_chapter_is_the_one_mentioning_the_organization_most_often():
    from library.event_description import best_chapter

    title, body = best_chapter(CHAPTERS, ["EDF"])
    assert title == "Energetyka" and "operator" in body
    assert best_chapter(CHAPTERS, ["NATO"]) is None and best_chapter("", ["EDF"]) is None


def test_describe_organization_sends_the_chapter_and_maps_brak_to_none():
    from library.event_description import describe_organization

    with ask_returning("Francuski operator energetyczny.") as ask:
        assert describe_organization("EDF", "Energetyka", "EDF to operator.", "Tytuł") == "Francuski operator energetyczny."
    assert "EDF to operator." in ask.call_args.args[0] and "Energetyka" in ask.call_args.args[0]
    with ask_returning("BRAK"):
        assert describe_organization("EDF", "", "EDF.") is None
    assert describe_organization("EDF", "", "   ") is None


def test_build_organization_prompt_is_pure_and_caps_the_chapter():
    from library.event_description import MAX_CHAPTER_CHARS, build_organization_prompt

    prompt = build_organization_prompt("EDF", "Energetyka", "x" * (MAX_CHAPTER_CHARS + 500), "Tytuł")
    assert "„EDF”" in prompt and "TYTUŁ ROZDZIAŁU: Energetyka" in prompt
    assert prompt.count("x") == MAX_CHAPTER_CHARS
    assert build_organization_prompt("EDF", "E", "tekst") == build_organization_prompt("EDF", "E", "tekst")


def test_run_organization_description_separates_ok_brak_and_error():
    from library.event_description import run_organization_description

    with ask_returning("  Francuski operator.  ") as ask:
        result = run_organization_description("prompt", "gpt-4o-mini")
    assert result["status"] == "ok" and result["description"] == "Francuski operator."
    assert ask.call_args.kwargs["model"] == "gpt-4o-mini" and ask.call_args.args[0] == "prompt"
    with ask_returning("BRAK"):
        assert run_organization_description("p", "gpt-4o-mini")["status"] == "insufficient_context"
    with patch("library.ai.ai_ask", side_effect=RuntimeError("boom")):
        failed = run_organization_description("p", "gpt-4o-mini")
    assert failed["status"] == "error" and failed["error_code"] == "RuntimeError" and failed["description"] is None


def test_model_registry_allowlist():
    from library.llm_model_registry import is_selectable, selectable_models

    assert is_selectable("Bielik-11B-v3.0-Instruct") and not is_selectable("evil/model")
    assert all({"id", "label", "provider"} <= set(item) for item in selectable_models())
