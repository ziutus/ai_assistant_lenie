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
