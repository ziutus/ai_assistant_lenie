"""Unit tests for ORM models (WebDocument, WebsiteEmbedding, STI subclasses,
lookup table models).

Tests model structure, column mappings, STI configuration, domain methods,
dict() output, relationships, and lookup table ORM models — all without a
database connection.
"""

import datetime

import pytest

sqlalchemy = pytest.importorskip("sqlalchemy")
from sqlalchemy import inspect, String, Text, Boolean, Integer, Date, DateTime  # noqa: E402

from library.db.engine import Base  # noqa: E402
from library.db.models import (  # noqa: E402
    DocumentStatusType,
    DocumentStatusErrorType,
    DocumentType,
    EmbeddingModel,
    WebDocument,
    WebsiteEmbedding,
    LinkDocument,
    YouTubeDocument,
    MovieDocument,
    WebpageDocument,
    TextMessageDocument,
    TextDocument,
)


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
        "document_type": "link",
        "document_state": "URL_ADDED",
    }
    defaults.update(overrides)
    return WebDocument(**defaults)


# ---------------------------------------------------------------------------
# Lookup table ORM models (B-96 Task 9)
# ---------------------------------------------------------------------------

class TestDocumentStatusType:
    def test_tablename(self):
        assert DocumentStatusType.__tablename__ == "document_status_types"

    def test_inherits_base(self):
        assert issubclass(DocumentStatusType, Base)

    def test_columns(self):
        cols = _column_names(DocumentStatusType)
        assert cols == {"id", "name"}

    def test_instantiation(self):
        obj = DocumentStatusType(name="URL_ADDED")
        assert obj.name == "URL_ADDED"

    def test_repr(self):
        obj = DocumentStatusType(id=1, name="URL_ADDED")
        assert repr(obj) == "DocumentStatusType(id=1, name='URL_ADDED')"

    def test_name_is_unique_not_nullable(self):
        col = _get_column(DocumentStatusType, "name")
        assert col.unique
        assert not col.nullable


class TestDocumentStatusErrorType:
    def test_tablename(self):
        assert DocumentStatusErrorType.__tablename__ == "document_status_error_types"

    def test_inherits_base(self):
        assert issubclass(DocumentStatusErrorType, Base)

    def test_columns(self):
        cols = _column_names(DocumentStatusErrorType)
        assert cols == {"id", "name"}

    def test_instantiation(self):
        obj = DocumentStatusErrorType(name="ERROR_DOWNLOAD")
        assert obj.name == "ERROR_DOWNLOAD"

    def test_repr(self):
        obj = DocumentStatusErrorType(id=2, name="ERROR_DOWNLOAD")
        assert repr(obj) == "DocumentStatusErrorType(id=2, name='ERROR_DOWNLOAD')"


class TestDocumentType:
    def test_tablename(self):
        assert DocumentType.__tablename__ == "document_types"

    def test_inherits_base(self):
        assert issubclass(DocumentType, Base)

    def test_columns(self):
        cols = _column_names(DocumentType)
        assert cols == {"id", "name"}

    def test_instantiation(self):
        obj = DocumentType(name="link")
        assert obj.name == "link"

    def test_repr(self):
        obj = DocumentType(id=3, name="link")
        assert repr(obj) == "DocumentType(id=3, name='link')"


class TestEmbeddingModel:
    def test_tablename(self):
        assert EmbeddingModel.__tablename__ == "embedding_models"

    def test_inherits_base(self):
        assert issubclass(EmbeddingModel, Base)

    def test_columns(self):
        cols = _column_names(EmbeddingModel)
        assert cols == {"id", "name"}

    def test_instantiation(self):
        obj = EmbeddingModel(name="text-embedding-ada-002")
        assert obj.name == "text-embedding-ada-002"

    def test_repr(self):
        obj = EmbeddingModel(id=1, name="text-embedding-ada-002")
        assert repr(obj) == "EmbeddingModel(id=1, name='text-embedding-ada-002')"


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
        "transcript_needed", "reviewed_at", "obsidian_note_paths",
    }

    def test_column_count(self):
        assert len(_column_names(WebDocument)) == 28

    def test_all_column_names(self):
        assert _column_names(WebDocument) == self.EXPECTED_COLUMNS


