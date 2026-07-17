"""SQLAlchemy ORM models for web_documents and websites_embeddings tables.

Provides:
- Lookup models: ``DocumentStatusType``, ``DocumentStatusErrorType``,
  ``DocumentType``, ``EmbeddingModel``
- ``WebDocument`` — Single Table Inheritance model for web_documents
- 6 STI subclasses: LinkDocument, YouTubeDocument, MovieDocument, etc.
- ``WebsiteEmbedding`` — model for websites_embeddings with pgvector support
"""

import datetime
import logging

from sqlalchemy import (
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
    event,
    func,
    select,
    text as sa_text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from pgvector.sqlalchemy import Vector

from library.db.engine import Base
from library.models.stalker_document_status import StalkerDocumentStatus
from library.models.stalker_document_status_error import StalkerDocumentStatusError
from library.models.stalker_document_type import StalkerDocumentType

logger = logging.getLogger(__name__)


DOCUMENT_TYPE_LOOKUP = {
    "movie": StalkerDocumentType.movie.name,
    "youtube": StalkerDocumentType.youtube.name,
    "link": StalkerDocumentType.link.name,
    "webpage": StalkerDocumentType.webpage.name,
    "website": StalkerDocumentType.webpage.name,
    "sms": StalkerDocumentType.text_message.name,
    "text_message": StalkerDocumentType.text_message.name,
    "text": StalkerDocumentType.text.name,
    "social_media_post": StalkerDocumentType.social_media_post.name,
    "social": StalkerDocumentType.social_media_post.name,
}

DOCUMENT_STATE_LOOKUP = {
    "ERROR_DOWNLOAD": StalkerDocumentStatus.ERROR.name,
    "ERROR": StalkerDocumentStatus.ERROR.name,
    "URL_ADDED": StalkerDocumentStatus.URL_ADDED.name,
    "NEED_TRANSCRIPTION": StalkerDocumentStatus.NEED_TRANSCRIPTION.name,
    "TRANSCRIPTION_DONE": StalkerDocumentStatus.TRANSCRIPTION_DONE.name,
    "TRANSCRIPTION_IN_PROGRESS": StalkerDocumentStatus.TRANSCRIPTION_IN_PROGRESS.name,
    "NEED_MANUAL_REVIEW": StalkerDocumentStatus.NEED_MANUAL_REVIEW.name,
    "READY_FOR_TRANSLATION": StalkerDocumentStatus.READY_FOR_TRANSLATION.name,
    "READY_FOR_EMBEDDING": StalkerDocumentStatus.READY_FOR_EMBEDDING.name,
    "EMBEDDING_EXIST": StalkerDocumentStatus.EMBEDDING_EXIST.name,
    "DOCUMENT_INTO_DATABASE": StalkerDocumentStatus.DOCUMENT_INTO_DATABASE.name,
    "NEED_CLEAN_TEXT": StalkerDocumentStatus.NEED_CLEAN_TEXT.name,
    "NEED_CLEAN_MD": StalkerDocumentStatus.NEED_CLEAN_MD.name,
    "TEXT_TO_MD_DONE": StalkerDocumentStatus.NEED_CLEAN_MD.name,
    "MD_SIMPLIFIED": StalkerDocumentStatus.MD_SIMPLIFIED.name,
    "TRANSCRIPTION_DONE_AND_SPLIT_BY_CHAPTERS": StalkerDocumentStatus.TRANSCRIPTION_DONE_AND_SPLIT_BY_CHAPTERS.name,
    "TEMPORARY_ERROR": StalkerDocumentStatus.TEMPORARY_ERROR.name,
}

DOCUMENT_STATE_ERROR_LOOKUP = {
    None: StalkerDocumentStatusError.NONE.name,
    "NONE": StalkerDocumentStatusError.NONE.name,
    "ERROR_DOWNLOAD": StalkerDocumentStatusError.ERROR_DOWNLOAD.name,
    "LINK_SUMMARY_MISSING": StalkerDocumentStatusError.LINK_SUMMARY_MISSING.name,
    "TITLE_MISSING": StalkerDocumentStatusError.TITLE_MISSING.name,
    "TEXT_MISSING": StalkerDocumentStatusError.TEXT_MISSING.name,
    "TEXT_TRANSLATION_ERROR": StalkerDocumentStatusError.TEXT_TRANSLATION_ERROR.name,
    "TITLE_TRANSLATION_ERROR": StalkerDocumentStatusError.TITLE_TRANSLATION_ERROR.name,
    "SUMMARY_TRANSLATION_ERROR": StalkerDocumentStatusError.SUMMARY_TRANSLATION_ERROR.name,
    "NO_URL_ERROR": StalkerDocumentStatusError.NO_URL_ERROR.name,
    "EMBEDDING_ERROR": StalkerDocumentStatusError.EMBEDDING_ERROR.name,
    "MISSING_TRANSLATION": StalkerDocumentStatusError.MISSING_TRANSLATION.name,
    "TRANSLATION_ERROR": StalkerDocumentStatusError.TRANSLATION_ERROR.name,
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
    __tablename__ = "document_status_types"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)

    def __repr__(self) -> str:
        return f"DocumentStatusType(id={self.id!r}, name={self.name!r})"


class DocumentStatusErrorType(Base):
    __tablename__ = "document_status_error_types"

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


class Source(Base):
    """Discovery source lookup — how the user found a document (NOT its author).

    web_documents.source references name (ADR-010) with ON UPDATE CASCADE, so
    renaming a source here rewrites all documents atomically. Deactivated
    sources stay valid on existing documents but disappear from pickers
    (GET /sources?active=1).
    """

    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa_text("true"))

    @classmethod
    def ensure(cls, session: Session, name: str) -> "Source | None":
        """Return the source row for ``name``, creating it if missing.

        Single get-or-create used by the before_flush hook and POST /sources —
        any write path may introduce a new source without violating fk_source.
        """
        name = (name or "").strip()
        if not name:
            return None
        existing = session.execute(
            select(cls).where(cls.name == name)
        ).scalar_one_or_none()
        if existing is not None:
            return existing
        row = cls(name=name)
        session.add(row)
        return row

    def __repr__(self) -> str:
        return f"Source(id={self.id!r}, name={self.name!r}, is_active={self.is_active!r})"


