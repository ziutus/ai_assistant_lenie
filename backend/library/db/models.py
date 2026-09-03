"""SQLAlchemy ORM models for documents and document_embeddings tables.

Provides:
- Lookup models: ``DocumentStatusType``, ``DocumentStatusErrorType``,
  ``DocumentType``, ``EmbeddingModel``
- ``Document`` — Single Table Inheritance model for documents
- 6 STI subclasses: LinkDocument, YouTubeDocument, MovieDocument, etc.
- ``DocumentEmbedding`` — model for document_embeddings with pgvector support
"""

import datetime
import decimal
import logging

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    select,
    text as sa_text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship, validates
from sqlalchemy.types import UserDefinedType

from library.publisher_domain import normalize_publisher_domain, registrable_domain
from library.url_normalization import canonicalize_url

from pgvector.sqlalchemy import Vector

from library.db.engine import Base
from library.models.stalker_document_status import StalkerDocumentStatus
from library.models.stalker_document_status_error import StalkerDocumentStatusError
from library.models.stalker_document_type import StalkerDocumentType

logger = logging.getLogger(__name__)


class GeographyPoint(UserDefinedType):
    """PostGIS WGS84 point, kept small to avoid a GeoAlchemy dependency."""

    cache_ok = True

    def get_col_spec(self, **_kw):
        return "GEOGRAPHY(POINT,4326)"


DOCUMENT_TYPE_LOOKUP = {
    "movie": StalkerDocumentType.movie.name,
    "youtube": StalkerDocumentType.youtube.name,
    "link": StalkerDocumentType.link.name,
    "webpage": StalkerDocumentType.webpage.name,
    "website": StalkerDocumentType.webpage.name,
    "sms": StalkerDocumentType.text_message.name,
    "text_message": StalkerDocumentType.text_message.name,
    "text": StalkerDocumentType.text.name,
    "email": StalkerDocumentType.email.name,
    "social_media_post": StalkerDocumentType.social_media_post.name,
    "social": StalkerDocumentType.social_media_post.name,
    "obsidian_note": StalkerDocumentType.obsidian_note.name,
}

PROCESSING_STATUS_LOOKUP = {
    "ERROR_DOWNLOAD": StalkerDocumentStatus.ERROR.name,
    "ERROR": StalkerDocumentStatus.ERROR.name,
    "URL_ADDED": StalkerDocumentStatus.URL_ADDED.name,
    "NEED_TRANSCRIPTION": StalkerDocumentStatus.NEED_TRANSCRIPTION.name,
    "TRANSCRIPTION_DONE": StalkerDocumentStatus.TRANSCRIPTION_DONE.name,
    "TRANSCRIPTION_IN_PROGRESS": StalkerDocumentStatus.TRANSCRIPTION_IN_PROGRESS.name,
    "NEED_MANUAL_REVIEW": StalkerDocumentStatus.NEED_MANUAL_REVIEW.name,
    "READY_FOR_EMBEDDING": StalkerDocumentStatus.READY_FOR_EMBEDDING.name,
    "EMBEDDING_EXIST": StalkerDocumentStatus.EMBEDDING_EXIST.name,
    "DOCUMENT_INTO_DATABASE": StalkerDocumentStatus.DOCUMENT_INTO_DATABASE.name,
    "NEED_CLEAN_TEXT": StalkerDocumentStatus.NEED_CLEAN_TEXT.name,
    "NEED_CLEAN_MD": StalkerDocumentStatus.NEED_CLEAN_MD.name,
    "TEXT_TO_MD_DONE": StalkerDocumentStatus.NEED_CLEAN_MD.name,
    "MD_SIMPLIFIED": StalkerDocumentStatus.MD_SIMPLIFIED.name,
    "TRANSCRIPTION_DONE_AND_SPLIT_BY_CHAPTERS": StalkerDocumentStatus.TRANSCRIPTION_DONE_AND_SPLIT_BY_CHAPTERS.name,
    "TEMPORARY_ERROR": StalkerDocumentStatus.TEMPORARY_ERROR.name,
    "NEED_LLM_ANALYSIS": StalkerDocumentStatus.NEED_LLM_ANALYSIS.name,
}

PROCESSING_ERROR_CODE_LOOKUP = {
    None: StalkerDocumentStatusError.NONE.name,
    "NONE": StalkerDocumentStatusError.NONE.name,
    "ERROR_DOWNLOAD": StalkerDocumentStatusError.ERROR_DOWNLOAD.name,
    "LINK_SUMMARY_MISSING": StalkerDocumentStatusError.LINK_SUMMARY_MISSING.name,
    "TITLE_MISSING": StalkerDocumentStatusError.TITLE_MISSING.name,
    "TEXT_MISSING": StalkerDocumentStatusError.TEXT_MISSING.name,
    "NO_URL_ERROR": StalkerDocumentStatusError.NO_URL_ERROR.name,
    "EMBEDDING_ERROR": StalkerDocumentStatusError.EMBEDDING_ERROR.name,
    "REGEX_ERROR": StalkerDocumentStatusError.REGEX_ERROR.name,
    "TEXT_TO_MD_ERROR": StalkerDocumentStatusError.TEXT_TO_MD_ERROR.name,
    "NO_CAPTIONS_AVAILABLE": StalkerDocumentStatusError.NO_CAPTIONS_AVAILABLE.name,
    "CAPTIONS_LANGUAGE_MISMATCH": StalkerDocumentStatusError.CAPTIONS_LANGUAGE_MISMATCH.name,
    "CAPTIONS_FETCH_ERROR": StalkerDocumentStatusError.CAPTIONS_FETCH_ERROR.name,
    "TRANSCRIPTION_ERROR": StalkerDocumentStatusError.TRANSCRIPTION_ERROR.name,
    "TRANSCRIPTION_INSUFFICIENT_FUNDS": StalkerDocumentStatusError.TRANSCRIPTION_INSUFFICIENT_FUNDS.name,
}


# ---------------------------------------------------------------------------
# Lookup tables (B-94/B-95 — DDL, B-96 — ORM models)
# ---------------------------------------------------------------------------


class DocumentStatusType(Base):
    __tablename__ = "processing_status_types"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)

    def __repr__(self) -> str:
        return f"DocumentStatusType(id={self.id!r}, name={self.name!r})"


class DocumentStatusErrorType(Base):
    __tablename__ = "processing_error_types"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)

    def __repr__(self) -> str:
        return f"DocumentStatusErrorType(id={self.id!r}, name={self.name!r})"


class DocumentType(Base):
    __tablename__ = "document_types"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)

    def __repr__(self) -> str:
        return f"DocumentType(id={self.id!r}, name={self.name!r})"


class EmbeddingModel(Base):
    __tablename__ = "embedding_models"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)

    def __repr__(self) -> str:
        return f"EmbeddingModel(id={self.id!r}, name={self.name!r})"


class DiscoverySource(Base):
    """Discovery source lookup — how the user found a document (NOT its author).

    documents.discovery_source_id references id (stage 11d normalization;
    the old name-based fk_source with ON UPDATE CASCADE is gone — renaming a
    source only edits this row, documents follow via the id). Deactivated
    sources stay valid on existing documents but disappear from pickers
    (GET /sources?active=1). The HTTP wire format keeps the NAME (`source`
    field) — resolution to id happens in DocumentService/set_discovery_source.
    """

    __tablename__ = "discovery_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa_text("true"))

    @classmethod
    def ensure(cls, session: Session, name: str) -> "DiscoverySource | None":
        """Return the discovery-source row for ``name``, creating it if missing.

        Single get-or-create used by Document.set_discovery_source() and
        POST /sources — any write path may introduce a new source safely.
        """
        name = (name or "").strip()
        if not name:
            return None
        # A SELECT does not find pending instances before an explicit flush
        # when autoflush is disabled. Reuse one already staged in this unit of
        # work so two documents with the same new source cannot enqueue
        # duplicate rows and violate discovery_sources.name at commit time.
        for pending in session.new:
            if isinstance(pending, cls) and pending.name == name:
                return pending
        existing = session.execute(
            select(cls).where(cls.name == name)
        ).scalar_one_or_none()
        if existing is not None:
            return existing
        row = cls(name=name)
        session.add(row)
        return row

    def __repr__(self) -> str:
        return f"DiscoverySource(id={self.id!r}, name={self.name!r}, is_active={self.is_active!r})"


class Collection(Base):
    """Thematic collection a document belongs to (ADR-017: 1:N via collection_id)."""

    __tablename__ = "collections"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(),
    )


class FeedSource(Base):
    """Persistent feed configuration; YAML is only a migration seed."""
    __tablename__ = "feed_sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    url: Mapped[str | None] = mapped_column(Text)
    channel_id: Mapped[str | None] = mapped_column(String(128))
    # Explicit creator mapping for a monitored YouTube channel.  This is not
    # inferred from the feed name: a channel may have a different public
    # creator name, and feeds can be renamed independently.
    author_name: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(10), nullable=False, server_default=sa_text("'pl'"))
    collection_id: Mapped[int | None] = mapped_column(ForeignKey("collections.id", ondelete="SET NULL"))
    tags: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=sa_text("'[]'::jsonb"))
    default_topic_group_ids: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=sa_text("'[]'::jsonb"))
    auto_import: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa_text("false"))
    disabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa_text("false"))
    auto_import_after: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    discovery_source_id: Mapped[int | None] = mapped_column(ForeignKey("discovery_sources.id", ondelete="SET NULL"))
    default_state: Mapped[str] = mapped_column(String(50), nullable=False, server_default=sa_text("'URL_ADDED'"))
    field_mapping: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=sa_text("'{}'::jsonb"))
    skip_url_patterns: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=sa_text("'[]'::jsonb"))
    skip_title_patterns: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=sa_text("'[]'::jsonb"))
    last_checked_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    last_successful_import_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ContentGroup(Base):
    """Shared user-managed topic or work-priority group."""

    __tablename__ = "content_groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    priority_rank: Mapped[int | None] = mapped_column(Integer)
    archived_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    __table_args__ = (
        CheckConstraint("kind IN ('topic', 'priority')", name="ck_content_groups_kind"),
        CheckConstraint(
            "(kind = 'topic' AND priority_rank IS NULL) OR (kind = 'priority' AND priority_rank BETWEEN 1 AND 100)",
            name="ck_content_groups_priority_rank",
        ),
        Index("uq_content_groups_active_lower_name", sa_text("lower(name)"), unique=True, postgresql_where=sa_text("archived_at IS NULL")),
    )
    feed_item_memberships: Mapped[list["FeedItemGroupMembership"]] = relationship(
        back_populates="group", cascade="all, delete-orphan", overlaps="groups,group_memberships",
    )
    document_memberships: Mapped[list["DocumentGroupMembership"]] = relationship(
        back_populates="group", cascade="all, delete-orphan", overlaps="groups,group_memberships",
    )
    chunk_memberships: Mapped[list["DocumentChunkGroupMembership"]] = relationship(
        back_populates="group", cascade="all, delete-orphan", overlaps="groups,group_memberships",
    )
    suggestions: Mapped[list["ContentGroupSuggestion"]] = relationship(back_populates="group")
    feed_items: Mapped[list["FeedItem"]] = relationship(
        secondary="feed_item_group_memberships", back_populates="groups",
        overlaps="feed_item_memberships,group_memberships,group,feed_item",
    )
    documents: Mapped[list["Document"]] = relationship(
        secondary="document_group_memberships", back_populates="groups",
        overlaps="document_memberships,group_memberships,group,document",
    )
    chunks: Mapped[list["DocumentChunk"]] = relationship(
        secondary="document_chunk_group_memberships", back_populates="groups",
        overlaps="chunk_memberships,group_memberships,group,chunk",
    )


class FeedItem(Base):
    __tablename__ = "feed_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    feed_source_id: Mapped[int] = mapped_column(ForeignKey("feed_sources.id", ondelete="RESTRICT"), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False, server_default=sa_text("''"))
    summary: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    raw_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=sa_text("'{}'::jsonb"))
    status: Mapped[str] = mapped_column(String(40), nullable=False, server_default=sa_text("'new'"))
    first_seen_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_seen_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    saved_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    saved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
    review_note: Mapped[str | None] = mapped_column(Text)
    review_reason: Mapped[str | None] = mapped_column(String(40))
    ignored_pattern: Mapped[str | None] = mapped_column(Text)
    last_error: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (
        UniqueConstraint("feed_source_id", "canonical_url", name="uq_feed_items_source_canonical"),
        CheckConstraint(
            "status IN ('new','llm_analysis_requested','saved_for_later','imported','skipped','ignored','error')",
            name="ck_feed_items_status",
        ),
        CheckConstraint(
            "review_reason IS NULL OR review_reason IN ('not_interested','duplicate','already_known','too_long','other')",
            name="ck_feed_items_review_reason",
        ),
        Index("idx_feed_items_source_status", "feed_source_id", "status"),
        Index("idx_feed_items_status_first_seen", "status", "first_seen_at"),
        Index("idx_feed_items_status_saved_at", "status", "saved_at"),
    )
    group_memberships: Mapped[list["FeedItemGroupMembership"]] = relationship(
        back_populates="feed_item", cascade="all, delete-orphan", overlaps="groups",
    )
    groups: Mapped[list[ContentGroup]] = relationship(
        secondary="feed_item_group_memberships", back_populates="feed_items",
        overlaps="group_memberships,feed_item",
    )


