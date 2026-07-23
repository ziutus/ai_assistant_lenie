"""Unit tests for library/entity_service.py — document_entities persistence layer."""

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("requests")

from library.db.models import DocumentEntity, NerExclusion  # noqa: E402
from library.entity_service import (  # noqa: E402
    _temporal_candidate_rows,
    get_document_entities,
    is_excluded,
    refresh_document_entities,
)


RAW = [
    {"text": "Tuska", "label": "persName", "lemma": "Tusk"},
    {"text": "Tusk", "label": "persName", "lemma": "Tusk"},
    {"text": "Cieśninie Ormuz", "label": "geogName", "lemma": "cieśnina Ormuz"},
]


def _session_with_exclusions(exclusions):
    session = MagicMock()
    session.execute.return_value.scalars.return_value.all.return_value = exclusions
    session.get.return_value = MagicMock(byline=None)
    return session


class TestRefreshDocumentEntities:
    def test_temporal_candidates_keep_type_position_and_context(self):
        text = "Wstęp. 17 września 1939 rozpoczęła się wojna o godzinie 4:45."
        raw = [
            {"text": "17 września 1939", "label": "date", "lemma": "17 wrzesień 1939"},
            {"text": "4:45", "label": "time", "lemma": "4:45"},
        ]

        rows = _temporal_candidate_rows(42, text, raw)

        assert [(row.entity_type, row.raw_text) for row in rows] == [
            ("date", "17 września 1939"),
            ("time", "4:45"),
        ]
        assert rows[0].char_start == text.index("17 września 1939")
        assert "rozpoczęła się wojna" in rows[0].context_excerpt

    def test_compact_dates_replace_split_ner_candidates(self):
        text = "Od 06.04 do 08.04 trwały testy. W środę 09.04 wystrzelono pociski."
        raw = [
            {"text": "06.", "label": "date", "lemma": "06."},
            {"text": "04", "label": "time", "lemma": "04"},
            {"text": "08.", "label": "date", "lemma": "08."},
            {"text": "04", "label": "time", "lemma": "04"},
            {"text": "09.", "label": "date", "lemma": "09."},
            {"text": "04", "label": "date", "lemma": "04"},
        ]

        rows = _temporal_candidate_rows(42, text, raw)

        assert [(row.entity_type, row.raw_text) for row in rows] == [
            ("date", "06.04"),
            ("date", "08.04"),
            ("date", "09.04"),
        ]

    def test_replaces_rows_with_aggregated_entities(self):
        session = _session_with_exclusions([])
        with patch("library.entity_service.extract_entities", return_value=RAW):
            rows = refresh_document_entities(session, 42, "jakiś tekst")

        # SELECT exclusions + replace temporal candidates + replace entities
        assert session.execute.call_count == 3
        session.add_all.assert_called_once_with(rows)
        assert {(r.entity_type, r.entity_text, r.mention_count) for r in rows} == {
            ("persName", "Tusk", 2),
            ("geogName", "cieśnina Ormuz", 1),
        }
        assert all(isinstance(r, DocumentEntity) and r.document_id == 42 for r in rows)
        # formy powierzchniowe z tekstu zapisane per wiersz (filtr per rozdział)
        assert {r.entity_text: r.variants for r in rows} == {
            "Tusk": ["Tuska", "Tusk"],
            "cieśnina Ormuz": ["Cieśninie Ormuz"],
        }

    def test_rows_sorted_most_mentioned_first(self):
        session = _session_with_exclusions([])
        with patch("library.entity_service.extract_entities", return_value=RAW):
            rows = refresh_document_entities(session, 42, "jakiś tekst")
        assert rows[0].entity_text == "Tusk"

    def test_genuinely_empty_extraction_keeps_existing_rows(self):
        """Empty extraction with the service reachable must not touch document_entities."""
        session = MagicMock()
        with patch("library.entity_service.extract_entities", return_value=[]), \
             patch("library.entity_service.is_available", return_value=True):
            rows = refresh_document_entities(session, 42, "jakiś tekst")

        assert rows == []
        session.add_all.assert_not_called()
        session.commit.assert_called_once()  # clears any stale ner_unavailable_at

    def test_service_unavailable_raises_and_flags_document_without_touching_rows(self):
        """Empty extraction with the service down must raise, not silently return []."""
        from library.ner_client import NERServiceUnavailable

        session = MagicMock()
        with patch("library.entity_service.extract_entities", return_value=[]), \
             patch("library.entity_service.is_available", return_value=False):
            with pytest.raises(NERServiceUnavailable):
                refresh_document_entities(session, 42, "jakiś tekst")

        session.add_all.assert_not_called()
        session.commit.assert_called_once()  # sets ner_unavailable_at, own transaction

    def test_global_exclusion_drops_entity(self):
        session = _session_with_exclusions(
            [NerExclusion(entity_text="tusk", entity_type="persName", scope="global")]
        )
        with patch("library.entity_service.extract_entities", return_value=RAW):
            rows = refresh_document_entities(session, 42, "jakiś tekst")

        assert {r.entity_text for r in rows} == {"cieśnina Ormuz"}

    def test_exclusion_matches_raw_variant_after_country_canonicalization(self):
        session = _session_with_exclusions(
            [NerExclusion(entity_text="Turcy", entity_type="placeName", scope="global")]
        )
        raw = [{"text": "Turcy", "label": "placeName", "lemma": "Turk", "pos": "NOUN"}]
        with patch("library.entity_service.extract_entities", return_value=raw):
            rows = refresh_document_entities(session, 42, "Turcy")
        assert rows == []

    def test_exclusion_matches_raw_lemma_after_country_canonicalization(self):
        session = _session_with_exclusions(
            [NerExclusion(entity_text="Turk", entity_type="placeName", scope="global")]
        )
        raw = [{"text": "Turcy", "label": "placeName", "lemma": "Turk", "pos": "NOUN"}]
        with patch("library.entity_service.extract_entities", return_value=raw):
            rows = refresh_document_entities(session, 42, "Turcy")
        assert rows == []

    def test_author_exclusion_applies_only_to_matching_author(self):
        exclusions = [NerExclusion(entity_text="Tusk", entity_type="*", scope="author",
                                   author="Good Times Bad Times")]
        session = _session_with_exclusions(exclusions)
        session.get.return_value = MagicMock(byline="Good Times Bad Times")
        with patch("library.entity_service.extract_entities", return_value=RAW):
            rows = refresh_document_entities(session, 42, "jakiś tekst")
        assert {r.entity_text for r in rows} == {"cieśnina Ormuz"}

        session2 = _session_with_exclusions(exclusions)
        session2.get.return_value = MagicMock(byline="Inny Kanał")
        with patch("library.entity_service.extract_entities", return_value=RAW):
            rows2 = refresh_document_entities(session2, 42, "jakiś tekst")
        assert {r.entity_text for r in rows2} == {"Tusk", "cieśnina Ormuz"}


    def test_high_confidence_context_verdict_drops_false_person_and_records_it(self):
        session = _session_with_exclusions([])
        raw = [{"text": "Pocisków", "label": "persName", "lemma": "Pocisków"}]
        verdict = {
            "key": ("persName", "Pocisków"),
            "entity_text": "Pocisków",
            "context": "dostawy pocisków artyleryjskich",
            "predicted_class": "not_person",
            "confidence": "high",
            "rationale": "Rodzaj amunicji.",
            "model": "Bielik-11B-v3.0-Instruct",
            "dropped": True,
        }
        with patch("library.entity_service.extract_entities", return_value=raw), patch(
            "library.person_context_classifier.classify_single_word_person_candidates",
            return_value=[verdict],
        ):
            rows = refresh_document_entities(
                session, 42, "Rozpoczęto dostawy pocisków artyleryjskich."
            )

        assert rows == []
        classification_rows = session.add_all.call_args_list[0].args[0]
        assert len(classification_rows) == 1
        assert classification_rows[0].entity_text == "Pocisków"
        assert classification_rows[0].dropped is True


