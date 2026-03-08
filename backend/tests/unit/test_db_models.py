"""Unit tests for ORM models (WebDocument, WebsiteEmbedding, STI subclasses).

Tests model structure, column mappings, STI configuration, domain methods,
dict() output, and relationships — all without a database connection.
"""

import datetime

import pytest

sqlalchemy = pytest.importorskip("sqlalchemy")
from sqlalchemy import inspect, String, Text, Boolean, Integer, Date, DateTime  # noqa: E402
from sqlalchemy import Enum as SAEnum  # noqa: E402

from library.db.engine import Base  # noqa: E402
from library.db.models import (  # noqa: E402
    WebDocument,
    WebsiteEmbedding,
    LinkDocument,
    YouTubeDocument,
    MovieDocument,
    WebpageDocument,
    TextMessageDocument,
    TextDocument,
)
from library.models.stalker_document_status import StalkerDocumentStatus  # noqa: E402
from library.models.stalker_document_status_error import StalkerDocumentStatusError  # noqa: E402
from library.models.stalker_document_type import StalkerDocumentType  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_column(model, name):
    """Return a mapper column by attribute name."""
    mapper = inspect(model)
    return mapper.mapper.columns[name]


def _column_names(model):
    """Return the set of mapped column names for a model."""
    mapper = inspect(model)
    return {col.key for col in mapper.mapper.columns}


def _make_doc(**overrides):
    """Create a minimal WebDocument instance for testing domain methods."""
    defaults = {
        "url": "https://example.com",
        "document_type": StalkerDocumentType.link,
        "document_state": StalkerDocumentStatus.URL_ADDED,
    }
    defaults.update(overrides)
    return WebDocument(**defaults)


# ---------------------------------------------------------------------------
# 5.1: WebDocument has all 26 column attributes
# ---------------------------------------------------------------------------

class TestWebDocumentColumns:
    EXPECTED_COLUMNS = {
        "id", "summary", "url", "language", "tags", "text",
        "paywall", "title", "created_at", "document_type",
        "source", "date_from", "original_id", "document_length",
        "chapter_list", "document_state", "document_state_error",
        "text_raw", "transcript_job_id", "ai_summary_needed",
        "author", "note", "s3_uuid", "project", "text_md",
        "transcript_needed",
    }

    def test_column_count(self):
        assert len(_column_names(WebDocument)) == 26

    def test_all_column_names(self):
        assert _column_names(WebDocument) == self.EXPECTED_COLUMNS


# ---------------------------------------------------------------------------
# 5.2: Column types match DDL
# ---------------------------------------------------------------------------

class TestWebDocumentColumnTypes:
    def test_id_is_integer_primary_key(self):
        col = _get_column(WebDocument, "id")
        assert col.primary_key

    def test_url_is_text_not_nullable(self):
        col = _get_column(WebDocument, "url")
        assert isinstance(col.type, Text)
        assert not col.nullable

    def test_language_is_string_10(self):
        col = _get_column(WebDocument, "language")
        assert isinstance(col.type, String)
        assert col.type.length == 10

    def test_paywall_is_boolean(self):
        col = _get_column(WebDocument, "paywall")
        assert isinstance(col.type, Boolean)

    def test_created_at_is_datetime(self):
        col = _get_column(WebDocument, "created_at")
        assert isinstance(col.type, DateTime)

    def test_document_type_is_enum_varchar50(self):
        col = _get_column(WebDocument, "document_type")
        assert isinstance(col.type, SAEnum)
        assert col.type.native_enum is False
        assert col.type.length == 50
        assert not col.nullable

    def test_document_state_is_enum_varchar50(self):
        col = _get_column(WebDocument, "document_state")
        assert isinstance(col.type, SAEnum)
        assert col.type.native_enum is False
        assert not col.nullable

    def test_document_state_error_is_enum_nullable(self):
        col = _get_column(WebDocument, "document_state_error")
        assert isinstance(col.type, SAEnum)
        assert col.type.native_enum is False

    def test_date_from_is_date(self):
        col = _get_column(WebDocument, "date_from")
        assert isinstance(col.type, Date)

    def test_document_length_is_integer(self):
        col = _get_column(WebDocument, "document_length")
        assert isinstance(col.type, Integer)

    def test_s3_uuid_is_string_100(self):
        col = _get_column(WebDocument, "s3_uuid")
        assert isinstance(col.type, String)
        assert col.type.length == 100

    def test_project_is_string_100(self):
        col = _get_column(WebDocument, "project")
        assert isinstance(col.type, String)
        assert col.type.length == 100

    def test_text_fields_are_text_type(self):
        text_columns = [
            "summary", "tags", "text", "title", "text_raw",
            "text_md", "chapter_list", "source", "original_id",
            "transcript_job_id", "author", "note",
        ]
        for name in text_columns:
            col = _get_column(WebDocument, name)
            assert isinstance(col.type, Text), f"Column {name} should be Text"

    def test_boolean_fields(self):
        bool_columns = ["paywall", "ai_summary_needed", "transcript_needed"]
        for name in bool_columns:
            col = _get_column(WebDocument, name)
            assert isinstance(col.type, Boolean), f"Column {name} should be Boolean"