class FeedReviewDecision(Base):
    __tablename__ = "feed_review_decisions"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    batch_id: Mapped[str] = mapped_column(String(32), nullable=False)
    job_id: Mapped[str | None] = mapped_column(String(32))
    feed_item_id: Mapped[int] = mapped_column(ForeignKey("feed_items.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    previous_status: Mapped[str] = mapped_column(String(40), nullable=False)
    new_status: Mapped[str] = mapped_column(String(40), nullable=False)
    previous_document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
    new_document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
    previous_saved_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    previous_review_reason: Mapped[str | None] = mapped_column(String(40))
    previous_ignored_pattern: Mapped[str | None] = mapped_column(Text)
    previous_group_ids: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=sa_text("'[]'::jsonb"))
    new_group_ids: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=sa_text("'[]'::jsonb"))
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, server_default=sa_text("'{}'::jsonb"))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    undone_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    undone_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    feed_item: Mapped[FeedItem] = relationship()


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    type: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default=sa_text("'queued'"))
    parameters: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=sa_text("'{}'::jsonb"))
    progress: Mapped[dict | None] = mapped_column(JSONB)
    result: Mapped[dict | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, server_default=sa_text("0"))
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=sa_text("3"))
    available_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    started_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    initiated_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    idempotency_key: Mapped[str | None] = mapped_column(String(255), unique=True)
    __table_args__ = (
        CheckConstraint("type IN ('feed_check','feed_check_all','feed_auto_import','feed_daily','content_group_suggest','document_prepare','entity_enrichment','legacy_aws_pull','obsidian_reimport','tool_candidate_detect')", name="ck_jobs_type"),
    )


class ScheduledTask(Base):
    """Application-owned definitions for all jobs created by the coordinator."""

    __tablename__ = "scheduled_tasks"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa_text("TRUE"))
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    times: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default=sa_text("'[]'::jsonb"))
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )


class FeedItemGroupMembership(Base):
    __tablename__ = "feed_item_group_memberships"

    feed_item_id: Mapped[int] = mapped_column(ForeignKey("feed_items.id", ondelete="CASCADE"), primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("content_groups.id", ondelete="RESTRICT"), primary_key=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    source: Mapped[str] = mapped_column(String(20), nullable=False, server_default=sa_text("'manual'"))
    source_suggestion_id: Mapped[int | None] = mapped_column(ForeignKey("content_group_suggestions.id", ondelete="SET NULL"))
    feed_item: Mapped[FeedItem] = relationship(back_populates="group_memberships", overlaps="groups")
    group: Mapped[ContentGroup] = relationship(back_populates="feed_item_memberships", overlaps="groups,group_memberships")
    __table_args__ = (
        CheckConstraint("source IN ('manual', 'llm_suggestion')", name="ck_feed_item_group_memberships_source"),
        CheckConstraint("(source = 'llm_suggestion' AND source_suggestion_id IS NOT NULL) OR (source <> 'llm_suggestion' AND source_suggestion_id IS NULL)", name="ck_feed_item_group_memberships_suggestion_source"),
        Index("idx_feed_item_group_memberships_group_id", "group_id"),
    )


class DocumentGroupMembership(Base):
    __tablename__ = "document_group_memberships"

    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("content_groups.id", ondelete="RESTRICT"), primary_key=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    source: Mapped[str] = mapped_column(String(20), nullable=False, server_default=sa_text("'manual'"))
    source_suggestion_id: Mapped[int | None] = mapped_column(ForeignKey("content_group_suggestions.id", ondelete="SET NULL"))
    document: Mapped["Document"] = relationship(back_populates="group_memberships", overlaps="groups")
    group: Mapped[ContentGroup] = relationship(back_populates="document_memberships", overlaps="groups,group_memberships")
    __table_args__ = (
        CheckConstraint("source IN ('manual', 'feed_import', 'chrome_link', 'llm_suggestion')", name="ck_document_group_memberships_source"),
        CheckConstraint("(source = 'llm_suggestion' AND source_suggestion_id IS NOT NULL) OR (source <> 'llm_suggestion' AND source_suggestion_id IS NULL)", name="ck_document_group_memberships_suggestion_source"),
        Index("idx_document_group_memberships_group_id", "group_id"),
    )


class ContentGroupSuggestionRun(Base):
    __tablename__ = "content_group_suggestion_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    feed_item_id: Mapped[int | None] = mapped_column(ForeignKey("feed_items.id", ondelete="CASCADE"))
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    job_id: Mapped[str | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(30), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    catalog_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    raw_result: Mapped[dict | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    completed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    suggestions: Mapped[list["ContentGroupSuggestion"]] = relationship(back_populates="run", cascade="all, delete-orphan")
    __table_args__ = (
        CheckConstraint("(feed_item_id IS NOT NULL) <> (document_id IS NOT NULL)", name="ck_content_group_suggestion_runs_one_target"),
        CheckConstraint("status IN ('queued', 'running', 'completed', 'error')", name="ck_content_group_suggestion_runs_status"),
        Index("uq_active_feed_group_suggestion_run", "feed_item_id", unique=True, postgresql_where=sa_text("feed_item_id IS NOT NULL AND status IN ('queued','running')")),
        Index("uq_active_document_group_suggestion_run", "document_id", unique=True, postgresql_where=sa_text("document_id IS NOT NULL AND status IN ('queued','running')")),
    )


class ContentGroupSuggestion(Base):
    __tablename__ = "content_group_suggestions"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("content_group_suggestion_runs.id", ondelete="CASCADE"), nullable=False)
    group_id: Mapped[int] = mapped_column(ForeignKey("content_groups.id", ondelete="RESTRICT"), nullable=False)
    confidence: Mapped[decimal.Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=sa_text("'pending'"))
    membership_created: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa_text("false"))
    decided_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    decided_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    run: Mapped[ContentGroupSuggestionRun] = relationship(back_populates="suggestions")
    group: Mapped[ContentGroup] = relationship(back_populates="suggestions")
    __table_args__ = (
        UniqueConstraint("run_id", "group_id"),
        CheckConstraint("confidence BETWEEN 0 AND 1", name="ck_content_group_suggestions_confidence"),
        CheckConstraint("status IN ('pending', 'accepted', 'dismissed', 'reverted')", name="ck_content_group_suggestions_status"),
    )


class FeedItemLlmAnalysis(Base):
    __tablename__ = "feed_item_llm_analyses"
    id: Mapped[int] = mapped_column(primary_key=True)
    feed_item_id: Mapped[int] = mapped_column(ForeignKey("feed_items.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=sa_text("'requested'"))
    requested_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    claimed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    claimed_by: Mapped[str | None] = mapped_column(String(255))
    prompt_payload: Mapped[dict | None] = mapped_column(JSONB)
    result: Mapped[dict | None] = mapped_column(JSONB)
    recommendation: Mapped[str | None] = mapped_column(String(30))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    completed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (Index("uq_feed_item_active_llm", "feed_item_id", unique=True,
                            postgresql_where=sa_text("status IN ('requested', 'claimed')")),)


class DocumentLlmAnalysis(Base):
    __tablename__ = "document_llm_analyses"
    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=sa_text("'requested'"))
    requested_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    claimed_by: Mapped[str | None] = mapped_column(String(255))
    input_payload: Mapped[dict | None] = mapped_column(JSONB)
    result: Mapped[dict | None] = mapped_column(JSONB)
    next_status: Mapped[str | None] = mapped_column(String(50))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    completed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))


class Language(Base):
    """Known language lookup backing the /search languages filter picker.

    documents.language stays free text (String(10), not FK'd to this
    table) — language detection and every import path that writes it keep
    working unchanged; this is a curated "known good" reference list, not
    a hard constraint. Seeded by migration f3a4b5c6d7e8 from the distinct
    codes observed in production after folding case/region variants.
    """

    __tablename__ = "languages"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    name_pl: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(),
    )

    def __repr__(self) -> str:
        return f"Language(id={self.id!r}, code={self.code!r})"


class Publisher(Base):
    """Portal which published a document (not its discovery/information source)."""

    __tablename__ = "publishers"

    id: Mapped[int] = mapped_column(primary_key=True)
    canonical_name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(),
    )
    domains: Mapped[list["PublisherDomain"]] = relationship(
        back_populates="publisher", cascade="all, delete-orphan",
    )

    @classmethod
    def ensure(cls, session: Session, domain: str) -> "Publisher | None":
        """Return the publisher owning `domain`, creating both if missing.

        `domain` must already be a registrable domain (see
        library/publisher_domain.registrable_domain()) — this only
        case-folds it, it does not re-derive the registrable domain, so
        callers control exactly what a "publisher" groups by. Mirrors
        DiscoverySource.ensure()'s get-or-create/pending-flush pattern.
        """
        domain = normalize_publisher_domain(domain)
        if not domain:
            return None
        for pending in session.new:
            if isinstance(pending, PublisherDomain) and pending.domain == domain:
                return pending.publisher
        existing = session.execute(
            select(PublisherDomain).where(PublisherDomain.domain == domain)
        ).scalar_one_or_none()
        if existing is not None:
            return existing.publisher
        publisher = cls(canonical_name=domain)
        session.add(publisher)
        session.add(PublisherDomain(domain=domain, publisher=publisher))
        return publisher


class PublisherDomain(Base):
    """Globally unique, normalized hostname belonging to one publisher."""

    __tablename__ = "publisher_domains"

    id: Mapped[int] = mapped_column(primary_key=True)
    publisher_id: Mapped[int] = mapped_column(
        ForeignKey("publishers.id", ondelete="CASCADE"), nullable=False,
    )
    domain: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    publisher: Mapped["Publisher"] = relationship(back_populates="domains")


# ---------------------------------------------------------------------------
# Document — Single Table Inheritance on documents
# ---------------------------------------------------------------------------


