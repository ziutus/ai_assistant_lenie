"""DocumentService — business logic extracted from Flask routes.

Orchestrates document lifecycle operations by composing:
- WebDocument ORM model (data + domain methods)
- WebsitesDBPostgreSQL repository (complex queries)
- Library modules (website/, text_functions, text_transcript)

No Flask dependencies — works in any context (Flask, MCP server, scripts).
Session is passed in by the caller, not created here.
"""

import logging
import os
import uuid

from sqlalchemy.orm import Session

from library.config_loader import load_config
from library.db.models import WebDocument
from library.stalker_web_documents_db_postgresql import WebsitesDBPostgreSQL
from library.text_functions import split_text_for_embedding
from library.text_transcript import chapters_text_to_list
from library.website.website_download_context import download_raw_html, webpage_raw_parse, webpage_text_clean

logger = logging.getLogger(__name__)


class DocumentService:
    """Stateless service for document business logic.

    Accepts a SQLAlchemy Session in its constructor.
    Raises ValueError for validation errors, RuntimeError for failures.
    """

    def __init__(self, session: Session):
        self.session = session
        self.repo = WebsitesDBPostgreSQL(session)

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
    ) -> WebDocument:
        """Create a new document, optionally storing text/html to S3 or local disk.

        Returns the persisted WebDocument with its assigned id.
        Raises ValueError for missing required params, RuntimeError for storage/DB failures.
        """
        if not url or not url_type:
            raise ValueError("Missing required parameter(s): 'url' or 'type'")

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

        doc = WebDocument(url=url)
        doc.set_document_type(url_type)
        doc.note = note
        doc.title = title
        doc.language = language
        doc.paywall = paywall
        doc.source = source
        doc.ai_summary_needed = ai_summary
        doc.chapter_list = chapter_list
        doc.uuid = doc_uuid
        doc.set_document_state("URL_ADDED")

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

    def save_document(
        self,
        url: str,
        link_id: int | None = None,
        document_state: str | None = None,
        document_type: str | None = None,
        **attrs,
    ) -> WebDocument:
        """Look up or create a document, apply attribute updates, and commit.

        Accepted keyword attrs: text, title, language, tags, summary, source, author, note.
        Raises ValueError for invalid document_type.
        Returns the saved WebDocument.
        """
        if not url:
            raise ValueError("Missing data. Make sure you provide 'url'")

        if link_id is not None:
            doc = WebDocument.get_by_id(self.session, int(link_id))
        else:
            doc = WebDocument.get_by_url(self.session, url)

        if doc is None:
            doc = WebDocument(url=url)
            self.session.add(doc)

        if document_state is not None:
            doc.set_document_state(document_state)

        for attr in ("text", "title", "language", "tags", "summary", "source", "author", "note"):
            value = attrs.get(attr)
            if value is not None:
                setattr(doc, attr, value)

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
        doc = WebDocument.get_by_id(self.session, doc_id)
        if doc is None:
            return False

        self.session.delete(doc)
        self.session.commit()
        return True

    # ------------------------------------------------------------------
    # get_document — extracted from /website_get
    # ------------------------------------------------------------------

    def get_document(self, doc_id: int, reach: bool = True) -> WebDocument | None:
        """Retrieve a document by ID with optional neighbor population.

        Returns None if not found.
        """
        return WebDocument.get_by_id(self.session, doc_id, reach=reach)

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
        document_state: str | None = None,
        skip_if_exists: bool = True,
        **metadata,
    ) -> tuple[WebDocument | None, str]:
        """Import a document from an external source.

        Unlike create_document(), does NOT upload content to S3.
        Content (text, text_raw) is set directly on the model.

        Args:
            url: Document URL (required)
            document_type: Document type string (link, webpage, youtube, etc.)
            document_state: Initial state (default: URL_ADDED)
            skip_if_exists: If True, return (existing, "skipped") for duplicate URLs
            **metadata: Any WebDocument attribute (title, language, source, note,
                        uuid, chapter_list, created_at, text, text_raw, summary,
                        paywall, date_from, project, ai_summary_needed)

        Returns:
            (WebDocument, "added") for new documents
            (existing_doc, "skipped") if URL exists and skip_if_exists=True
        """
        if not url:
            raise ValueError("Missing required parameter: 'url'")

        if skip_if_exists:
            existing = WebDocument.get_by_url(self.session, url)
            if existing is not None:
                return existing, "skipped"

        doc = WebDocument(url=url)
        doc.set_document_type(document_type)

        if document_state:
            doc.set_document_state(document_state)
        else:
            doc.set_document_state("URL_ADDED")

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