class TestIsExcluded:
    def test_case_insensitive_text_match(self):
        rules = [NerExclusion(entity_text="starling", entity_type="persName", scope="global")]
        assert is_excluded(rules, "persName", "Starling", None) is True

    def test_wildcard_type_matches_all_types(self):
        rules = [NerExclusion(entity_text="Taliban", entity_type="*", scope="global")]
        assert is_excluded(rules, "persName", "Taliban", None) is True
        assert is_excluded(rules, "geogName", "Taliban", None) is True

    def test_specific_type_does_not_match_other_types(self):
        rules = [NerExclusion(entity_text="Taliban", entity_type="persName", scope="global")]
        assert is_excluded(rules, "geogName", "Taliban", None) is False

    def test_place_types_are_equivalent_after_label_merging(self):
        rules = [NerExclusion(entity_text="Ukraina", entity_type="geogName", scope="global")]
        assert is_excluded(rules, "placeName", "Ukraina", None) is True

    def test_author_scope_needs_author(self):
        rules = [NerExclusion(entity_text="Starlinek", entity_type="persName",
                              scope="author", author="Kanał X")]
        assert is_excluded(rules, "persName", "Starlinek", None) is False
        assert is_excluded(rules, "persName", "Starlinek", "kanał x") is True
        assert is_excluded(rules, "persName", "Starlinek", "Inny") is False

    def test_matches_raw_terms(self):
        rules = [NerExclusion(entity_text="Turcy", entity_type="placeName", scope="global")]
        assert is_excluded(rules, "placeName", "Turcja", None, raw_terms=["Turk", "Turcy"]) is True


