"""Unit tests for image extraction in library.book_pdf_import.

extract_page_images() uses fitz (PyMuPDF) lazily, at call time — a fake fitz
module is injected into sys.modules instead of importing the real one, same
pattern as library.document_prepare in test_article_pipeline.py. The other
functions under test (caption_for_page, build_book_markdown's image-marker
insertion, page_chapter_positions) are pure text functions and need no fitz
at all.
"""

import sys
import types

import pytest

pytest.importorskip("sqlalchemy")

from library.book_pdf_import import (  # noqa: E402
    build_book_markdown,
    caption_for_page,
    detect_heading_texts,
    extract_page_images,
)


class _FakePage:
    def __init__(self, images):
        self._images = images  # list of (xref,) tuples

    def get_images(self, full=True):
        return self._images


class _FakeFitzDocument:
    def __init__(self, pages, extract_image_map):
        self._pages = pages
        self._extract_image_map = extract_image_map

    def __iter__(self):
        return iter(self._pages)

    def extract_image(self, xref):
        return self._extract_image_map[xref]


def _install_fake_fitz(monkeypatch, pages, extract_image_map):
    fake_fitz = types.ModuleType("fitz")
    fake_fitz.open = lambda stream, filetype: _FakeFitzDocument(pages, extract_image_map)
    monkeypatch.setitem(sys.modules, "fitz", fake_fitz)


# ---------------------------------------------------------------------------
# extract_page_images
# ---------------------------------------------------------------------------


class TestExtractPageImages:
    def test_filters_small_dimensions_and_small_bytes(self, monkeypatch):
        extract_image_map = {
            10: {"image": b"x" * 6000, "width": 50, "height": 400, "ext": "png"},   # too narrow
            11: {"image": b"x" * 1000, "width": 200, "height": 200, "ext": "png"},  # too few bytes
            12: {"image": b"x" * 6000, "width": 200, "height": 300, "ext": "png"},  # keeps
        }
        pages = [_FakePage([(10,), (11,), (12,)])]
        _install_fake_fitz(monkeypatch, pages, extract_image_map)

        images = extract_page_images(b"fake-pdf-bytes")

        assert len(images) == 1
        assert images[0].xref == 12

    def test_dedup_by_xref_keeps_first_occurrence(self, monkeypatch):
        extract_image_map = {
            12: {"image": b"x" * 6000, "width": 200, "height": 300, "ext": "png"},
            13: {"image": b"x" * 7000, "width": 150, "height": 150, "ext": "jpeg"},
        }
        pages = [
            _FakePage([(12,)]),
            _FakePage([(12,), (13,)]),  # xref 12 repeats (e.g. a running-head logo)
        ]
        _install_fake_fitz(monkeypatch, pages, extract_image_map)

        images = extract_page_images(b"fake-pdf-bytes")

        assert [(img.page_index, img.xref) for img in images] == [(0, 12), (1, 13)]


# ---------------------------------------------------------------------------
# detect_heading_texts — font_prefix/min_size are per-book overrides (each
# book gets its own imports/book_import_pdf_<slug>.py with its own values)
# ---------------------------------------------------------------------------


class _FakeTextPage:
    def __init__(self, lines):
        # lines: list of list-of-span-dicts, one inner list per text line
        self._lines = lines

    def get_text(self, mode):
        assert mode == "dict"
        return {"blocks": [{"type": 0, "lines": [{"spans": spans} for spans in self._lines]}]}


def _install_fake_fitz_text(monkeypatch, pages):
    fake_fitz = types.ModuleType("fitz")
    fake_doc = pages

    class _FakeDoc:
        def __iter__(self):
            return iter(fake_doc)

    fake_fitz.open = lambda stream, filetype: _FakeDoc()
    monkeypatch.setitem(sys.modules, "fitz", fake_fitz)


class TestDetectHeadingTexts:
    def test_matches_default_font_and_size(self, monkeypatch):
        page = _FakeTextPage([
            [{"text": "Nazewnictwo w książce", "font": "BarlowCondensed-Bold", "size": 14.0}],
            [{"text": "Zwykly akapit tekstu.", "font": "NotoSerif", "size": 8.5}],
        ])
        _install_fake_fitz_text(monkeypatch, [page])

        headings = detect_heading_texts(b"fake-pdf-bytes")

        assert headings == {"Nazewnictwo w książce"}

    def test_custom_font_prefix_and_min_size_override_default(self, monkeypatch):
        page = _FakeTextPage([
            # Would NOT match the default BarlowCondensed/12.0, but should
            # match a book-specific override.
            [{"text": "Inny styl podrozdzialu", "font": "Montserrat-Bold", "size": 10.0}],
        ])
        _install_fake_fitz_text(monkeypatch, [page])

        assert detect_heading_texts(b"fake-pdf-bytes") == set()
        assert detect_heading_texts(
            b"fake-pdf-bytes", font_prefix="Montserrat", min_size=10.0,
        ) == {"Inny styl podrozdzialu"}