class Document(Base):
    __tablename__ = "documents"

    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True)

    # Content fields (order matches DDL in 03-create-table.sql)
    summary: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_url: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    language: Mapped[str | None] = mapped_column(String(10))
    tags: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str | None] = mapped_column(Text)
    paywall: Mapped[bool | None] = mapped_column(Boolean, server_default=sa_text("false"))
    # The source may require an authenticated session even when the content
    # is not paid (e.g. a Facebook post). This is separate from paywall.
    requires_login: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa_text("false"))
    # Platform for social posts (e.g. facebook, linkedin); NULL for other documents.
    social_platform: Mapped[str | None] = mapped_column(String(30))
    title: Mapped[str | None] = mapped_column(Text)
    # When the document entered Lenie (stage 11g rename from created_at) —
    # distinct from published_on, which is when the content was published.
    ingested_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime, server_default=sa_text("CURRENT_TIMESTAMP"),
    )

    # FK columns — reference lookup tables by name (ADR-010)
    document_type: Mapped[str] = mapped_column(
        String(50), ForeignKey("document_types.name"), nullable=False,
    )

    # How the user discovered this content (e.g. "own", "unknow.news", "friend").
    # Used to evaluate recommendation source quality over time — NOT who created
    # the content. FK by id since stage 11d; the wire format stays the NAME —
    # writers resolve it via set_discovery_source() (auto-creates unknown names).
    discovery_source_id: Mapped[int | None] = mapped_column(
        ForeignKey("discovery_sources.id"), index=True,
    )
    discovery_source: Mapped["DiscoverySource | None"] = relationship("DiscoverySource")
    publisher_id: Mapped[int | None] = mapped_column(
        ForeignKey("publishers.id", ondelete="SET NULL"), index=True,
    )
    publisher: Mapped["Publisher | None"] = relationship("Publisher")
    published_on: Mapped[datetime.date | None] = mapped_column(Date)
    # How published_on was set — "manual" (reviewer typed it on /chunks), "llm"
    # (extract_publication_date), or "relative" (resolve_relative_publication_date
    # — a relative-date artifact like "Wczoraj, HH:MM" resolved deterministically
    # against ingested_at, no LLM call). NULL for legacy/import-set values
    # (unknown provenance). Lets a future pass find documents where the
    # automatic pipeline never found a date, to build deterministic per-portal
    # rules — the same workflow document_removed_lines already does for
    # cleanup rules. ck_documents_published_on_method enforces this set.
    published_on_method: Mapped[str | None] = mapped_column(String(10))
    original_id: Mapped[str | None] = mapped_column(Text)
    # Stable mailbox identity for email documents.  Deliberately separate from
    # byline: a display name is not a reliable key for sender-specific rules.
    email_sender: Mapped[str | None] = mapped_column(String(320), index=True)
    # SHA-256 of the source file's content (obsidian_note documents only) —
    # lets the reimport job (Story 42.2) tell an unchanged file apart from an
    # edited one without trusting Obsidian Sync's file mtime, which is not
    # guaranteed to survive cross-device sync.
    obsidian_source_hash: Mapped[str | None] = mapped_column(String(64))
    # Short LLM-generated retrieval aliases, e.g. "audyt NDA, sprawdzenie umowy".
    # Separate from the controlled thematic taxonomy in ``tags``.
    search_terms: Mapped[str | None] = mapped_column(Text)
    document_length: Mapped[int | None] = mapped_column(Integer)
    chapter_list: Mapped[str | None] = mapped_column(Text)
    video_description: Mapped[str | None] = mapped_column(Text)

    processing_status: Mapped[str] = mapped_column(
        String(50), ForeignKey("processing_status_types.name"),
        nullable=False, server_default="URL_ADDED",
    )
    processing_error_code: Mapped[str | None] = mapped_column(
        String, ForeignKey("processing_error_types.name"), nullable=True,
    )

    text_raw: Mapped[str | None] = mapped_column(Text)
    transcript_job_id: Mapped[str | None] = mapped_column(Text)
    ai_summary_needed: Mapped[bool | None] = mapped_column(Boolean, server_default=sa_text("false"))
    # Content creator: YouTube channel name, article author, etc. — metadata about who made it.
    # Multiple authors are stored comma-separated; the structured links live in
    # document_persons (role="author"), this column is the display cache.
    byline: Mapped[str | None] = mapped_column(Text)
    # How byline was set — "manual" (reviewer typed it on /chunks), "llm"
    # (extract_author / pipeline step 11b2) or "html" (deterministic metadata
    # extraction). NULL for legacy/import-set values.
    # Mirrors published_on_method: lets a future pass find documents where the
    # byline extraction failed and a human had to fix it.
    byline_method: Mapped[str | None] = mapped_column(String(10))
    note: Mapped[str | None] = mapped_column(Text)
    uuid: Mapped[str] = mapped_column(
        String(100), nullable=False, unique=True,
        server_default=func.gen_random_uuid(),
    )
    collection_id: Mapped[int | None] = mapped_column(
        ForeignKey("collections.id", ondelete="SET NULL"), index=True,
    )
    text_md: Mapped[str | None] = mapped_column(Text)
    # Raw LLM article extraction output (pre clean_article_text) — diagnostic only,
    # intentionally NOT exposed via dict()/API (used for article_cleaner regression checks).
    text_extracted: Mapped[str | None] = mapped_column(Text)
    transcript_needed: Mapped[bool | None] = mapped_column(Boolean, server_default=sa_text("false"))

    # Review & Obsidian tracking (Story 33.4, ADR-014)
    reviewed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime)
    obsidian_note_paths: Mapped[list] = mapped_column(JSONB, server_default=sa_text("'[]'"))

    # Set when the last NER refresh (entity_service.refresh_document_entities)
    # found the ner_service unreachable — distinguishes "service down" from
    # "genuinely no entities found" so the reader can warn instead of staying
    # silently empty. Cleared on the next successful refresh (found or not).
    ner_unavailable_at: Mapped[datetime.datetime | None] = mapped_column(DateTime)

    # Bumped by refresh_document_events/refresh_document_periods/refresh_document_tones
    # (library/timeline_events.py, time_periods.py, tones.py) every time they run,
    # regardless of how many rows they produce — lets the reader's Oś czasu/Ton/Okres
    # treści panels tell "never analyzed" apart from "analyzed, found nothing".
    enrichment_run_at: Mapped[datetime.datetime | None] = mapped_column(DateTime)
    # Bumped by refresh_document_entities (library/entity_service.py) on every
    # successful run (found or not) — same "never checked" vs "checked, empty"
    # distinction as enrichment_run_at, but for the entities sidebar. Separate
    # from ner_unavailable_at, which only records the service-down failure case.
    entities_checked_at: Mapped[datetime.datetime | None] = mapped_column(DateTime)

    # Article quality ("staranność") assessment — JSONB: score 0-100, per-signal
    # penalties (photo captions, missing author, noise share, ...) and the LLM
    # rubric. Computed by library/article_quality.py at the end of an article-mode
    # analysis run, or on demand via POST /document/<id>/quality.
    quality: Mapped[dict | None] = mapped_column(JSONB)

    # Lookup-table relationships (many-to-one)
    document_type_ref: Mapped["DocumentType"] = relationship(
        foreign_keys=[document_type],
    )
    processing_status_ref: Mapped["DocumentStatusType"] = relationship(
        foreign_keys=[processing_status],
    )
    processing_error_code_ref: Mapped["DocumentStatusErrorType | None"] = relationship(
        foreign_keys=[processing_error_code],
    )

    # Relationship to embeddings
    embeddings: Mapped[list["DocumentEmbedding"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    group_memberships: Mapped[list["DocumentGroupMembership"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", overlaps="groups",
    )
    groups: Mapped[list[ContentGroup]] = relationship(
        secondary="document_group_memberships", back_populates="documents",
        overlaps="group_memberships,document",
    )

    # STI configuration
    __mapper_args__ = {"polymorphic_on": "document_type"}

    # Navigation fields (transient — populated by repository, NOT mapped columns)
    next_id = None
    next_type = None
    previous_id = None
    previous_type = None

    # --- Classmethods (Story 27.1) ---

    @classmethod
    def populate_neighbors(cls, session: Session, doc: "Document") -> None:
        """Populate transient navigation fields (next_id, next_type, previous_id, previous_type)."""
        next_row = session.execute(
            select(cls.id, cls.document_type)
            .where(cls.id > doc.id)
            .order_by(cls.id.asc())
            .limit(1)
        ).first()
        if next_row is not None:
            doc.next_id = next_row[0]
            doc.next_type = next_row[1]
        else:
            doc.next_id = None
            doc.next_type = None

        prev_row = session.execute(
            select(cls.id, cls.document_type)
            .where(cls.id < doc.id)
            .order_by(cls.id.desc())
            .limit(1)
        ).first()
        if prev_row is not None:
            doc.previous_id = prev_row[0]
            doc.previous_type = prev_row[1]
        else:
            doc.previous_id = None
            doc.previous_type = None

    @classmethod
    def get_by_id(cls, session: Session, doc_id: int, reach: bool = False) -> "Document | None":
        """Return document by primary key, or None if not found.

        When reach=True, populate transient navigation fields (next_id,
        next_type, previous_id, previous_type) with neighboring documents.
        """
        doc = session.get(cls, doc_id)
        if doc is None:
            return None
        if reach:
            cls.populate_neighbors(session, doc)
        return doc

    @classmethod
    def get_by_url(cls, session: Session, url: str) -> "Document | None":
        """Return a document matching the canonical identity of the URL."""
        return session.scalars(
            select(cls).where(cls.canonical_url == canonicalize_url(url))
        ).first()

    @validates("url")
    def _set_canonical_url(self, _key: str, value: str) -> str:
        self.canonical_url = canonicalize_url(value)
        return value

    # --- Domain methods (migrated from stalker_web_document.py) ---

    def set_document_type(self, document_type: str) -> None:
        mapped_type = DOCUMENT_TYPE_LOOKUP.get(document_type)
        if mapped_type is None:
            raise ValueError(
                f"document_type must be one of 'movie', 'webpage', 'text_message', 'text', 'link', 'email', 'social_media_post', "
                f"'obsidian_note' not >{document_type}<"
            )
        self.document_type = mapped_type

    def set_processing_status(self, processing_status: str) -> None:
        mapped_state = PROCESSING_STATUS_LOOKUP.get(processing_status)
        if mapped_state is None:
            raise ValueError("processing_status must be one of the valid StalkerDocumentStatus values")
        self.processing_status = mapped_state

    def set_discovery_source(self, session: Session, name: str | None) -> None:
        """Resolve a discovery-source NAME (the HTTP wire format) to the FK.

        Unknown names are auto-created in discovery_sources (the stage-11d
        replacement for the old before_flush hook). Empty/whitespace names
        clear the FK — the pre-11d behaviour for blank `source` values.
        """
        name = (name or "").strip()
        if not name:
            self.discovery_source_id = None
            self.discovery_source = None
            return
        row = DiscoverySource.ensure(session, name)
        # A freshly created row has no id until flush; assigning the
        # relationship lets the unit of work fill the FK on flush.
        self.discovery_source = row

    def set_publisher_from_url(self, session: Session, url: str | None = None) -> None:
        """Resolve this document's URL to a Publisher via its registrable domain.

        Auto-creates an unknown domain's publisher (bootstrap-then-curate,
        same as set_discovery_source()/DiscoverySource.ensure()). Uses the
        registrable domain (library.publisher_domain.registrable_domain()),
        not the raw hostname, so multi-section sites sharing one
        organization's domain (tech.wp.pl, wiadomosci.wp.pl -> wp.pl)
        resolve to the same publisher, while sites merely sharing a public
        suffix (knf.gov.pl vs nik.gov.pl) or a multi-tenant hosting
        platform (foo.github.io vs bar.github.io) correctly stay distinct.
        """
        domain = registrable_domain(url if url is not None else self.url)
        self.publisher = Publisher.ensure(session, domain) if domain else None

    @property
    def discovery_source_name(self) -> str | None:
        """The discovery source's NAME — what the HTTP wire format exposes."""
        return self.discovery_source.name if self.discovery_source else None

    def set_processing_error_code(self, processing_error_code: str | None) -> None:
        mapped_state_error = PROCESSING_ERROR_CODE_LOOKUP.get(processing_error_code)
        if mapped_state_error is None:
            raise ValueError(
                f"processing_error_code must be one of the valid StalkerDocumentStatusError values, not >{processing_error_code}<"
            )
        self.processing_error_code = mapped_state_error

    def analyze(self) -> None:
        if self.processing_status == StalkerDocumentStatus.NEED_LLM_ANALYSIS.name:
            return None
        if self.processing_status == StalkerDocumentStatus.EMBEDDING_EXIST.name:
            return None

        if not self.text_raw:
            logger.info("This is adding new entry, so raw text is equal to text")
            self.text_raw = self.text

        if self.document_type == StalkerDocumentType.link.name:
            self.text = None

    def validate(self) -> None:
        if self.processing_status == StalkerDocumentStatus.NEED_LLM_ANALYSIS.name:
            return None
        self.processing_error_code = StalkerDocumentStatusError.NONE.name

        if self.processing_status == StalkerDocumentStatus.EMBEDDING_EXIST.name:
            return None

        if not self.title or len(self.title) < 3:
            self.processing_status = StalkerDocumentStatus.NEED_MANUAL_REVIEW.name
            self.processing_error_code = StalkerDocumentStatusError.TITLE_MISSING.name

        if self.document_type == StalkerDocumentType.link.name:
            if not self.summary or len(self.summary) < 3:
                self.processing_status = StalkerDocumentStatus.NEED_MANUAL_REVIEW.name
                self.processing_error_code = StalkerDocumentStatusError.LINK_SUMMARY_MISSING.name

        if self.document_type == StalkerDocumentType.webpage.name:
            if not self.text or len(self.text) < 3:
                self.processing_status = StalkerDocumentStatus.NEED_MANUAL_REVIEW.name
                self.processing_error_code = StalkerDocumentStatusError.TEXT_MISSING.name

    def dict(self):
        ingested_at_str = self.ingested_at.strftime("%Y-%m-%d %H:%M:%S") if self.ingested_at else None
        return {
            "id": self.id,
            "next_id": self.next_id,
            "next_type": self.next_type,
            "previous_id": self.previous_id,
            "previous_type": self.previous_type,
            "summary": self.summary,
            "url": self.url,
            "canonical_url": self.canonical_url,
            "language": self.language,
            "tags": self.tags,
            "search_terms": self.search_terms,
            "text": self.text,
            "paywall": self.paywall,
            "requires_login": self.requires_login,
            "social_platform": self.social_platform,
            "title": self.title,
            "ingested_at": ingested_at_str,
            "document_type": self.document_type,
            # Wire format keeps the NAME under "source" (Chrome extension /
            # editor compatibility); the FK is exposed alongside it.
            "source": self.discovery_source_name,
            "discovery_source_id": self.discovery_source_id,
            "published_on": self.published_on,
            "published_on_method": self.published_on_method,
            "original_id": self.original_id,
            "email_sender": self.email_sender,
            "document_length": self.document_length,
            "chapter_list": self.chapter_list,
            "video_description": self.video_description,
            "processing_status": self.processing_status,
            "processing_error_code": self.processing_error_code or "NONE",
            "text_raw": self.text_raw,
            "transcript_job_id": self.transcript_job_id,
            "ai_summary_needed": self.ai_summary_needed,
            "byline": self.byline,
            "byline_method": self.byline_method,
            "note": self.note,
            "uuid": self.uuid,
            "collection_id": self.collection_id,
            "text_md": self.text_md,
            "transcript_needed": self.transcript_needed,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "obsidian_note_paths": self.obsidian_note_paths or [],
            "quality": self.quality,
        }


# ---------------------------------------------------------------------------
# STI Subclasses — one per document_type, no extra columns
# ---------------------------------------------------------------------------


class LinkDocument(Document):
    __mapper_args__ = {"polymorphic_identity": "link"}


class YouTubeDocument(Document):
    __mapper_args__ = {"polymorphic_identity": "youtube"}


class MovieDocument(Document):
    __mapper_args__ = {"polymorphic_identity": "movie"}


class WebpageDocument(Document):
    __mapper_args__ = {"polymorphic_identity": "webpage"}


class TextMessageDocument(Document):
    __mapper_args__ = {"polymorphic_identity": "text_message"}


class TextDocument(Document):
    __mapper_args__ = {"polymorphic_identity": "text"}


class SocialMediaPostDocument(Document):
    __mapper_args__ = {"polymorphic_identity": "social_media_post"}


class EmailDocument(Document):
    __mapper_args__ = {"polymorphic_identity": "email"}


class ObsidianNoteDocument(Document):
    __mapper_args__ = {"polymorphic_identity": "obsidian_note"}


# ---------------------------------------------------------------------------
# DocumentEmbedding — vector embeddings for document chunks
# ---------------------------------------------------------------------------


class DocumentEmbedding(Base):
    __tablename__ = "document_embeddings"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    language: Mapped[str | None] = mapped_column(String(10))
    text: Mapped[str | None] = mapped_column(Text)
    text_original: Mapped[str | None] = mapped_column(Text)
    embedding: Mapped[list | None] = mapped_column(Vector(), nullable=True)
    model: Mapped[str] = mapped_column(
        String(100), ForeignKey("embedding_models.name"), nullable=False,
    )
    chunk_id: Mapped[int | None] = mapped_column(
        ForeignKey("document_chunks.id", ondelete="SET NULL"), nullable=True,
    )
    created_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime, server_default=sa_text("CURRENT_TIMESTAMP"),
    )

    # Relationships
    document: Mapped["Document"] = relationship(back_populates="embeddings")
    model_ref: Mapped["EmbeddingModel"] = relationship(foreign_keys=[model])
    chunk: Mapped["DocumentChunk | None"] = relationship(foreign_keys=[chunk_id])


# ---------------------------------------------------------------------------
# TranscriptionLog — tracks transcription usage and costs
# ---------------------------------------------------------------------------


class TranscriptionLog(Base):
    __tablename__ = "transcription_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), nullable=True,
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    speech_model: Mapped[str | None] = mapped_column(String(100))
    audio_duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_usd: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False)
    transcript_job_id: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime, server_default=sa_text("CURRENT_TIMESTAMP"),
    )

    document: Mapped["Document | None"] = relationship(foreign_keys=[document_id])

    @classmethod
    def get_usage_summary(cls, session: Session, provider: str | None = None) -> dict:
        """Return aggregated transcription usage: total cost, duration, count, grouped by provider."""
        query = select(
            cls.provider,
            func.sum(cls.cost_usd).label("spent_usd"),
            func.sum(cls.audio_duration_seconds).label("total_seconds"),
            func.count(cls.id).label("count"),
        ).group_by(cls.provider)

        if provider:
            query = query.where(cls.provider == provider)

        rows = session.execute(query).all()

        total_spent = 0.0
        total_seconds = 0
        total_count = 0
        by_provider = {}

        for row in rows:
            spent = float(row.spent_usd or 0)
            seconds = int(row.total_seconds or 0)
            count = int(row.count or 0)
            total_spent += spent
            total_seconds += seconds
            total_count += count
            by_provider[row.provider] = {
                "spent_usd": round(spent, 4),
                "minutes": seconds // 60,
                "count": count,
            }

        return {
            "total_spent_usd": round(total_spent, 4),
            "total_seconds": total_seconds,
            "total_minutes": total_seconds // 60,
            "transactions_count": total_count,
            "by_provider": by_provider,
        }


