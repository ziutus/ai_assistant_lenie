"""Unit tests for library/entity_service.py — document_entities persistence layer."""

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("requests")

from library.db.models import DocumentEntity  # noqa: E402
from library.entity_service import get_document_entities, refresh_document_entities  # noqa: E402


RAW = [
    {"text": "Tuska", "label": "persName", "lemma": "Tusk"},
    {"text": "Tusk", "label": "persName", "lemma": "Tusk"},
    {"text": "Cieśninie Ormuz", "label": "geogName", "lemma": "cieśnina Ormuz"},
]


class TestRefreshDocumentEntities:
    def test_replaces_rows_with_aggregated_entities(self):
        session = MagicMock()
        with patch("library.entity_service.extract_entities", return_value=RAW):
            rows = refresh_document_entities(session, 42, "jakiś tekst")

        session.execute.assert_called_once()  # DELETE of previous rows
        session.add_all.assert_called_once_with(rows)
        assert {(r.entity_type, r.entity_text, r.mention_count) for r in rows} == {
            ("persName", "Tusk", 2),
            ("geogName", "cieśnina Ormuz", 1),
        }
        assert all(isinstance(r, DocumentEntity) and r.document_id == 42 for r in rows)

    def test_rows_sorted_most_mentioned_first(self):
        session = MagicMock()
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


class TestGetDocumentEntities:
    def test_groups_by_type(self):
        row1 = MagicMock(entity_type="persName", entity_text="Tusk", mention_count=2)
        row2 = MagicMock(entity_type="geogName", entity_text="cieśnina Ormuz", mention_count=1)
        session = MagicMock()
        session.query.return_value.filter.return_value.order_by.return_value.all.return_value = [row1, row2]

        grouped = get_document_entities(session, 42)

        assert grouped == {
            "persName": [{"text": "Tusk", "count": 2}],
            "geogName": [{"text": "cieśnina Ormuz", "count": 1}],
            "placeName": [],
        }

    def test_empty_document_returns_all_type_keys(self):
        session = MagicMock()
        session.query.return_value.filter.return_value.order_by.return_value.all.return_value = []
        assert get_document_entities(session, 42) == {"persName": [], "geogName": [], "placeName": []}
