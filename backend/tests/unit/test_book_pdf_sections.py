"""Unit tests for the pure-text helpers in library.book_pdf_import added for
front/back-matter section detection, callout boxes and table conversion —
_wrap_callout_boxes() and _table_to_markdown() need no fitz at all. The
PDF-dependent functions (detect_named_sections, apply_inline_styles,
insert_page_tables) were validated against the real "Twierdza Linux" PDF
during development rather than covered here — faithfully mocking PyMuPDF's
dict/words/find_tables APIs would test the mock more than the code.
"""

import pytest

pytest.importorskip("sqlalchemy")

from library.book_pdf_import import (  # noqa: E402
    _REPLACEMENT_CHAR_RUN_RE,
    _STRAY_CONTROL_CHAR_RE,
    _link_table_captions,
    _table_to_markdown,
    _wrap_callout_boxes,
    link_toc_entries,
)

INFO = "ℹ"
WARN = ""


FFFD = "�"


class TestReplacementCharRun:
    def test_strips_run_with_leading_whitespace(self):
        text = f"Tabela 1. Tytul {FFFD * 20}\nTabela 2. Inny tytul"
        result = _REPLACEMENT_CHAR_RUN_RE.sub("", text)
        assert FFFD not in result
        assert result == "Tabela 1. Tytul\nTabela 2. Inny tytul"

    def test_single_char_is_stripped_too(self):
        assert _REPLACEMENT_CHAR_RUN_RE.sub("", f"a {FFFD} b") == "a b"

    def test_leaves_normal_text_untouched(self):
        text = "Zwykly tekst bez zadnych artefaktow."
        assert _REPLACEMENT_CHAR_RUN_RE.sub("", text) == text


class TestStrayControlChar:
    def test_strips_backspace(self):
        assert _STRAY_CONTROL_CHAR_RE.sub("", "Tabela 1. Tytul \x08\ndalej") == "Tabela 1. Tytul \ndalej"

    def test_strips_soh_bullet_glyph(self):
        assert _STRAY_CONTROL_CHAR_RE.sub("", "\t\x01\nalbo") == "\t\nalbo"

    def test_keeps_tab_newline_and_carriage_return(self):
        text = "a\tb\nc\rd"
        assert _STRAY_CONTROL_CHAR_RE.sub("", text) == text

    def test_leaves_normal_text_untouched(self):
        text = "Zwykly tekst z polskimi znakami: ążśźćłóęń."
        assert _STRAY_CONTROL_CHAR_RE.sub("", text) == text


class TestLinkTableCaptions:
    def test_real_occurrence_gets_anchor_and_index_entry_gets_link(self):
        text = (
            "Some prose (tabela 1).\n\n"
            "Tabela 1. Ustalenie czegoś\n"
            "| a | b |\n"
            "| --- | --- |\n"
            "| 1 | 2 |\n\n"
            "## Spis tabel\n\n"
            "Tabela 1. Ustalenie czegoś\n"
            "Tabela 2. Nieistniejąca tabela"
        )
        result = _link_table_captions(text)
        assert "[#tabela-1]" in result
        assert "**Tabela 1. Ustalenie czegoś**" in result
        assert "[Tabela 1. Ustalenie czegoś](anchor:tabela-1)" in result
        # a table find_tables() never detected keeps its plain caption everywhere
        assert "Tabela 2. Nieistniejąca tabela" in result
        assert "anchor:tabela-2" not in result

    def test_anchor_placed_directly_before_the_table_not_the_index(self):
        text = (
            "Tabela 5. Prawdziwa tabela\n"
            "| x |\n"
            "| --- |\n"
            "| 1 |\n\n"
            "Tabela 5. Prawdziwa tabela"
        )
        result = _link_table_captions(text)
        assert result.index("[#tabela-5]") < result.index("| x |")
        assert "[Tabela 5. Prawdziwa tabela](anchor:tabela-5)" in result

    def test_no_tables_leaves_text_untouched(self):
        text = "Zwykly tekst bez zadnych tabel."
        assert _link_table_captions(text) == text


DOTS = ". " * 20  # dot-leader fill, as extracted from the PDF: "Tytuł . . . . 35"


