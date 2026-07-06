"""Unit tests for detect_chapters (book table-of-contents from markdown headers).

Pure function — runs in the lightweight (uvx) environment too.
"""

from library.text_functions import detect_chapters


BOOK_H1 = (
    "Strona tytułowa\nAutor: Jan Kowalski\n\n"
    "# Rozdział 1: Geneza\n\nTreść pierwszego rozdziału. " + "x" * 50 + "\n\n"
    "## Podrozdział 1.1\n\nSzczegóły.\n\n"
    "# Rozdział 2: Rozwój\n\nTreść drugiego rozdziału."
)


class TestDetectChapters:
    def test_h1_chapters_with_preamble(self):
        chapters = detect_chapters(BOOK_H1)

        assert [c["title"] for c in chapters] == [
            "(wstęp)", "Rozdział 1: Geneza", "Rozdział 2: Rozwój",
        ]
        assert [c["position"] for c in chapters] == [1, 2, 3]
        assert all(c["level"] == 1 for c in chapters[1:])

    def test_ranges_are_contiguous_and_cover_text(self):
        text = BOOK_H1.rstrip()
        chapters = detect_chapters(text)

        assert chapters[0]["char_start"] == 0
        assert chapters[-1]["char_end"] == len(text)
        for prev, nxt in zip(chapters, chapters[1:]):
            assert prev["char_end"] == nxt["char_start"]
        assert all(c["length"] == c["char_end"] - c["char_start"] for c in chapters)

    def test_h2_inside_h1_chapter_is_not_a_chapter(self):
        chapters = detect_chapters(BOOK_H1)
        titles = [c["title"] for c in chapters]
        assert "Podrozdział 1.1" not in titles
        # subsection text stays inside chapter 1's range
        ch1 = chapters[1]
        assert "Podrozdział 1.1" in BOOK_H1[ch1["char_start"]:ch1["char_end"]]

    def test_single_h1_title_falls_back_to_h2_chapters(self):
        """OCR books often have one H1 (book title) and H2 chapters."""
        text = (
            "# Polska do potęgi\n\nWprowadzenie autora.\n\n"
            "## Rozdział pierwszy\n\nTreść.\n\n"
            "## Rozdział drugi\n\nTreść."
        )
        chapters = detect_chapters(text)

        assert [c["title"] for c in chapters] == [
            "(wstęp)", "Rozdział pierwszy", "Rozdział drugi",
        ]
        assert all(c["level"] == 2 for c in chapters[1:])
        # H1 title line lands in the preamble pseudo-chapter
        assert "# Polska do potęgi" in text[:chapters[1]["char_start"]]

    def test_only_h2_headers(self):
        text = "## A\n\ntreść a\n\n## B\n\ntreść b"
        chapters = detect_chapters(text)
        assert [c["title"] for c in chapters] == ["A", "B"]
        assert chapters[0]["char_start"] == 0

    def test_single_h1_only_is_one_chapter(self):
        text = "# Jedyny rozdział\n\nCała treść dokumentu."
        chapters = detect_chapters(text)
        assert len(chapters) == 1
        assert chapters[0]["title"] == "Jedyny rozdział"
        assert chapters[0]["level"] == 1

    def test_no_headers_returns_empty(self):
        assert detect_chapters("Zwykły tekst bez nagłówków.\nDruga linia.") == []

    def test_h3_headers_do_not_count(self):
        assert detect_chapters("### Sekcja\n\ntreść") == []

    def test_empty_text_returns_empty(self):
        assert detect_chapters("") == []
        assert detect_chapters("   \n  ") == []

    def test_trailing_hashes_stripped_from_title(self):
        text = "# Rozdział 1 #\n\ntreść\n\n# Rozdział 2 ##\n\ntreść"
        chapters = detect_chapters(text)
        assert [c["title"] for c in chapters] == ["Rozdział 1", "Rozdział 2"]

    def test_tiny_whitespace_preamble_skipped(self):
        text = "\n\n# Rozdział 1\n\ntreść\n\n# Rozdział 2\n\ntreść"
        chapters = detect_chapters(text.strip())
        assert chapters[0]["title"] == "Rozdział 1"