# ---------------------------------------------------------------------------
# ImportLog — tracks import script operations
# ---------------------------------------------------------------------------


class ImportLog(Base):
    __tablename__ = "import_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    script_name: Mapped[str] = mapped_column(String(100), nullable=False)
    started_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(),
    )
    finished_at: Mapped[datetime.datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=sa_text("'running'"))
    since_date: Mapped[datetime.date | None] = mapped_column(Date)
    until_date: Mapped[datetime.date | None] = mapped_column(Date)
    items_found: Mapped[int | None] = mapped_column(Integer, server_default=sa_text("0"))
    items_added: Mapped[int | None] = mapped_column(Integer, server_default=sa_text("0"))
    items_skipped: Mapped[int | None] = mapped_column(Integer, server_default=sa_text("0"))
    items_error: Mapped[int | None] = mapped_column(Integer, server_default=sa_text("0"))
    parameters: Mapped[dict | None] = mapped_column(JSONB, server_default=sa_text("'{}'"))
    error_message: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)

    def __repr__(self) -> str:
        return (
            f"ImportLog(id={self.id!r}, script_name={self.script_name!r}, "
            f"status={self.status!r}, started_at={self.started_at!r})"
        )


# ---------------------------------------------------------------------------
# Document Analysis — runs, chunks, topic sections
# ---------------------------------------------------------------------------


class DocumentAnalysisRun(Base):
    __tablename__ = "document_analysis_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False,
    )
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    chunk_size: Mapped[int] = mapped_column(Integer, nullable=False, server_default=sa_text("5000"))
    synthesis: Mapped[str | None] = mapped_column(Text)
    speakers: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=sa_text("'[]'"))
    # mode: transcript (YouTube STT — rewrite + speakers) | article (clean markdown — no rewrite)
    mode: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=sa_text("'transcript'"),
    )
    # status: created | in_review | reviewed | superseded (replaced by a newer
    # run of the same document+scope before ever reaching reviewed — see
    # document_analysis_service.supersede_unfinished_runs)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=sa_text("'created'"),
    )
    # scope: human-readable analysed range (e.g. chapter title); NULL = whole document
    scope: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(),
    )

    document: Mapped["Document"] = relationship(foreign_keys=[document_id])
    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="DocumentChunk.position",
    )
    topic_sections: Mapped[list["DocumentTopicSection"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="DocumentTopicSection.position",
    )

    def __repr__(self) -> str:
        return f"DocumentAnalysisRun(id={self.id!r}, document_id={self.document_id!r}, model={self.model!r})"


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("document_analysis_runs.id", ondelete="CASCADE"), nullable=False,
    )
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False,
    )
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)         # TEMAT | ZRODLA | REKLAMA | SZUM
    topic: Mapped[str | None] = mapped_column(String(500))
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    corrected_text: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    seg_start: Mapped[int | None] = mapped_column(Integer)
    seg_end: Mapped[int | None] = mapped_column(Integer)
    rewrite_ratio: Mapped[int | None] = mapped_column(SmallInteger)
    # status: pending | approved | needs_reanalysis | split_requested | split | skipped
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default=sa_text("'pending'"),
    )
    split_at_seg: Mapped[int | None] = mapped_column(Integer)
    split_first_type: Mapped[str | None] = mapped_column(String(20))
    split_second_type: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(),
    )
    obsidian_note_paths: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, server_default=sa_text("'{}'"),
    )
    # Reviewer flag: this TEMAT chunk is not worth a standalone Obsidian note
    # (too thin / not interesting). It stays in every other pipeline (still
    # embedded when approved) but drops out of the "chunks still missing an
    # Obsidian note" counter and filter.
    obsidian_note_not_needed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa_text("false"),
    )
    # Exact substrings a reviewer cut out of original_text (e.g. an ad spliced
    # mid-sentence into a transcript segment) via POST /chunk/<id>/remove_span.
    # Kept around (rather than only mutating original_text) so merge/split can
    # re-apply them when they rebuild text from raw transcript segments.
    removed_text_spans: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, server_default=sa_text("'{}'"),
    )

    run: Mapped["DocumentAnalysisRun"] = relationship(back_populates="chunks")
    document: Mapped["Document"] = relationship(foreign_keys=[document_id])
    group_memberships: Mapped[list["DocumentChunkGroupMembership"]] = relationship(
        back_populates="chunk", cascade="all, delete-orphan", overlaps="groups,chunk_memberships",
    )
    groups: Mapped[list[ContentGroup]] = relationship(
        secondary="document_chunk_group_memberships", back_populates="chunks",
        overlaps="group_memberships,chunk_memberships,group,chunk",
    )

    def __repr__(self) -> str:
        return f"DocumentChunk(id={self.id!r}, run_id={self.run_id!r}, position={self.position!r}, type={self.type!r})"


class DocumentChunkGroupMembership(Base):
    """Manual category assignment for one reader chapter backed by a chunk."""

    __tablename__ = "document_chunk_group_memberships"

    chunk_id: Mapped[int] = mapped_column(
        ForeignKey("document_chunks.id", ondelete="CASCADE"), primary_key=True,
    )
    group_id: Mapped[int] = mapped_column(
        ForeignKey("content_groups.id", ondelete="RESTRICT"), primary_key=True,
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    chunk: Mapped["DocumentChunk"] = relationship(back_populates="group_memberships")
    group: Mapped["ContentGroup"] = relationship(back_populates="chunk_memberships")


class DocumentTopicSection(Base):
    __tablename__ = "document_topic_sections"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("document_analysis_runs.id", ondelete="CASCADE"), nullable=False,
    )
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False,
    )
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)         # TEMAT | ZRODLA | REKLAMA | SZUM
    title: Mapped[str | None] = mapped_column(String(500))
    summary: Mapped[str | None] = mapped_column(Text)
    chunk_positions: Mapped[list[int]] = mapped_column(ARRAY(Integer), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(),
    )

    run: Mapped["DocumentAnalysisRun"] = relationship(back_populates="topic_sections")
    document: Mapped["Document"] = relationship(foreign_keys=[document_id])

    def __repr__(self) -> str:
        return f"DocumentTopicSection(id={self.id!r}, run_id={self.run_id!r}, position={self.position!r})"


class DocumentRemovedLine(Base):
    """Line/block removed from a document during manual chunk review cleanup.

    Training data for improving article_cleaner.py / site_rules.json: what the
    automatic cleaner missed and a human had to remove. Claude Code/Codex rule
    reviews should only inspect ``pending`` rows and record a terminal decision
    using ``scripts/review_removed_lines.py``. Rows survive run/chunk
    deletion (FKs SET NULL) so aggregate queries (e.g. most-removed lines per
    portal, via join on documents.url) keep working over time.
    """

    __tablename__ = "document_removed_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False,
    )
    run_id: Mapped[int | None] = mapped_column(
        ForeignKey("document_analysis_runs.id", ondelete="SET NULL"),
    )
    chunk_id: Mapped[int | None] = mapped_column(
        ForeignKey("document_chunks.id", ondelete="SET NULL"),
    )
    # source: manual (line removed in chunk-review UI) | szum_chunk (whole
    # SZUM/REKLAMA chunk dropped by apply_cleanup)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    line_text: Mapped[str] = mapped_column(Text, nullable=False)
    # Lifecycle for cleaner-rule mining. Only ``pending`` rows should be
    # presented for analysis; terminal statuses prevent repeated review.
    review_status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=sa_text("'pending'"),
    )
    reviewed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime)
    review_note: Mapped[str | None] = mapped_column(Text)
    rule_reference: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(),
    )

    document: Mapped["Document"] = relationship(foreign_keys=[document_id])

    def __repr__(self) -> str:
        return f"DocumentRemovedLine(id={self.id!r}, document_id={self.document_id!r}, source={self.source!r})"


class EmailFooterRule(Base):
    """One opt-in, exact trailing-footer rule per normalized sender address."""

    __tablename__ = "email_footer_rules"
    __table_args__ = (UniqueConstraint("sender_email", name="uq_email_footer_rules_sender_email"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    sender_email: Mapped[str] = mapped_column(String(320), nullable=False)
    footer_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now(),
    )


class GeocodeCache(Base):
    """Cached geocoder response for one query string (NER stage 3).

    Negative results are cached too (resolved=False) so a name is never sent
    to the geocoder twice. resolved means the hit also passed the match-quality
    check in library/locationiq_client.py — rare Polish exonyms fuzzy-match to
    wrong places, so a bare HTTP 200 is not proof the place exists.
    """

    __tablename__ = "geocode_cache"

    id: Mapped[int] = mapped_column(primary_key=True)
    query: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    resolved: Mapped[bool] = mapped_column(Boolean, nullable=False)
    display_name: Mapped[str | None] = mapped_column(Text)
    lat: Mapped[float | None] = mapped_column(Numeric(9, 6))
    lon: Mapped[float | None] = mapped_column(Numeric(9, 6))
    osm_class: Mapped[str | None] = mapped_column(String(50))
    osm_type: Mapped[str | None] = mapped_column(String(50))
    importance: Mapped[float | None] = mapped_column()
    raw: Mapped[dict | None] = mapped_column(JSONB)
    provider: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=sa_text("'locationiq'"),
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(),
    )

    def __repr__(self) -> str:
        return f"GeocodeCache(id={self.id!r}, query={self.query!r}, resolved={self.resolved!r})"


class DocumentReference(Base):
    """Footnote/reference extracted out of a book's text_md (library/references.py).

    OCR-ed books carry footnote lines inline where they fell on the scanned
    page — they interrupt reading and pollute NER/embeddings. Extraction is
    replace-per-document (derived data, like document_entities); the reader
    renders a per-chapter "Przypisy" section from these rows.
    """

    __tablename__ = "document_references"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False,
    )
    # 1-based, matches detect_chapters(); NULL = unassigned
    chapter_position: Mapped[int | None] = mapped_column(Integer)
    # footnote number as printed ("18" — superscript markers are normalized to digits)
    marker: Mapped[str] = mapped_column(String(10), nullable=False)
    ref_text: Mapped[str] = mapped_column(Text, nullable=False)
    # first URL found in the footnote, normalized to an absolute https:// form
    url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(),
    )

    document: Mapped["Document"] = relationship(foreign_keys=[document_id])

    def __repr__(self) -> str:
        return (
            f"DocumentReference(id={self.id!r}, document_id={self.document_id!r}, "
            f"chapter={self.chapter_position!r}, marker={self.marker!r})"
        )


class DocumentImage(Base):
    """Image belonging to a document, from one of two sources.

    ``url`` = external image belonging to a web article
    (``library/article_cleaner.py``). ``clean_article_text()`` replaces inline
    ``![alt](url)`` markdown images with ``[imgN]`` markers in ``text_md`` —
    the URL used to be discarded. This table keeps the image (and its
    adjacent caption/credit line, when present — attached via
    ``article_quality.photo_caption_candidates()``, the same classification
    used to score photo sourcing) so article_quality.py can score it without
    needing the image markup to still live inline in the text.

    ``storage_key`` = object in our own object storage (``library/storage.py``),
    used for images extracted from imported book PDFs
    (``library/book_pdf_import.py``). Exactly one of ``url``/``storage_key`` is
    required per row (``document_images_source_present`` CHECK constraint).

    Replace-per-document semantics (like document_entities), but the two
    sources are replaced independently — see
    ``library.document_images.replace_document_images()`` (url-sourced rows)
    vs. ``replace_storage_images()`` (storage_key-sourced rows).
    """

    __tablename__ = "document_images"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False,
    )
    chunk_id: Mapped[int | None] = mapped_column(
        ForeignKey("document_chunks.id", ondelete="SET NULL"),
    )
    # 0-based position of the [imgN] marker in the cleaned text
    position: Mapped[int | None] = mapped_column(SmallInteger)
    url: Mapped[str | None] = mapped_column(Text)
    storage_key: Mapped[str | None] = mapped_column(Text)
    # 1-based PDF page the image was extracted from (storage_key rows only)
    page_number: Mapped[int | None] = mapped_column(SmallInteger)
    # 1-based reader chapter position (detect_chapters()), storage_key rows only
    chapter_position: Mapped[int | None] = mapped_column(SmallInteger)
    alt_text: Mapped[str | None] = mapped_column(Text)
    caption_text: Mapped[str | None] = mapped_column(Text)
    # own_or_private_archive | agency | creative_commons | public_domain | stock |
    # illustrative | image_credit | other | image_description — see
    # article_quality.photo_caption_candidates() / PHOTO_SOURCE_PENALTY_WEIGHTS
    caption_category: Mapped[str | None] = mapped_column(String(30))
    is_stock_photo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa_text("false"))
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(),
    )

    document: Mapped["Document"] = relationship(foreign_keys=[document_id])

    def __repr__(self) -> str:
        return f"DocumentImage(id={self.id!r}, document_id={self.document_id!r}, url={self.url!r})"


class CitedPublication(Base):
    """A canonical scholarly work cited by one or more documents."""

    __tablename__ = "cited_publications"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str | None] = mapped_column(Text)
    journal: Mapped[str | None] = mapped_column(Text)
    publication_year: Mapped[int | None] = mapped_column(Integer)
    doi: Mapped[str | None] = mapped_column(Text)
    pmid: Mapped[str | None] = mapped_column(String(20))
    pmcid: Mapped[str | None] = mapped_column(String(30))
    canonical_url: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(),
    )


