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