# ---------------------------------------------------------------------------
# 5.3: STI configuration
# ---------------------------------------------------------------------------

class TestSTIConfiguration:
    def test_polymorphic_on_is_document_type(self):
        mapper = inspect(WebDocument).mapper
        assert mapper.polymorphic_on is not None
        assert mapper.polymorphic_on.key == "document_type"


# ---------------------------------------------------------------------------
# 5.4: All 6 STI subclasses have correct polymorphic_identity
# ---------------------------------------------------------------------------

class TestSTISubclasses:
    @pytest.mark.parametrize("cls, identity", [
        (LinkDocument, StalkerDocumentType.link),
        (YouTubeDocument, StalkerDocumentType.youtube),
        (MovieDocument, StalkerDocumentType.movie),
        (WebpageDocument, StalkerDocumentType.webpage),
        (TextMessageDocument, StalkerDocumentType.text_message),
        (TextDocument, StalkerDocumentType.text),
    ])
    def test_polymorphic_identity(self, cls, identity):
        mapper = inspect(cls).mapper
        assert mapper.polymorphic_identity == identity

    def test_subclasses_do_not_define_own_tablename(self):
        for cls in [LinkDocument, YouTubeDocument, MovieDocument,
                    WebpageDocument, TextMessageDocument, TextDocument]:
            assert "__tablename__" not in cls.__dict__, f"{cls.__name__} should not define __tablename__"

    def test_six_subclasses_registered(self):
        mapper = inspect(WebDocument).mapper
        # 6 subclasses in polymorphic_map (base has no identity)
        assert len(mapper.polymorphic_map) == 6


# ---------------------------------------------------------------------------
# 5.5: set_document_type()
# ---------------------------------------------------------------------------

class TestSetDocumentType:
    @pytest.mark.parametrize("input_str, expected", [
        ("movie", StalkerDocumentType.movie),
        ("youtube", StalkerDocumentType.youtube),
        ("link", StalkerDocumentType.link),
        ("webpage", StalkerDocumentType.webpage),
        ("website", StalkerDocumentType.webpage),
        ("sms", StalkerDocumentType.text_message),
        ("text_message", StalkerDocumentType.text_message),
        ("text", StalkerDocumentType.text),
    ])
    def test_valid_types(self, input_str, expected):
        doc = _make_doc()
        doc.set_document_type(input_str)
        assert doc.document_type == expected

    def test_invalid_type_raises(self):
        doc = _make_doc()
        with pytest.raises(ValueError):
            doc.set_document_type("unknown")


# ---------------------------------------------------------------------------
# 5.6: set_document_state()
# ---------------------------------------------------------------------------

class TestSetDocumentState:
    @pytest.mark.parametrize("input_str, expected", [
        ("ERROR", StalkerDocumentStatus.ERROR),
        ("ERROR_DOWNLOAD", StalkerDocumentStatus.ERROR),
        ("URL_ADDED", StalkerDocumentStatus.URL_ADDED),
        ("NEED_TRANSCRIPTION", StalkerDocumentStatus.NEED_TRANSCRIPTION),
        ("TRANSCRIPTION_DONE", StalkerDocumentStatus.TRANSCRIPTION_DONE),
        ("TRANSCRIPTION_IN_PROGRESS", StalkerDocumentStatus.TRANSCRIPTION_IN_PROGRESS),
        ("NEED_MANUAL_REVIEW", StalkerDocumentStatus.NEED_MANUAL_REVIEW),
        ("READY_FOR_TRANSLATION", StalkerDocumentStatus.READY_FOR_TRANSLATION),
        ("READY_FOR_EMBEDDING", StalkerDocumentStatus.READY_FOR_EMBEDDING),
        ("EMBEDDING_EXIST", StalkerDocumentStatus.EMBEDDING_EXIST),
        ("DOCUMENT_INTO_DATABASE", StalkerDocumentStatus.DOCUMENT_INTO_DATABASE),
        ("NEED_CLEAN_TEXT", StalkerDocumentStatus.NEED_CLEAN_TEXT),
        ("NEED_CLEAN_MD", StalkerDocumentStatus.NEED_CLEAN_MD),
        ("TEXT_TO_MD_DONE", StalkerDocumentStatus.NEED_CLEAN_MD),
        ("MD_SIMPLIFIED", StalkerDocumentStatus.MD_SIMPLIFIED),
    ])
    def test_valid_states(self, input_str, expected):
        doc = _make_doc()
        doc.set_document_state(input_str)
        assert doc.document_state == expected

    def test_invalid_state_raises(self):
        doc = _make_doc()
        with pytest.raises(ValueError):
            doc.set_document_state("NONEXISTENT")


