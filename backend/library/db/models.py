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
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
    select,
    text as sa_text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from pgvector.sqlalchemy import Vector

from library.db.engine import Base
from library.models.stalker_document_status import StalkerDocumentStatus
from library.models.stalker_document_status_error import StalkerDocumentStatusError
from library.models.stalker_document_type import StalkerDocumentType

logger = logging.getLogger(__name__)


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
    source: Mapped[str | None] = mapped_column(Text)
    date_from: Mapped[datetime.date | None] = mapped_column(Date)
    original_id: Mapped[str | None] = mapped_column(Text)
    document_length: Mapped[int | None] = mapped_column(Integer)
    chapter_list: Mapped[str | None] = mapped_column(Text)

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
    transcript_needed: Mapped[bool | None] = mapped_column(Boolean, server_default=sa_text("false"))

    # Review & Obsidian tracking (Story 33.4, ADR-014)
    reviewed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime)
    obsidian_note_paths: Mapped[list] = mapped_column(JSONB, server_default=sa_text("'[]'"))

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
        if document_type == "movie":
            self.document_type = StalkerDocumentType.movie.name
        elif document_type == "youtube":
            self.document_type = StalkerDocumentType.youtube.name
        elif document_type == "link":
            self.document_type = StalkerDocumentType.link.name
        elif document_type in ["webpage", "website"]:
            self.document_type = StalkerDocumentType.webpage.name
        elif document_type in ["sms", "text_message"]:
            self.document_type = StalkerDocumentType.text_message.name
        elif document_type in ["text"]:
            self.document_type = StalkerDocumentType.text.name
        elif document_type in ["social_media_post", "social"]:
            self.document_type = StalkerDocumentType.social_media_post.name
        else:
            raise ValueError(
                f"document_type must be one of 'movie', 'webpage', 'text_message', 'text', 'link', 'social_media_post' not >{document_type}<"
            )

    def set_document_state(self, document_state: str) -> None:
        if document_state in ["ERROR_DOWNLOAD", "ERROR"]:
            self.document_state = StalkerDocumentStatus.ERROR.name
        elif document_state == "URL_ADDED":
            self.document_state = StalkerDocumentStatus.URL_ADDED.name
        elif document_state == "NEED_TRANSCRIPTION":
            self.document_state = StalkerDocumentStatus.NEED_TRANSCRIPTION.name
        elif document_state == "TRANSCRIPTION_DONE":
            self.document_state = StalkerDocumentStatus.TRANSCRIPTION_DONE.name
        elif document_state == "TRANSCRIPTION_IN_PROGRESS":
            self.document_state = StalkerDocumentStatus.TRANSCRIPTION_IN_PROGRESS.name
        elif document_state == "NEED_MANUAL_REVIEW":
            self.document_state = StalkerDocumentStatus.NEED_MANUAL_REVIEW.name
        elif document_state == "READY_FOR_TRANSLATION":
            self.document_state = StalkerDocumentStatus.READY_FOR_TRANSLATION.name
        elif document_state == "READY_FOR_EMBEDDING":
            self.document_state = StalkerDocumentStatus.READY_FOR_EMBEDDING.name
        elif document_state == "EMBEDDING_EXIST":
            self.document_state = StalkerDocumentStatus.EMBEDDING_EXIST.name
        elif document_state == "DOCUMENT_INTO_DATABASE":
            self.document_state = StalkerDocumentStatus.DOCUMENT_INTO_DATABASE.name
        elif document_state == "NEED_CLEAN_TEXT":
            self.document_state = StalkerDocumentStatus.NEED_CLEAN_TEXT.name
        elif document_state == "NEED_CLEAN_MD":
            self.document_state = StalkerDocumentStatus.NEED_CLEAN_MD.name
        elif document_state == "TEXT_TO_MD_DONE":
            self.document_state = StalkerDocumentStatus.NEED_CLEAN_MD.name
        elif document_state == "MD_SIMPLIFIED":
            self.document_state = StalkerDocumentStatus.MD_SIMPLIFIED.name
        elif document_state == "TRANSCRIPTION_DONE_AND_SPLIT_BY_CHAPTERS":
            self.document_state = StalkerDocumentStatus.TRANSCRIPTION_DONE_AND_SPLIT_BY_CHAPTERS.name
        elif document_state == "TEMPORARY_ERROR":
            self.document_state = StalkerDocumentStatus.TEMPORARY_ERROR.name
        else:
            raise ValueError("document_state must be one of the valid StalkerDocumentStatus values")

    def set_document_state_error(self, document_state_error: str | None) -> None:
        if document_state_error is None or document_state_error == "NONE":
            self.document_state_error = StalkerDocumentStatusError.NONE.name
        elif document_state_error == "ERROR_DOWNLOAD":
            self.document_state_error = StalkerDocumentStatusError.ERROR_DOWNLOAD.name
        elif document_state_error == "LINK_SUMMARY_MISSING":
            self.document_state_error = StalkerDocumentStatusError.LINK_SUMMARY_MISSING.name
        elif document_state_error == "TITLE_MISSING":
            self.document_state_error = StalkerDocumentStatusError.TITLE_MISSING.name
        elif document_state_error == "TEXT_MISSING":
            self.document_state_error = StalkerDocumentStatusError.TEXT_MISSING.name
        elif document_state_error == "TEXT_TRANSLATION_ERROR":
            self.document_state_error = StalkerDocumentStatusError.TEXT_TRANSLATION_ERROR.name
        elif document_state_error == "TITLE_TRANSLATION_ERROR":
            self.document_state_error = StalkerDocumentStatusError.TITLE_TRANSLATION_ERROR.name
        elif document_state_error == "SUMMARY_TRANSLATION_ERROR":
            self.document_state_error = StalkerDocumentStatusError.SUMMARY_TRANSLATION_ERROR.name
        elif document_state_error == "NO_URL_ERROR":
            self.document_state_error = StalkerDocumentStatusError.NO_URL_ERROR.name
        elif document_state_error == "EMBEDDING_ERROR":
            self.document_state_error = StalkerDocumentStatusError.EMBEDDING_ERROR.name
        elif document_state_error == "MISSING_TRANSLATION":
            self.document_state_error = StalkerDocumentStatusError.MISSING_TRANSLATION.name
        elif document_state_error == "TRANSLATION_ERROR":
            self.document_state_error = StalkerDocumentStatusError.TRANSLATION_ERROR.name
        elif document_state_error == "REGEX_ERROR":
            self.document_state_error = StalkerDocumentStatusError.REGEX_ERROR.name
        elif document_state_error == "TEXT_TO_MD_ERROR":
            self.document_state_error = StalkerDocumentStatusError.TEXT_TO_MD_ERROR.name
        elif document_state_error == "NO_CAPTIONS_AVAILABLE":
            self.document_state_error = StalkerDocumentStatusError.NO_CAPTIONS_AVAILABLE.name
        elif document_state_error == "CAPTIONS_LANGUAGE_MISMATCH":
            self.document_state_error = StalkerDocumentStatusError.CAPTIONS_LANGUAGE_MISMATCH.name
        elif document_state_error == "CAPTIONS_FETCH_ERROR":
            self.document_state_error = StalkerDocumentStatusError.CAPTIONS_FETCH_ERROR.name
        elif document_state_error == "TRANSCRIPTION_ERROR":
            self.document_state_error = StalkerDocumentStatusError.TRANSCRIPTION_ERROR.name
        elif document_state_error == "TRANSCRIPTION_INSUFFICIENT_FUNDS":
            self.document_state_error = StalkerDocumentStatusError.TRANSCRIPTION_INSUFFICIENT_FUNDS.name
        else:
            raise ValueError(
                f"document_state_error must be one of the valid StalkerDocumentStatusError values, not >{document_state_error}<"
            )

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
    created_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime, server_default=sa_text("CURRENT_TIMESTAMP"),
    )

    # Relationships
    document: Mapped["WebDocument"] = relationship(back_populates="embeddings")
    model_ref: Mapped["EmbeddingModel"] = relationship(foreign_keys=[model])


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