class TestGetDocumentEntities:
    def test_groups_by_type(self):
        row1 = MagicMock(id=1, entity_type="persName", entity_text="Tusk", mention_count=2, geocode=None,
                         variants=["Tuska", "Tusk"])
        row2 = MagicMock(id=2, entity_type="geogName", entity_text="cieśnina Ormuz", mention_count=1, geocode=None,
                         variants=["Cieśninie Ormuz"])
        session = MagicMock()
        session.query.return_value.filter.return_value.order_by.return_value.all.return_value = [row1, row2]

        grouped = get_document_entities(session, 42)

        assert grouped == {
            "persName": [{"id": 1, "text": "Tusk", "count": 2, "variants": ["Tuska", "Tusk"]}],
            "orgName": [],
            "geogName": [{"id": 2, "text": "cieśnina Ormuz", "count": 1, "variants": ["Cieśninie Ormuz"]}],
            "placeName": [],
        }

    def test_groups_organization_without_geocoding_fields(self):
        row = MagicMock(
            id=4, entity_type="orgName", entity_text="Bloomberg",
            mention_count=1, geocode=None, variants=["Bloomberg"],
        )
        session = MagicMock()
        session.query.return_value.filter.return_value.order_by.return_value.all.return_value = [row]

        grouped = get_document_entities(session, 42)

        assert grouped["orgName"] == [{
            "id": 4, "text": "Bloomberg", "count": 1, "variants": ["Bloomberg"],
        }]
        assert grouped["geogName"] == []
        assert grouped["placeName"] == []

    def test_verified_place_carries_geocode_fields(self):
        geo = MagicMock(resolved=True, lat=50.45, lon=30.52, display_name="Kyiv, Ukraine")
        row = MagicMock(id=3, entity_type="placeName", entity_text="Kijów", mention_count=3, geocode=geo,
                        variants=["Kijowa"])
        session = MagicMock()
        session.query.return_value.filter.return_value.order_by.return_value.all.return_value = [row]

        grouped = get_document_entities(session, 42)

        assert grouped["placeName"] == [{
            "id": 3, "text": "Kijów", "count": 3, "variants": ["Kijowa"], "verified": True,
            "lat": 50.45, "lon": 30.52, "display_name": "Kyiv, Ukraine",
        }]

    def test_unresolved_place_marked_not_verified(self):
        geo = MagicMock(resolved=False)
        row = MagicMock(id=4, entity_type="geogName", entity_text="Jagami", mention_count=1, geocode=geo,
                        variants=[])
        session = MagicMock()
        session.query.return_value.filter.return_value.order_by.return_value.all.return_value = [row]

        grouped = get_document_entities(session, 42)

        assert grouped["geogName"] == [{"id": 4, "text": "Jagami", "count": 1, "variants": [],
                                        "verified": False}]

    def test_empty_document_returns_all_type_keys(self):
        session = MagicMock()
        session.query.return_value.filter.return_value.order_by.return_value.all.return_value = []
        assert get_document_entities(session, 42) == {
            "persName": [], "orgName": [], "geogName": [], "placeName": [],
        }
