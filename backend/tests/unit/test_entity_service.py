"""Unit tests for library/entity_service.py — document_entities persistence layer."""

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("requests")

from library.db.models import DocumentEntity, NerExclusion  # noqa: E402
from library.entity_service import get_document_entities, is_excluded, refresh_document_entities  # noqa: E402


RAW = [
    {"text": "Tuska", "label": "persName", "lemma": "Tusk"},
    {"text": "Tusk", "label": "persName", "lemma": "Tusk"},
    {"text": "Cieśninie Ormuz", "label": "geogName", "lemma": "cieśnina Ormuz"},
]


def _session_with_exclusions(exclusions):
    session = MagicMock()
    session.execute.return_value.scalars.return_value.all.return_value = exclusions
    return session


class TestRefreshDocumentEntities:
    def test_replaces_rows_with_aggregated_entities(self):
        session = _session_with_exclusions([])
        with patch("library.entity_service.extract_entities", return_value=RAW):
            rows = refresh_document_entities(session, 42, "jakiś tekst")

        assert session.execute.call_count == 2  # SELECT exclusions + DELETE of previous rows
        session.add_all.assert_called_once_with(rows)
        assert {(r.entity_type, r.entity_text, r.mention_count) for r in rows} == {
            ("persName", "Tusk", 2),
            ("geogName", "cieśnina Ormuz", 1),
        }
        assert all(isinstance(r, DocumentEntity) and r.document_id == 42 for r in rows)

    def test_rows_sorted_most_mentioned_first(self):
        session = _session_with_exclusions([])
        with patch("library.entity_service.extract_entities", return_value=RAW):
            rows = refresh_document_entities(session, 42, "jakiś tekst")
        assert rows[0].entity_text == "Tusk"

    def test_service_unavailable_keeps_existing_rows(self):
        """Empty extraction (service down) must not delete previously stored entities."""
        session = MagicMock()
        with patch("library.entity_service.extract_entities", return_value=[]):
            rows = refresh_document_entities(session, 42, "jakiś tekst")

        assert rows == []
        session.execute.assert_not_called()
        session.add_all.assert_not_called()

    def test_global_exclusion_drops_entity(self):
        session = _session_with_exclusions(
            [NerExclusion(entity_text="tusk", entity_type="persName", scope="global")]
        )
        with patch("library.entity_service.extract_entities", return_value=RAW):
            rows = refresh_document_entities(session, 42, "jakiś tekst")

        assert {r.entity_text for r in rows} == {"cieśnina Ormuz"}

    def test_author_exclusion_applies_only_to_matching_author(self):
        exclusions = [NerExclusion(entity_text="Tusk", entity_type="*", scope="author",
                                   author="Good Times Bad Times")]
        session = _session_with_exclusions(exclusions)
        session.get.return_value = MagicMock(author="Good Times Bad Times")
        with patch("library.entity_service.extract_entities", return_value=RAW):
            rows = refresh_document_entities(session, 42, "jakiś tekst")
        assert {r.entity_text for r in rows} == {"cieśnina Ormuz"}

        session2 = _session_with_exclusions(exclusions)
        session2.get.return_value = MagicMock(author="Inny Kanał")
        with patch("library.entity_service.extract_entities", return_value=RAW):
            rows2 = refresh_document_entities(session2, 42, "jakiś tekst")
        assert {r.entity_text for r in rows2} == {"Tusk", "cieśnina Ormuz"}


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

    def test_author_scope_needs_author(self):
        rules = [NerExclusion(entity_text="Starlinek", entity_type="persName",
                              scope="author", author="Kanał X")]
        assert is_excluded(rules, "persName", "Starlinek", None) is False
        assert is_excluded(rules, "persName", "Starlinek", "kanał x") is True
        assert is_excluded(rules, "persName", "Starlinek", "Inny") is False


class TestGetDocumentEntities:
    def test_groups_by_type(self):
        row1 = MagicMock(id=1, entity_type="persName", entity_text="Tusk", mention_count=2, geocode=None)
        row2 = MagicMock(id=2, entity_type="geogName", entity_text="cieśnina Ormuz", mention_count=1, geocode=None)
        session = MagicMock()
        session.query.return_value.filter.return_value.order_by.return_value.all.return_value = [row1, row2]

        grouped = get_document_entities(session, 42)

        assert grouped == {
            "persName": [{"id": 1, "text": "Tusk", "count": 2}],
            "geogName": [{"id": 2, "text": "cieśnina Ormuz", "count": 1}],
            "placeName": [],
        }

    def test_verified_place_carries_geocode_fields(self):
        geo = MagicMock(resolved=True, lat=50.45, lon=30.52, display_name="Kyiv, Ukraine")
        row = MagicMock(id=3, entity_type="placeName", entity_text="Kijów", mention_count=3, geocode=geo)
        session = MagicMock()
        session.query.return_value.filter.return_value.order_by.return_value.all.return_value = [row]

        grouped = get_document_entities(session, 42)

        assert grouped["placeName"] == [{
            "id": 3, "text": "Kijów", "count": 3, "verified": True,
            "lat": 50.45, "lon": 30.52, "display_name": "Kyiv, Ukraine",
        }]

    def test_unresolved_place_marked_not_verified(self):
        geo = MagicMock(resolved=False)
        row = MagicMock(id=4, entity_type="geogName", entity_text="Jagami", mention_count=1, geocode=geo)
        session = MagicMock()
        session.query.return_value.filter.return_value.order_by.return_value.all.return_value = [row]

        grouped = get_document_entities(session, 42)

        assert grouped["geogName"] == [{"id": 4, "text": "Jagami", "count": 1, "verified": False}]

    def test_empty_document_returns_all_type_keys(self):
        session = MagicMock()
        session.query.return_value.filter.return_value.order_by.return_value.all.return_value = []
        assert get_document_entities(session, 42) == {"persName": [], "geogName": [], "placeName": []}
