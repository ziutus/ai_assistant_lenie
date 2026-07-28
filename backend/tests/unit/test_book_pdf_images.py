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
        pages = ["intro text, no chapter marker here"] + [
            f"// ROZDZIAL {i} //\ntytul{i}\ntresc rozdzialu" for i in range(1, 4)
        ]
        result = build_book_markdown(pages)

        assert len(result.page_chapter_positions) == len(pages)
        assert result.page_chapter_positions == sorted(result.page_chapter_positions)
        assert result.page_chapter_positions[0] == 0
        assert result.page_chapter_positions[-1] == len(result.chapters)