# ---------------------------------------------------------------------------
# caption_for_page
# ---------------------------------------------------------------------------


class TestCaptionForPage:
    def test_matches_rysunek(self):
        assert caption_for_page("intro\nRysunek 5. Schemat sieci\nwiecej tekstu") == "Rysunek 5. Schemat sieci"

    def test_matches_rys_abbreviation(self):
        assert caption_for_page("Rys. 12: opis grafu") == "Rys. 12: opis grafu"

    def test_does_not_match_ordinary_paragraph_starting_with_number(self):
        assert caption_for_page("12. To jest zwykly akapit zaczynajacy sie od liczby.") is None

    def test_no_caption_returns_none(self):
        assert caption_for_page("Zadnego podpisu tutaj nie ma.") is None


# ---------------------------------------------------------------------------
# build_book_markdown — image marker insertion
# ---------------------------------------------------------------------------


class TestBuildBookMarkdownImageMarkers:
    def test_inserts_marker_before_caption_line(self):
        pages = ["Some intro text.\nRysunek 3. Schemat instalacji\nDalszy tekst."]
        result = build_book_markdown(pages, images_by_page={0: [3]})

        lines = result.markdown.split("\n")
        caption_idx = next(i for i, line in enumerate(lines) if line.startswith("Rysunek 3."))
        marker_idx = next(i for i, line in enumerate(lines) if line == "[img3]")
        assert marker_idx < caption_idx

    def test_appends_marker_at_page_end_without_caption(self):
        pages = ["Just some text with no figure caption at all."]
        result = build_book_markdown(pages, images_by_page={0: [5]})

        assert result.markdown.strip().endswith("[img5]")

    def test_no_images_by_page_inserts_no_markers(self):
        pages = ["Plain text, nothing special."]
        result = build_book_markdown(pages)

        assert "[img" not in result.markdown


# ---------------------------------------------------------------------------
# page_chapter_positions
# ---------------------------------------------------------------------------


class TestPageChapterPositions:
    def test_length_matches_page_count_and_is_monotonic(self):
        # Real front-matter text before the first chapter marker — detect_chapters()
        # (the reader) inserts a "(wstęp)" pseudo-chapter at position 1 for this,
        # so real chapter 1 becomes reader position 2, not 1.
        pages = ["intro text, no chapter marker here"] + [
            f"// ROZDZIAL {i} //\ntytul{i}\ntresc rozdzialu" for i in range(1, 4)
        ]
        result = build_book_markdown(pages)

        assert len(result.page_chapter_positions) == len(pages)
        assert result.page_chapter_positions == sorted(result.page_chapter_positions)
        assert result.page_chapter_positions[0] == 1  # wstęp
        assert result.page_chapter_positions[-1] == len(result.chapters) + 1

    def test_no_preamble_matches_chapter_position_unshifted(self):
        # First page IS the first chapter marker — detect_chapters() has no
        # front-matter text to turn into a "(wstęp)" pseudo-chapter, so chapter
        # numbering is unshifted (real chapter 1 == reader position 1).
        pages = [f"// ROZDZIAL {i} //\ntytul{i}\ntresc rozdzialu" for i in range(1, 3)]
        result = build_book_markdown(pages)

        assert result.page_chapter_positions == [1, 2]

    def test_matches_reader_detect_chapters(self):
        """Regression test for the reader/import chapter-numbering mismatch:
        an image's stored chapter_position must be the SAME position
        detect_chapters() (GET /document/<id>/chapter/<pos>) assigns to the
        chapter whose text actually contains that image's [imgN] marker."""
        from library.text_functions import detect_chapters

        pages = [
            "Strona tytulowa i wstep ksiazki.",
            "// ROZDZIAL 1 //\ntytul1\ntresc rozdzialu pierwszego",
            "// ROZDZIAL 2 //\ntytul2\ntresc rozdzialu drugiego",
        ]
        images_by_page = {0: [0], 1: [1], 2: [2]}
        result = build_book_markdown(pages, images_by_page=images_by_page)

        reader_chapters = detect_chapters(result.markdown)
        for page_idx, marker_n in [(0, 0), (1, 1), (2, 2)]:
            expected_position = result.page_chapter_positions[page_idx]
            idx = result.markdown.index(f"[img{marker_n}]")
            chapter = next(c for c in reader_chapters if c["position"] == expected_position)
            assert chapter["char_start"] <= idx < chapter["char_end"]