# ---------------------------------------------------------------------------
# WebDocument — Single Table Inheritance on web_documents
# ---------------------------------------------------------------------------


class WebDocument(Base):
    __tablename__ = "web_documents"

    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True)

    # Content fields (order matches DDL in 03-create-table.sql)
    summary: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str | None] = mapped_column(String(10))
    tags: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str | None] = mapped_column(Text)
    paywall: Mapped[bool | None] = mapped_column(Boolean, server_default=sa_text("false"))
    title: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime, server_default=sa_text("CURRENT_TIMESTAMP"),
    )

    # FK columns — reference lookup tables by name (ADR-010)
    document_type: Mapped[str] = mapped_column(
        String(50), ForeignKey("document_types.name"), nullable=False,
    )

    # How the user discovered this content (e.g. "own", "unknow.news", "friend").
    # Used to evaluate recommendation source quality over time — NOT who created the content.
    # FK by name (ADR-010); unknown values are auto-created in `sources` by the
    # before_flush hook at the bottom of this module.
    source: Mapped[str | None] = mapped_column(Text, ForeignKey("sources.name"))
    date_from: Mapped[datetime.date | None] = mapped_column(Date)
    original_id: Mapped[str | None] = mapped_column(Text)
    document_length: Mapped[int | None] = mapped_column(Integer)
    chapter_list: Mapped[str | None] = mapped_column(Text)
    video_description: Mapped[str | None] = mapped_column(Text)

    document_state: Mapped[str] = mapped_column(
        String(50), ForeignKey("document_status_types.name"),
        nullable=False, server_default="URL_ADDED",
    )
    document_state_error: Mapped[str | None] = mapped_column(
        String, ForeignKey("document_status_error_types.name"), nullable=True,
    )

    text_raw: Mapped[str | None] = mapped_column(Text)
    transcript_job_id: Mapped[str | None] = mapped_column(Text)
    ai_summary_needed: Mapped[bool | None] = mapped_column(Boolean, server_default=sa_text("false"))
    # Content creator: YouTube channel name, article author, etc. — metadata about who made it.
    author: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    uuid: Mapped[str] = mapped_column(
        String(100), nullable=False, unique=True,
        server_default=func.gen_random_uuid(),
    )
    project: Mapped[str | None] = mapped_column(String(100))
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

    # Article quality ("staranność") assessment — JSONB: score 0-100, per-signal
    # penalties (photo captions, missing author, noise share, ...) and the LLM
    # rubric. Computed by library/article_quality.py at the end of an article-mode
    # analysis run, or on demand via POST /document/<id>/quality.
    quality: Mapped[dict | None] = mapped_column(JSONB)

    # Lookup-table relationships (many-to-one)
    document_type_ref: Mapped["DocumentType"] = relationship(
        foreign_keys=[document_type],
    )
    document_state_ref: Mapped["DocumentStatusType"] = relationship(
        foreign_keys=[document_state],
    )
    document_state_error_ref: Mapped["DocumentStatusErrorType | None"] = relationship(
        foreign_keys=[document_state_error],
    )

    # Relationship to embeddings
    embeddings: Mapped[list["WebsiteEmbedding"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
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
    def populate_neighbors(cls, session: Session, doc: "WebDocument") -> None:
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
    def get_by_id(cls, session: Session, doc_id: int, reach: bool = False) -> "WebDocument | None":
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
    def get_by_url(cls, session: Session, url: str) -> "WebDocument | None":
        """Return document matching the given URL, or None."""
        return session.scalars(
            select(cls).where(cls.url == url)
        ).first()

    # --- Domain methods (migrated from stalker_web_document.py) ---

    def set_document_type(self, document_type: str) -> None:
        mapped_type = DOCUMENT_TYPE_LOOKUP.get(document_type)
        if mapped_type is None:
            raise ValueError(
                f"document_type must be one of 'movie', 'webpage', 'text_message', 'text', 'link', 'social_media_post' not >{document_type}<"
            )
        self.document_type = mapped_type

    def set_document_state(self, document_state: str) -> None:
        mapped_state = DOCUMENT_STATE_LOOKUP.get(document_state)
        if mapped_state is None:
            raise ValueError("document_state must be one of the valid StalkerDocumentStatus values")
        self.document_state = mapped_state

    def set_document_state_error(self, document_state_error: str | None) -> None:
        mapped_state_error = DOCUMENT_STATE_ERROR_LOOKUP.get(document_state_error)
        if mapped_state_error is None:
            raise ValueError(
                f"document_state_error must be one of the valid StalkerDocumentStatusError values, not >{document_state_error}<"
            )
        self.document_state_error = mapped_state_error

    def analyze(self) -> None:
        if self.document_state == StalkerDocumentStatus.EMBEDDING_EXIST.name:
            return None

        if not self.text_raw:
            logger.info("This is adding new entry, so raw text is equal to text")
            self.text_raw = self.text

        if self.document_type == StalkerDocumentType.link.name:
            self.text = None

    def validate(self) -> None:
        self.document_state_error = StalkerDocumentStatusError.NONE.name

        if self.document_state == StalkerDocumentStatus.EMBEDDING_EXIST.name:
            return None

        if not self.title or len(self.title) < 3:
            self.document_state = StalkerDocumentStatus.NEED_MANUAL_REVIEW.name
            self.document_state_error = StalkerDocumentStatusError.TITLE_MISSING.name

        if self.document_type == StalkerDocumentType.link.name:
            if not self.summary or len(self.summary) < 3:
                self.document_state = StalkerDocumentStatus.NEED_MANUAL_REVIEW.name
                self.document_state_error = StalkerDocumentStatusError.LINK_SUMMARY_MISSING.name

        if self.document_type == StalkerDocumentType.webpage.name:
            if not self.text or len(self.text) < 3:
                self.document_state = StalkerDocumentStatus.NEED_MANUAL_REVIEW.name
                self.document_state_error = StalkerDocumentStatusError.TEXT_MISSING.name

    def dict(self):
        created_at_str = self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else None
        return {
            "id": self.id,
            "next_id": self.next_id,
            "next_type": self.next_type,
            "previous_id": self.previous_id,
            "previous_type": self.previous_type,
            "summary": self.summary,
            "url": self.url,
            "language": self.language,
            "tags": self.tags,
            "text": self.text,
            "paywall": self.paywall,
            "title": self.title,
            "created_at": created_at_str,
            "document_type": self.document_type,
            "source": self.source,
            "date_from": self.date_from,
            "original_id": self.original_id,
            "document_length": self.document_length,
            "chapter_list": self.chapter_list,
            "video_description": self.video_description,
            "document_state": self.document_state,
            "document_state_error": self.document_state_error or "NONE",
            "text_raw": self.text_raw,
            "transcript_job_id": self.transcript_job_id,
            "ai_summary_needed": self.ai_summary_needed,
            "author": self.author,
            "note": self.note,
            "uuid": self.uuid,
            "project": self.project,
            "text_md": self.text_md,
            "transcript_needed": self.transcript_needed,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "obsidian_note_paths": self.obsidian_note_paths or [],
            "quality": self.quality,
        }


# ---------------------------------------------------------------------------
# STI Subclasses — one per document_type, no extra columns
# ---------------------------------------------------------------------------


class LinkDocument(WebDocument):
    __mapper_args__ = {"polymorphic_identity": "link"}


class YouTubeDocument(WebDocument):
    __mapper_args__ = {"polymorphic_identity": "youtube"}


class MovieDocument(WebDocument):
    __mapper_args__ = {"polymorphic_identity": "movie"}


class WebpageDocument(WebDocument):
    __mapper_args__ = {"polymorphic_identity": "webpage"}


class TextMessageDocument(WebDocument):
    __mapper_args__ = {"polymorphic_identity": "text_message"}


class TextDocument(WebDocument):
    __mapper_args__ = {"polymorphic_identity": "text"}


class SocialMediaPostDocument(WebDocument):
    __mapper_args__ = {"polymorphic_identity": "social_media_post"}


# ---------------------------------------------------------------------------
# WebsiteEmbedding — vector embeddings for document chunks
# ---------------------------------------------------------------------------


class WebsiteEmbedding(Base):
    __tablename__ = "websites_embeddings"

    id: Mapped[int] = mapped_column(primary_key=True)
    website_id: Mapped[int] = mapped_column(
        ForeignKey("web_documents.id", ondelete="CASCADE"),
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
    document: Mapped["WebDocument"] = relationship(back_populates="embeddings")
    model_ref: Mapped["EmbeddingModel"] = relationship(foreign_keys=[model])
    chunk: Mapped["DocumentChunk | None"] = relationship(foreign_keys=[chunk_id])


# ---------------------------------------------------------------------------
# TranscriptionLog — tracks transcription usage and costs
# ---------------------------------------------------------------------------


class TranscriptionLog(Base):
    __tablename__ = "transcription_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int | None] = mapped_column(
        ForeignKey("web_documents.id", ondelete="SET NULL"), nullable=True,
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    speech_model: Mapped[str | None] = mapped_column(String(100))
    audio_duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_usd: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False)
    transcript_job_id: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime, server_default=sa_text("CURRENT_TIMESTAMP"),
    )

    document: Mapped["WebDocument | None"] = relationship(foreign_keys=[document_id])

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
        ForeignKey("web_documents.id", ondelete="CASCADE"), nullable=False,
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

    document: Mapped["WebDocument"] = relationship(foreign_keys=[document_id])
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
        ForeignKey("web_documents.id", ondelete="CASCADE"), nullable=False,
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

    run: Mapped["DocumentAnalysisRun"] = relationship(back_populates="chunks")
    document: Mapped["WebDocument"] = relationship(foreign_keys=[document_id])

    def __repr__(self) -> str:
        return f"DocumentChunk(id={self.id!r}, run_id={self.run_id!r}, position={self.position!r}, type={self.type!r})"


class DocumentTopicSection(Base):
    __tablename__ = "document_topic_sections"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("document_analysis_runs.id", ondelete="CASCADE"), nullable=False,
    )
    document_id: Mapped[int] = mapped_column(
        ForeignKey("web_documents.id", ondelete="CASCADE"), nullable=False,
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
    document: Mapped["WebDocument"] = relationship(foreign_keys=[document_id])

    def __repr__(self) -> str:
        return f"DocumentTopicSection(id={self.id!r}, run_id={self.run_id!r}, position={self.position!r})"


class DocumentRemovedLine(Base):
    """Line/block removed from a document during manual chunk review cleanup.

    Training data for improving article_cleaner.py / site_rules.json: what the
    automatic cleaner missed and a human had to remove. Claude Code/Codex rule
    reviews should only inspect ``pending`` rows and record a terminal decision
    using ``scripts/review_removed_lines.py``. Rows survive run/chunk
    deletion (FKs SET NULL) so aggregate queries (e.g. most-removed lines per
    portal, via join on web_documents.url) keep working over time.
    """

    __tablename__ = "document_removed_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("web_documents.id", ondelete="CASCADE"), nullable=False,
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

    document: Mapped["WebDocument"] = relationship(foreign_keys=[document_id])

    def __repr__(self) -> str:
        return f"DocumentRemovedLine(id={self.id!r}, document_id={self.document_id!r}, source={self.source!r})"


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
        ForeignKey("web_documents.id", ondelete="CASCADE"), nullable=False,
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

    document: Mapped["WebDocument"] = relationship(foreign_keys=[document_id])

    def __repr__(self) -> str:
        return (
            f"DocumentReference(id={self.id!r}, document_id={self.document_id!r}, "
            f"chapter={self.chapter_position!r}, marker={self.marker!r})"
        )


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
        ForeignKey("web_documents.id", ondelete="CASCADE"), nullable=False,
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

    document: Mapped["WebDocument"] = relationship(foreign_keys=[document_id])
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
        ForeignKey("web_documents.id", ondelete="CASCADE"), nullable=False,
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

    document: Mapped["WebDocument"] = relationship(foreign_keys=[document_id])

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
        Index("idx_document_time_periods_years", "period_start_year", "period_end_year"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("web_documents.id", ondelete="CASCADE"), nullable=False,
    )
    chapter_position: Mapped[int | None] = mapped_column(Integer)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    period_label: Mapped[str] = mapped_column(String(100), nullable=False)
    period_start_year: Mapped[int | None] = mapped_column(Integer)
    period_end_year: Mapped[int | None] = mapped_column(Integer)
    confidence: Mapped[str] = mapped_column(String(10), nullable=False, default="low", server_default="low")
    evidence: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(),
    )

    document: Mapped["WebDocument"] = relationship(foreign_keys=[document_id])

    def __repr__(self) -> str:
        return (
            f"DocumentTimePeriod(id={self.id!r}, document_id={self.document_id!r}, "
            f"chapter={self.chapter_position!r}, period_label={self.period_label!r})"
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
        ForeignKey("web_documents.id", ondelete="CASCADE"), nullable=False,
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

    document: Mapped["WebDocument"] = relationship(foreign_keys=[document_id])

    def __repr__(self) -> str:
        return (
            f"DocumentTone(id={self.id!r}, document_id={self.document_id!r}, "
            f"chapter={self.chapter_position!r}, emotion={self.emotion!r})"
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
        ForeignKey("web_documents.id", ondelete="CASCADE"), nullable=False,
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

    document: Mapped["WebDocument"] = relationship(foreign_keys=[document_id])
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
        ForeignKey("web_documents.id", ondelete="CASCADE"), nullable=False,
    )
    # entity_type: persName | geogName | placeName (spaCy pl_core_news_lg labels)
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
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(),
    )

    document: Mapped["WebDocument"] = relationship(foreign_keys=[document_id])
    geocode: Mapped["GeocodeCache | None"] = relationship(foreign_keys=[geocode_id])

    def __repr__(self) -> str:
        return (
            f"DocumentEntity(id={self.id!r}, document_id={self.document_id!r}, "
            f"entity_type={self.entity_type!r}, entity_text={self.entity_text!r})"
        )


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
        ForeignKey("web_documents.id", ondelete="CASCADE"), nullable=False,
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

    document: Mapped["WebDocument"] = relationship(foreign_keys=[document_id])
    person: Mapped["Person"] = relationship(foreign_keys=[person_id])

    def __repr__(self) -> str:
        return (
            f"DocumentPerson(id={self.id!r}, document_id={self.document_id!r}, "
            f"person_id={self.person_id!r}, confidence={self.confidence!r})"
        )