class DocumentCitedPublication(Base):
    """Document-to-publication citation with grounded evidence."""

    __tablename__ = "document_cited_publications"
    __table_args__ = (UniqueConstraint("document_id", "publication_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False,
    )
    publication_id: Mapped[int] = mapped_column(
        ForeignKey("cited_publications.id", ondelete="CASCADE"), nullable=False,
    )
    chunk_id: Mapped[int | None] = mapped_column(
        ForeignKey("document_chunks.id", ondelete="SET NULL"),
    )
    raw_citation: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_excerpt: Mapped[str | None] = mapped_column(Text)
    extraction_method: Mapped[str] = mapped_column(String(30), nullable=False)
    review_status: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default="auto_accepted",
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(),
    )

    document: Mapped["Document"] = relationship(foreign_keys=[document_id])
    publication: Mapped["CitedPublication"] = relationship(foreign_keys=[publication_id])
    chunk: Mapped["DocumentChunk | None"] = relationship(foreign_keys=[chunk_id])


class DocumentEvent(Base):
    """Dated event discussed in a document, extracted by timeline_events.py."""

    __tablename__ = "document_events"
    __table_args__ = (
        CheckConstraint(
            "date_precision IN ('day', 'month', 'year', 'decade', 'century', 'era', 'unknown')",
            name="ck_document_events_date_precision",
        ),
        Index("idx_document_events_document_sort_year", "document_id", "sort_year"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False,
    )
    chapter_position: Mapped[int | None] = mapped_column(Integer)
    event_date: Mapped[datetime.date | None] = mapped_column(Date)
    event_date_end: Mapped[datetime.date | None] = mapped_column(Date)
    date_precision: Mapped[str] = mapped_column(String(10), nullable=False)
    date_text: Mapped[str] = mapped_column(Text, nullable=False)
    sort_year: Mapped[int | None] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    anchor_quote: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(),
    )

    document: Mapped["Document"] = relationship(foreign_keys=[document_id])

    def __repr__(self) -> str:
        return (
            f"DocumentEvent(id={self.id!r}, document_id={self.document_id!r}, "
            f"chapter={self.chapter_position!r}, date_text={self.date_text!r})"
        )


class DocumentTimePeriod(Base):
    """Historical period a document (or one reader chapter) is about, classified by time_periods.py."""

    __tablename__ = "document_time_periods"
    __table_args__ = (
        CheckConstraint(
            "confidence IN ('high', 'medium', 'low')",
            name="ck_document_time_periods_confidence",
        ),
        Index("idx_document_time_periods_document_chapter", "document_id", "chapter_position"),
        Index("idx_document_time_periods_years", "subject_period_start_year", "subject_period_end_year"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False,
    )
    chapter_position: Mapped[int | None] = mapped_column(Integer)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    subject_period_label: Mapped[str] = mapped_column(String(100), nullable=False)
    subject_period_start_year: Mapped[int | None] = mapped_column(Integer)
    subject_period_end_year: Mapped[int | None] = mapped_column(Integer)
    confidence: Mapped[str] = mapped_column(String(10), nullable=False, default="low", server_default="low")
    evidence: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(),
    )

    document: Mapped["Document"] = relationship(foreign_keys=[document_id])

    def __repr__(self) -> str:
        return (
            f"DocumentTimePeriod(id={self.id!r}, document_id={self.document_id!r}, "
            f"chapter={self.chapter_position!r}, subject_period_label={self.subject_period_label!r})"
        )


class DocumentTone(Base):
    """Emotional tone and language register of a document chapter, classified by tones.py."""

    __tablename__ = "document_tones"
    __table_args__ = (
        CheckConstraint(
            "sentiment IN ('pozytywne', 'negatywne', 'neutralne', 'mieszane')",
            name="ck_document_tones_sentiment",
        ),
        CheckConstraint(
            "intensity IN ('niska', 'średnia', 'wysoka')",
            name="ck_document_tones_intensity",
        ),
        Index("idx_document_tones_document_chapter", "document_id", "chapter_position"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False,
    )
    chapter_position: Mapped[int | None] = mapped_column(Integer)
    emotion: Mapped[str] = mapped_column(String(20), nullable=False)
    secondary_emotions: Mapped[str | None] = mapped_column(String(100))
    sentiment: Mapped[str] = mapped_column(String(10), nullable=False)
    intensity: Mapped[str] = mapped_column(String(10), nullable=False)
    registers: Mapped[str | None] = mapped_column(String(100))
    evidence: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(),
    )

    document: Mapped["Document"] = relationship(foreign_keys=[document_id])

    def __repr__(self) -> str:
        return (
            f"DocumentTone(id={self.id!r}, document_id={self.document_id!r}, "
            f"chapter={self.chapter_position!r}, emotion={self.emotion!r})"
        )


class ControlQuestion(Base):
    """Geopolitical control question, imported from the Obsidian question bank.

    Lookup/reference table (replace-semantics per source_file re-import) — see
    imports/import_control_questions.py. Backend has no runtime access to the
    Obsidian vault (local to the user's machine), so this table is the only
    copy available to a document running on the NAS.
    """

    __tablename__ = "control_questions"
    __table_args__ = (
        Index("idx_control_questions_source_file", "source_file"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_file: Mapped[str] = mapped_column(String(255), nullable=False)
    section_header: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[str | None] = mapped_column(String(255))
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(),
    )

    def __repr__(self) -> str:
        return f"ControlQuestion(id={self.id!r}, section_header={self.section_header!r})"


class DocumentControlAnswer(Base):
    """Control question a document answers, selected by library/control_question_selection.py.

    question_header/tags are a snapshot taken at selection time (not just the
    question_id FK) so a later re-import of the question bank never silently
    invalidates historical answers — same pattern as
    DocumentInformationSource.raw_mention.
    """

    __tablename__ = "document_control_answers"
    __table_args__ = (
        Index("idx_document_control_answers_document_chapter", "document_id", "chapter_position"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False,
    )
    chapter_position: Mapped[int | None] = mapped_column(Integer)
    question_id: Mapped[int | None] = mapped_column(
        ForeignKey("control_questions.id", ondelete="SET NULL"),
    )
    question_header: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[str | None] = mapped_column(String(255))
    answer_summary: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(),
    )

    document: Mapped["Document"] = relationship(foreign_keys=[document_id])

    def __repr__(self) -> str:
        return (
            f"DocumentControlAnswer(id={self.id!r}, document_id={self.document_id!r}, "
            f"question_header={self.question_header!r})"
        )


class DocumentAnalysisJob(Base):
    """Persistent queue entry for document chunk analysis.

    The job outlives browser navigation and backend restarts. A single backend
    worker claims queued rows and writes progress/result back to PostgreSQL.
    """

    __tablename__ = "document_analysis_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'done', 'failed')",
            name="ck_document_analysis_jobs_status",
        ),
        Index("idx_document_analysis_jobs_document_created", "document_id", "created_at"),
        Index("idx_document_analysis_jobs_status_created", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False,
    )
    run_id: Mapped[int | None] = mapped_column(
        ForeignKey("document_analysis_runs.id", ondelete="SET NULL"),
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="queued")
    parameters: Mapped[dict] = mapped_column(JSONB, nullable=False)
    progress: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    chunk_count: Mapped[int | None] = mapped_column(Integer)
    ad_count: Mapped[int | None] = mapped_column(Integer)
    topic_section_count: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(),
    )
    started_at: Mapped[datetime.datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime.datetime | None] = mapped_column(DateTime)

    document: Mapped["Document"] = relationship(foreign_keys=[document_id])
    run: Mapped["DocumentAnalysisRun | None"] = relationship(foreign_keys=[run_id])


class InfraGeometry(Base):
    """Cached Overpass API lookup for linear infrastructure (pipelines) by name.

    Same philosophy as GeocodeCache: one live call ever per distinct query
    string, negative results cached too (resolved=False). geojson holds a
    simplified GeoJSON MultiLineString rendered as polylines on the reader
    map. Populated by library/overpass_client.py during entity refresh.
    """

    __tablename__ = "infra_geometries"

    id: Mapped[int] = mapped_column(primary_key=True)
    query: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    resolved: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # kind: 'pipeline' (future: power_line, ...)
    kind: Mapped[str | None] = mapped_column(String(30))
    # substance: gas | oil | ... (OSM tag of the matched pipeline)
    substance: Mapped[str | None] = mapped_column(String(30))
    name: Mapped[str | None] = mapped_column(Text)
    wikidata_qid: Mapped[str | None] = mapped_column(String(20))
    geojson: Mapped[dict | None] = mapped_column(JSONB)
    provider: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=sa_text("'overpass'"),
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(),
    )

    def __repr__(self) -> str:
        return f"InfraGeometry(id={self.id!r}, query={self.query!r}, resolved={self.resolved!r})"


class Facility(Base):
    """Canonical physical facility, distinct from a settlement and its operator.

    ``latitude``/``longitude`` are deliberately stored on the facility as the
    stable geographic identity used by proximity queries.  ``geocode_id`` is
    retained as provenance for the first place-resolution result; it must not
    be mistaken for the facility itself (a power plant and its town can have
    different coordinates).
    """

    __tablename__ = "facilities"
    __table_args__ = (
        UniqueConstraint("canonical_name", "facility_type", "place_name", name="uq_facilities_identity"),
        CheckConstraint("latitude IS NULL OR latitude BETWEEN -90 AND 90", name="ck_facilities_latitude"),
        CheckConstraint("longitude IS NULL OR longitude BETWEEN -180 AND 180", name="ck_facilities_longitude"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    canonical_name: Mapped[str] = mapped_column(Text, nullable=False)
    # Controlled by facility_service.FACILITY_PATTERNS, e.g. nuclear_power_plant.
    facility_type: Mapped[str] = mapped_column(String(50), nullable=False)
    place_name: Mapped[str | None] = mapped_column(Text)
    latitude: Mapped[float | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[float | None] = mapped_column(Numeric(9, 6))
    # Spatial source of truth for radius/nearest-neighbour queries.  lat/lon
    # stay denormalised for compact JSON responses and simple form editing.
    location: Mapped[object | None] = mapped_column(GeographyPoint())
    geocode_id: Mapped[int | None] = mapped_column(ForeignKey("geocode_cache.id", ondelete="SET NULL"))
    wikidata_qid: Mapped[str | None] = mapped_column(String(20), unique=True)
    # Curated profile fields.  Unlike the generated document mention, these
    # describe the real-world object and may be safely reused across documents.
    description: Mapped[str | None] = mapped_column(Text)
    operator_name: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    # Alternative names and inflected surface forms used for reader matching.
    aliases: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default=sa_text("'[]'::jsonb"))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    geocode: Mapped["GeocodeCache | None"] = relationship(foreign_keys=[geocode_id])


class DocumentFacility(Base):
    """A rule-detected facility mention in one document.

    The link is derived data and is replaced with each NER refresh.  A future
    external resolver can upgrade ``confidence`` and attach exact coordinates
    without changing the raw mention or document evidence.
    """

    __tablename__ = "document_facilities"
    __table_args__ = (UniqueConstraint("document_id", "facility_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    facility_id: Mapped[int] = mapped_column(ForeignKey("facilities.id", ondelete="CASCADE"), nullable=False)
    place_entity_id: Mapped[int | None] = mapped_column(ForeignKey("document_entities.id", ondelete="SET NULL"))
    raw_mention: Mapped[str] = mapped_column(Text, nullable=False)
    mention_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=sa_text("1"))
    confidence: Mapped[str] = mapped_column(String(30), nullable=False, server_default="rule_candidate")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    facility: Mapped["Facility"] = relationship(foreign_keys=[facility_id])


class DocumentEntity(Base):
    """Raw NER entity (person/place mention) detected in a document.

    MVP of docs/ner-integration-plan.md: aggregated mentions from the NER
    microservice (ner_service/, via library/ner_client.py), no disambiguation.
    Rows are derived data — refreshing a document's entities replaces them
    (library/entity_service.py). geocode_id links place entities to the
    geocoder verdict (stage 3, library/place_verification.py); NULL = not
    checked yet.
    """

    __tablename__ = "document_entities"
    __table_args__ = (UniqueConstraint("document_id", "entity_type", "entity_text"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False,
    )
    # entity_type: persName | orgName | geogName | placeName
    entity_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # entity_text: base form of the mention (lemma when available)
    entity_text: Mapped[str] = mapped_column(Text, nullable=False)
    mention_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=sa_text("1"))
    # variants: distinct surface forms seen in the text ("Kijów", "Kijowa") —
    # lets the chapter-scoped entity filter match regardless of Polish
    # inflection. Empty = row predates the column (refilled on next refresh).
    variants: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=sa_text("'{}'"),
    )
    geocode_id: Mapped[int | None] = mapped_column(
        ForeignKey("geocode_cache.id", ondelete="SET NULL"),
    )
    # source: 'ner' (default, refresh_document_entities() may replace) | 'manual'
    # (survives refresh — set by merge_document_entities())
    source: Mapped[str] = mapped_column(String(20), nullable=False, server_default=sa_text("'ner'"))
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(),
    )

    document: Mapped["Document"] = relationship(foreign_keys=[document_id])
    geocode: Mapped["GeocodeCache | None"] = relationship(foreign_keys=[geocode_id])

    def __repr__(self) -> str:
        return (
            f"DocumentEntity(id={self.id!r}, document_id={self.document_id!r}, "
            f"entity_type={self.entity_type!r}, entity_text={self.entity_text!r})"
        )


class EntityReviewDecision(Base):
    """Immutable audit trail for human decisions about detected entities."""

    __tablename__ = "entity_review_decisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"),
    )
    document_entity_id: Mapped[int | None] = mapped_column(BigInteger)
    document_person_id: Mapped[int | None] = mapped_column(BigInteger)
    person_id: Mapped[int | None] = mapped_column(BigInteger)
    entity_type: Mapped[str] = mapped_column(String(20), nullable=False)
    entity_text: Mapped[str] = mapped_column(Text, nullable=False)
    decision: Mapped[str] = mapped_column(String(30), nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String(50))
    comment: Mapped[str | None] = mapped_column(Text)
    original_confidence: Mapped[str | None] = mapped_column(String(30))
    replacement_person_id: Mapped[int | None] = mapped_column(BigInteger)
    source_excerpt: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(),
    )

    document: Mapped["Document | None"] = relationship(foreign_keys=[document_id])


