"""Persist images extracted from article text (library/article_cleaner.py) into
document_images. Replace-per-document semantics (like document_entities /
entity_service.refresh_document_entities): each call replaces the document's
full row set with the images produced by the latest clean_article_text() run.
"""

from sqlalchemy import delete

from library.db.models import DocumentImage


def replace_document_images(
    session, document_id: int, images: list[dict], chunk_id: int | None = None,
) -> list[DocumentImage]:
    """Replace document_images rows for document_id with the given extracted images.

    images: the "images" list from clean_article_text()'s return dict — each
    item has url/alt and, when a caption/credit line was detected next to the
    [imgN] marker, caption_text/caption_category (article_quality.photo_caption_candidates).

    Queues the changes on the session without committing — caller owns the
    transaction, same convention as refresh_document_entities().
    """
    session.execute(delete(DocumentImage).where(DocumentImage.document_id == document_id))
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
