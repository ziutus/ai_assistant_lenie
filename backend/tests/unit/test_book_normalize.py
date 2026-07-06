# -*- coding: utf-8 -*-
"""Unit tests for imports/book_normalize.py (OCR book markdown normalization)."""

import pytest

from imports.book_normalize import (
    join_broken_paragraphs,
    norm_title,
    normalize_book,
    remove_blocks,
)


class TestNormTitle:
    def test_strips_heading_markers_and_case(self):
        assert norm_title("## Wobec Niemiec") == "wobec niemiec"
        assert norm_title("WYZWANIA") == "wyzwania"

    def test_unifies_dashes_quotes_ellipsis(self):
        assert norm_title("Polska – potencjał i słabości") == norm_title("POLSKA-POTENCJAŁ I SŁABOŚCI")
        assert norm_title("„Brudny” węgiel") == norm_title('"Brudny" węgiel')
        assert norm_title("Awaria systemu… prawnego") == norm_title("Awaria systemu... prawnego")

    def test_collapses_whitespace(self):
        assert norm_title("Zasoby   ludzkie ") == "zasoby ludzkie"


class TestRemoveBlocks:
    def test_removes_block_between_phrases(self):
        text = "keep1\nSTART\njunk\nmore junk\nEND MARKER\nkeep2"
        result, log = remove_blocks(text, [{"name": "b", "start": "START", "end_before": "END MARKER"}])
        assert result == "keep1\nEND MARKER\nkeep2"
        assert "removed block b" in log[0]

    def test_start_occurrence_selects_nth_match(self):
        text = "Title\ncontent A\nTitle\ndup content\nNext chapter\nrest"
        result, _ = remove_blocks(
            text, [{"name": "d", "start": "Title", "start_occurrence": 2, "end_before": "Next chapter"}]
        )
        assert result == "Title\ncontent A\nNext chapter\nrest"

    def test_missing_phrase_raises(self):
        with pytest.raises(ValueError, match="not found"):
            remove_blocks("abc", [{"name": "x", "start": "nope", "end_before": "abc"}])

    def test_oversized_block_raises(self):
        text = "START\n" + "x" * 100 + "\nEND"
        with pytest.raises(ValueError, match="max_chars"):
            remove_blocks(text, [{"name": "big", "start": "START", "end_before": "END", "max_chars": 50}])


class TestJoinBrokenParagraphs:
    def test_joins_paragraph_split_mid_sentence(self):
        prev = "W interesie Polski jest zapobiegnięcie sytuacji, w której Rosja przejęłaby " + "x" * 30
        text = prev + "\n\nkontrolę nad wszystkimi państwami buforowymi."
        result, joined = join_broken_paragraphs(text)
        assert joined == 1
        assert "przejęłaby " + "x" * 30 + " kontrolę" in result

    def test_does_not_join_after_sentence_end(self):
        text = ("Zdanie kończy się kropką i jest wystarczająco długie " + "y" * 20 + " żeby przejść próg."
                + "\n\nnowy akapit zaczyna się małą literą.")
        _, joined = join_broken_paragraphs(text)
        assert joined == 0

    def test_does_not_join_headings_or_uppercase_starts(self):
        prev = "Akapit kończy się przecinkiem, i jest odpowiednio długi na potrzeby testu tutaj,"
        assert join_broken_paragraphs(prev + "\n\n## Nagłówek")[1] == 0
        assert join_broken_paragraphs(prev + "\n\nNowy akapit z wielkiej litery")[1] == 0


BOOK = """Wprowadzenie

Drogi Czytelniku! To jest wprowadzenie do książki i ma odpowiednio długi akapit tekstu.

9

WPROWADZENIE

# Spis treści

## WPROWADZENIE
9

Rozdział pierwszy 25

GOSPODARCZA GONITWA

# Rozdział pierwszy

Treść pierwszego rozdziału, która ciągnie się dość długo i kończy się przecinkiem,

12

ROZDZIAŁ PIERWSZY

więc zostanie sklejona z powrotem w jeden akapit po usunięciu paginy.

# Ważny podrozdział

Treść podrozdziału.

WYZWANIA

Treść rozdziału Wyzwania.
"""

BOOK_MAP = {
    "remove_blocks": [
        {"name": "toc", "start": "# Spis treści", "end_before": "GOSPODARCZA GONITWA"},
    ],
    "running_heads": ["Spis treści", "Gospodarcza gonitwa"],
    "chapters": [
        {"title": "Wprowadzenie"},
        {"title": "Rozdział pierwszy"},
        {"title": "Wyzwania"},
    ],
}


class TestNormalizeBook:
    def test_full_pipeline(self):
        result, log = normalize_book(BOOK, BOOK_MAP)
        lines = result.split("\n")
        # chapter anchors become H1 with map titles (caps WYZWANIA included)
        assert "# Wprowadzenie" in lines
        assert "# Rozdział pierwszy" in lines
        assert "# Wyzwania" in lines
        # non-chapter H1 demoted to H2
        assert "## Ważny podrozdział" in lines
        # page numbers, running heads and TOC gone
        assert "9" not in lines and "12" not in lines
        assert "WPROWADZENIE" not in result and "GOSPODARCZA GONITWA" not in result
        assert "Spis treści" not in result
        # paragraph split by page break re-joined
        assert "kończy się przecinkiem, więc zostanie sklejona" in result

    def test_detect_chapters_on_normalized_text(self):
        from library.text_functions import detect_chapters

        result, _ = normalize_book(BOOK, BOOK_MAP)
        chapters = detect_chapters(result)
        assert [c["title"] for c in chapters] == ["Wprowadzenie", "Rozdział pierwszy", "Wyzwania"]

    def test_missing_anchor_raises(self):
        book_map = {"chapters": [{"title": "Nie ma takiego rozdziału"}]}
        with pytest.raises(ValueError, match="anchors not found"):
            normalize_book("Tylko trochę tekstu.", book_map)

    def test_anchor_different_from_title(self):
        text = "# Niewydolna służba zdrowia\n\nTreść o zdrowiu."
        book_map = {"chapters": [{"title": "Instytucje — System opieki zdrowotnej",
                                  "anchor": "Niewydolna służba zdrowia"}]}
        result, _ = normalize_book(text, book_map)
        assert result.startswith("# Instytucje — System opieki zdrowotnej")
