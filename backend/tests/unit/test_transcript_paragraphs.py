"""Tests for safe LLM-guided transcript paragraphization."""

import json

from library.transcript_paragraphs import paragraphize_transcript


TEXT = """## Rozdział pierwszy

To jest pierwsze zdanie o ważnym zagadnieniu. Drugie zdanie rozwija ten sam temat. Trzecie zdanie zamyka pierwszą myśl. Czwarte zdanie zaczyna zupełnie inny temat. Piąte zdanie go objaśnia wystarczająco długo, aby przekroczyć minimalny próg wywołania modelu.

## Rozdział drugi

Pierwsze zdanie kolejnego rozdziału opisuje inne zdarzenie. Drugie zdanie dodaje szczegół potrzebny do zachowania kontekstu. Trzecie zdanie kończy tę krótką wypowiedź, która również ma dostateczną długość. Czwarte zdanie dopowiada jeszcze jeden szczegół, dzięki któremu okno ma wymagany rozmiar.
"""


class Response:
    response_text = json.dumps({"break_after": [3]})


def test_paragraphize_keeps_headings_and_only_replaces_boundary_whitespace(monkeypatch):
    calls = []

    def fake_ai_ask(prompt, **kwargs):
        calls.append((prompt, kwargs))
        return Response()

    monkeypatch.setattr("library.ai.ai_ask", fake_ai_ask)

    result = paragraphize_transcript(TEXT, document_id=9348)

    assert result.chapter_count == 2
    assert result.model_calls == 2
    assert result.paragraph_count == 4
    assert result.text.startswith("## Rozdział pierwszy\n\n")
    assert "pierwszą myśl.\n\nCzwarte zdanie" in result.text
    assert "## Rozdział drugi\n\n" in result.text
    assert calls[0][1]["document_id"] == 9348
    assert calls[0][1]["operation"] == "transcript_paragraphization"


def test_paragraphize_rejects_text_without_chapters():
    try:
        paragraphize_transcript("Zwykła transkrypcja bez rozdziałów.", document_id=9348)
    except ValueError as exc:
        assert "no Markdown chapter headings" in str(exc)
    else:
        raise AssertionError("Expected paragraphization to require chapter headings")