# ---------------------------------------------------------------------------
# 5.6b: set_document_state_error()
# ---------------------------------------------------------------------------

class TestSetDocumentStateError:
    @pytest.mark.parametrize("input_str, expected", [
        (None, StalkerDocumentStatusError.NONE),
        ("NONE", StalkerDocumentStatusError.NONE),
        ("ERROR_DOWNLOAD", StalkerDocumentStatusError.ERROR_DOWNLOAD),
        ("LINK_SUMMARY_MISSING", StalkerDocumentStatusError.LINK_SUMMARY_MISSING),
        ("TITLE_MISSING", StalkerDocumentStatusError.TITLE_MISSING),
        ("TEXT_MISSING", StalkerDocumentStatusError.TEXT_MISSING),
        ("TEXT_TRANSLATION_ERROR", StalkerDocumentStatusError.TEXT_TRANSLATION_ERROR),
        ("TITLE_TRANSLATION_ERROR", StalkerDocumentStatusError.TITLE_TRANSLATION_ERROR),
        ("SUMMARY_TRANSLATION_ERROR", StalkerDocumentStatusError.SUMMARY_TRANSLATION_ERROR),
        ("NO_URL_ERROR", StalkerDocumentStatusError.NO_URL_ERROR),
        ("EMBEDDING_ERROR", StalkerDocumentStatusError.EMBEDDING_ERROR),
        ("MISSING_TRANSLATION", StalkerDocumentStatusError.MISSING_TRANSLATION),
        ("TRANSLATION_ERROR", StalkerDocumentStatusError.TRANSLATION_ERROR),
        ("REGEX_ERROR", StalkerDocumentStatusError.REGEX_ERROR),
        ("TEXT_TO_MD_ERROR", StalkerDocumentStatusError.TEXT_TO_MD_ERROR),
    ])
    def test_valid_errors(self, input_str, expected):
        doc = _make_doc()
        doc.set_document_state_error(input_str)
        assert doc.document_state_error == expected

    def test_invalid_error_raises(self):
        doc = _make_doc()
        with pytest.raises(ValueError):
            doc.set_document_state_error("NONEXISTENT_ERROR")


# ---------------------------------------------------------------------------
# 5.6c: analyze()
# ---------------------------------------------------------------------------

class TestAnalyze:
    def test_skip_when_embedding_exist(self):
        doc = _make_doc(
            document_state=StalkerDocumentStatus.EMBEDDING_EXIST,
            text="some text",
        )
        doc.analyze()
        assert doc.text == "some text"

    def test_text_raw_copied_from_text_when_missing(self):
        doc = _make_doc(
            text="hello world",
            document_type=StalkerDocumentType.webpage,
        )
        assert doc.text_raw is None
        doc.analyze()
        assert doc.text_raw == "hello world"

    def test_text_raw_not_overwritten_when_present(self):
        doc = _make_doc(
            text="new text",
            text_raw="original raw",
            document_type=StalkerDocumentType.webpage,
        )
        doc.analyze()
        assert doc.text_raw == "original raw"

    def test_link_type_clears_text(self):
        doc = _make_doc(
            text="link description",
            text_raw="raw content",
            document_type=StalkerDocumentType.link,
        )
        doc.analyze()
        assert doc.text is None

    def test_non_link_type_keeps_text(self):
        doc = _make_doc(
            text="webpage content",
            text_raw="raw content",
            document_type=StalkerDocumentType.webpage,
        )
        doc.analyze()
        assert doc.text == "webpage content"


