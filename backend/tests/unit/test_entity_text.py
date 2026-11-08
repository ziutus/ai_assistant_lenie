from types import SimpleNamespace

import pytest

from library.entity_text import document_ner_text

TEXT = "## Temat\n\nJan.\n\n## Reklama\n\nSponsor.\n\n## Szum\n\nHałas.\n\n## Źródła\n\nGazeta."


@pytest.mark.parametrize("types,md,expected", [
    (["TEMAT", "REKLAMA", "SZUM", "ZRODLA"], None, "## Temat\n\nJan."),
    (["REKLAMA"] * 4, "Markdown", "Markdown"),
    (None, None, TEXT),
    ([], None, TEXT),
    (["REKLAMA"], None, TEXT),
    (["TEMAT"] * 4, None, TEXT),
    (["REKLAMA", "SZUM", "ZRODLA", "REKLAMA"], None, ""),
])
def test_document_ner_text(types, md, expected):
    doc = SimpleNamespace(text=TEXT, text_md=md, chapter_types=types)
    assert document_ner_text(doc) == expected


def test_preamble_and_topic_body_kept():
    doc = SimpleNamespace(text="Wstęp.\n\n" + TEXT, text_md="",
                          chapter_types=["TEMAT", "REKLAMA", "SZUM", "ZRODLA"])
    assert document_ner_text(doc) == "Wstęp.\n\n## Temat\n\nJan."
    doc.chapter_types = ["SZUM"] * 4
    assert document_ner_text(doc) == "Wstęp."


def test_no_headings_unchanged():
    doc = SimpleNamespace(text="Bez rozdziałów.\n", text_md=None, chapter_types=["SZUM"])
    assert document_ner_text(doc) == doc.text


@pytest.mark.parametrize("document_type", ["webpage", "link", "youtube", "movie", "obsidian_note", "book", None])
@pytest.mark.parametrize("markdown", [True, False])
@pytest.mark.parametrize("byline", [None, "Anna Nowak", "Inny Autor"])
def test_author_block_is_only_excluded_from_portal_ner(document_type, markdown, byline):
    body = ("Treść artykułu. " * 80).rstrip()
    text = body + "\n\nAnna Nowak Dziennikarka\n\nPracuje w redakcji.\n\na@example.plwięcej o autorze"
    doc = SimpleNamespace(text_md=text if markdown else None, text=text, chapter_types=None, byline=byline)
    if document_type is not None:
        doc.document_type = document_type
    assert document_ner_text(doc) == (body if document_type in ("webpage", "link") else text)
    assert text.startswith(document_ner_text(doc))
    assert doc.text == text
    assert doc.text_md == (text if markdown else None)


def test_known_byline_is_used_without_email_marker():
    body = ("Treść artykułu. " * 80).rstrip()
    text = body + "\n\nAnna Nowak Dziennikarka\n\nPracuje w redakcji."
    doc = SimpleNamespace(document_type="webpage", text_md=text, text=text, byline="Anna Nowak")
    assert document_ner_text(doc) == body
