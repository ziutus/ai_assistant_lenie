import logging

from library import ner_normalization
from library.ner_normalization import (
    normalize_ner_text,
    strip_content_markers,
    strip_wrapping_quotes,
)


def test_missing_rules_file_falls_back_to_empty_rules(monkeypatch, tmp_path, caplog):
    missing_path = tmp_path / "missing-ner-normalization.json"
    monkeypatch.setattr(ner_normalization, "RULES_PATH", missing_path)
    ner_normalization.load_ner_normalization_rules.cache_clear()

    try:
        with caplog.at_level(logging.WARNING, logger=ner_normalization.__name__):
            assert ner_normalization.load_ner_normalization_rules() == {}

        assert "NER normalization rules file does not exist" in caplog.text
        assert ner_normalization.canonical_country_for_surface("Iranem") == "Iran"
        assert not ner_normalization.is_rejected_surface_lemma_pair("Dana", "Dan", "PROPN")
    finally:
        ner_normalization.load_ner_normalization_rules.cache_clear()


class TestStripMarkdownEmphasis:
    def test_bold_marker_glued_to_word_is_blanked(self):
        text = "źródło w Ministerstwie Aktywów Państwowych.**- Tymczasem ta koalicja"
        result = ner_normalization.strip_markdown_emphasis(text)
        assert "**" not in result
        assert "Ministerstwie Aktywów Państwowych." in result

    def test_preserves_length_and_surrounding_text(self):
        text = "a **bold** b __also__ c"
        result = ner_normalization.strip_markdown_emphasis(text)
        assert len(result) == len(text)
        assert result == "a   bold   b   also   c"

    def test_text_without_markdown_is_unchanged(self):
        text = "Donald Tusk spotkał się z premierem."
        assert ner_normalization.strip_markdown_emphasis(text) == text


class TestNormalizeNerText:
    def test_collapses_internal_newline_from_line_wrapped_span(self):
        # spaCy's Span.text preserves the original inter-token whitespace, so
        # a multiword entity split across a markdown line wrap comes back
        # with a literal newline inside it (seen live: "Unia\nEuropejska"
        # ended up stored as an organization's canonical_name).
        assert normalize_ner_text("Unia\nEuropejska") == "Unia Europejska"

    def test_collapses_tabs_and_multiple_spaces(self):
        assert normalize_ner_text("Siły\t Zbrojne   Sudanu") == "Siły Zbrojne Sudanu"

    def test_strips_leading_and_trailing_whitespace(self):
        assert normalize_ner_text("  Interia  ") == "Interia"

    def test_single_space_between_words_is_unchanged(self):
        assert normalize_ner_text("Arabia Saudyjska") == "Arabia Saudyjska"


class TestStripContentMarkers:
    def test_blanks_link_marker_glued_to_entity(self):
        # Live bug: "Ministerstwo Obrony[link1]" -> spaCy folded "[link1" into
        # the entity span, producing canonical_name "ministerstwo obrona [link1".
        text = "Ministerstwo Obrony[link1] ogłosiło."
        result = strip_content_markers(text)
        assert "[link1]" not in result
        assert len(result) == len(text)

    def test_blanks_img_marker(self):
        text = "Zdjęcie[img3] przedstawia most."
        assert "[img3]" not in strip_content_markers(text)

    def test_leaves_unrelated_brackets_untouched(self):
        text = "Ustawa [Dz.U. 2024] weszła w życie."
        assert strip_content_markers(text) == text


class TestStripWrappingQuotes:
    def test_live_bug_dangling_ascii_closing_quote_is_stripped(self):
        # Live case (doc 9394): 'jako "sudańskie Bractwo Muzułmańskie", zostali'
        # produced the orgName span 'Bractwo Muzułmańskie"' and the mangled
        # lemma 'bractwo Muzułmański"' — both ended up in organizations.
        assert strip_wrapping_quotes('Bractwo Muzułmańskie"') == "Bractwo Muzułmańskie"
        assert strip_wrapping_quotes('bractwo Muzułmański"') == "bractwo Muzułmański"

    def test_fully_wrapped_span_is_stripped(self):
        assert strip_wrapping_quotes('"Financial Times"') == "Financial Times"

    def test_polish_quotes_wrapping_span_are_stripped(self):
        assert strip_wrapping_quotes("„przyjaźń”") == "przyjaźń"

    def test_mixed_polish_opener_with_ascii_closer_is_stripped(self):
        # Polish typing habitually pairs „ with ".
        assert strip_wrapping_quotes('„Grot"') == "Grot"

    def test_dangling_interior_quote_is_removed(self):
        # Live pollution: persName 'Hans Pool "Bellingcat' (source text opened
        # a quotation the span cuts short) and geogName '"ZOO zapraszać'.
        assert strip_wrapping_quotes("Hans Pool \"Bellingcat") == "Hans Pool Bellingcat"
        assert strip_wrapping_quotes('"ZOO zapraszać') == "ZOO zapraszać"

    def test_dangling_interior_quote_after_comma_is_removed(self):
        # Live pollution: persName 'Donald Trump,"szejk' — the unmatched '"'
        # goes, the surrounding junk (comma) is out of scope for this helper.
        assert strip_wrapping_quotes('Donald Trump,"szejk') == "Donald Trump,szejk"

    def test_stacked_edge_quotes_are_stripped(self):
        assert strip_wrapping_quotes('""Grot"') == "Grot"

    def test_inner_quotation_closer_is_never_touched(self):
        # The trailing ” legitimately closes the inner „Rocky” nickname —
        # its partner sits inside the span, so the pair stays untouched.
        assert strip_wrapping_quotes("Aleksander „Rocky”") == "Aleksander „Rocky”"
        assert strip_wrapping_quotes('CBRE "European data Centres"') == 'CBRE "European data Centres"'

    def test_mid_span_junk_comma_is_out_of_scope(self):
        assert strip_wrapping_quotes("prezydent Donald Trump, kanclerz") == "prezydent Donald Trump, kanclerz"

    def test_apostrophes_are_name_content_and_untouched(self):
        assert strip_wrapping_quotes("O'Brien") == "O'Brien"

    def test_plain_names_pass_through_unchanged(self):
        assert strip_wrapping_quotes("Bractwo Muzułmańskie") == "Bractwo Muzułmańskie"

    def test_whitespace_after_edge_strip_is_removed(self):
        assert strip_wrapping_quotes('" Financial Times "') == "Financial Times"

    def test_only_quotes_returns_unchanged(self):
        # Never returns an empty string for a quote-only span.
        assert strip_wrapping_quotes('""') == '""'
