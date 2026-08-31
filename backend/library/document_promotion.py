"""Promote an existing ``link`` document to ``webpage`` in place.

A ``link`` document holds only a URL plus metadata (title/summary/byline/tags).
Once created there was no supported path to turn it into a ``webpage`` with
fetched content without deleting and re-importing — which loses feed-item
links, ``FeedReviewDecision`` history, collections and Tematy.

``promote_link_to_webpage`` flips the type on the same ``documents`` row,
attaches the page HTML (client-supplied or downloaded), and leaves the rest to
the existing ``document_prepare`` job (HTML -> Markdown -> LLM article
extraction). Document metadata is deliberately left untouched: the link's
title/summary/byline stay authoritative.

Transport-independent, no Flask. The caller supplies the session and object
storage and owns the ``commit()`` — this module never commits.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from library.db.models import Document
from library.storage import ObjectStorage
from library.website.website_download_context import download_raw_html
from library.website.website_paid import website_is_paid

logger = logging.getLogger(__name__)


class PromotionError(ValueError):
    """A promotion could not proceed. ``reason`` is a stable machine code."""

    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason  # "not_a_link" | "paywall" | "requires_login" | "download_failed"


def _decode_html(raw: bytes) -> str:
    try:
        import chardet

        guess = chardet.detect(raw).get("encoding") or "utf-8"
    except Exception:  # pragma: no cover - chardet failure is non-fatal
        guess = "utf-8"
    return raw.decode(guess, errors="replace")


def _store_source_html(session: Session, storage: ObjectStorage, doc: Document, html: str) -> None:
    """Persist the raw HTML as ``{uuid}.html`` (same layout as create_document)."""
    from library.document_service import DocumentService

    DocumentService(session, storage=storage)._store_file(doc.uuid, "html", html, storage=storage)


def promote_link_to_webpage(
    session: Session,
    storage: ObjectStorage,
    doc: Document,
    html: str = "",
    *,
    run_feed_linking: bool = True,
    downloader=download_raw_html,
    paid_check=website_is_paid,
) -> Document:
    """Flip a ``link`` document to ``webpage`` in place. No commit, no job enqueue.

    Args:
        html: captured page HTML (from the browser extension). When empty the
            page is downloaded server-side, which fails for paywalled/login
            pages.
        run_feed_linking: re-sync feed items for this canonical URL. The feed
            import path passes ``False`` because it manages its own item.
        downloader / paid_check: injected for tests.

    Raises:
        PromotionError: with ``.reason`` in {not_a_link, paywall,
            requires_login, download_failed}.
    """
    # 1. Idempotency — already a webpage.
    if doc.document_type == "webpage":
        if html:
            # Re-attach a fresh source and re-run extraction. This is the
            # recovery path after a failed download left an empty webpage.
            _store_source_html(session, storage, doc, html)
            doc.text_raw = html
            doc.text_md = None
            doc.text_extracted = None
            doc.processing_error_code = None
            doc.set_processing_status("NEED_CLEAN_MD")
            session.flush()
        return doc

    # 2. Type guard.
    if doc.document_type != "link":
        raise PromotionError("not_a_link", f"Dokument {doc.id} nie jest typu link ({doc.document_type}).")

    # 3. Wall guard — enforced here so every entry point is covered.
    if doc.requires_login:
        raise PromotionError("requires_login", "Strona wymaga logowania — pobranie treści nie zadziała.")
    if doc.paywall:
        raise PromotionError("paywall", "Strona jest za paywallem — pobranie treści nie zadziała.")

    # 4. Obtain HTML.
    if html:
        html_str = html
    else:
        if paid_check(doc.url):
            raise PromotionError("paywall", "Strona jest za paywallem — pobranie treści nie zadziała.")
        try:
            raw = downloader(doc.url)
        except ValueError as exc:
            raise PromotionError("download_failed", f"Nie udało się pobrać strony: {exc}") from exc
        if not raw:
            raise PromotionError("download_failed", "Nie udało się pobrać treści strony.")
        html_str = _decode_html(raw) if isinstance(raw, bytes) else str(raw)

    # 5. Store the source artifact under the existing uuid.
    _store_source_html(session, storage, doc, html_str)

    # 6-9. Flip the type and hand off to document_prepare.
    doc.set_document_type("webpage")
    doc.text_raw = html_str
    doc.set_processing_status("NEED_CLEAN_MD")

    # 10. Re-sync feed items (idempotent) unless the caller owns that.
    if run_feed_linking:
        from library.feed_monitor_service import link_matching_feed_items_to_document

        link_matching_feed_items_to_document(session, doc)

    session.flush()
    logger.info("Promoted document %s from link to webpage", doc.id)
    return doc
