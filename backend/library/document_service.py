"""DocumentService — business logic extracted from Flask routes.

Orchestrates document lifecycle operations by composing:
- Document ORM model (data + domain methods)
- DocumentRepository repository (complex queries)
- Library modules (website/, text_functions, text_transcript)

No Flask dependencies — works in any context (Flask, MCP server, scripts).
Session is passed in by the caller, not created here.
"""

import logging
import os
import uuid
from dataclasses import dataclass
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from library.config_loader import load_config
from library.db.models import Document
from library.document_repository import DocumentRepository
from library.text_functions import split_text_for_embedding
from library.text_transcript import chapters_text_to_list
from library.website.website_download_context import download_raw_html, webpage_raw_parse, webpage_text_clean
from library.storage import ObjectStorage, storage_from_config

logger = logging.getLogger(__name__)


class ExistingDocumentError(ValueError):
    """Raised when an URL submitted as new already belongs to a document."""

    def __init__(self, document: Document):
        super().__init__(f"Document for URL already exists: {document.id}")
        self.document = document


@dataclass
class PromotionResult:
    """Outcome of promoting a link document to a webpage."""

    document_id: int
    document_type: str
    processing_job_id: str | None
    already_webpage: bool


class DocumentService:
    """Stateless service for document business logic.

    Accepts a SQLAlchemy Session in its constructor.
    Raises ValueError for validation errors, RuntimeError for failures.
    """

    def __init__(self, session: Session, storage: ObjectStorage | None = None):
        self.session = session
        self.repo = DocumentRepository(session)
        self.storage = storage

    def _get_storage(self) -> ObjectStorage:
        """Return injected storage, constructing the legacy default lazily."""
        if self.storage is None:
            self.storage = storage_from_config(load_config())
        return self.storage

    # ------------------------------------------------------------------
    # create_document — extracted from /url_add
    # ------------------------------------------------------------------

    def create_document(
        self,
        url: str,
        url_type: str,
        text: str = "",
        html: str = "",
        title: str = "",
        language: str = "",
        note: str = "default_note",
        paywall: bool = False,
        requires_login: bool | None = None,
        social_platform: str | None = None,
        source: str = "own",
        ai_summary: bool = False,
        chapter_list: bool = False,
        byline: str = "",
        email_sender: str | None = None,
        images: list[dict] | None = None,
        original_id: str | None = None,
        published_on=None,
        external_uuid: str | None = None,
        ingested_at=None,
    ) -> Document:
        """Create a new document, optionally storing text/html to S3 or local disk.

        Returns the persisted Document with its assigned id.
        Raises ValueError for missing required params, RuntimeError for storage/DB failures.
        """
        if not url or not url_type:
            raise ValueError("Missing required parameter(s): 'url' or 'type'")

        existing = Document.get_by_url(self.session, url)
        if existing is not None:
            raise ExistingDocumentError(existing)

        # Plain-text captures (social posts, emails) never use object storage.
        # Avoid constructing a storage backend for them so an import can work
        # even when only the database/API is available.
        storage = self._get_storage() if url_type == "webpage" else None

        # An external UUID is the import idempotency key for every document
        # type, not just webpages.  Social posts do not use object storage,
        # but must still retain the legacy UUID so a later bridge run finds
        # the local record before attempting S3.
        doc_uuid = external_uuid

        if url_type == "webpage":
            uid = external_uuid or str(uuid.uuid4())
            doc_uuid = uid

            if text:
                self._store_file(uid, "txt", text, storage=storage)
            if html:
                self._store_file(uid, "html", html, storage=storage)
            else:
                logger.info("Missing HTML part!")

        doc = Document(url=url)
        doc.set_document_type(url_type)
        doc.note = note
        doc.title = title
        doc.language = language
        doc.paywall = paywall
        doc.requires_login = (
            url_type in {"social_media_post", "email"} if requires_login is None else bool(requires_login)
        )
        doc.social_platform = social_platform or None
        if url_type in {"social_media_post", "email"}:
            # Social posts and emails arrive as already extracted plain text.
            # Do not send them through webpage HTML storage/cleanup, which
            # would reintroduce the source application's UI and thread chrome.
            if url_type == "email":
                from library.email_footer_rules import apply_footer_rule, normalize_sender_email
                from library.tracking_urls import resolve_tracking_urls_in_text

                doc.email_sender = normalize_sender_email(email_sender)
                normalized_text = resolve_tracking_urls_in_text(text)
                doc.text = apply_footer_rule(self.session, doc.email_sender, normalized_text) or None
            else:
                doc.text = text or None
            doc.text_raw = text or None
            doc.document_length = len(doc.text) if doc.text else None
        doc.byline = byline or None
        doc.original_id = original_id
        if published_on:
            doc.published_on = published_on
            doc.published_on_method = "manual"
        doc.set_discovery_source(self.session, source)
        doc.set_publisher_from_url(self.session)
        doc.ai_summary_needed = ai_summary
        doc.chapter_list = chapter_list
        if ingested_at is not None:
            doc.ingested_at = ingested_at
        if doc_uuid is not None:
            doc.uuid = doc_uuid
        if url_type == "webpage":
            doc.text_raw = html or None
        doc.set_processing_status("URL_ADDED")

        self.session.add(doc)
        self.session.commit()

        if url_type == "email" and images:
            self.replace_email_images(doc.id, images)

        logger.info("Successfully saved document to database with ID: %s", doc.id)
        return doc

    def replace_email_images(self, document_id: int, images: list[dict]) -> None:
        """Replace externally hosted images captured from an email body.

        This supports a re-import of the same Gmail message: its stable
        ``gmail://`` identity keeps the text record, while newly supported
        image metadata can be populated without deleting the document.
        """
        normalized_images = []
        for fallback_position, image in enumerate(images[:30]):
            if not isinstance(image, dict):
                continue
            raw_url = image.get("url")
            if not isinstance(raw_url, str):
                continue
            url_value = raw_url.strip()
            if urlparse(url_value).scheme not in {"http", "https"}:
                continue
            try:
                position = int(image.get("position", fallback_position))
            except (TypeError, ValueError):
                position = fallback_position
            if position < 0:
                continue
            alt = image.get("alt_text") or image.get("alt") or ""
            normalized_images.append({
                "url": url_value,
                "alt": str(alt).strip()[:500],
                "position": position,
            })
        if not normalized_images:
            return

        from library.document_images import replace_document_images

        replace_document_images(self.session, document_id, normalized_images)
        self.session.commit()

    def normalize_email_tracking_links(self, doc: Document) -> bool:
        """Repair tracking links in an existing email without replacing edits."""
        if doc.document_type != "email" or not doc.text:
            return False
        from library.tracking_urls import resolve_tracking_urls_in_text

        normalized_text = resolve_tracking_urls_in_text(doc.text)
        if normalized_text == doc.text:
            return False
        doc.text = normalized_text
        doc.text_raw = resolve_tracking_urls_in_text(doc.text_raw or "") or None
        doc.document_length = len(doc.text)
        self.session.commit()
        return True

    def apply_email_footer_rule(self, doc: Document) -> bool:
        """Apply the current sender footer rule to a re-imported email.

        ``text_raw`` deliberately remains untouched: it preserves the
        originally captured source, while ``text`` is the canonical content
        shown and analysed by Lenie.
        """
        if doc.document_type != "email" or not doc.text:
            return False

        from library.email_footer_rules import apply_footer_rule

        cleaned_text = apply_footer_rule(self.session, doc.email_sender, doc.text)
        if cleaned_text == doc.text:
            return False
        doc.text = cleaned_text
        doc.document_length = len(cleaned_text)
        self.session.commit()
        return True

    def _store_file(self, uid: str, extension: str, content: str, use_s3=None, s3_client=None,
                    bucket_name: str | None = None, storage=None) -> None:
        """Store a file through the configured backend. Legacy args remain for callers/tests."""
        file_name = f"{uid}.{extension}"
        if storage is None:  # compatibility for older direct callers
            try:
                if use_s3:
                    s3_client.put_object(Bucket=bucket_name, Key=file_name, Body=content)
                else:
                    os.makedirs("/app/data", exist_ok=True)
                    with open(f"/app/data/{file_name}", "w", encoding="utf-8") as handle:
                        handle.write(content)
                return
            except Exception as e:
                raise RuntimeError(f"Failed to upload {extension} file to storage" if use_s3 else
                                   f"Failed to save {extension} file locally") from e
        try:
            storage.put_bytes(file_name, content.encode("utf-8"), f"text/{extension}; charset=utf-8")
            logger.info("Successfully stored %s", file_name)
        except Exception as e:
            logger.error("Failed to store %s: %s", file_name, e)
            raise RuntimeError(f"Failed to upload {extension} file to storage" if use_s3 else
                               f"Failed to save {extension} file locally") from e

    # ------------------------------------------------------------------
    # save_document — extracted from /website_save
    # ------------------------------------------------------------------

    def fill_missing_source_html(self, url: str, html: str, text: str = "",
                                 external_uuid: str | None = None) -> Document:
        """Attach captured HTML only when the existing document has no raw source."""
        doc = Document.get_by_url(self.session, url)
        if doc is None:
            raise ValueError("Document for URL does not exist")
        if doc.document_type != "webpage" or not html:
            raise ValueError("Filling source requires a webpage with HTML")
        if doc.text_raw:
            raise ValueError("Document already has raw HTML")

        storage = self._get_storage()
        new_uuid = external_uuid or str(uuid.uuid4())
        if text:
            self._store_file(new_uuid, "txt", text, storage=storage)
        self._store_file(new_uuid, "html", html, storage=storage)

        doc.uuid = new_uuid
        doc.text_raw = html
        from library.article_metadata import extract_article_authors
        from library.author_service import set_document_authors

        set_document_authors(self.session, doc, extract_article_authors(html, url), method="html")
        self.session.commit()
        return doc

    def refresh_document_source(self, document_id: int, url: str, html: str,
                                text: str = "") -> Document:
        """Backward-compatible entry point with safe fill-only semantics."""
        doc = Document.get_by_id(self.session, int(document_id))
        if doc is None or doc.url != url:
            raise ValueError("Refresh target does not match URL")
        return self.fill_missing_source_html(url=url, html=html, text=text)

    # ------------------------------------------------------------------
    # promote_link_to_webpage — turn a link document into a webpage in place
    # ------------------------------------------------------------------

    def promote_link_to_webpage(self, doc_id: int, html: str = "") -> PromotionResult:
        """Flip a link document to a webpage and queue content extraction.

        ``html`` is the browser-captured page source; when empty the page is
        downloaded server-side (fails for paywalled/login pages). The document
        id, feed-item links and metadata are preserved. Raises ``ValueError``
        when the document is missing and ``PromotionError`` (with ``.reason``)
        when promotion cannot proceed.
        """
        from library.document_processing_service import ensure_document_prepare_job
        from library.document_promotion import promote_link_to_webpage as _promote

        doc = Document.get_by_id(self.session, int(doc_id))
        if doc is None:
            raise ValueError("Document does not exist")

        already_webpage = doc.document_type == "webpage"
        _promote(self.session, self._get_storage(), doc, html=html)
        self.session.commit()

        # The commit expired `doc`, and it is still the pre-flip STI class
        # (LinkDocument) — reloading it against a row that is now `webpage`
        # raises ObjectDeletedError. Re-fetch a correctly-typed instance.
        doc = Document.get_by_id(self.session, int(doc_id))
        job = ensure_document_prepare_job(self.session, doc) if not doc.text_md else None
        return PromotionResult(
            document_id=doc.id,
            document_type=doc.document_type,
            processing_job_id=job.id if job else None,
            already_webpage=already_webpage,
        )

    def save_document(
        self,
        url: str,
        link_id: int | None = None,
        processing_status: str | None = None,
        document_type: str | None = None,
        **attrs,
    ) -> Document:
        """Look up or create a document, apply attribute updates, and commit.

        Accepted keyword attrs: text, text_md, title, language, tags, search_terms,
        summary, source, byline, email_sender, note.

        For webpages ``text_md`` is the canonical editable article body.
        ``text`` is maintained as a derived plain-text compatibility/search
        representation so the two fields cannot silently diverge.
        Raises ValueError for invalid document_type.
        Returns the saved Document.
        """
        if not url:
            raise ValueError("Missing data. Make sure you provide 'url'")

        if link_id is not None:
            doc = Document.get_by_id(self.session, int(link_id))
        else:
            doc = Document.get_by_url(self.session, url)

        if doc is None:
            doc = Document(url=url)
            doc.set_publisher_from_url(self.session)
            self.session.add(doc)

        if processing_status is not None:
            doc.set_processing_status(processing_status)

        for attr in ("title", "language", "tags", "search_terms", "summary", "byline", "note"):
            value = attrs.get(attr)
            if value is not None:
                setattr(doc, attr, value)

        # "source" arrives as a NAME (wire format) and resolves to the
        # discovery_sources FK, auto-creating unknown names (stage 11d).
        if attrs.get("source") is not None:
            doc.set_discovery_source(self.session, attrs["source"])

        if document_type is not None:
            doc.set_document_type(document_type)

        effective_type = document_type or doc.document_type
        if effective_type == "email" and attrs.get("email_sender") is not None:
            from library.email_footer_rules import normalize_sender_email

            doc.email_sender = normalize_sender_email(attrs["email_sender"])
        submitted_text = attrs.get("text")
        submitted_md = attrs.get("text_md")
        previous_canonical_text = (
            doc.text_md if effective_type == "webpage" and doc.text_md is not None else doc.text
        ) or ""
        if effective_type == "webpage":
            # Legacy webpages may only have plain text. The next explicit save
            # promotes it to the canonical Markdown field (plain text is valid
            # Markdown), while all normal saves derive text from text_md.
            canonical_md = submitted_md or submitted_text
            if canonical_md is not None:
                from library.lenie_markdown import md_remove_markdown

                doc.text_md = canonical_md
                doc.text = md_remove_markdown(canonical_md)
                doc.document_length = len(canonical_md)
                doc.quality = None
        elif submitted_text is not None:
            # Transcripts and other non-webpage documents keep plain text as
            # their native canonical representation.
            if effective_type == "email":
                from library.email_footer_rules import apply_footer_rule

                submitted_text = apply_footer_rule(self.session, doc.email_sender, submitted_text)
            doc.text = submitted_text
            doc.document_length = len(submitted_text) if submitted_text else None
        if effective_type != "webpage" and submitted_md is not None:
            doc.text_md = submitted_md

        current_canonical_text = (
            doc.text_md if effective_type == "webpage" and doc.text_md is not None else doc.text
        ) or ""
        if (submitted_text is not None or submitted_md is not None) and current_canonical_text != previous_canonical_text:
            # A later chunk run must refresh entities against the edited text.
            # Keep rows for review history, but mark them as stale immediately.
            doc.entities_checked_at = None
            doc.ner_unavailable_at = None

        doc.analyze()

        self.session.commit()
        return doc

    # ------------------------------------------------------------------
    # delete_document — extracted from /website_delete
    # ------------------------------------------------------------------

    def delete_document(self, doc_id: int) -> bool:
        """Delete a document by ID. Returns True if deleted, False if not found."""
        doc = Document.get_by_id(self.session, doc_id)
        if doc is None:
            return False

        self.session.delete(doc)
        self.session.commit()
        return True

    # ------------------------------------------------------------------
    # get_document — extracted from /website_get
    # ------------------------------------------------------------------

    def get_document(self, doc_id: int, reach: bool = True) -> Document | None:
        """Retrieve a document by ID with optional neighbor population.

        Returns None if not found.
        """
        return Document.get_by_id(self.session, doc_id, reach=reach)

    # ------------------------------------------------------------------
    # Content methods — thin wrappers around library calls
    # ------------------------------------------------------------------

    def download_and_parse(self, url: str) -> dict:
        """Download a URL and parse its content. Returns dict with text, title, summary, language.

        Raises RuntimeError if download fails.
        """
        raw_html = download_raw_html(url)
        if not raw_html:
            raise RuntimeError("empty response from download raw html function")

        result = webpage_raw_parse(url, raw_html)

        return {
            "text": result.text,
            "title": result.title,
            "summary": result.summary,
            "language": result.language,
        }

    def clean_text(self, url: str, text: str) -> str:
        """Remove site-specific boilerplate from text."""
        return webpage_text_clean(url, text)

    # ------------------------------------------------------------------
    # import_document — for import scripts (dynamodb_sync, feed monitor service, batch pipeline)
    # ------------------------------------------------------------------

    def import_document(
        self,
        url: str,
        document_type: str,
        processing_status: str | None = None,
        skip_if_exists: bool = True,
        **metadata,
    ) -> tuple[Document | None, str]:
        """Import a document from an external source.

        Unlike create_document(), does NOT upload content to S3.
        Content (text, text_raw) is set directly on the model.

        Args:
            url: Document URL (required)
            document_type: Document type string (link, webpage, youtube, etc.)
            processing_status: Initial state (default: URL_ADDED)
            skip_if_exists: If True, return (existing, "skipped") for duplicate URLs
            **metadata: Any Document attribute (title, language, source, note,
                        uuid, chapter_list, ingested_at, text, text_raw, summary,
                        paywall, published_on, collection_id, ai_summary_needed)

        Returns:
            (Document, "added") for new documents
            (existing_doc, "skipped") if URL exists and skip_if_exists=True
        """
        if not url:
            raise ValueError("Missing required parameter: 'url'")

        if skip_if_exists:
            existing = Document.get_by_url(self.session, url)
            if existing is not None:
                return existing, "skipped"

        doc = Document(url=url)
        doc.set_document_type(document_type)
        doc.set_publisher_from_url(self.session)

        if processing_status:
            doc.set_processing_status(processing_status)
        else:
            doc.set_processing_status("URL_ADDED")

        # "source" is the discovery-source NAME (wire/import format) — it
        # resolves to the discovery_sources FK instead of a direct attribute
        # (stage 11d normalization; unknown names are auto-created).
        source_name = metadata.pop("source", None)
        if source_name is not None:
            doc.set_discovery_source(self.session, source_name)

        for attr, value in metadata.items():
            if value is not None:
                if hasattr(doc, attr):
                    setattr(doc, attr, value)
                else:
                    logger.warning("import_document: unknown attribute '%s' ignored", attr)

        self.session.add(doc)
        self.session.commit()
        return doc, "added"

    def split_for_embedding(self, text: str, chapters_list_text: str | None = None) -> list:
        """Split text into chunks suitable for embedding generation."""
        chapters_list = chapters_text_to_list(chapters_list_text)
        chapter_list_simple = [chapter["title"] for chapter in chapters_list]
        return split_text_for_embedding(text, chapter_list_simple)
