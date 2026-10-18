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