class TestLinkTocEntries:
    def test_entry_matching_a_chapter_becomes_a_link_on_its_own_line(self):
        text = (
            "## Wstęp\n\n"
            f"1. Linux i bezpieczeństwo {DOTS}35\n"
            "Dalszy tekst wstępu.\n\n"
            "## Linux i bezpieczeństwo\n\n"
            "Treść rozdziału."
        )
        result = link_toc_entries(text)
        # "## Wstęp" opens at position 0 (no real preamble) and gets no
        # anchor of its own, so the first (and only) anchor issued is toc-1.
        assert "[1. Linux i bezpieczeństwo](anchor:toc-1)" in result
        # each entry is its own blank-line-delimited paragraph
        assert "\n\n[1. Linux i bezpieczeństwo](anchor:toc-1)\n\n" in result
        # an anchor sits right before the real header, not the index entry
        assert result.index("[#toc-1]") < result.index("## Linux i bezpieczeństwo")
        assert result.index("[#toc-1]") > result.index("[1. Linux i bezpieczeństwo]")

    def test_subheading_entry_with_no_chapter_number_also_links(self):
        text = (
            "## Rozdział\n\n"
            f"Co to jest Linux? {DOTS}37\n\n"
            "### Co to jest Linux?\n\n"
            "Treść."
        )
        result = link_toc_entries(text)
        assert "[Co to jest Linux?](anchor:toc-1)" in result

    def test_entry_with_no_matching_header_keeps_plain_title_no_link(self):
        text = f"Coś, czego nie ma jako nagłówka {DOTS}73"
        result = link_toc_entries(text)
        assert "anchor:" not in result
        assert "Coś, czego nie ma jako nagłówka" in result
        # dot leaders and the printed page number are gone, just the title remains
        assert result.strip() == "Coś, czego nie ma jako nagłówka"

    def test_short_dot_runs_are_not_touched(self):
        text = "Zobacz str. 12. To jest zwykłe zdanie z kropkami... koniec."
        assert link_toc_entries(text) == text

    def test_duplicate_header_titles_consume_anchors_in_order(self):
        text = (
            "## Rozdział pierwszy\n\n"
            "### Checklista\n\n"
            "## Rozdział drugi\n\n"
            "### Checklista\n\n"
            f"Checklista {DOTS}10\nCzęść pierwsza\n"
            f"Checklista {DOTS}20\nCzęść druga"
        )
        result = link_toc_entries(text)
        # "## Rozdział pierwszy" opens at position 0 and gets no anchor of
        # its own; counting from there, "### Checklista" (1st) = toc-1,
        # "## Rozdział drugi" = toc-2, "### Checklista" (2nd) = toc-3 — each
        # duplicate-titled subheading gets its own distinct anchor, consumed
        # in header order.
        assert "[Checklista](anchor:toc-1)" in result
        assert "[Checklista](anchor:toc-3)" in result

    def test_no_headers_and_no_toc_lines_leaves_text_untouched(self):
        text = "Zwykly tekst bez naglowkow i bez spisu tresci."
        assert link_toc_entries(text) == text

    def test_recovers_subheading_missed_by_font_detection_and_links_it(self):
        # The body line matching the TOC's own title has no "### " marker at
        # all here — simulating detect_heading_texts()'s font/size heuristic
        # missing it at import time. The book's own TOC still lists it, so
        # link_toc_entries() should promote and link it anyway.
        text = (
            "## Rozdział\n\n"
            f"Ukryty podtytuł {DOTS}42\n\n"
            "Ukryty podtytuł\n\n"
            "Treść akapitu."
        )
        result = link_toc_entries(text)
        assert "### Ukryty podtytuł" in result
        assert "[Ukryty podtytuł](anchor:toc-1)" in result

    def test_does_not_promote_a_toc_entry_that_never_recurs_in_the_body(self):
        # Same missing-heading shape, but the title genuinely doesn't appear
        # again anywhere — nothing for _mark_headings() to promote, so the
        # entry stays a plain, unlinked (but still dot-leader-stripped) line.
        text = (
            "## Rozdział\n\n"
            f"Nigdzie indziej {DOTS}42\n\n"
            "Treść akapitu bez powtórzenia tytułu."
        )
        result = link_toc_entries(text)
        assert "###" not in result
        assert "anchor:" not in result
        assert "Nigdzie indziej" in result

    def test_does_not_promote_a_toc_entry_matching_a_known_chapter_title(self):
        # A numbered chapter entry's title is already a "## " header — must
        # never be re-marked as a spurious "### " subheading of itself.
        text = (
            "## Rozdział pierwszy\n\n"
            f"1. Rozdział pierwszy {DOTS}5\n\n"
            "Treść rozdziału, w tym zdanie: Rozdział pierwszy."
        )
        result = link_toc_entries(text)
        assert "### Rozdział pierwszy" not in result

    def test_rerun_recovers_entry_left_unmatched_by_a_previous_run(self):
        # Simulates text a previous link_toc_entries() run already produced:
        # the TOC region has a bare, unmatched paragraph (nothing matched it
        # last time) and the real body now has a matching line to promote.
        text = (
            "SPIS TREŚCI\n\n"
            "Ukryty podtytuł\n\n"
            "## Rozdział\n\n"
            "Ukryty podtytuł\n\n"
            "Treść akapitu."
        )
        result = link_toc_entries(text)
        assert result.count("### Ukryty podtytuł") == 1
        assert "[Ukryty podtytuł](anchor:toc-" in result
        # the TOC region's own listing must NOT itself become a header
        toc_region_text = result[: result.index("## Rozdział")]
        assert "###" not in toc_region_text

    def test_rerun_reuses_an_existing_anchor_instead_of_stacking_a_duplicate(self):
        text = (
            "[#toc-1]\n\n"
            "## Rozdział\n\n"
            "Treść."
        )
        result = link_toc_entries(text)
        assert result == text
        assert result.count("[#toc-1]") == 1


