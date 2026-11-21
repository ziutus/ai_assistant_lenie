"""Tests for safe LLM-guided transcript paragraphization."""

import json

from library.transcript_paragraphs import paragraphize_chunk_text, paragraphize_transcript


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


PREAMBLE_TEXT = (
    "Krótki wstęp bez nagłówka, ale z kilkoma zdaniami o tym, o czym będzie ten film. Drugie zdanie wstępu dodaje kontekst. "
    "Trzecie zdanie wstępu zamyka pierwszą myśl. Czwarte zdanie wstępu zaczyna inną myśl. Piąte zdanie wstępu domyka całość "
    "i daje oknu wymagany rozmiar.\n\n" + TEXT
)


def test_paragraphize_handles_a_headless_preamble(monkeypatch):
    monkeypatch.setattr("library.ai.ai_ask", lambda prompt, **kwargs: Response())

    result = paragraphize_transcript(PREAMBLE_TEXT, document_id=11278)

    assert result.chapter_count == 3
    assert result.model_calls == 3
    assert result.skipped_chapters == 0
    # The preamble keeps no invented heading, gets its paragraph break and stays before the first chapter.
    assert result.text.startswith("Krótki wstęp bez nagłówka")
    assert "zamyka pierwszą myśl.\n\nCzwarte zdanie wstępu" in result.text
    assert result.text.index("## Rozdział pierwszy") > result.text.index("Czwarte zdanie wstępu")


def test_paragraphize_skips_chapters_that_are_not_content(monkeypatch):
    calls = []

    def fake_ai_ask(prompt, **kwargs):
        calls.append(prompt)
        return Response()

    monkeypatch.setattr("library.ai.ai_ask", fake_ai_ask)

    # Chapter 1 = TEMAT, chapter 2 = REKLAMA: only the first one reaches the model.
    result = paragraphize_transcript(TEXT, document_id=11278, chapter_types=["TEMAT", "REKLAMA"])

    assert result.chapter_count == 2
    assert result.model_calls == 1
    assert len(calls) == 1
    assert result.skipped_chapters == 1
    assert "pierwszą myśl.\n\nCzwarte zdanie" in result.text
    # The advertisement chapter is copied as it was, no paragraph break added.
    assert result.text.split("## Rozdział drugi")[1].strip() == TEXT.split("## Rozdział drugi")[1].strip()


def test_paragraphize_skips_noise_and_sources_too_and_keeps_the_preamble(monkeypatch):
    calls = []
    monkeypatch.setattr("library.ai.ai_ask", lambda prompt, **kwargs: calls.append(prompt) or Response())

    result = paragraphize_transcript(PREAMBLE_TEXT, document_id=11278, chapter_types=["SZUM", "ZRODLA"])

    assert result.skipped_chapters == 2
    assert result.model_calls == 1  # only the preamble
    assert "zamyka pierwszą myśl.\n\nCzwarte zdanie wstępu" in result.text


def test_paragraphize_ignores_a_stored_type_list_that_does_not_match_the_chapters(monkeypatch):
    monkeypatch.setattr("library.ai.ai_ask", lambda prompt, **kwargs: Response())

    # Three types for two chapters: alignment is unknown, so nothing may be skipped.
    result = paragraphize_transcript(TEXT, document_id=11278, chapter_types=["REKLAMA", "REKLAMA", "SZUM"])

    assert result.skipped_chapters == 0
    assert result.model_calls == 2


def test_paragraphize_rejects_text_without_chapters():
    try:
        paragraphize_transcript("Zwykła transkrypcja bez rozdziałów.", document_id=9348)
    except ValueError as exc:
        assert "no Markdown chapter headings" in str(exc)
    else:
        raise AssertionError("Expected paragraphization to require chapter headings")


CHUNK_TEXT = (
    "To jest pierwsze zdanie o ważnym zagadnieniu. Drugie zdanie rozwija ten sam temat. "
    "Trzecie zdanie zamyka pierwszą myśl. Czwarte zdanie zaczyna zupełnie inny temat. "
    "Piąte zdanie go objaśnia wystarczająco długo, aby przekroczyć minimalny próg wywołania modelu."
)


def test_paragraphize_chunk_text_works_without_chapter_headings(monkeypatch):
    calls = []

    def fake_ai_ask(prompt, **kwargs):
        calls.append(kwargs)
        return Response()

    monkeypatch.setattr("library.ai.ai_ask", fake_ai_ask)

    result = paragraphize_chunk_text(CHUNK_TEXT, document_id=9353, analysis_run_id=163)

    assert result.model_calls == 1
    assert result.paragraph_count == 2
    assert "pierwszą myśl.\n\nCzwarte zdanie" in result.text
    assert calls[0]["document_id"] == 9353
    assert calls[0]["analysis_run_id"] == 163
    assert calls[0]["operation"] == "transcript_paragraphization"


def test_paragraphize_chapter_changes_only_the_chosen_chapter(monkeypatch):
    from library.transcript_paragraphs import paragraphize_chapter

    monkeypatch.setattr("library.ai.ai_ask", lambda prompt, **kwargs: Response())

    result = paragraphize_chapter(TEXT, 2, document_id=11222)

    assert result.chapter_count == 1
    assert result.model_calls == 1
    first_chapter = TEXT.split("## Rozdział drugi")[0]
    assert result.text.startswith(first_chapter)  # chapter 1 untouched, byte for byte
    assert "pierwszą myśl.\n\nCzwarte" not in result.text.split("## Rozdział drugi")[0]
    assert "kontekstu.\n\nCzwarte" not in result.text  # sanity: break is after sentence 3 of chapter 2
    assert "kończy tę krótką wypowiedź, która również ma dostateczną długość.\n\nCzwarte" in result.text
    assert result.text.endswith("kontekst.\n") is False
    assert result.text.endswith("wymagany rozmiar.\n")


def test_paragraphize_chapter_rejects_unknown_position():
    import pytest
    from library.transcript_paragraphs import paragraphize_chapter

    with pytest.raises(ValueError):
        paragraphize_chapter(TEXT, 9, document_id=1)