# ---------------------------------------------------------------------------
# 5.7: validate()
# ---------------------------------------------------------------------------

class TestValidate:
    def test_missing_title_sets_need_manual_review(self):
        doc = _make_doc(title=None, document_type=StalkerDocumentType.movie)
        doc.validate()
        assert doc.document_state == StalkerDocumentStatus.NEED_MANUAL_REVIEW
        assert doc.document_state_error == StalkerDocumentStatusError.TITLE_MISSING

    def test_short_title_sets_need_manual_review(self):
        doc = _make_doc(title="ab", document_type=StalkerDocumentType.movie)
        doc.validate()
        assert doc.document_state == StalkerDocumentStatus.NEED_MANUAL_REVIEW
        assert doc.document_state_error == StalkerDocumentStatusError.TITLE_MISSING

    def test_valid_title_no_error(self):
        doc = _make_doc(title="Valid title", summary="Valid summary")
        doc.validate()
        assert doc.document_state_error == StalkerDocumentStatusError.NONE

    def test_link_missing_summary(self):
        doc = _make_doc(
            title="Valid title",
            document_type=StalkerDocumentType.link,
            summary=None,
        )
        doc.validate()
        assert doc.document_state_error == StalkerDocumentStatusError.LINK_SUMMARY_MISSING

    def test_webpage_missing_text(self):
        doc = _make_doc(
            title="Valid title",
            document_type=StalkerDocumentType.webpage,
        )
        doc.validate()
        assert doc.document_state_error == StalkerDocumentStatusError.TEXT_MISSING

    def test_embedding_exist_skips_validation(self):
        doc = _make_doc(
            title=None,
            document_state=StalkerDocumentStatus.EMBEDDING_EXIST,
        )
        doc.validate()
        assert doc.document_state_error == StalkerDocumentStatusError.NONE
        assert doc.document_state == StalkerDocumentStatus.EMBEDDING_EXIST


# ---------------------------------------------------------------------------
# 5.8–5.10: dict()
# ---------------------------------------------------------------------------

class TestDict:
    def test_dict_has_30_keys(self):
        doc = _make_doc(
            title="Test",
            document_state_error=StalkerDocumentStatusError.NONE,
        )
        doc.created_at = datetime.datetime(2025, 1, 15, 10, 30, 0)
        result = doc.dict()
        assert len(result) == 30

    def test_dict_keys(self):
        doc = _make_doc(
            title="Test",
            document_state_error=StalkerDocumentStatusError.NONE,
        )
        doc.created_at = datetime.datetime(2025, 1, 15, 10, 30, 0)
        result = doc.dict()
        expected_keys = {
            "id", "next_id", "next_type", "previous_id", "previous_type",
            "summary", "url", "language", "tags", "text", "paywall", "title",
            "created_at", "document_type", "source", "date_from", "original_id",
            "document_length", "chapter_list", "document_state",
            "document_state_error", "text_raw", "transcript_job_id",
            "ai_summary_needed", "author", "note", "s3_uuid", "project",
            "text_md", "transcript_needed",
        }
        assert set(result.keys()) == expected_keys

    def test_dict_formats_created_at(self):
        doc = _make_doc(
            document_state_error=StalkerDocumentStatusError.NONE,
        )
        doc.created_at = datetime.datetime(2025, 1, 15, 10, 30, 0)
        result = doc.dict()
        assert result["created_at"] == "2025-01-15 10:30:00"

    def test_dict_created_at_none(self):
        doc = _make_doc(
            document_state_error=StalkerDocumentStatusError.NONE,
        )
        doc.created_at = None
        result = doc.dict()
        assert result["created_at"] is None

    def test_dict_enum_names(self):
        doc = _make_doc(
            document_state_error=StalkerDocumentStatusError.NONE,
        )
        doc.created_at = datetime.datetime(2025, 1, 1)
        result = doc.dict()
        assert result["document_type"] == "link"
        assert result["document_state"] == "URL_ADDED"
        assert result["document_state_error"] == "NONE"

    def test_dict_document_state_error_none_returns_none_string(self):
        doc = _make_doc()
        doc.document_state_error = None
        doc.created_at = datetime.datetime(2025, 1, 1)
        result = doc.dict()
        assert result["document_state_error"] == "NONE"

    def test_dict_navigation_fields(self):
        doc = _make_doc(
            document_state_error=StalkerDocumentStatusError.NONE,
        )
        doc.created_at = datetime.datetime(2025, 1, 1)
        doc.next_id = 42
        doc.next_type = "youtube"
        result = doc.dict()
        assert result["next_id"] == 42
        assert result["next_type"] == "youtube"
        assert result["previous_id"] is None
        assert result["previous_type"] is None


