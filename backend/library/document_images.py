"""Persist document_images rows from two independent sources — article images
(library/article_cleaner.py, url-sourced) and book-PDF images
(library/book_pdf_import.py, storage_key-sourced). Each source has its own
replace-per-document function (like document_entities /
entity_service.refresh_document_entities) that only ever touches its own
rows: re-cleaning a web article must never delete a book's PDF images, and
vice versa — see DocumentImage's docstring in library/db/models.py.
"""

from sqlalchemy import delete

from library.db.models import DocumentImage


def replace_document_images(
    session, document_id: int, images: list[dict], chunk_id: int | None = None,
) -> list[DocumentImage]:
    """Replace the url-sourced document_images rows for document_id.

    images: the "images" list from clean_article_text()'s return dict — each
    item has url/alt and, when a caption/credit line was detected next to the
    [imgN] marker, caption_text/caption_category (article_quality.photo_caption_candidates).

    Only deletes rows with storage_key IS NULL — storage_key-sourced (PDF)
    rows belong to replace_storage_images() and are left untouched.

    Queues the changes on the session without committing — caller owns the
    transaction, same convention as refresh_document_entities().
    """
    session.execute(
        delete(DocumentImage).where(
            DocumentImage.document_id == document_id,
            DocumentImage.storage_key.is_(None),
        )
    )
    rows = [
        DocumentImage(
            document_id=document_id,
            chunk_id=chunk_id,
            position=position,
            url=image["url"],
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

    Only deletes rows with storage_key IS NOT NULL — url-sourced (article)
    rows belong to replace_document_images() and are left untouched.

    Queues the changes on the session without committing — caller owns the
    transaction, same convention as replace_document_images().
    """
    session.execute(
        delete(DocumentImage).where(
            DocumentImage.document_id == document_id,
            DocumentImage.storage_key.is_not(None),
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
