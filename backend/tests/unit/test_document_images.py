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
from library.document_images import (  # noqa: E402
    image_marker_present,
    prune_images_removed_from_text,
    replace_document_images,
    replace_storage_images,
)


# ---------------------------------------------------------------------------
# ORM model
# ---------------------------------------------------------------------------


class TestDocumentImageModel:
    EXPECTED_COLUMNS = {
        "id", "document_id", "chunk_id", "position", "url", "storage_key",
        "page_number", "chapter_position", "alt_text",
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

    def test_url_nullable(self):
        assert inspect(DocumentImage).mapper.columns["url"].nullable is True

    def test_storage_key_nullable(self):
        assert inspect(DocumentImage).mapper.columns["storage_key"].nullable is True


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
        delete_stmt = session.execute.call_args[0][0]
        assert delete_stmt.is_delete

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

    def test_preserves_explicit_marker_position(self):
        session = MagicMock(spec=["execute", "add_all"])
        rows = replace_document_images(
            session, document_id=1,
            images=[{"position": 7, "alt": "wykres", "url": "https://example.com/chart.png"}],
        )
        assert rows[0].position == 7

    def test_only_deletes_url_sourced_rows(self):
        """A web-article reclean must never touch a book's storage_key-only rows."""
        session = MagicMock(spec=["execute", "add_all"])
        replace_document_images(session, document_id=9332, images=[])
        delete_stmt = session.execute.call_args[0][0]
        assert "url is not null" in str(delete_stmt.whereclause).lower()

    def test_downloaded_copy_is_carried_over_to_row_with_same_url(self):
        session = MagicMock(spec=["execute", "add_all"])
        session.execute.return_value.all.return_value = [
            ("https://example.com/1.jpg", "documents/5/web_images/11.jpg"),
        ]
        rows = replace_document_images(
            session, document_id=5,
            images=[
                {"alt": "a", "url": "https://example.com/1.jpg"},
                {"alt": "b", "url": "https://example.com/2.jpg"},
            ],
        )
        assert rows[0].storage_key == "documents/5/web_images/11.jpg"
        assert rows[1].storage_key is None


# ---------------------------------------------------------------------------
# replace_storage_images
# ---------------------------------------------------------------------------


class TestReplaceStorageImages:
    def _added_rows(self, session):
        calls = session.add_all.call_args_list
        assert len(calls) == 1
        return list(calls[0].args[0])

    def test_builds_one_row_per_image(self):
        session = MagicMock(spec=["execute", "add_all"])
        images = [
            {"storage_key": "documents/uuid/images/1.png", "position": 3, "page_number": 12,
             "chapter_position": 2, "caption_text": "Rysunek 1. Schemat"},
            {"storage_key": "documents/uuid/images/2.png", "page_number": 15, "chapter_position": 2},
        ]

        rows = replace_storage_images(session, document_id=9332, images=images)

        assert len(rows) == 2
        stored = self._added_rows(session)
        assert stored == rows
        assert [r.storage_key for r in stored] == [
            "documents/uuid/images/1.png", "documents/uuid/images/2.png",
        ]
        assert stored[0].position == 3
        assert stored[1].position is None
        assert [r.document_id for r in stored] == [9332, 9332]
        assert stored[0].caption_text == "Rysunek 1. Schemat"

    def test_skips_images_without_storage_key(self):
        session = MagicMock(spec=["execute", "add_all"])
        images = [{"storage_key": None, "page_number": 1}, {"storage_key": "documents/uuid/images/1.png"}]

        rows = replace_storage_images(session, document_id=1, images=images)

        assert len(rows) == 1
        assert rows[0].storage_key == "documents/uuid/images/1.png"

    def test_empty_images_list_does_not_call_add_all(self):
        session = MagicMock(spec=["execute", "add_all"])
        rows = replace_storage_images(session, document_id=1, images=[])

        assert rows == []
        session.add_all.assert_not_called()

    def test_does_not_commit(self):
        session = MagicMock(spec=["execute", "add_all", "commit"])
        replace_storage_images(
            session, document_id=1, images=[{"storage_key": "documents/uuid/images/1.png"}],
        )
        session.commit.assert_not_called()

    def test_only_deletes_storage_key_sourced_rows(self):
        """A book's PDF re-extraction must never touch a web article's url rows."""
        session = MagicMock(spec=["execute", "add_all"])
        replace_storage_images(session, document_id=9332, images=[])
        delete_stmt = session.execute.call_args[0][0]
        where = str(delete_stmt.whereclause).lower()
        assert "storage_key is not null" in where
        assert "url is null" in where


# ---------------------------------------------------------------------------
# image_marker_present / prune_images_removed_from_text
# ---------------------------------------------------------------------------


class TestImageMarkerPresent:
    @pytest.mark.parametrize("text,position,expected", [
        ("tekst [img3] dalej", 3, True),
        ("tekst [img3: podpis zdjęcia] dalej", 3, True),
        ("tekst [img30] dalej", 3, False),
        ("[img3]", 30, False),
        ("brak markera", 0, False),
        ("", 0, False),
        (None, 0, False),
    ])
    def test_marker_detection(self, text, position, expected):
        assert image_marker_present(text, position) is expected


class TestPruneImagesRemovedFromText:
    @staticmethod
    def _session(rows):
        session = MagicMock(spec=["execute", "delete"])
        session.execute.return_value.scalars.return_value.all.return_value = rows
        return session

    @staticmethod
    def _row(position, storage_key=None):
        return DocumentImage(
            document_id=1, position=position, url=f"https://example.com/{position}.jpg",
            storage_key=storage_key,
        )

    def test_deletes_only_images_whose_marker_was_removed(self):
        rows = [self._row(0), self._row(1)]
        session = self._session(rows)

        removed = prune_images_removed_from_text(
            session, 1, "a [img0: x]\n[img1]\nb", "a [img0: x]\nb",
        )

        assert removed == 1
        session.delete.assert_called_once_with(rows[1])

    def test_image_without_marker_in_old_text_is_kept(self):
        """An image that never had a marker in the text is not the user's deletion."""
        rows = [self._row(2)]
        session = self._session(rows)

        removed = prune_images_removed_from_text(session, 1, "tekst bez markerów", "inny tekst")

        assert removed == 0
        session.delete.assert_not_called()

    def test_deletes_stored_copy_of_removed_image(self):
        rows = [self._row(0, storage_key="documents/1/web_images/5.jpg")]
        session = self._session(rows)
        storage = MagicMock()

        prune_images_removed_from_text(session, 1, "[img0]", "", get_storage=lambda: storage)

        storage.delete.assert_called_once_with("documents/1/web_images/5.jpg")
        session.delete.assert_called_once_with(rows[0])

    def test_storage_failure_does_not_block_row_deletion(self):
        rows = [self._row(0, storage_key="documents/1/web_images/5.jpg")]
        session = self._session(rows)
        storage = MagicMock()
        storage.delete.side_effect = RuntimeError("minio down")

        removed = prune_images_removed_from_text(session, 1, "[img0]", "", get_storage=lambda: storage)

        assert removed == 1
        session.delete.assert_called_once_with(rows[0])

    def test_storage_not_built_when_nothing_stored(self):
        rows = [self._row(0)]
        session = self._session(rows)
        get_storage = MagicMock()

        prune_images_removed_from_text(session, 1, "[img0]", "", get_storage=get_storage)

        get_storage.assert_not_called()
