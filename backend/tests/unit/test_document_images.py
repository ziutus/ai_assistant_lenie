"""Unit tests for document_images (library/document_images.py + ORM model).

Images extracted from article text used to have their URL discarded once
article_cleaner.clean_article_text() replaced ![alt](url) with an [imgN]
marker. This table preserves url/alt/caption so article_quality.py can score
photo sourcing without the markup needing to stay inline in text_md.
"""

from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")

from sqlalchemy import inspect  # noqa: E402

from library.db.models import DocumentImage  # noqa: E402
from library.document_images import replace_document_images  # noqa: E402


# ---------------------------------------------------------------------------
# ORM model
# ---------------------------------------------------------------------------


class TestDocumentImageModel:
    EXPECTED_COLUMNS = {
        "id", "document_id", "chunk_id", "position", "url", "alt_text",
        "caption_text", "caption_category", "is_stock_photo", "created_at",
    }

    def test_tablename(self):
        assert DocumentImage.__tablename__ == "document_images"

    def test_columns(self):
        mapper = inspect(DocumentImage).mapper
        assert {col.key for col in mapper.columns} == self.EXPECTED_COLUMNS

    def test_document_fk_cascade(self):
        col = inspect(DocumentImage).mapper.columns["document_id"]
        fk = next(iter(col.foreign_keys))
        assert fk.column.table.name == "documents"
        assert fk.ondelete == "CASCADE"
        assert col.nullable is False

    def test_chunk_fk_set_null(self):
        col = inspect(DocumentImage).mapper.columns["chunk_id"]
        fk = next(iter(col.foreign_keys))
        assert fk.column.table.name == "document_chunks"
        assert fk.ondelete == "SET NULL"
        assert col.nullable is True

    def test_url_not_nullable(self):
        assert inspect(DocumentImage).mapper.columns["url"].nullable is False


# ---------------------------------------------------------------------------
# replace_document_images
# ---------------------------------------------------------------------------


class TestReplaceDocumentImages:
    def _added_rows(self, session):
        calls = session.add_all.call_args_list
        assert len(calls) == 1
        return list(calls[0].args[0])

    def test_builds_one_row_per_image(self):
        session = MagicMock(spec=["execute", "add_all"])
        images = [
            {"alt": "Pierwsze", "url": "https://example.com/1.jpg"},
            {"alt": "Drugie", "url": "https://example.com/2.jpg",
             "caption_text": "Fot. Jan Kowalski / PAP", "caption_category": "agency"},
        ]

        rows = replace_document_images(session, document_id=9094, images=images)

        assert len(rows) == 2
        stored = self._added_rows(session)
        assert stored == rows
        assert [r.url for r in stored] == [
            "https://example.com/1.jpg", "https://example.com/2.jpg",
        ]
        assert [r.position for r in stored] == [0, 1]
        assert [r.document_id for r in stored] == [9094, 9094]
        assert stored[0].caption_text is None
        assert stored[0].caption_category is None
        assert stored[1].caption_text == "Fot. Jan Kowalski / PAP"
        assert stored[1].caption_category == "agency"

    def test_marks_stock_category_as_stock_photo(self):
        session = MagicMock(spec=["execute", "add_all"])
        images = [{
            "alt": "", "url": "https://example.com/1.jpg",
            "caption_text": "Jan Nowak / Shutterstock", "caption_category": "stock",
        }]

        rows = replace_document_images(session, document_id=1, images=images)

        assert rows[0].is_stock_photo is True

    def test_non_stock_category_not_marked(self):
        session = MagicMock(spec=["execute", "add_all"])
        images = [{
            "alt": "", "url": "https://example.com/1.jpg",
            "caption_text": "Fot. Jan Kowalski / PAP", "caption_category": "agency",
        }]

        rows = replace_document_images(session, document_id=1, images=images)

        assert rows[0].is_stock_photo is False

    def test_skips_images_without_url(self):
        session = MagicMock(spec=["execute", "add_all"])
        images = [{"alt": "brak url", "url": ""}, {"alt": "ok", "url": "https://example.com/1.jpg"}]

        rows = replace_document_images(session, document_id=1, images=images)

        assert len(rows) == 1
        assert rows[0].url == "https://example.com/1.jpg"

    def test_empty_alt_stored_as_null(self):
        session = MagicMock(spec=["execute", "add_all"])
        images = [{"alt": "", "url": "https://example.com/1.jpg"}]

        rows = replace_document_images(session, document_id=1, images=images)

        assert rows[0].alt_text is None

    def test_empty_images_list_does_not_call_add_all(self):
        session = MagicMock(spec=["execute", "add_all"])
        rows = replace_document_images(session, document_id=1, images=[])

        assert rows == []
        session.add_all.assert_not_called()

    def test_always_deletes_existing_rows_first(self):
        """Replace semantics: even an empty new set must clear old rows."""
        session = MagicMock(spec=["execute", "add_all"])
        replace_document_images(session, document_id=1, images=[])
        session.execute.assert_called_once()

    def test_does_not_commit(self):
        """Caller owns the transaction — helper must only queue changes."""
        session = MagicMock(spec=["execute", "add_all", "commit"])
        replace_document_images(
            session, document_id=1, images=[{"alt": "x", "url": "https://example.com/1.jpg"}],
        )
        session.commit.assert_not_called()

    def test_chunk_id_passed_through(self):
        session = MagicMock(spec=["execute", "add_all"])
        rows = replace_document_images(
            session, document_id=1, images=[{"alt": "x", "url": "https://example.com/1.jpg"}],
            chunk_id=42,
        )
        assert rows[0].chunk_id == 42