# ---------------------------------------------------------------------------
# 5.2: Column types match DDL (updated for String+FK)
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

    def test_document_type_is_string_with_fk(self):
        col = _get_column(WebDocument, "document_type")
        assert isinstance(col.type, String)
        assert col.type.length == 50
        assert not col.nullable
        fk = list(col.foreign_keys)[0]
        assert fk.target_fullname == "document_types.name"

    def test_document_state_is_string_with_fk(self):
        col = _get_column(WebDocument, "document_state")
        assert isinstance(col.type, String)
        assert col.type.length == 50
        assert not col.nullable
        fk = list(col.foreign_keys)[0]
        assert fk.target_fullname == "document_status_types.name"

    def test_document_state_error_is_string_with_fk_nullable(self):
        col = _get_column(WebDocument, "document_state_error")
        assert isinstance(col.type, String)
        fk = list(col.foreign_keys)[0]
        assert fk.target_fullname == "document_status_error_types.name"

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
# 5.4: All 6 STI subclasses have correct polymorphic_identity (now strings)
# ---------------------------------------------------------------------------

class TestSTISubclasses:
    @pytest.mark.parametrize("cls, identity", [
        (LinkDocument, "link"),
        (YouTubeDocument, "youtube"),
        (MovieDocument, "movie"),
        (WebpageDocument, "webpage"),
        (TextMessageDocument, "text_message"),
        (TextDocument, "text"),
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
# 5.5: set_document_type() — stores string names
# ---------------------------------------------------------------------------

class TestSetDocumentType:
    @pytest.mark.parametrize("input_str, expected", [
        ("movie", "movie"),
        ("youtube", "youtube"),
        ("link", "link"),
        ("webpage", "webpage"),
        ("website", "webpage"),
        ("sms", "text_message"),
        ("text_message", "text_message"),
        ("text", "text"),
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
# 5.6: set_document_state() — stores string names
# ---------------------------------------------------------------------------

class TestSetDocumentState:
    @pytest.mark.parametrize("input_str, expected", [
        ("ERROR", "ERROR"),
        ("ERROR_DOWNLOAD", "ERROR"),
        ("URL_ADDED", "URL_ADDED"),
        ("NEED_TRANSCRIPTION", "NEED_TRANSCRIPTION"),
        ("TRANSCRIPTION_DONE", "TRANSCRIPTION_DONE"),
        ("TRANSCRIPTION_IN_PROGRESS", "TRANSCRIPTION_IN_PROGRESS"),
        ("NEED_MANUAL_REVIEW", "NEED_MANUAL_REVIEW"),
        ("READY_FOR_TRANSLATION", "READY_FOR_TRANSLATION"),
        ("READY_FOR_EMBEDDING", "READY_FOR_EMBEDDING"),
        ("EMBEDDING_EXIST", "EMBEDDING_EXIST"),
        ("DOCUMENT_INTO_DATABASE", "DOCUMENT_INTO_DATABASE"),
        ("NEED_CLEAN_TEXT", "NEED_CLEAN_TEXT"),
        ("NEED_CLEAN_MD", "NEED_CLEAN_MD"),
        ("TEXT_TO_MD_DONE", "NEED_CLEAN_MD"),
        ("MD_SIMPLIFIED", "MD_SIMPLIFIED"),
        ("TRANSCRIPTION_DONE_AND_SPLIT_BY_CHAPTERS", "TRANSCRIPTION_DONE_AND_SPLIT_BY_CHAPTERS"),
        ("TEMPORARY_ERROR", "TEMPORARY_ERROR"),
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
# 5.6b: set_document_state_error() — stores string names
# ---------------------------------------------------------------------------

class TestSetDocumentStateError:
    @pytest.mark.parametrize("input_str, expected", [
        (None, "NONE"),
        ("NONE", "NONE"),
        ("ERROR_DOWNLOAD", "ERROR_DOWNLOAD"),
        ("LINK_SUMMARY_MISSING", "LINK_SUMMARY_MISSING"),
        ("TITLE_MISSING", "TITLE_MISSING"),
        ("TEXT_MISSING", "TEXT_MISSING"),
        ("TEXT_TRANSLATION_ERROR", "TEXT_TRANSLATION_ERROR"),
        ("TITLE_TRANSLATION_ERROR", "TITLE_TRANSLATION_ERROR"),
        ("SUMMARY_TRANSLATION_ERROR", "SUMMARY_TRANSLATION_ERROR"),
        ("NO_URL_ERROR", "NO_URL_ERROR"),
        ("EMBEDDING_ERROR", "EMBEDDING_ERROR"),
        ("MISSING_TRANSLATION", "MISSING_TRANSLATION"),
        ("TRANSLATION_ERROR", "TRANSLATION_ERROR"),
        ("REGEX_ERROR", "REGEX_ERROR"),
        ("TEXT_TO_MD_ERROR", "TEXT_TO_MD_ERROR"),
        ("NO_CAPTIONS_AVAILABLE", "NO_CAPTIONS_AVAILABLE"),
        ("CAPTIONS_LANGUAGE_MISMATCH", "CAPTIONS_LANGUAGE_MISMATCH"),
        ("CAPTIONS_FETCH_ERROR", "CAPTIONS_FETCH_ERROR"),
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
            document_state="EMBEDDING_EXIST",
            text="some text",
        )
        doc.analyze()
        assert doc.text == "some text"

    def test_text_raw_copied_from_text_when_missing(self):
        doc = _make_doc(
            text="hello world",
            document_type="webpage",
        )
        assert doc.text_raw is None
        doc.analyze()
        assert doc.text_raw == "hello world"

    def test_text_raw_not_overwritten_when_present(self):
        doc = _make_doc(
            text="new text",
            text_raw="original raw",
            document_type="webpage",
        )
        doc.analyze()
        assert doc.text_raw == "original raw"

    def test_link_type_clears_text(self):
        doc = _make_doc(
            text="link description",
            text_raw="raw content",
            document_type="link",
        )
        doc.analyze()
        assert doc.text is None

    def test_non_link_type_keeps_text(self):
        doc = _make_doc(
            text="webpage content",
            text_raw="raw content",
            document_type="webpage",
        )
        doc.analyze()
        assert doc.text == "webpage content"


# ---------------------------------------------------------------------------
# 5.7: validate()
# ---------------------------------------------------------------------------

class TestValidate:
    def test_missing_title_sets_need_manual_review(self):
        doc = _make_doc(title=None, document_type="movie")
        doc.validate()
        assert doc.document_state == "NEED_MANUAL_REVIEW"
        assert doc.document_state_error == "TITLE_MISSING"

    def test_short_title_sets_need_manual_review(self):
        doc = _make_doc(title="ab", document_type="movie")
        doc.validate()
        assert doc.document_state == "NEED_MANUAL_REVIEW"
        assert doc.document_state_error == "TITLE_MISSING"

    def test_valid_title_no_error(self):
        doc = _make_doc(title="Valid title", summary="Valid summary")
        doc.validate()
        assert doc.document_state_error == "NONE"

    def test_link_missing_summary(self):
        doc = _make_doc(
            title="Valid title",
            document_type="link",
            summary=None,
        )
        doc.validate()
        assert doc.document_state_error == "LINK_SUMMARY_MISSING"

    def test_webpage_missing_text(self):
        doc = _make_doc(
            title="Valid title",
            document_type="webpage",
        )
        doc.validate()
        assert doc.document_state_error == "TEXT_MISSING"

    def test_embedding_exist_skips_validation(self):
        doc = _make_doc(
            title=None,
            document_state="EMBEDDING_EXIST",
        )
        doc.validate()
        assert doc.document_state_error == "NONE"
        assert doc.document_state == "EMBEDDING_EXIST"


# ---------------------------------------------------------------------------
# 5.8-5.10: dict()
# ---------------------------------------------------------------------------

class TestDict:
    def test_dict_has_32_keys(self):
        doc = _make_doc(
            title="Test",
            document_state_error="NONE",
        )
        doc.created_at = datetime.datetime(2025, 1, 15, 10, 30, 0)
        result = doc.dict()
        assert len(result) == 32

    def test_dict_keys(self):
        doc = _make_doc(
            title="Test",
            document_state_error="NONE",
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
            "reviewed_at", "obsidian_note_paths",
        }
        assert set(result.keys()) == expected_keys

    def test_dict_formats_created_at(self):
        doc = _make_doc(
            document_state_error="NONE",
        )
        doc.created_at = datetime.datetime(2025, 1, 15, 10, 30, 0)
        result = doc.dict()
        assert result["created_at"] == "2025-01-15 10:30:00"

    def test_dict_created_at_none(self):
        doc = _make_doc(
            document_state_error="NONE",
        )
        doc.created_at = None
        result = doc.dict()
        assert result["created_at"] is None

    def test_dict_string_values(self):
        doc = _make_doc(
            document_state_error="NONE",
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
            document_state_error="NONE",
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
# 5.12: WebsiteEmbedding FK targets
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

    def test_model_fk_target(self):
        col = _get_column(WebsiteEmbedding, "model")
        fk = list(col.foreign_keys)[0]
        assert fk.target_fullname == "embedding_models.name"


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
# Lookup relationship declarations (B-96 Task 9)
# ---------------------------------------------------------------------------

class TestLookupRelationships:
    def test_document_type_ref_exists(self):
        mapper = inspect(WebDocument).mapper
        assert "document_type_ref" in mapper.relationships

    def test_document_state_ref_exists(self):
        mapper = inspect(WebDocument).mapper
        assert "document_state_ref" in mapper.relationships

    def test_document_state_error_ref_exists(self):
        mapper = inspect(WebDocument).mapper
        assert "document_state_error_ref" in mapper.relationships

    def test_model_ref_exists_on_embedding(self):
        mapper = inspect(WebsiteEmbedding).mapper
        assert "model_ref" in mapper.relationships

    def test_document_type_ref_target(self):
        mapper = inspect(WebDocument).mapper
        rel = mapper.relationships["document_type_ref"]
        assert rel.mapper.class_ is DocumentType

    def test_document_state_ref_target(self):
        mapper = inspect(WebDocument).mapper
        rel = mapper.relationships["document_state_ref"]
        assert rel.mapper.class_ is DocumentStatusType

    def test_document_state_error_ref_target(self):
        mapper = inspect(WebDocument).mapper
        rel = mapper.relationships["document_state_error_ref"]
        assert rel.mapper.class_ is DocumentStatusErrorType

    def test_model_ref_target(self):
        mapper = inspect(WebsiteEmbedding).mapper
        rel = mapper.relationships["model_ref"]
        assert rel.mapper.class_ is EmbeddingModel


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
# 5.15: Fields store strings (not enums)
# ---------------------------------------------------------------------------

class TestFieldsAreStrings:
    def test_document_type_is_string(self):
        doc = _make_doc()
        assert isinstance(doc.document_type, str)

    def test_document_state_is_string(self):
        doc = _make_doc()
        assert isinstance(doc.document_state, str)

    def test_document_state_error_is_string_when_set(self):
        doc = _make_doc(document_state_error="NONE")
        assert isinstance(doc.document_state_error, str)


# ---------------------------------------------------------------------------
# 5.16: Base is imported from library.db.engine
# ---------------------------------------------------------------------------

class TestBaseImport:
    def test_web_document_uses_engine_base(self):
        assert issubclass(WebDocument, Base)

    def test_website_embedding_uses_engine_base(self):
        assert issubclass(WebsiteEmbedding, Base)
