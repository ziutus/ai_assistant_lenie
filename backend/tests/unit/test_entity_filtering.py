"""Unit tests for entity_service.filter_entities_to_text — chapter-scoped entity attribution.

The document-level pipeline verifies entities once (geocoder/Wikidata/LLM);
this filter only decides which verified entities appear in a given chapter's
text, matching the stored surface variants at word-start boundaries.
"""

import pytest

pytest.importorskip("sqlalchemy")

from library.entity_service import filter_entities_to_text  # noqa: E402


def _grouped(**overrides):
    grouped = {"persName": [], "geogName": [], "placeName": []}
    grouped.update(overrides)
    return grouped


class TestFilterEntitiesToText:
    def test_variant_matches_inflected_form_as_prefix(self):
        """"Iran" (wariant) znajduje "Iranie" w tekście — polska odmiana to sufiks."""
        grouped = _grouped(placeName=[{"text": "Iran", "count": 5, "variants": ["Iran"]}])
        out = filter_entities_to_text(grouped, "Konflikt w Iranie trwa od lat.")
        assert [i["text"] for i in out["placeName"]] == ["Iran"]

    def test_no_match_inside_word(self):
        grouped = _grouped(placeName=[{"text": "Iran", "count": 1, "variants": ["Iran"]}])
        out = filter_entities_to_text(grouped, "Samolot Airanu wystartował.")
        assert out["placeName"] == []

    def test_any_stored_variant_matches(self):
        """Lemat "Kijów" nie występuje w rozdziale, ale wariant "Kijowa" tak."""
        grouped = _grouped(placeName=[
            {"text": "Kijów", "count": 2, "variants": ["Kijowie", "Kijowa"]},
        ])
        out = filter_entities_to_text(grouped, "Delegacja wróciła z Kijowa wieczorem.")
        assert [i["text"] for i in out["placeName"]] == ["Kijów"]

    def test_match_is_case_insensitive(self):
        grouped = _grouped(persName=[{"text": "Tusk", "count": 1, "variants": ["Tusk"]}])
        out = filter_entities_to_text(grouped, "TUSK zapowiedział zmiany.")
        assert [i["text"] for i in out["persName"]] == ["Tusk"]

    def test_rows_without_variants_fall_back_to_entity_text(self):
        """Wiersze sprzed kolumny variants — dopasowanie po entity_text (lemacie)."""
        grouped = _grouped(geogName=[{"text": "Bosfor", "count": 1, "variants": []}])
        out = filter_entities_to_text(grouped, "Statki przepłynęły Bosfor nocą.")
        assert [i["text"] for i in out["geogName"]] == ["Bosfor"]

    def test_unmentioned_entities_are_dropped_per_type(self):
        """Regresja na realny przypadek (doc 9216): Beludżystan nie należy do rozdziału o Iranie."""
        grouped = _grouped(
            persName=[{"text": "Macron", "count": 3, "variants": ["Macron", "Macrona"]}],
            placeName=[
                {"text": "Teheran", "count": 2, "variants": ["Teheranie"]},
                {"text": "Beludżystan", "count": 2, "variants": ["Beludżystanie"]},
            ],
        )
        out = filter_entities_to_text(grouped, "USA bombardują Iran. W Teheranie ogłoszono alarm.")
        assert out["persName"] == []
        assert [i["text"] for i in out["placeName"]] == ["Teheran"]

    def test_count_localized_to_text_metadata_preserved(self):
        """Chip "Putin ×50" w trybie rozdziału pokazywał licznik z całej książki — teraz lokalny."""
        item = {"text": "Teheran", "count": 42, "variants": ["Teheran", "Teheranie"], "verified": True,
                "lat": 35.7, "lon": 51.4, "display_name": "Teheran, Iran"}
        out = filter_entities_to_text(_grouped(placeName=[item]), "Teheran nocą. W Teheranie alarm.")
        assert out["placeName"][0]["count"] == 2
        assert out["placeName"][0]["verified"] is True
        assert out["placeName"][0]["display_name"] == "Teheran, Iran"
        assert item["count"] == 42  # oryginał (widok całego dokumentu) nietknięty

    def test_kept_items_sorted_by_local_count(self):
        grouped = _grouped(persName=[
            {"text": "Putin", "count": 50, "variants": ["Putin"]},
            {"text": "Merkel", "count": 3, "variants": ["Merkel"]},
        ])
        out = filter_entities_to_text(grouped, "Merkel i Merkel rozmawiały o Putinie.")
        assert [(i["text"], i["count"]) for i in out["persName"]] == [("Merkel", 2), ("Putin", 1)]
