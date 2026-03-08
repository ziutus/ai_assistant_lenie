"""SQLAlchemy ORM models for web_documents and websites_embeddings tables.

Provides:
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
    Enum as SAEnum,
    ForeignKey,
    Integer,
    String,
    Text,
    text as sa_text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pgvector.sqlalchemy import Vector

from library.db.engine import Base
from library.models.stalker_document_status import StalkerDocumentStatus
from library.models.stalker_document_status_error import StalkerDocumentStatusError
from library.models.stalker_document_type import StalkerDocumentType

logger = logging.getLogger(__name__)


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

    # Enums — stored as VARCHAR, not native PostgreSQL ENUM types
    document_type: Mapped[StalkerDocumentType] = mapped_column(
        SAEnum(
            StalkerDocumentType,
            values_callable=lambda x: [e.name for e in x],
            native_enum=False,
            length=50,
        ),
        nullable=False,
    )

    source: Mapped[str | None] = mapped_column(Text)
    date_from: Mapped[datetime.date | None] = mapped_column(Date)
    original_id: Mapped[str | None] = mapped_column(Text)
    document_length: Mapped[int | None] = mapped_column(Integer)
    chapter_list: Mapped[str | None] = mapped_column(Text)

    document_state: Mapped[StalkerDocumentStatus] = mapped_column(
        SAEnum(
            StalkerDocumentStatus,
            values_callable=lambda x: [e.name for e in x],
            native_enum=False,
            length=50,
        ),
        nullable=False,
        server_default="URL_ADDED",
    )
    document_state_error: Mapped[StalkerDocumentStatusError | None] = mapped_column(
        SAEnum(
            StalkerDocumentStatusError,
            values_callable=lambda x: [e.name for e in x],
            native_enum=False,
            # No explicit length — DDL column is TEXT, not VARCHAR(50).
            # Alembic (Story 26.3) must handle this drift consciously.
        ),
    )

    text_raw: Mapped[str | None] = mapped_column(Text)
    transcript_job_id: Mapped[str | None] = mapped_column(Text)
    ai_summary_needed: Mapped[bool | None] = mapped_column(Boolean, server_default=sa_text("false"))
    author: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    s3_uuid: Mapped[str | None] = mapped_column(String(100))
    project: Mapped[str | None] = mapped_column(String(100))
    text_md: Mapped[str | None] = mapped_column(Text)
    transcript_needed: Mapped[bool | None] = mapped_column(Boolean, server_default=sa_text("false"))

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

    # --- Domain methods (migrated from stalker_web_document.py) ---

    def set_document_type(self, document_type: str) -> None:
        if document_type == "movie":
            self.document_type = StalkerDocumentType.movie
        elif document_type == "youtube":
            self.document_type = StalkerDocumentType.youtube
        elif document_type == "link":
            self.document_type = StalkerDocumentType.link
        elif document_type in ["webpage", "website"]:
            self.document_type = StalkerDocumentType.webpage
        elif document_type in ["sms", "text_message"]:
            self.document_type = StalkerDocumentType.text_message
        elif document_type in ["text"]:
            self.document_type = StalkerDocumentType.text
        else:
            raise ValueError(
                f"document_type must be either 'movie', 'webpage', 'text_message', 'text' or 'link' not >{document_type}<"
            )

    def set_document_state(self, document_state: str) -> None:
        if document_state in ["ERROR_DOWNLOAD", "ERROR"]:
            self.document_state = StalkerDocumentStatus.ERROR
        elif document_state == "URL_ADDED":
            self.document_state = StalkerDocumentStatus.URL_ADDED
        elif document_state == "NEED_TRANSCRIPTION":
            self.document_state = StalkerDocumentStatus.NEED_TRANSCRIPTION
        elif document_state == "TRANSCRIPTION_DONE":
            self.document_state = StalkerDocumentStatus.TRANSCRIPTION_DONE
        elif document_state == "TRANSCRIPTION_IN_PROGRESS":
            self.document_state = StalkerDocumentStatus.TRANSCRIPTION_IN_PROGRESS
        elif document_state == "NEED_MANUAL_REVIEW":
            self.document_state = StalkerDocumentStatus.NEED_MANUAL_REVIEW
        elif document_state == "READY_FOR_TRANSLATION":
            self.document_state = StalkerDocumentStatus.READY_FOR_TRANSLATION
        elif document_state == "READY_FOR_EMBEDDING":
            self.document_state = StalkerDocumentStatus.READY_FOR_EMBEDDING
        elif document_state == "EMBEDDING_EXIST":
            self.document_state = StalkerDocumentStatus.EMBEDDING_EXIST
        elif document_state == "DOCUMENT_INTO_DATABASE":
            self.document_state = StalkerDocumentStatus.DOCUMENT_INTO_DATABASE
        elif document_state == "NEED_CLEAN_TEXT":
            self.document_state = StalkerDocumentStatus.NEED_CLEAN_TEXT
        elif document_state == "NEED_CLEAN_MD":
            self.document_state = StalkerDocumentStatus.NEED_CLEAN_MD
        elif document_state == "TEXT_TO_MD_DONE":
            self.document_state = StalkerDocumentStatus.NEED_CLEAN_MD
        elif document_state == "MD_SIMPLIFIED":
            self.document_state = StalkerDocumentStatus.MD_SIMPLIFIED
        else:
            raise ValueError("document_state must be one of the valid StalkerDocumentStatus values")

    def set_document_state_error(self, document_state_error: str | None) -> None:
        if document_state_error is None or document_state_error == "NONE":
            self.document_state_error = StalkerDocumentStatusError.NONE
        elif document_state_error == "ERROR_DOWNLOAD":
            self.document_state_error = StalkerDocumentStatusError.ERROR_DOWNLOAD
        elif document_state_error == "LINK_SUMMARY_MISSING":
            self.document_state_error = StalkerDocumentStatusError.LINK_SUMMARY_MISSING
        elif document_state_error == "TITLE_MISSING":
            self.document_state_error = StalkerDocumentStatusError.TITLE_MISSING
        elif document_state_error == "TEXT_MISSING":
            self.document_state_error = StalkerDocumentStatusError.TEXT_MISSING
        elif document_state_error == "TEXT_TRANSLATION_ERROR":
            self.document_state_error = StalkerDocumentStatusError.TEXT_TRANSLATION_ERROR
        elif document_state_error == "TITLE_TRANSLATION_ERROR":
            self.document_state_error = StalkerDocumentStatusError.TITLE_TRANSLATION_ERROR
        elif document_state_error == "SUMMARY_TRANSLATION_ERROR":
            self.document_state_error = StalkerDocumentStatusError.SUMMARY_TRANSLATION_ERROR
        elif document_state_error == "NO_URL_ERROR":
            self.document_state_error = StalkerDocumentStatusError.NO_URL_ERROR
        elif document_state_error == "EMBEDDING_ERROR":
            self.document_state_error = StalkerDocumentStatusError.EMBEDDING_ERROR
        elif document_state_error == "MISSING_TRANSLATION":
            self.document_state_error = StalkerDocumentStatusError.MISSING_TRANSLATION
        elif document_state_error == "TRANSLATION_ERROR":
            self.document_state_error = StalkerDocumentStatusError.TRANSLATION_ERROR
        elif document_state_error == "REGEX_ERROR":
            self.document_state_error = StalkerDocumentStatusError.REGEX_ERROR
        elif document_state_error == "TEXT_TO_MD_ERROR":
            self.document_state_error = StalkerDocumentStatusError.TEXT_TO_MD_ERROR
        else:
            raise ValueError(
                f"document_state_error must be one of the valid StalkerDocumentStatusError values, not >{document_state_error}<"
            )

    def analyze(self) -> None:
        if self.document_state == StalkerDocumentStatus.EMBEDDING_EXIST:
            return None

        if not self.text_raw:
            logger.info("This is adding new entry, so raw text is equal to text")
            self.text_raw = self.text

        if self.document_type == StalkerDocumentType.link:
            self.text = None

    def validate(self) -> None:
        self.document_state_error = StalkerDocumentStatusError.NONE

        if self.document_state == StalkerDocumentStatus.EMBEDDING_EXIST:
            return None

        if not self.title or len(self.title) < 3:
            self.document_state = StalkerDocumentStatus.NEED_MANUAL_REVIEW
            self.document_state_error = StalkerDocumentStatusError.TITLE_MISSING

        if self.document_type == StalkerDocumentType.link:
            if not self.summary or len(self.summary) < 3:
                self.document_state = StalkerDocumentStatus.NEED_MANUAL_REVIEW
                self.document_state_error = StalkerDocumentStatusError.LINK_SUMMARY_MISSING

        if self.document_type == StalkerDocumentType.webpage:
            if not self.text or len(self.text) < 3:
                self.document_state = StalkerDocumentStatus.NEED_MANUAL_REVIEW
                self.document_state_error = StalkerDocumentStatusError.TEXT_MISSING

    def dict(self):
        created_at_str = self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else None
        document_state_error_name = (
            self.document_state_error.name if self.document_state_error else "NONE"
        )
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
            "document_type": self.document_type.name,
            "source": self.source,
            "date_from": self.date_from,
            "original_id": self.original_id,
            "document_length": self.document_length,
            "chapter_list": self.chapter_list,
            "document_state": self.document_state.name,
            "document_state_error": document_state_error_name,
            "text_raw": self.text_raw,
            "transcript_job_id": self.transcript_job_id,
            "ai_summary_needed": self.ai_summary_needed,
            "author": self.author,
            "note": self.note,
            "s3_uuid": self.s3_uuid,
            "project": self.project,
            "text_md": self.text_md,
            "transcript_needed": self.transcript_needed,
        }


# ---------------------------------------------------------------------------
# STI Subclasses — one per document_type, no extra columns
# ---------------------------------------------------------------------------


class LinkDocument(WebDocument):
    __mapper_args__ = {"polymorphic_identity": StalkerDocumentType.link}


class YouTubeDocument(WebDocument):
    __mapper_args__ = {"polymorphic_identity": StalkerDocumentType.youtube}


class MovieDocument(WebDocument):
    __mapper_args__ = {"polymorphic_identity": StalkerDocumentType.movie}


class WebpageDocument(WebDocument):
    __mapper_args__ = {"polymorphic_identity": StalkerDocumentType.webpage}


class TextMessageDocument(WebDocument):
    __mapper_args__ = {"polymorphic_identity": StalkerDocumentType.text_message}


class TextDocument(WebDocument):
    __mapper_args__ = {"polymorphic_identity": StalkerDocumentType.text}


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
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime, server_default=sa_text("CURRENT_TIMESTAMP"),
    )

    # Relationship back to document
    document: Mapped["WebDocument"] = relationship(back_populates="embeddings")