class NerContextClassification(Base):
    """LLM verdict for an ambiguous NER candidate (persName or geogName/placeName)."""

    __tablename__ = "ner_context_classifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"),
    )
    # entity_type: persName (library/person_context_classifier.py) or
    # geogName/placeName (library/place_context_classifier.py)
    entity_type: Mapped[str] = mapped_column(String(20), nullable=False, server_default=sa_text("'persName'"))
    entity_text: Mapped[str] = mapped_column(Text, nullable=False)
    predicted_class: Mapped[str] = mapped_column(String(20), nullable=False)
    confidence: Mapped[str] = mapped_column(String(10), nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text)
    context_excerpt: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    dropped: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa_text("false"))
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(),
    )

    document: Mapped["Document | None"] = relationship(foreign_keys=[document_id])


class NerTemporalCandidate(Base):
    """Raw date/time mention detected by NER before timeline interpretation."""

    __tablename__ = "ner_temporal_candidates"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False,
    )
    entity_type: Mapped[str] = mapped_column(String(10), nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    lemma: Mapped[str | None] = mapped_column(Text)
    char_start: Mapped[int | None] = mapped_column(Integer)
    context_excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(),
    )

    document: Mapped["Document"] = relationship(foreign_keys=[document_id])


class NerExclusion(Base):
    """NER false-positive suppression (exclusion dictionary).

    Applied at entity-refresh time (library/entity_service.py) so a recurring
    NER mistake — "Taliban" as a person, an STT artifact like "Starling" — is
    dropped before it lands in document_entities (and therefore never reaches
    person resolution or place verification). scope='author' limits the rule
    to documents by one author (e.g. a podcast channel whose STT keeps
    producing the same artifact); entity_type='*' matches all entity types.
    Matching is case-insensitive on the aggregated entity base form.
    """

    __tablename__ = "ner_exclusions"

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_text: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(20), nullable=False, server_default=sa_text("'*'"))
    scope: Mapped[str] = mapped_column(String(10), nullable=False, server_default=sa_text("'global'"))
    author: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(),
    )

    def __repr__(self) -> str:
        return (
            f"NerExclusion(id={self.id!r}, entity_text={self.entity_text!r}, "
            f"entity_type={self.entity_type!r}, scope={self.scope!r}, author={self.author!r})"
        )


class NerCorrection(Base):
    """Human-curated NER correction dictionary (Faza 6, tmp/plan-ner-multiword-place-display-names.md).

    Mirrors NerExclusion's scope/entity_type/author shape but corrects an
    entity instead of dropping it — applied at entity-refresh time
    (library/ner_corrections.py), right after ner_exclusions, before
    person/org registry resolution. match_lemma matches the (spaCy-
    deterministic) lemma ner_client.py computed, not a specific surface
    form or the already-resolved display text — one approved correction
    then generalizes to every future document whose NER run produces the
    same mangled lemma, without needing a fresh approval per inflected
    form. reason/approved_by are the "why" half of the decision log; every
    actual application is separately recorded in NerCorrectionApplication
    (the "where/when" half).
    """

    __tablename__ = "ner_corrections"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_lemma: Mapped[str] = mapped_column(Text, nullable=False)
    match_entity_type: Mapped[str] = mapped_column(String(20), nullable=False, server_default=sa_text("'*'"))
    corrected_text: Mapped[str] = mapped_column(Text, nullable=False)
    corrected_entity_type: Mapped[str | None] = mapped_column(String(20))
    scope: Mapped[str] = mapped_column(String(10), nullable=False, server_default=sa_text("'global'"))
    author: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    approved_by: Mapped[str] = mapped_column(Text, nullable=False)
    source_document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(),
    )

    def __repr__(self) -> str:
        return (
            f"NerCorrection(id={self.id!r}, match_lemma={self.match_lemma!r}, "
            f"corrected_text={self.corrected_text!r}, scope={self.scope!r})"
        )


class NerCorrectionApplication(Base):
    """Immutable audit record: one row per time a NerCorrection rule actually fired.

    correction_id is ON DELETE SET NULL so history survives a later rule
    deletion (the "immutable audit record" convention already used by
    DocumentRelationshipRemoval).
    """

    __tablename__ = "ner_correction_applications"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    correction_id: Mapped[int | None] = mapped_column(ForeignKey("ner_corrections.id", ondelete="SET NULL"))
    entity_type_before: Mapped[str] = mapped_column(String(20), nullable=False)
    entity_text_before: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type_after: Mapped[str] = mapped_column(String(20), nullable=False)
    entity_text_after: Mapped[str] = mapped_column(Text, nullable=False)
    applied_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    document: Mapped["Document"] = relationship(foreign_keys=[document_id])
    correction: Mapped["NerCorrection | None"] = relationship(foreign_keys=[correction_id])

    def __repr__(self) -> str:
        return (
            f"NerCorrectionApplication(id={self.id!r}, document_id={self.document_id!r}, "
            f"entity_text_before={self.entity_text_before!r}, entity_text_after={self.entity_text_after!r})"
        )


class Person(Base):
    """Canonical person entity — one row per real person (NER stage 4).

    A relational model instead of tags because two people can share a name and
    one person appears under many spelling variants. wikidata_qid is NULL for
    people without a Wikidata entry (local/less-known figures). See
    docs/person-ner-plan.md.
    """

    __tablename__ = "persons"

    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(
        String(100), nullable=False, unique=True, server_default=func.gen_random_uuid(),
    )
    canonical_name: Mapped[str] = mapped_column(Text, nullable=False)
    wikidata_qid: Mapped[str | None] = mapped_column(String(20), unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(),
    )

    aliases: Mapped[list["PersonAlias"]] = relationship(
        back_populates="person", cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"Person(id={self.id!r}, canonical_name={self.canonical_name!r}, wikidata_qid={self.wikidata_qid!r})"


class PersonAlias(Base):
    """Spelling variant of a person's name seen in articles (inflection, initials)."""

    __tablename__ = "person_aliases"
    __table_args__ = (UniqueConstraint("person_id", "alias"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(
        ForeignKey("persons.id", ondelete="CASCADE"), nullable=False,
    )
    alias: Mapped[str] = mapped_column(Text, nullable=False)

    person: Mapped["Person"] = relationship(back_populates="aliases")

    def __repr__(self) -> str:
        return f"PersonAlias(id={self.id!r}, person_id={self.person_id!r}, alias={self.alias!r})"


class DocumentPerson(Base):
    """Document<->person link (M:N) with extraction metadata (NER stage 4).

    confidence: wikidata_matched (Wikidata human entity + LLM context match)
              | alias_matched    (existing alias/canonical name matched)
              | manual_review    (new/uncertain person — review queue)
              | manual_confirmed (human approved a manual_review row)
    """

    __tablename__ = "document_persons"
    __table_args__ = (UniqueConstraint("document_id", "person_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False,
    )
    person_id: Mapped[int] = mapped_column(
        ForeignKey("persons.id", ondelete="CASCADE"), nullable=False,
    )
    raw_mention: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[str] = mapped_column(String(20), nullable=False)
    role: Mapped[str] = mapped_column(String(30), nullable=False, server_default="mentioned")
    source_excerpt: Mapped[str | None] = mapped_column(Text)
    bio_review_status: Mapped[str | None] = mapped_column(String(30))
    bio_review_result: Mapped[dict | None] = mapped_column(JSONB)
    bio_reviewed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(),
    )

    document: Mapped["Document"] = relationship(foreign_keys=[document_id])
    person: Mapped["Person"] = relationship(foreign_keys=[person_id])

    def __repr__(self) -> str:
        return (
            f"DocumentPerson(id={self.id!r}, document_id={self.document_id!r}, "
            f"person_id={self.person_id!r}, confidence={self.confidence!r})"
        )


class InformationSource(Base):
    """Canonical publisher/reporting/data source mentioned by documents.

    This is intentionally separate from ``DiscoverySource``: DiscoverySource records how the
    user discovered a document, while InformationSource records where claims
    or reporting contained in the document originated.
    """

    __tablename__ = "information_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    canonical_name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    source_type: Mapped[str | None] = mapped_column(String(30))
    domain: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    # Set only when this source IS an organization mentioned via NER (orgName).
    # NULL for URL-domain publisher entries and LLM-extracted sources that
    # never resolved through the organizations registry — see
    # docs/organization-ner-alias-plan.md.
    organization_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), unique=True,
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(),
    )

    aliases: Mapped[list["InformationSourceAlias"]] = relationship(
        back_populates="source", cascade="all, delete-orphan",
    )
    organization: Mapped["Organization | None"] = relationship(foreign_keys=[organization_id])


class InformationSourceAlias(Base):
    """Observed alternate name, e.g. WSJ for The Wall Street Journal."""

    __tablename__ = "information_source_aliases"
    __table_args__ = (UniqueConstraint("source_id", "alias"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("information_sources.id", ondelete="CASCADE"), nullable=False,
    )
    alias: Mapped[str] = mapped_column(Text, nullable=False)

    source: Mapped["InformationSource"] = relationship(back_populates="aliases")


class DocumentInformationSource(Base):
    """Document-to-information-source provenance with role and evidence."""

    __tablename__ = "document_information_sources"
    __table_args__ = (UniqueConstraint("document_id", "source_id", "role"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False,
    )
    source_id: Mapped[int] = mapped_column(
        ForeignKey("information_sources.id", ondelete="CASCADE"), nullable=False,
    )
    role: Mapped[str] = mapped_column(String(30), nullable=False)
    raw_mention: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    evidence_excerpt: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[int | None] = mapped_column(Integer)
    extraction_method: Mapped[str] = mapped_column(String(30), nullable=False)
    review_status: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default="auto_accepted",
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(),
    )

    document: Mapped["Document"] = relationship(foreign_keys=[document_id])
    source: Mapped["InformationSource"] = relationship(foreign_keys=[source_id])


class Organization(Base):
    """Canonical organization entity — one row per real organization (orgName NER).

    Analogous to Person, but deliberately simpler: no Wikidata/LLM
    disambiguation, no fuzzy auto-merge (docs/organization-ner-alias-plan.md).
    canonical_name is intentionally not unique — two different organizations
    could share a display name; disambiguation is out of scope for now.
    """

    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(
        String(100), nullable=False, unique=True, server_default=func.gen_random_uuid(),
    )
    canonical_name: Mapped[str] = mapped_column(Text, nullable=False)
    organization_type: Mapped[str | None] = mapped_column(String(30))
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(),
    )

    aliases: Mapped[list["OrganizationAlias"]] = relationship(
        back_populates="organization", cascade="all, delete-orphan",
    )
    ambiguous_aliases: Mapped[list["OrganizationAmbiguousAlias"]] = relationship(
        back_populates="organization", cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"Organization(id={self.id!r}, canonical_name={self.canonical_name!r})"


class OrganizationAlias(Base):
    """Spelling variant of an organization's name seen in articles.

    normalized_alias is globally unique (unlike PersonAlias/InformationSourceAlias,
    which are unique only per-owner) — a name-merge decision must apply the same
    way to every future document, so one alias can never point at two different
    organizations (docs/organization-ner-alias-plan.md, point 3 of the review).
    """

    __tablename__ = "organization_aliases"
    __table_args__ = (UniqueConstraint("normalized_alias"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False,
    )
    alias: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_alias: Mapped[str] = mapped_column(Text, nullable=False)
    # alias_kind: inflection | abbreviation | former_name | manual | ner_observed
    alias_kind: Mapped[str] = mapped_column(String(20), nullable=False, server_default="ner_observed")
    # created_by: manual | migration | ner
    created_by: Mapped[str] = mapped_column(String(20), nullable=False, server_default="ner")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(),
    )

    organization: Mapped["Organization"] = relationship(back_populates="aliases")

    def __repr__(self) -> str:
        return f"OrganizationAlias(id={self.id!r}, organization_id={self.organization_id!r}, alias={self.alias!r})"


class OrganizationAmbiguousAlias(Base):
    """One possible meaning of a context-dependent organization abbreviation.

    Unlike ``OrganizationAlias``, an ambiguous alias is deliberately *not*
    globally unique: the same abbreviation (for example ``SAF``) may refer to
    several organizations. It is candidate data for a document-context rule or
    an LLM decision, never an automatic global name-resolution rule.
    """

    __tablename__ = "organization_ambiguous_aliases"
    __table_args__ = (UniqueConstraint("organization_id", "normalized_alias"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False,
    )
    alias: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_alias: Mapped[str] = mapped_column(Text, nullable=False)
    # A compact cue supplied to a resolver, e.g. a country/domain distinction.
    context_hint: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(String(10))
    # approved | needs_review | retired
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="approved")
    created_by: Mapped[str] = mapped_column(String(20), nullable=False, server_default="manual")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(),
    )

    organization: Mapped["Organization"] = relationship(back_populates="ambiguous_aliases")

    def __repr__(self) -> str:
        return (
            "OrganizationAmbiguousAlias("
            f"id={self.id!r}, organization_id={self.organization_id!r}, alias={self.alias!r})"
        )


class DocumentOrganization(Base):
    """Document<->organization link (M:N).

    A pure link, mirroring DocumentPerson — mention_count/variants stay in
    DocumentEntity, not duplicated here (docs/organization-ner-alias-plan.md,
    point 2 of the review).
    """

    __tablename__ = "document_organizations"
    __table_args__ = (UniqueConstraint("document_id", "organization_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False,
    )
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False,
    )
    document_entity_id: Mapped[int | None] = mapped_column(
        ForeignKey("document_entities.id", ondelete="SET NULL"),
    )
    # confidence: alias_matched | canonical_matched | manual_confirmed | needs_review
    confidence: Mapped[str] = mapped_column(String(20), nullable=False)
    # Only an explicit human approval protects a link from a later NER refresh.
    review_status: Mapped[str] = mapped_column(String(30), nullable=False, server_default="auto_accepted")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(),
    )

    document: Mapped["Document"] = relationship(foreign_keys=[document_id])
    organization: Mapped["Organization"] = relationship(foreign_keys=[organization_id])

    def __repr__(self) -> str:
        return (
            f"DocumentOrganization(id={self.id!r}, document_id={self.document_id!r}, "
            f"organization_id={self.organization_id!r})"
        )


