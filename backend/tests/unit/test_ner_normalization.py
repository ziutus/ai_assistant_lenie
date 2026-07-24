import logging

from library import ner_normalization


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
