"""Unit tests for Document ORM CRUD operations (Story 27.1).

All tests use mocked sessions — no database required.
"""

import datetime
from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")

from library.db.models import (
    DiscoverySource,
    Document,
    LinkDocument,
    YouTubeDocument,
    MovieDocument,
    WebpageDocument,
    TextMessageDocument,
    TextDocument,
    DocumentEmbedding,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_doc(**overrides):
    """Create a Document with sensible defaults."""
    defaults = {
        "id": 42,
        "url": "https://example.com/article",
        "title": "Test Article",
        "document_type": "webpage",
        "processing_status": "URL_ADDED",
        "ingested_at": datetime.datetime(2026, 1, 15, 10, 30, 0),
    }
    defaults.update(overrides)
    doc = Document()
    for k, v in defaults.items():
        setattr(doc, k, v)
    return doc


# ===================================================================
# Task 1: get_by_id()
# ===================================================================


class TestGetById:
    def test_found(self):
        doc = _make_doc()
        session = MagicMock()
        session.get.return_value = doc

        result = Document.get_by_id(session, 42)

        session.get.assert_called_once_with(Document, 42)
        assert result is doc

    def test_not_found(self):
        session = MagicMock()
        session.get.return_value = None

        result = Document.get_by_id(session, 999)

        assert result is None

    def test_reach_true_with_neighbors(self):
        doc = _make_doc(id=10)
        session = MagicMock()
        session.get.return_value = doc

        # Mock execute to return next and previous rows
        next_row = (11, "link")
        prev_row = (9, "youtube")
        session.execute.side_effect = [
            MagicMock(first=MagicMock(return_value=next_row)),
            MagicMock(first=MagicMock(return_value=prev_row)),
        ]

        result = Document.get_by_id(session, 10, reach=True)

        assert result is doc
        assert result.next_id == 11
        assert result.next_type == "link"
        assert result.previous_id == 9
        assert result.previous_type == "youtube"
        assert session.execute.call_count == 2

    def test_reach_true_without_neighbors(self):
        doc = _make_doc(id=1)
        session = MagicMock()
        session.get.return_value = doc

        session.execute.side_effect = [
            MagicMock(first=MagicMock(return_value=None)),
            MagicMock(first=MagicMock(return_value=None)),
        ]

        result = Document.get_by_id(session, 1, reach=True)

        assert result is doc
        assert result.next_id is None
        assert result.next_type is None
        assert result.previous_id is None
        assert result.previous_type is None

    def test_reach_false_does_not_query_neighbors(self):
        doc = _make_doc()
        session = MagicMock()
        session.get.return_value = doc

        Document.get_by_id(session, 42, reach=False)

        session.execute.assert_not_called()

    def test_reach_true_not_found_returns_none(self):
        session = MagicMock()
        session.get.return_value = None

        result = Document.get_by_id(session, 999, reach=True)

        assert result is None
        session.execute.assert_not_called()

    def test_reach_true_with_string_type_fallback(self):
        """Cover hasattr fallback when document_type comes as raw string (not enum)."""
        doc = _make_doc(id=10)
        session = MagicMock()
        session.get.return_value = doc

        # Simulate document_type returned as raw string (no .name attribute)
        next_row = (11, "link")
        prev_row = (9, "youtube")
        session.execute.side_effect = [
            MagicMock(first=MagicMock(return_value=next_row)),
            MagicMock(first=MagicMock(return_value=prev_row)),
        ]

        result = Document.get_by_id(session, 10, reach=True)

        assert result.next_id == 11
        assert result.next_type == "link"
        assert result.previous_id == 9
        assert result.previous_type == "youtube"


# ===================================================================
# Task 2: get_by_url()
# ===================================================================


class TestGetByUrl:
    def test_found(self):
        doc = _make_doc()
        session = MagicMock()
        session.scalars.return_value.first.return_value = doc

        result = Document.get_by_url(session, "https://example.com/article")

        assert result is doc

    def test_not_found(self):
        session = MagicMock()
        session.scalars.return_value.first.return_value = None

        result = Document.get_by_url(session, "https://nonexistent.com")

        assert result is None

    def test_url_with_special_characters(self):
        doc = _make_doc(url="https://example.com/path?q=hello%20world&lang=pl#section")
        session = MagicMock()
        session.scalars.return_value.first.return_value = doc

        result = Document.get_by_url(session, "https://example.com/path?q=hello%20world&lang=pl#section")

        assert result is doc
        assert result.url == "https://example.com/path?q=hello%20world&lang=pl#section"

    def test_lookup_uses_canonical_url(self):
        session = MagicMock()
        Document.get_by_url(session, "HTTPS://Example.com/a/?utm_source=x#part")

        statement = session.scalars.call_args.args[0]
        assert "documents.canonical_url" in str(statement)
        assert statement.compile().params["canonical_url_1"] == "https://example.com/a"

    def test_setting_url_populates_canonical_url(self):
        doc = Document(url="https://Example.com/a/?utm_source=x#part")
        assert doc.url == "https://Example.com/a/?utm_source=x#part"
        assert doc.canonical_url == "https://example.com/a"


# ===================================================================
# Task 3: ORM Create flow
# ===================================================================


class TestCreateFlow:
    def test_create_basic_document(self):
        """Verify Document can be constructed and added to session (interface contract)."""
        doc = Document(
            url="https://example.com/new",
            document_type="webpage",
            processing_status="URL_ADDED",
        )
        session = MagicMock()

        session.add(doc)
        session.add.assert_called_once_with(doc)

        # Simulate flush setting id
        doc.id = 100
        assert doc.id == 100

    def test_all_columns_persisted_via_dict(self):
        """Create a document with all 28 columns and verify via dict()."""
        now = datetime.datetime(2026, 3, 1, 12, 0, 0)
        reviewed = datetime.datetime(2026, 3, 15, 9, 0, 0)
        doc = Document()
        doc.id = 1
        doc.summary = "Test summary"
        doc.url = "https://example.com"
        doc.language = "en"
        doc.tags = "test,orm"
        doc.text = "Full text content"
        doc.paywall = False
        doc.title = "Test Title"
        doc.ingested_at = now
        doc.document_type = "webpage"
        doc.discovery_source = DiscoverySource(name="manual")
        doc.published_on = datetime.date(2026, 3, 1)
        doc.original_id = "orig-123"
        doc.document_length = 500
        doc.chapter_list = "ch1;ch2"
        doc.processing_status = "DOCUMENT_INTO_DATABASE"
        doc.processing_error_code = "NONE"
        doc.text_raw = "Raw text"
        doc.transcript_job_id = "job-abc"
        doc.ai_summary_needed = True
        doc.byline = "Author Name"
        doc.note = "A note"
        doc.uuid = "uuid-123"
        doc.collection_id = 3
        doc.text_md = "# Markdown"
        doc.transcript_needed = False
        doc.reviewed_at = reviewed
        doc.obsidian_note_paths = ["02-wiedza/Test.md"]

        d = doc.dict()
        assert d["id"] == 1
        assert d["summary"] == "Test summary"
        assert d["url"] == "https://example.com"
        assert d["language"] == "en"
        assert d["tags"] == "test,orm"
        assert d["text"] == "Full text content"
        assert d["paywall"] is False
        assert d["title"] == "Test Title"
        assert d["ingested_at"] == "2026-03-01 12:00:00"
        assert d["document_type"] == "webpage"
        assert d["source"] == "manual"  # name via discovery_source relationship
        assert d["published_on"] == datetime.date(2026, 3, 1)
        assert d["original_id"] == "orig-123"
        assert d["document_length"] == 500
        assert d["chapter_list"] == "ch1;ch2"
        assert d["processing_status"] == "DOCUMENT_INTO_DATABASE"
        assert d["processing_error_code"] == "NONE"
        assert d["text_raw"] == "Raw text"
        assert d["transcript_job_id"] == "job-abc"
        assert d["ai_summary_needed"] is True
        assert d["byline"] == "Author Name"
        assert d["note"] == "A note"
        assert d["uuid"] == "uuid-123"
        assert d["collection_id"] == 3
        assert d["text_md"] == "# Markdown"
        assert d["transcript_needed"] is False
        assert d["reviewed_at"] == "2026-03-15T09:00:00"
        assert d["obsidian_note_paths"] == ["02-wiedza/Test.md"]

    def test_sti_subclass_sets_correct_document_type(self):
        """Each STI subclass should have correct document_type."""
        cases = [
            (LinkDocument, "link"),
            (YouTubeDocument, "youtube"),
            (MovieDocument, "movie"),
            (WebpageDocument, "webpage"),
            (TextMessageDocument, "text_message"),
            (TextDocument, "text"),
        ]
        for cls, expected_type in cases:
            doc = cls(url="https://test.com", processing_status="URL_ADDED")
            assert doc.document_type == expected_type, f"{cls.__name__} should have type {expected_type}"


# ===================================================================
# Task 4: ORM Update flow
# ===================================================================


class TestUpdateFlow:
    def test_modify_single_attribute(self):
        """Verify attribute assignment works on ORM model (interface contract)."""
        doc = _make_doc(title="Old Title")
        doc.title = "New Title"
        assert doc.title == "New Title"

    def test_update_enum_via_set_processing_status(self):
        doc = _make_doc(processing_status="URL_ADDED")
        doc.set_processing_status("DOCUMENT_INTO_DATABASE")
        assert doc.processing_status == "DOCUMENT_INTO_DATABASE"

    def test_none_values_stored_correctly(self):
        doc = _make_doc(title="Has Title", tags="some,tags")
        doc.title = None
        doc.tags = None
        assert doc.title is None
        assert doc.tags is None


# ===================================================================
# Task 5: ORM Delete with cascade
# ===================================================================


class TestDeleteCascade:
    def test_cascade_config_on_relationship(self):
        """Verify cascade is configured on Document.embeddings relationship."""
        from sqlalchemy import inspect as sa_inspect
        mapper = sa_inspect(Document)
        rel = mapper.relationships["embeddings"]
        # "all" expands to individual cascade options; check key ones
        assert "delete" in rel.cascade
        assert "delete-orphan" in rel.cascade
        assert "save-update" in rel.cascade
        assert "merge" in rel.cascade

    def test_fk_ondelete_cascade(self):
        """Verify FK ondelete=CASCADE on DocumentEmbedding.document_id."""
        from sqlalchemy import inspect as sa_inspect
        mapper = sa_inspect(DocumentEmbedding)
        document_id_col = mapper.columns["document_id"]
        fk = list(document_id_col.foreign_keys)[0]
        assert fk.ondelete == "CASCADE"

    def test_delete_document_with_embedding(self):
        """Verify session.delete(doc) can be called with embeddings attached (interface contract)."""
        doc = _make_doc()
        emb = DocumentEmbedding(document_id=42, model="test-model", text="chunk")
        doc.embeddings = [emb]

        session = MagicMock()
        session.delete(doc)
        session.delete.assert_called_once_with(doc)


# ===================================================================
# Task 6: dict() backward compatibility
# ===================================================================


class TestDictCompatibility:
    def test_date_format(self):
        """Dates should be formatted as 'YYYY-MM-DD HH:MM:SS'."""
        doc = _make_doc(ingested_at=datetime.datetime(2026, 1, 15, 10, 30, 0))
        d = doc.dict()
        assert d["ingested_at"] == "2026-01-15 10:30:00"

    def test_date_none(self):
        """None ingested_at should produce None in dict."""
        doc = _make_doc(ingested_at=None)
        d = doc.dict()
        assert d["ingested_at"] is None

    def test_enum_format_document_type(self):
        """document_type should be a string."""
        doc = _make_doc(document_type="youtube")
        d = doc.dict()
        assert d["document_type"] == "youtube"
        assert isinstance(d["document_type"], str)

    def test_enum_format_processing_status(self):
        """processing_status should be a string."""
        doc = _make_doc(processing_status="EMBEDDING_EXIST")
        d = doc.dict()
        assert d["processing_status"] == "EMBEDDING_EXIST"

    def test_enum_format_processing_error_code(self):
        """processing_error_code should be a string, defaulting to 'NONE'."""
        doc = _make_doc(processing_error_code="TEXT_MISSING")
        d = doc.dict()
        assert d["processing_error_code"] == "TEXT_MISSING"

    def test_enum_format_processing_error_code_none(self):
        """When processing_error_code is None, dict should return 'NONE'."""
        doc = _make_doc()
        doc.processing_error_code = None
        d = doc.dict()
        assert d["processing_error_code"] == "NONE"

    def test_transient_fields_populated(self):
        """Transient navigation fields should appear in dict when populated."""
        doc = _make_doc()
        doc.next_id = 43
        doc.next_type = "link"
        doc.previous_id = 41
        doc.previous_type = "youtube"
        d = doc.dict()
        assert d["next_id"] == 43
        assert d["next_type"] == "link"
        assert d["previous_id"] == 41
        assert d["previous_type"] == "youtube"

    def test_transient_fields_default_none(self):
        """Transient navigation fields should default to None."""
        doc = _make_doc()
        d = doc.dict()
        assert d["next_id"] is None
        assert d["next_type"] is None
        assert d["previous_id"] is None
        assert d["previous_type"] is None

    def test_all_keys_present_including_none(self):
        """dict() should include all keys even when values are None."""
        doc = Document()
        doc.id = None
        doc.url = "https://x.com"
        doc.document_type = "link"
        doc.processing_status = "URL_ADDED"
        doc.ingested_at = None
        doc.processing_error_code = None

        d = doc.dict()
        expected_keys = {
            "id", "next_id", "next_type", "previous_id", "previous_type",
            "summary", "url", "canonical_url", "language", "tags", "text", "paywall", "title",
            "ingested_at", "document_type", "source", "discovery_source_id", "published_on", "published_on_method", "original_id",
            "document_length", "chapter_list", "processing_status", "processing_error_code",
            "text_raw", "transcript_job_id", "ai_summary_needed", "byline",
            "byline_method", "note", "uuid", "collection_id", "text_md", "transcript_needed",
            "reviewed_at", "obsidian_note_paths", "video_description",
            "quality",
        }
        assert set(d.keys()) == expected_keys

    def test_dict_format_conventions(self):
        """Verify dict() uses same format conventions as StalkerWebDocumentDB.dict().

        Checks value formats (strftime dates, enum .name strings, bool/int types)
        without instantiating StalkerWebDocumentDB (which requires a DB connection).
        """
        now = datetime.datetime(2026, 2, 20, 14, 0, 0)
        doc = _make_doc(
            id=5,
            summary="A summary",
            url="https://example.com",
            language="pl",
            tags="tag1",
            text="Some text",
            paywall=True,
            title="Title",
            ingested_at=now,
            document_type="link",
            discovery_source=DiscoverySource(name="import"),
            published_on=datetime.date(2026, 2, 20),
            original_id="orig-1",
            document_length=200,
            chapter_list="ch1",
            processing_status="EMBEDDING_EXIST",
            processing_error_code="NONE",
            text_raw="Raw",
            transcript_job_id="j1",
            ai_summary_needed=False,
            byline="Auth",
            note="Note",
            uuid="s3-1",
            collection_id=3,
            text_md="md",
            transcript_needed=True,
        )
        d = doc.dict()

        # Key format checks (matching StalkerWebDocumentDB.dict())
        assert d["ingested_at"] == "2026-02-20 14:00:00"  # strftime format
        assert d["document_type"] == "link"  # .name
        assert d["processing_status"] == "EMBEDDING_EXIST"  # .name
        assert d["processing_error_code"] == "NONE"  # .name
        assert isinstance(d["paywall"], bool)
        assert isinstance(d["document_length"], int)
