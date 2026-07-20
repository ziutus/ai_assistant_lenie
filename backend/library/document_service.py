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

from sqlalchemy.orm import Session

from library.config_loader import load_config
from library.db.models import Document
from library.document_repository import DocumentRepository
from library.text_functions import split_text_for_embedding
from library.text_transcript import chapters_text_to_list
from library.website.website_download_context import download_raw_html, webpage_raw_parse, webpage_text_clean

logger = logging.getLogger(__name__)


class ExistingDocumentError(ValueError):
    """Raised when an URL submitted as new already belongs to a document."""

    def __init__(self, document: Document):
        super().__init__(f"Document for URL already exists: {document.id}")
        self.document = document


class DocumentService:
    """Stateless service for document business logic.

    Accepts a SQLAlchemy Session in its constructor.
    Raises ValueError for validation errors, RuntimeError for failures.
    """

    def __init__(self, session: Session):
        self.session = session
        self.repo = DocumentRepository(session)

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
        source: str = "own",
        ai_summary: bool = False,
        chapter_list: bool = False,
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

        cfg = load_config()
        bucket_name = cfg.get("AWS_S3_WEBSITE_CONTENT")
        use_aws_s3 = bucket_name is not None

        logger.info("Using AWS S3: %s", use_aws_s3)

        doc_uuid = None

        if use_aws_s3:
            import boto3
            s3_client = boto3.client("s3")
        else:
            s3_client = None

        if url_type == "webpage":
            uid = str(uuid.uuid4())
            doc_uuid = uid

            if text:
                self._store_file(uid, "txt", text, use_aws_s3, s3_client, bucket_name)
            if html:
                self._store_file(uid, "html", html, use_aws_s3, s3_client, bucket_name)
            else:
                logger.info("Missing HTML part!")

        doc = Document(url=url)
        doc.set_document_type(url_type)
        doc.note = note
        doc.title = title
        doc.language = language
        doc.paywall = paywall
        doc.set_discovery_source(self.session, source)
        doc.set_publisher_from_url(self.session)
        doc.ai_summary_needed = ai_summary
        doc.chapter_list = chapter_list
        doc.uuid = doc_uuid
        doc.set_processing_status("URL_ADDED")

        self.session.add(doc)
        self.session.commit()

        logger.info("Successfully saved document to database with ID: %s", doc.id)
        return doc

    def _store_file(self, uid: str, extension: str, content: str, use_s3: bool, s3_client, bucket_name: str | None) -> None:
        """Store a file to S3 or local disk. Raises RuntimeError on failure."""
        file_name = f"{uid}.{extension}"

        if use_s3:
            try:
                s3_client.put_object(Bucket=bucket_name, Key=file_name, Body=content)
                logger.info("Successfully uploaded %s to %s", file_name, bucket_name)
            except Exception as e:
                logger.error("Failed to upload %s to %s: %s", file_name, bucket_name, e)
                raise RuntimeError(f"Failed to upload {extension} file to storage") from e
        else:
            try:
                os.makedirs("/app/data", exist_ok=True)
                local_file_path = f"/app/data/{file_name}"
                with open(local_file_path, "w", encoding="utf-8") as f:
                    f.write(content)
                logger.info("Successfully saved %s to /app/data/", file_name)
            except Exception as e:
                logger.error("Failed to save %s to /app/data/: %s", file_name, e)
                raise RuntimeError(f"Failed to save {extension} file locally") from e

    # ------------------------------------------------------------------
    # save_document — extracted from /website_save
    # ------------------------------------------------------------------

    def fill_missing_source_html(self, url: str, html: str, text: str = "") -> Document:
        """Attach captured HTML only when the existing document has no raw source."""
        doc = Document.get_by_url(self.session, url)
        if doc is None:
            raise ValueError("Document for URL does not exist")
        if doc.document_type != "webpage" or not html:
            raise ValueError("Filling source requires a webpage with HTML")
        if doc.text_raw:
            raise ValueError("Document already has raw HTML")

        cfg = load_config()
        bucket_name = cfg.get("AWS_S3_WEBSITE_CONTENT")
        use_s3 = bucket_name is not None
        s3_client = __import__("boto3").client("s3") if use_s3 else None
        new_uuid = str(uuid.uuid4())
        if text:
            self._store_file(new_uuid, "txt", text, use_s3, s3_client, bucket_name)
        self._store_file(new_uuid, "html", html, use_s3, s3_client, bucket_name)

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

    def save_document(
        self,
        url: str,
        link_id: int | None = None,
        processing_status: str | None = None,
        document_type: str | None = None,
        **attrs,
    ) -> Document:
        """Look up or create a document, apply attribute updates, and commit.

        Accepted keyword attrs: text, title, language, tags, summary, source, byline, note.
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

        for attr in ("text", "title", "language", "tags", "summary", "byline", "note"):
            value = attrs.get(attr)
            if value is not None:
                setattr(doc, attr, value)

        # "source" arrives as a NAME (wire format) and resolves to the
        # discovery_sources FK, auto-creating unknown names (stage 11d).
        if attrs.get("source") is not None:
            doc.set_discovery_source(self.session, attrs["source"])

        if document_type is not None:
            doc.set_document_type(document_type)

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
    # import_document — for import scripts (dynamodb_sync, feed_monitor, batch pipeline)
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
