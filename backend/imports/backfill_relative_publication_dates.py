#!/usr/bin/env python3
"""One-off backfill: resolve documents.published_on from relative-date
artifacts (e.g. interia.pl's "Wczoraj, HH:MM", "X minut/godzin temu")
already sitting in the database for documents where published_on was
never set — see library.article_cleaner.resolve_relative_publication_date.

create_run() (document_analysis_service.py, step 2b) does this automatically
for new/reanalyzed documents since #336, but documents already ingested and
chunked before that change never got the backfill. The artifact may now live
in one of three places depending on how far the document got in review, tried
in order of decreasing trustworthiness:
  1. documents.text_md/text/text_raw — untouched by chunk deletion
     (delete_noise_chunk() never modifies the source document), preserves
     natural reading order, so a first-match is reliably the article's own
     byline rather than an unrelated recommendation card.
  2. document_chunks.original_text for chunks that still exist, ordered by
     position (earliest first) — position is still meaningful here.
  3. document_removed_lines.line_text — position/order is NOT recoverable
     (chunk_id/run_id go NULL on delete, no ORDER BY reflects original page
     order). A "Zobacz również:" recommendation card embeds a DIFFERENT
     article's timestamp next to its own title — mistaking that for this
     document's publication date would write a wrong date. So: if ANY
     removed_lines row for a document contains a sidebar/recommendation
     marker, this level is skipped entirely for that document (safety over
     coverage — better to leave published_on empty than write a wrong date).

Never overwrites an existing published_on.

Usage:
    python imports/backfill_relative_publication_dates.py            # dry-run (default)
    python imports/backfill_relative_publication_dates.py --apply    # write changes
    python imports/backfill_relative_publication_dates.py --id 8865  # single document
"""

import argparse
import datetime
import logging

from library.config_loader import load_config

load_config()  # side effect: populates os.environ for library modules

from sqlalchemy import select  # noqa: E402

from library.article_cleaner import resolve_relative_publication_date  # noqa: E402
from library.db.engine import get_session  # noqa: E402
from library.db.models import Document, DocumentChunk, DocumentRemovedLine  # noqa: E402

logger = logging.getLogger(__name__)

# Only the 7 document_type values with a registered polymorphic subclass
# (library/db/models.py) — some rows carry a stray/legacy type (e.g. "email")
# that has no mapped subclass and crashes ORM polymorphic loading. Excluding
# them here is a query-side workaround, not a fix for that underlying gap.
_KNOWN_DOCUMENT_TYPES = (
    "link", "youtube", "movie", "webpage", "text_message", "text", "social_media_post",
)

# A relative-date line sitting near/under one of these markers most likely
# belongs to a DIFFERENT article referenced in a recommendation card, not to
# this document itself.
_SIDEBAR_MARKERS = (
    "zobacz również", "zobacz też", "czytaj także", "czytaj również",
    "polecane", "powiązane", "czytaj więcej", "warto przeczytać",
)


def _contains_sidebar_marker(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in _SIDEBAR_MARKERS)


def _resolve_for_document(session, doc: Document) -> datetime.date | None:
    """Find the safest relative-date candidate, most trustworthy source first."""
    for text in (doc.text_md, doc.text, doc.text_raw):
        if text:
            resolved = resolve_relative_publication_date(text, doc.ingested_at)
            if resolved is not None:
                return resolved

    chunk_texts = session.scalars(
        select(DocumentChunk.original_text)
        .where(DocumentChunk.document_id == doc.id)
        .order_by(DocumentChunk.position)
    ).all()
    for chunk_text in chunk_texts:
        if chunk_text and not _contains_sidebar_marker(chunk_text):
            resolved = resolve_relative_publication_date(chunk_text, doc.ingested_at)
            if resolved is not None:
                return resolved

    removed_lines = session.scalars(
        select(DocumentRemovedLine.line_text).where(DocumentRemovedLine.document_id == doc.id)
    ).all()
    if any(_contains_sidebar_marker(t) for t in removed_lines):
        return None
    for line_text in removed_lines:
        resolved = resolve_relative_publication_date(line_text, doc.ingested_at)
        if resolved is not None:
            return resolved
    return None


def main():
    parser = argparse.ArgumentParser(
        description="Backfill documents.published_on from relative-date artifacts (Wczoraj/Dziś, HH:MM; X minut/godzin temu)."
    )
    parser.add_argument("--apply", action="store_true", help="Write changes (default: dry-run preview only)")
    parser.add_argument("--id", type=int, help="Process a single document by id")
    parser.add_argument("--limit", type=int, help="Max number of documents to process")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    session = get_session()
    try:
        query = select(Document).where(
            Document.published_on.is_(None), Document.ingested_at.isnot(None),
            Document.document_type.in_(_KNOWN_DOCUMENT_TYPES),
        )
        if args.id:
            query = query.where(Document.id == args.id)
        query = query.order_by(Document.id)
        if args.limit:
            query = query.limit(args.limit)
        docs = session.scalars(query).all()

        logging.info(f"Checking {len(docs)} document(s) missing published_on")

        updated = 0
        for doc in docs:
            resolved = _resolve_for_document(session, doc)
            if resolved is None:
                continue

            logging.info(f"doc #{doc.id} ({doc.url}): published_on -> {resolved.isoformat()}")
            if args.apply:
                doc.published_on = resolved
                doc.published_on_method = "relative"
                session.commit()
            updated += 1

        logging.info(f"Done. Resolved: {updated}, checked: {len(docs)}")
        if not args.apply:
            logging.info("(dry-run — no changes were saved; re-run with --apply)")
    finally:
        session.close()


if __name__ == "__main__":
    main()
