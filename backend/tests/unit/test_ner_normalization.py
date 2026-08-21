import logging

from library import ner_normalization
from library.ner_normalization import normalize_ner_text, strip_content_markers


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
