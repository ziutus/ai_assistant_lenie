"""Persist document_images rows from two independent sources — article images
(library/article_cleaner.py, url-sourced) and book-PDF images
(library/book_pdf_import.py, storage_key-sourced). Each source has its own
replace-per-document function (like document_entities /
entity_service.refresh_document_entities) that only ever touches its own
rows: re-cleaning a web article must never delete a book's PDF images, and
vice versa — see DocumentImage's docstring in library/db/models.py.
"""

import logging
import re

from sqlalchemy import delete, select

from library.db.models import DocumentImage

logger = logging.getLogger(__name__)


def image_marker_present(text: str | None, position: int) -> bool:
    """True when text contains the "[imgN]" / "[imgN: alt]" marker for position N.

    The closing bracket / colon after the digits keeps "[img3" from matching
    the marker of image 30.
    """
    if not text:
        return False
    return re.search(rf"\[img{int(position)}(?::[^\]]{{0,2000}})?\]", text) is not None


def prune_images_removed_from_text(
    session, document_id: int, old_text: str | None, new_text: str | None, get_storage=None,
) -> int:
    """Delete document_images rows whose "[imgN]" marker the user removed from the text.

    Only a marker that WAS in old_text and is gone from new_text counts — an
    image that never had a marker in the text (e.g. a catalogue backfilled
    without one) is left alone. Rows with a downloaded copy
    (storage_key set alongside the original url) also lose the stored object,
    best effort (get_storage: zero-arg callable returning an ObjectStorage,
    only invoked when there is an object to delete). Book-PDF rows
    (url IS NULL) are never touched.

    Queues the changes on the session without committing — caller owns the
    transaction. Returns the number of removed rows.
    """
    rows = session.execute(
        select(DocumentImage).where(
            DocumentImage.document_id == document_id,
            DocumentImage.url.is_not(None),
            DocumentImage.position.is_not(None),
        )
    ).scalars().all()
    removed = 0
    for row in rows:
        if image_marker_present(old_text, row.position) and not image_marker_present(new_text, row.position):
            if row.storage_key and get_storage is not None:
                try:
                    get_storage().delete(row.storage_key)
                except Exception:  # noqa: BLE001 — an orphaned object must not block the text save
                    logger.warning("Could not delete stored image %s", row.storage_key, exc_info=True)
            session.delete(row)
            removed += 1
    return removed


def replace_document_images(
    session, document_id: int, images: list[dict], chunk_id: int | None = None,
) -> list[DocumentImage]:
    """Replace the url-sourced document_images rows for document_id.

    images: the "images" list from clean_article_text()'s return dict — each
    item has url/alt and, when a caption/credit line was detected next to the
    [imgN] marker, caption_text/caption_category (article_quality.photo_caption_candidates).

    Deletes rows that carry a url — both plain url-sourced ones and ones whose
    image was later downloaded to storage (url + storage_key); the stored copy
    is carried over to the new row with the same url, so re-cleaning a text
    does not lose a download. Pure storage_key rows (url IS NULL, PDF
    illustrations) belong to replace_storage_images() and are left untouched.

    Queues the changes on the session without committing — caller owns the
    transaction, same convention as refresh_document_entities().
    """
    downloaded = {
        url: storage_key
        for url, storage_key in session.execute(
            select(DocumentImage.url, DocumentImage.storage_key).where(
                DocumentImage.document_id == document_id,
                DocumentImage.url.is_not(None),
                DocumentImage.storage_key.is_not(None),
            )
        ).all()
    }
    session.execute(
        delete(DocumentImage).where(
            DocumentImage.document_id == document_id,
            DocumentImage.url.is_not(None),
        )
    )
    rows = [
        DocumentImage(
            document_id=document_id,
            chunk_id=chunk_id,
            position=image.get("position", position),
            url=image["url"],
            storage_key=downloaded.get(image["url"]),
            alt_text=image.get("alt") or None,
            caption_text=image.get("caption_text"),
            caption_category=image.get("caption_category"),
            is_stock_photo=image.get("caption_category") == "stock",
        )
        for position, image in enumerate(images)
        if image.get("url")
    ]
    if rows:
        session.add_all(rows)
    return rows


def replace_storage_images(
    session, document_id: int, images: list[dict],
) -> list[DocumentImage]:
    """Replace the storage_key-sourced document_images rows for document_id.

    images: dicts with storage_key, position (marker index, may be None for
    backfilled images with no [imgN] marker in text_md), page_number,
    chapter_position, caption_text, alt_text.

    Only deletes rows with storage_key IS NOT NULL and url IS NULL — url-sourced
    (article) rows, including ones whose image was downloaded to storage, belong
    to replace_document_images() and are left untouched.

    Queues the changes on the session without committing — caller owns the
    transaction, same convention as replace_document_images().
    """
    session.execute(
        delete(DocumentImage).where(
            DocumentImage.document_id == document_id,
            DocumentImage.storage_key.is_not(None),
            DocumentImage.url.is_(None),
        )
    )
    rows = [
        DocumentImage(
            document_id=document_id,
            position=image.get("position"),
            storage_key=image["storage_key"],
            page_number=image.get("page_number"),
            chapter_position=image.get("chapter_position"),
            alt_text=image.get("alt_text"),
            caption_text=image.get("caption_text"),
        )
        for image in images
        if image.get("storage_key")
    ]
    if rows:
        session.add_all(rows)
    return rows