class InformationSource(Base):
    """Canonical publisher/reporting/data source mentioned by documents.

    This is intentionally separate from ``Source``: Source records how the
    user discovered a document, while InformationSource records where claims
    or reporting contained in the document originated.
    """

    __tablename__ = "information_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    canonical_name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    source_type: Mapped[str | None] = mapped_column(String(30))
    domain: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(),
    )

    aliases: Mapped[list["InformationSourceAlias"]] = relationship(
        back_populates="source", cascade="all, delete-orphan",
    )


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
        ForeignKey("web_documents.id", ondelete="CASCADE"), nullable=False,
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

    document: Mapped["WebDocument"] = relationship(foreign_keys=[document_id])
    source: Mapped["InformationSource"] = relationship(foreign_keys=[source_id])


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
        ForeignKey("web_documents.id", ondelete="CASCADE"), nullable=False,
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
    document: Mapped["WebDocument"] = relationship(foreign_keys=[document_id])

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
        ForeignKey("web_documents.id", ondelete="CASCADE"), nullable=False,
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
    document: Mapped["WebDocument"] = relationship(foreign_keys=[document_id])

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
# Session events
# ---------------------------------------------------------------------------


@event.listens_for(Session, "before_flush")
def _ensure_document_sources_exist(session: Session, flush_context, instances) -> None:
    """Auto-create `sources` rows for WebDocument.source values (fk_source).

    Single choke point for every ORM write path (server endpoints, imports,
    feed monitor, DynamoDB sync, e-mail import): an unknown discovery source
    becomes a new active `sources` row instead of an IntegrityError. The
    unit of work inserts `sources` before `web_documents` (FK dependency).
    """
    seen: set[str] = set()
    for obj in list(session.new) + list(session.dirty):
        if not isinstance(obj, WebDocument):
            continue
        name = (obj.source or "").strip()
        if not name:
            # Whitespace-only values would violate fk_source — store NULL.
            if obj.source is not None:
                obj.source = None
            continue
        if obj.source != name:
            obj.source = name
        if name in seen:
            continue
        seen.add(name)
        Source.ensure(session, name)