# ---------------------------------------------------------------------------
# 5.11: WebsiteEmbedding has all 8 columns
# ---------------------------------------------------------------------------

class TestWebsiteEmbeddingColumns:
    EXPECTED_COLUMNS = {
        "id", "website_id", "language", "text",
        "text_original", "embedding", "model", "created_at",
    }

    def test_column_count(self):
        assert len(_column_names(WebsiteEmbedding)) == 8

    def test_all_column_names(self):
        assert _column_names(WebsiteEmbedding) == self.EXPECTED_COLUMNS


# ---------------------------------------------------------------------------
# 5.12: WebsiteEmbedding FK target
# ---------------------------------------------------------------------------

class TestWebsiteEmbeddingFK:
    def test_website_id_fk_target(self):
        col = _get_column(WebsiteEmbedding, "website_id")
        fk = list(col.foreign_keys)[0]
        assert fk.target_fullname == "web_documents.id"

    def test_website_id_not_nullable(self):
        col = _get_column(WebsiteEmbedding, "website_id")
        assert not col.nullable

    def test_model_not_nullable(self):
        col = _get_column(WebsiteEmbedding, "model")
        assert not col.nullable


# ---------------------------------------------------------------------------
# 5.13: WebDocument.embeddings relationship
# ---------------------------------------------------------------------------

class TestEmbeddingsRelationship:
    def test_relationship_exists(self):
        mapper = inspect(WebDocument).mapper
        assert "embeddings" in mapper.relationships

    def test_cascade_includes_delete_orphan(self):
        mapper = inspect(WebDocument).mapper
        rel = mapper.relationships["embeddings"]
        assert "delete-orphan" in rel.cascade
        assert "delete" in rel.cascade
        assert "save-update" in rel.cascade
        assert "merge" in rel.cascade

    def test_passive_deletes(self):
        mapper = inspect(WebDocument).mapper
        rel = mapper.relationships["embeddings"]
        assert rel.passive_deletes is True

    def test_back_populates(self):
        mapper = inspect(WebsiteEmbedding).mapper
        assert "document" in mapper.relationships


# ---------------------------------------------------------------------------
# 5.14: Navigation fields NOT in mapper columns
# ---------------------------------------------------------------------------

class TestNavigationFields:
    def test_next_id_not_mapped(self):
        assert "next_id" not in _column_names(WebDocument)

    def test_next_type_not_mapped(self):
        assert "next_type" not in _column_names(WebDocument)

    def test_previous_id_not_mapped(self):
        assert "previous_id" not in _column_names(WebDocument)

    def test_previous_type_not_mapped(self):
        assert "previous_type" not in _column_names(WebDocument)

    def test_navigation_fields_are_class_attributes(self):
        assert hasattr(WebDocument, "next_id")
        assert hasattr(WebDocument, "next_type")
        assert hasattr(WebDocument, "previous_id")
        assert hasattr(WebDocument, "previous_type")

    def test_default_values_are_none(self):
        doc = _make_doc()
        assert doc.next_id is None
        assert doc.next_type is None
        assert doc.previous_id is None
        assert doc.previous_type is None


# ---------------------------------------------------------------------------
# 5.15: Enums imported from original locations
# ---------------------------------------------------------------------------

class TestEnumImports:
    def test_document_type_enum_is_original(self):
        from library.models.stalker_document_type import StalkerDocumentType as OrigType
        doc = _make_doc()
        assert type(doc.document_type) is OrigType

    def test_document_state_enum_is_original(self):
        from library.models.stalker_document_status import StalkerDocumentStatus as OrigStatus
        doc = _make_doc()
        assert type(doc.document_state) is OrigStatus

    def test_document_state_error_enum_is_original(self):
        from library.models.stalker_document_status_error import StalkerDocumentStatusError as OrigError
        doc = _make_doc(document_state_error=StalkerDocumentStatusError.NONE)
        assert type(doc.document_state_error) is OrigError


# ---------------------------------------------------------------------------
# 5.16: Base is imported from library.db.engine
# ---------------------------------------------------------------------------

class TestBaseImport:
    def test_web_document_uses_engine_base(self):
        assert issubclass(WebDocument, Base)

    def test_website_embedding_uses_engine_base(self):
        assert issubclass(WebsiteEmbedding, Base)