class DocumentRelationshipRemoval(Base):
    """Immutable audit record for derived links removed during a refresh."""

    __tablename__ = "document_relationship_removals"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    relation_type: Mapped[str] = mapped_column(String(40), nullable=False)
    original_row_id: Mapped[int | None] = mapped_column(BigInteger)
    snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    removal_reason: Mapped[str] = mapped_column(String(80), nullable=False)
    removed_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    document: Mapped["Document"] = relationship(foreign_keys=[document_id])


class DocumentSourceRelationship(Base):
    """A reviewer decision about a grounded information-provenance relation."""

    __tablename__ = "document_source_relationships"
    __table_args__ = (UniqueConstraint("document_id", "subject_name", "predicate", "object_name", "evidence_excerpt"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    chunk_id: Mapped[int | None] = mapped_column(ForeignKey("document_chunks.id", ondelete="SET NULL"))
    subject_name: Mapped[str] = mapped_column(Text, nullable=False)
    predicate: Mapped[str] = mapped_column(String(40), nullable=False)
    object_name: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="proposed")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    decided_at: Mapped[datetime.datetime | None] = mapped_column(DateTime)

    document: Mapped["Document"] = relationship(foreign_keys=[document_id])


class User(Base):
    """Reader identity (household trust model).

    x-api-key stays the app-level auth; the x-user-id header only says WHO is
    reading — no passwords. Owns reading progress and document notes.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    display_name: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(),
    )

    def __repr__(self) -> str:
        return f"User(id={self.id!r}, username={self.username!r})"


class UserReadingProgress(Base):
    """Per-(user, document) reading position for the /read/:id reader.

    Chapter positions are 1-based and match GET /document/<id>/chapters
    (computed on the fly from text_md — independent of analysis runs).
    Renormalizing a book may shift positions; current_chapter_title is a
    snapshot that lets the UI notice the mismatch.
    """

    __tablename__ = "user_reading_progress"
    __table_args__ = (
        UniqueConstraint("user_id", "document_id", name="uq_reading_progress_user_document"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
    )
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False,
    )
    current_chapter: Mapped[int] = mapped_column(Integer, nullable=False)
    current_chapter_title: Mapped[str | None] = mapped_column(String(500))
    read_chapters: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), nullable=False, server_default=sa_text("'{}'"),
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(),
    )

    user: Mapped["User"] = relationship(foreign_keys=[user_id])
    document: Mapped["Document"] = relationship(foreign_keys=[document_id])

    def __repr__(self) -> str:
        return (
            f"UserReadingProgress(user_id={self.user_id!r}, document_id={self.document_id!r}, "
            f"current_chapter={self.current_chapter!r})"
        )


class UserDocumentNote(Base):
    """User note/reaction anchored to a document fragment.

    Anchored by exact quote + surrounding context (W3C TextQuoteSelector
    style) at the DOCUMENT level so the note survives analysis-run deletion;
    run_id/chunk_id are convenience links only (SET NULL). chapter_position
    is a hint where to re-anchor. stance: agree | disagree | neutral | NULL.
    """

    __tablename__ = "user_document_notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
    )
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False,
    )
    chapter_position: Mapped[int | None] = mapped_column(Integer)
    anchor_quote: Mapped[str] = mapped_column(Text, nullable=False)
    anchor_prefix: Mapped[str | None] = mapped_column(String(100))
    anchor_suffix: Mapped[str | None] = mapped_column(String(100))
    run_id: Mapped[int | None] = mapped_column(
        ForeignKey("document_analysis_runs.id", ondelete="SET NULL"),
    )
    chunk_id: Mapped[int | None] = mapped_column(
        ForeignKey("document_chunks.id", ondelete="SET NULL"),
    )
    note_text: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(String(80)), nullable=False, server_default=sa_text("'{}'"),
    )
    stance: Mapped[str | None] = mapped_column(String(10))
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(),
    )

    user: Mapped["User"] = relationship(foreign_keys=[user_id])
    document: Mapped["Document"] = relationship(foreign_keys=[document_id])

    def __repr__(self) -> str:
        return (
            f"UserDocumentNote(id={self.id!r}, user_id={self.user_id!r}, "
            f"document_id={self.document_id!r}, chapter_position={self.chapter_position!r})"
        )


class ApiKey(Base):
    """API key: service account (kind=service) or per-user key (kind=user).

    Only the SHA-256 hash of the plaintext key is stored; the plaintext is
    returned once at creation. kind=user keys carry the reader identity
    (user_id), replacing the x-user-id header. key_prefix keeps the first
    characters of the plaintext for recognizing keys without revealing them.
    """

    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa_text("TRUE"))
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(),
    )
    last_used_at: Mapped[datetime.datetime | None] = mapped_column(DateTime)

    user: Mapped["User | None"] = relationship(foreign_keys=[user_id])

    def __repr__(self) -> str:
        return f"ApiKey(id={self.id!r}, kind={self.kind!r}, name={self.name!r}, active={self.active!r})"


# ---------------------------------------------------------------------------
# Search audit and LLM usage (docs/search-rebuild-implementation-plan.md, stage 2)
# ---------------------------------------------------------------------------


class SearchInterpretationLog(Base):
    """Audit record of one attempt to interpret a natural-language search query.

    Stores the raw user query, the raw LLM response, the parsed/normalised
    interpretation and the outcome status (see InterpretationStatus in
    library/search/types.py). User feedback and a corrected interpretation are
    attached to the same row. Rows expire after the retention window
    (ADR-017: 90 days) via expires_at; raw queries may contain private data.
    """

    __tablename__ = "search_interpretation_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    raw_query: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str | None] = mapped_column(String(100))
    parser_version: Mapped[str | None] = mapped_column(String(50))
    prompt_version: Mapped[str | None] = mapped_column(String(50))
    raw_response: Mapped[str | None] = mapped_column(Text)
    parsed_query: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(50))
    error_message: Mapped[str | None] = mapped_column(Text)
    fallback_used: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa_text("FALSE"))
    llm_latency_ms: Mapped[int | None] = mapped_column(Integer)
    search_latency_ms: Mapped[int | None] = mapped_column(Integer)
    result_count: Mapped[int | None] = mapped_column(Integer)
    feedback_verdict: Mapped[str | None] = mapped_column(String(20))
    feedback_comment: Mapped[str | None] = mapped_column(Text)
    corrected_query: Mapped[dict | None] = mapped_column(JSONB)
    feedback_at: Mapped[datetime.datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(),
    )
    expires_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=sa_text("NOW() + INTERVAL '90 days'"),
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('parsed', 'ambiguous', 'invalid_json', 'validation_error', 'llm_error', 'fallback')",
            name="ck_search_interpretation_logs_status",
        ),
        CheckConstraint(
            "feedback_verdict IS NULL OR feedback_verdict IN ('correct', 'partially_correct', 'incorrect')",
            name="ck_search_interpretation_logs_feedback",
        ),
        Index("idx_search_interpretation_logs_created", "created_at"),
        Index("idx_search_interpretation_logs_status_created", "status", "created_at"),
        Index("idx_search_interpretation_logs_expires", "expires_at"),
    )

    usage_logs: Mapped[list["LlmUsageLog"]] = relationship(back_populates="search_interpretation_log")

    def __repr__(self) -> str:
        return (
            f"SearchInterpretationLog(id={self.id!r}, status={self.status!r}, "
            f"fallback_used={self.fallback_used!r}, created_at={self.created_at!r})"
        )


class LlmPricing(Base):
    """Versioned price list entry for one provider/model.

    Rows are immutable facts: a price change is a new row with a new
    pricing_version and effective_from, never an UPDATE — historical usage
    records must keep pointing at the rates that were valid when they were
    written. At most one open-ended (effective_to IS NULL) row per
    provider/model is allowed (partial unique index).
    """

    __tablename__ = "llm_pricing"

    id: Mapped[int] = mapped_column(primary_key=True)
    pricing_version: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    pricing_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    input_price_per_million: Mapped[decimal.Decimal | None] = mapped_column(Numeric(12, 6))
    output_price_per_million: Mapped[decimal.Decimal | None] = mapped_column(Numeric(12, 6))
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    effective_from: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[datetime.date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(),
    )

    __table_args__ = (
        CheckConstraint(
            "pricing_mode IN ('per_token', 'per_request', 'credits', 'subscription', 'free', 'unknown')",
            name="ck_llm_pricing_mode",
        ),
        Index(
            "uq_llm_pricing_active_model",
            "provider",
            "model",
            unique=True,
            postgresql_where=sa_text("effective_to IS NULL"),
        ),
    )

    def __repr__(self) -> str:
        return (
            f"LlmPricing(id={self.id!r}, pricing_version={self.pricing_version!r}, "
            f"provider={self.provider!r}, model={self.model!r})"
        )


class LlmUsageLog(Base):
    """One record per LLM/embedding call, independent of provider and model.

    Token counts are measured facts and are stored even when no price is
    known. Rates and currency are a denormalised snapshot of the pricing row
    used at write time, so later price changes never alter history. Money is
    NUMERIC/Decimal only; cost_status says how cost_amount was obtained
    (reported/estimated/allocated) or 'unknown' when it could not be.
    """

    __tablename__ = "llm_usage_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    request_id: Mapped[str | None] = mapped_column(String(64))
    search_interpretation_log_id: Mapped[int | None] = mapped_column(
        ForeignKey("search_interpretation_logs.id", ondelete="SET NULL"),
    )
    document_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"),
    )
    analysis_job_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("document_analysis_jobs.id", ondelete="SET NULL"),
    )
    analysis_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("document_analysis_runs.id", ondelete="SET NULL"),
    )
    operation: Mapped[str] = mapped_column(String(50), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    endpoint: Mapped[str | None] = mapped_column(String(200))
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    total_tokens: Mapped[int | None] = mapped_column(Integer)
    credits_used: Mapped[decimal.Decimal | None] = mapped_column(Numeric(18, 6))
    pricing_mode: Mapped[str] = mapped_column(String(20), nullable=False, server_default=sa_text("'unknown'"))
    pricing_version: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("llm_pricing.pricing_version"),
    )
    input_price_per_million: Mapped[decimal.Decimal | None] = mapped_column(Numeric(12, 6))
    output_price_per_million: Mapped[decimal.Decimal | None] = mapped_column(Numeric(12, 6))
    cost_amount: Mapped[decimal.Decimal | None] = mapped_column(Numeric(18, 10))
    cost_currency: Mapped[str | None] = mapped_column(String(3))
    cost_status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=sa_text("'unknown'"))
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa_text("TRUE"))
    error_code: Mapped[str | None] = mapped_column(String(100))
    called_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(),
    )
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(),
    )

    __table_args__ = (
        CheckConstraint(
            "pricing_mode IN ('per_token', 'per_request', 'credits', 'subscription', 'free', 'unknown')",
            name="ck_llm_usage_logs_pricing_mode",
        ),
        CheckConstraint(
            "cost_status IN ('reported', 'estimated', 'allocated', 'unknown')",
            name="ck_llm_usage_logs_cost_status",
        ),
        CheckConstraint(
            "(prompt_tokens IS NULL OR prompt_tokens >= 0)"
            " AND (completion_tokens IS NULL OR completion_tokens >= 0)"
            " AND (total_tokens IS NULL OR total_tokens >= 0)",
            name="ck_llm_usage_logs_tokens_nonneg",
        ),
        Index("idx_llm_usage_logs_called", "called_at"),
        Index("idx_llm_usage_logs_operation_called", "operation", "called_at"),
        Index("idx_llm_usage_logs_provider_model_called", "provider", "model", "called_at"),
        Index("idx_llm_usage_logs_document_called", "document_id", "called_at"),
        Index("idx_llm_usage_logs_analysis_job", "analysis_job_id"),
        Index("idx_llm_usage_logs_analysis_run", "analysis_run_id"),
        Index(
            "idx_llm_usage_logs_interpretation",
            "search_interpretation_log_id",
            postgresql_where=sa_text("search_interpretation_log_id IS NOT NULL"),
        ),
    )

    search_interpretation_log: Mapped["SearchInterpretationLog | None"] = relationship(
        back_populates="usage_logs",
    )
    pricing: Mapped["LlmPricing | None"] = relationship(foreign_keys=[pricing_version])

    def __repr__(self) -> str:
        return (
            f"LlmUsageLog(id={self.id!r}, operation={self.operation!r}, provider={self.provider!r}, "
            f"model={self.model!r}, cost_status={self.cost_status!r})"
        )


class ExternalServiceEvent(Base):
    """Outcome of one real request to a non-LLM external dependency."""

    __tablename__ = "external_service_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    service: Mapped[str] = mapped_column(String(50), nullable=False)
    operation: Mapped[str] = mapped_column(String(100), nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    status_code: Mapped[int | None] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(100))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    occurred_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(),
    )

    __table_args__ = (
        Index("idx_external_service_events_service_occurred", "service", "occurred_at"),
    )


class ToolCandidate(Base):
    """Bielik-detected tool/technology mention pending human review (Epic 43)."""

    __tablename__ = "tool_candidates"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=sa_text("'pending'"))
    source_document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    context_snippet: Mapped[str | None] = mapped_column(Text)
    detected_by: Mapped[str] = mapped_column(String(50), nullable=False, server_default=sa_text("'bielik'"))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    reviewed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("status IN ('pending', 'accepted', 'rejected', 'deferred')", name="ck_tool_candidates_status"),
        Index("idx_tool_candidates_source_status", "source_document_id", "status"),
    )


class ToolRecommendation(Base):
    """A recommendation worth remembering before it becomes a personally approved Tool.

    This deliberately preserves the distinction between somebody else's
    recommendation and a tool that has been evaluated and written to the
    personal catalog/Obsidian.
    """

    __tablename__ = "tool_recommendations"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    homepage_url: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=sa_text("'watchlist'"))
    personal_note: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    source_context: Mapped[str | None] = mapped_column(Text)
    source_document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
    source_candidate_id: Mapped[int | None] = mapped_column(ForeignKey("tool_candidates.id", ondelete="SET NULL"))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "status IN ('watchlist', 'compare', 'testing', 'adopted', 'rejected', 'archived')",
            name="ck_tool_recommendations_status",
        ),
        Index("idx_tool_recommendations_status_created", "status", "created_at"),
        Index("idx_tool_recommendations_source_candidate", "source_candidate_id"),
    )

    source_document: Mapped["Document | None"] = relationship(foreign_keys=[source_document_id])
    source_candidate: Mapped["ToolCandidate | None"] = relationship(foreign_keys=[source_candidate_id])
    evidences: Mapped[list["ToolRecommendationEvidence"]] = relationship(
        back_populates="tool_recommendation", cascade="all, delete-orphan",
    )


class ToolRecommendationEvidence(Base):
    """One directed provenance path supporting a tool recommendation.

    ``catalog_url`` is the intermediate external node (for example an Awesome
    list); ``recommender_document`` is the optional upstream Lenie document
    which recommended that catalog. More than one row may point at the same
    tool, so independent recommendations are never lost during deduplication.
    """

    __tablename__ = "tool_recommendation_evidence"

    id: Mapped[int] = mapped_column(primary_key=True)
    tool_recommendation_id: Mapped[int] = mapped_column(
        ForeignKey("tool_recommendations.id", ondelete="CASCADE"), nullable=False,
    )
    relation_type: Mapped[str] = mapped_column(String(30), nullable=False, server_default=sa_text("'listed_in'"))
    catalog_url: Mapped[str | None] = mapped_column(Text)
    catalog_label: Mapped[str | None] = mapped_column(String(255))
    context: Mapped[str | None] = mapped_column(Text)
    recommender_document_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"),
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    __table_args__ = (
        CheckConstraint("relation_type IN ('listed_in', 'recommended_by', 'mentioned_in')", name="ck_tool_recommendation_evidence_relation_type"),
        Index("idx_tool_recommendation_evidence_tool", "tool_recommendation_id"),
        Index("idx_tool_recommendation_evidence_recommender", "recommender_document_id"),
    )

    tool_recommendation: Mapped["ToolRecommendation"] = relationship(back_populates="evidences")
    recommender_document: Mapped["Document | None"] = relationship(foreign_keys=[recommender_document_id])


class Tool(Base):
    """Human-approved tool/technology entity, written to Obsidian (Epic 46/47).

    Schema pulled forward from Story 46.1 by Story 44.2 — AC #5's trigram
    duplicate check needs a real `name` column to query against. See Story
    44.2 Dev Notes for why this deviates from Story 43.1's "don't create
    tables ahead of their assigned story" precedent. Only the schema is
    pulled forward — POST /tools, obsidian_vault.py, and the write sequence
    remain Epic 46/47 (backlog).
    """

    __tablename__ = "tools"

    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(
        String(36), unique=True, nullable=False, server_default=sa_text("gen_random_uuid()::text")
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category_tags: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=sa_text("'[]'::jsonb"))
    homepage_url: Mapped[str | None] = mapped_column(Text)
    license: Mapped[str | None] = mapped_column(String(100))
    pricing: Mapped[str | None] = mapped_column(Text)
    personal_notes: Mapped[str | None] = mapped_column(Text)
    source_document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
    source_candidate_id: Mapped[int | None] = mapped_column(ForeignKey("tool_candidates.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=sa_text("'accepted'"))
    obsidian_note_path: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ObsidianNoteVersion(Base):
    """Content-before/after snapshot for every vault write (Epic 47).

    Re-homed unchanged from archived Epic 38 Story 38.1 -- see Story 47.1
    Dev Notes. `tool_id` replaces the archived design's `article_id`
    since every write on this PRD's path is a Tool save, never a note
    about an article.
    """

    __tablename__ = "obsidian_note_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    note_path: Mapped[str] = mapped_column(Text, nullable=False)
    content_before: Mapped[str | None] = mapped_column(Text)
    content_after: Mapped[str] = mapped_column(Text, nullable=False)
    user_prompt: Mapped[str | None] = mapped_column(Text)
    tool_id: Mapped[int | None] = mapped_column(ForeignKey("tools.id", ondelete="SET NULL"))
    changed_by: Mapped[str] = mapped_column(Text, nullable=False, server_default=sa_text("'backend'"))
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ContactCategory(Base):
    """Lookup table for contact categories (e.g. "Osoba prywatna").

    Managed from the UI (like DiscoverySource) rather than a fixed enum, so
    new categories don't require a migration.
    """

    __tablename__ = "contact_categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa_text("true"))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    def __repr__(self) -> str:
        return f"ContactCategory(id={self.id!r}, name={self.name!r})"


class Contact(Base):
    """Private contact book entry — independent of the NER persons registry
    (library/person_registry.py): a contact here may never appear in any
    document. google_contact_resource_name is a placeholder for a future
    Google Contacts sync (no sync logic exists yet).
    """

    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(
        String(100), nullable=False, unique=True, server_default=func.gen_random_uuid(),
    )
    category_id: Mapped[int] = mapped_column(ForeignKey("contact_categories.id"), nullable=False)
    first_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone_number: Mapped[str | None] = mapped_column(String(30))
    email: Mapped[str | None] = mapped_column(String(255))
    linkedin_url: Mapped[str | None] = mapped_column(Text)
    company: Mapped[str | None] = mapped_column(String(200))
    position: Mapped[str | None] = mapped_column(String(200))
    address: Mapped[str | None] = mapped_column(Text)
    birthday: Mapped[datetime.date | None] = mapped_column(Date)
    pesel: Mapped[str | None] = mapped_column(String(11), unique=True)
    notes: Mapped[str | None] = mapped_column(Text)
    google_contact_resource_name: Mapped[str | None] = mapped_column(String(255), unique=True)
    whatsapp_profile: Mapped[dict | None] = mapped_column(JSONB)
    photo_storage_key: Mapped[str | None] = mapped_column(Text)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa_text("false"))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    category: Mapped["ContactCategory"] = relationship(foreign_keys=[category_id])
    groups: Mapped[list["ContactGroup"]] = relationship(
        secondary="contact_group_memberships", back_populates="contacts",
    )

    __table_args__ = (
        Index("idx_contacts_last_name", "last_name"),
        Index("idx_contacts_category", "category_id"),
        Index("idx_contacts_is_archived", "is_archived"),
    )

    def __repr__(self) -> str:
        return f"Contact(id={self.id!r}, last_name={self.last_name!r})"


class ContactRelationship(Base):
    """Directional link between two contacts (e.g. spouse, child).

    relationship_type describes what related_contact_id is to contact_id —
    (contact_id=Adam, related_contact_id=Zofia, relationship_type="żona")
    reads "Zofia is Adam's wife". Single row, no automatic reciprocal
    row/label — the UI shows outgoing and incoming rows separately instead
    of guessing Polish kinship-term inflection.
    """

    __tablename__ = "contact_relationships"
    __table_args__ = (
        CheckConstraint("contact_id != related_contact_id", name="ck_contact_relationships_not_self"),
        UniqueConstraint("contact_id", "related_contact_id", "relationship_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    contact_id: Mapped[int] = mapped_column(ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False)
    related_contact_id: Mapped[int] = mapped_column(ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False)
    relationship_type: Mapped[str] = mapped_column(String(50), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    contact: Mapped["Contact"] = relationship(foreign_keys=[contact_id])
    related_contact: Mapped["Contact"] = relationship(foreign_keys=[related_contact_id])

    def __repr__(self) -> str:
        return (
            f"ContactRelationship(id={self.id!r}, contact_id={self.contact_id!r}, "
            f"related_contact_id={self.related_contact_id!r}, relationship_type={self.relationship_type!r})"
        )


class ContactLookupResult(Base):
    """One OSINT lookup attempt for a contact (e.g. from /lenie-person-lookup):
    either "searched and found nothing" (status=no_results) or "found a
    possible match, not confirmed" (status=candidate) — a contact can have
    several candidate rows of the same lookup_type. Confirming a candidate
    is a status update here; by convention its url is then also copied into
    contacts.linkedin_url, which stays single-valued.
    """

    __tablename__ = "contact_lookup_results"
    __table_args__ = (
        CheckConstraint(
            "lookup_type IN ('phone', 'linkedin', 'web')", name="ck_contact_lookup_results_lookup_type",
        ),
        CheckConstraint(
            "status IN ('no_results', 'candidate', 'confirmed', 'rejected')",
            name="ck_contact_lookup_results_status",
        ),
        Index("idx_contact_lookup_results_contact", "contact_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    contact_id: Mapped[int] = mapped_column(ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False)
    lookup_type: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    url: Mapped[str | None] = mapped_column(Text)
    query_used: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    searched_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    contact: Mapped["Contact"] = relationship(foreign_keys=[contact_id])

    def __repr__(self) -> str:
        return (
            f"ContactLookupResult(id={self.id!r}, contact_id={self.contact_id!r}, "
            f"lookup_type={self.lookup_type!r}, status={self.status!r})"
        )


class ContactOrganization(Base):
    """One organizational affiliation of a contact. A contact can have
    several at once — the common Polish pattern this exists for is one JDG
    (jednoosobowa dzialalnosc gospodarcza, often opened purely for tax
    optimization) alongside a separate full-time job, plus maybe an unpaid
    board seat. contacts.company/position stay a single-value "headline"
    field; this table is the structured, multi-row picture.

    org_type: 'employment' (etat), 'jdg' (sole proprietorship), 'board'
    (unpaid officer/board role), 'ownership' (equity in a company, not a
    JDG), 'other'. status mirrors ContactLookupResult so an OSINT hit can be
    recorded here directly as 'candidate' and promoted later. address is
    this organization's own registered/business address — separate from
    contacts.address (the contact's personal address); the two coinciding
    for a JDG is a hypothesis to verify, never assumed.
    """

    __tablename__ = "contact_organizations"
    __table_args__ = (
        CheckConstraint(
            "org_type IN ('employment', 'jdg', 'board', 'ownership', 'other')",
            name="ck_contact_organizations_org_type",
        ),
        CheckConstraint(
            "status IN ('candidate', 'confirmed', 'rejected')", name="ck_contact_organizations_status",
        ),
        Index("idx_contact_organizations_contact", "contact_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    contact_id: Mapped[int] = mapped_column(ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False)
    org_type: Mapped[str] = mapped_column(String(20), nullable=False)
    organization_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str | None] = mapped_column(String(200))
    nip: Mapped[str | None] = mapped_column(String(15))
    regon: Mapped[str | None] = mapped_column(String(20))
    address: Mapped[str | None] = mapped_column(Text)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa_text("false"))
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa_text("true"))
    start_date: Mapped[datetime.date | None] = mapped_column(Date)
    end_date: Mapped[datetime.date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="confirmed")
    source_url: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    contact: Mapped["Contact"] = relationship(foreign_keys=[contact_id])

    def __repr__(self) -> str:
        return (
            f"ContactOrganization(id={self.id!r}, contact_id={self.contact_id!r}, "
            f"org_type={self.org_type!r}, organization_name={self.organization_name!r})"
        )


class ContactGroup(Base):
    """User-managed many-to-many group for the private contact book (e.g.
    "Tuwima Gardens", "Rodzina") — distinct from ContactCategory, which is a
    single-value type classification per contact.
    """

    __tablename__ = "contact_groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    contacts: Mapped[list["Contact"]] = relationship(
        secondary="contact_group_memberships", back_populates="groups",
    )

    def __repr__(self) -> str:
        return f"ContactGroup(id={self.id!r}, name={self.name!r})"


class ContactGroupMembership(Base):
    __tablename__ = "contact_group_memberships"

    contact_id: Mapped[int] = mapped_column(ForeignKey("contacts.id", ondelete="CASCADE"), primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("contact_groups.id", ondelete="RESTRICT"), primary_key=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        Index("idx_contact_group_memberships_group_id", "group_id"),
    )


class ContactChangeLog(Base):
    """Append-only audit trail for a contact: how it was created/updated and
    why — 'manual_edit' (UI), 'google_import' (google_contacts_import.py),
    'whatsapp_analysis' (whatsapp_neighbor_profiles.py), 'linkedin_analysis'
    (a confirmed ContactLookupResult promoted onto contacts.linkedin_url),
    'osint_lookup', 'other'. changed_fields lists which Contact columns
    changed in this event (diffed by the caller before commit); note is an
    optional free-text reason. Deliberately NOT full row versioning —
    contacts.updated_at remains the cheap "last touched" timestamp, this
    table is the readable trail behind it.
    """

    __tablename__ = "contact_change_log"
    __table_args__ = (
        CheckConstraint(
            "source IN ('manual_edit', 'google_import', 'linkedin_analysis', "
            "'whatsapp_analysis', 'osint_lookup', 'other')",
            name="ck_contact_change_log_source",
        ),
        Index("idx_contact_change_log_contact", "contact_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    contact_id: Mapped[int] = mapped_column(ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False)
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    changed_fields: Mapped[list[str]] = mapped_column(
        ARRAY(String(50)), nullable=False, server_default=sa_text("'{}'"),
    )
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    contact: Mapped["Contact"] = relationship(foreign_keys=[contact_id])

    def __repr__(self) -> str:
        return (
            f"ContactChangeLog(id={self.id!r}, contact_id={self.contact_id!r}, "
            f"source={self.source!r}, changed_fields={self.changed_fields!r})"
        )


# The pre-11d before_flush hook that auto-created `sources` rows for
# Document.source strings is gone: discovery-source resolution is explicit
# now — every writer goes through Document.set_discovery_source(), which
# auto-creates unknown names via DiscoverySource.ensure().
