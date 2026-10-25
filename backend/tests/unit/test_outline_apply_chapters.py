"""Applying stored outline anchors as ``##`` chapters of a headerless transcript."""

import hashlib

import pytest

from library import outline_boundaries as ob

OUTLINE = "### Pierwszy\n\nOpis.\n\n### Drugi\n\nOpis.\n\n### Trzeci\n\nOpis.\n"
TEXT = (
    "Dzień dobry wszystkim.\nTo jest początek.\n"
    "Teraz drugi temat zaczyna się tutaj.\nI trwa dalej.\n"
    "Wreszcie trzeci temat otwiera się teraz.\nKoniec.\n"
)
SENTENCES = ["Dzień dobry wszystkim.", "Teraz drugi temat zaczyna się tutaj.",
             "Wreszcie trzeci temat otwiera się teraz."]


def payload(sentences, outline=OUTLINE):
    titles = ["Pierwszy", "Drugi", "Trzeci"]
    return {
        "version": 1,
        "outline_sha256": hashlib.sha256(outline.encode("utf-8")).hexdigest(),
        "anchors": [{"title": t, "sentence": s} for t, s in zip(titles, sentences)],
    }


def test_inserts_headings_and_keeps_every_character():
    marked, applied, dropped = ob.apply_anchors_as_chapters(TEXT, OUTLINE, payload(SENTENCES))
    assert applied == ["Pierwszy", "Drugi", "Trzeci"] and dropped == []
    assert marked.startswith("## Pierwszy\n\nDzień dobry")
    assert "\n\n## Drugi\n\nTeraz drugi temat" in marked
    assert "\n\n## Trzeci\n\nWreszcie trzeci" in marked
    body = "".join(line for line in marked.splitlines(keepends=True) if not line.startswith("## "))
    assert body.replace("\n", "") == TEXT.replace("\n", "")


def test_unlocated_topic_is_reported_as_dropped():
    anchors = payload([SENTENCES[0], "Takiego zdania nie ma.", SENTENCES[2]])
    _, applied, dropped = ob.apply_anchors_as_chapters(TEXT, OUTLINE, anchors)
    assert applied == ["Pierwszy", "Trzeci"] and dropped == ["Drugi"]


def test_rejects_anchors_written_for_another_outline():
    with pytest.raises(ValueError, match="innego spisu"):
        ob.apply_anchors_as_chapters(TEXT, "### Inny\n", payload(SENTENCES))


def test_needs_at_least_two_located_topics():
    with pytest.raises(ValueError, match="dwóch"):
        ob.apply_anchors_as_chapters(TEXT, OUTLINE, payload([SENTENCES[0], "brak", "brak"]))


def test_result_is_detected_as_markdown_chapters():
    marked, _, _ = ob.apply_anchors_as_chapters(TEXT, OUTLINE, payload(SENTENCES))
    from library.transcript_chapter_boundaries import describe_sections

    titles = [section["title"] for section in describe_sections(marked)]
    assert "Pierwszy" in titles and "Drugi" in titles and "Trzeci" in titles