class TestWrapCalloutBoxes:
    def test_wraps_info_paragraph(self):
        text = f"Before.\n\n{INFO}\nZielone ramki niosa informacje.\n\nAfter."
        result = _wrap_callout_boxes(text, info_icon=INFO, warning_icon=WARN)
        assert "[!INFO]\nZielone ramki niosa informacje.\n[!/INFO]" in result
        assert INFO not in result
        assert "Before." in result and "After." in result

    def test_wraps_warning_paragraph(self):
        text = f"{WARN}\nRamka czerwona ostrzega."
        result = _wrap_callout_boxes(text, info_icon=INFO, warning_icon=WARN)
        assert result.strip() == "[!WARN]\nRamka czerwona ostrzega.\n[!/WARN]"

    def test_two_callouts_with_no_blank_line_between_dont_merge(self):
        # Real-world layout found in the book: the info box's own paragraph
        # flows directly into the next icon line with no blank separator.
        text = (
            f"{INFO}\nZielony akapit.\n{WARN}\nCzerwony akapit.\n\nZwykly tekst."
        )
        result = _wrap_callout_boxes(text, info_icon=INFO, warning_icon=WARN)
        assert "[!INFO]\nZielony akapit.\n[!/INFO]" in result
        assert "[!WARN]\nCzerwony akapit.\n[!/WARN]" in result
        assert "Zwykly tekst." in result
        # the warning paragraph must not have leaked into the info box
        info_block = result.split("[!INFO]")[1].split("[!/INFO]")[0]
        assert "Czerwony" not in info_block

    def test_icon_at_end_of_text_with_nothing_after_is_dropped_not_left_dangling(self):
        text = f"Coś.\n\n{INFO}\n\n"
        result = _wrap_callout_boxes(text, info_icon=INFO, warning_icon=WARN)
        assert "[!INFO]" not in result
        assert INFO not in result
        assert "Coś." in result

    def test_icon_skips_blank_lines_before_its_paragraph(self):
        # A gap of blank lines between the icon and its own paragraph (page
        # layout artifact) must not stop the icon from finding its content.
        text = f"{INFO}\n\n\nZielony akapit po pustych liniach."
        result = _wrap_callout_boxes(text, info_icon=INFO, warning_icon=WARN)
        assert "[!INFO]\nZielony akapit po pustych liniach.\n[!/INFO]" in result

    def test_plain_text_without_icons_is_unchanged(self):
        text = "Zwykly akapit bez zadnych ramek.\n\nDrugi akapit."
        assert _wrap_callout_boxes(text, info_icon=INFO, warning_icon=WARN) == text


class TestTableToMarkdown:
    def test_renders_header_and_data_rows(self):
        rows = [["A", "B"], ["1", "2"], ["3", "4"]]
        markdown = _table_to_markdown(rows)
        assert markdown == "| A | B |\n| --- | --- |\n| 1 | 2 |\n| 3 | 4 |"

    def test_none_and_missing_cells_become_blank(self):
        rows = [["A", "B", "C"], [None, "x"]]
        markdown = _table_to_markdown(rows)
        lines = markdown.split("\n")
        assert lines[2] == "|  | x |  |"

    def test_multiline_cell_collapses_to_single_line(self):
        rows = [["H"], ["line one\nline two"]]
        markdown = _table_to_markdown(rows)
        assert "\n" not in markdown.split("\n")[2]
        assert "line one line two" in markdown

    def test_pipe_in_cell_is_escaped(self):
        rows = [["H"], ["a | b"]]
        markdown = _table_to_markdown(rows)
        assert "a \\| b" in markdown

    def test_single_row_table_is_not_a_real_table(self):
        # Matches the callout-box false positive PyMuPDF's find_tables()
        # detects (icon | text, one row) — must not become a markdown table.
        assert _table_to_markdown([["icon", "text"]]) is None

    def test_empty_header_returns_none(self):
        assert _table_to_markdown([["", None], ["1", "2"]]) is None

    def test_empty_rows_returns_none(self):
        assert _table_to_markdown([]) is None
