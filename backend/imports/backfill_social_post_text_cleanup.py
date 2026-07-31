#!/usr/bin/env python3
"""One-off backfill: strip trailing comment/reaction noise from social_media_post
text captured before web_chrome_extension's trimAtEngagementBoundary() fix
(popup.js 1.0.43).

Facebook/LinkedIn posts captured by earlier extension versions could have a
full comment thread (reaction counts, "Most relevant", a commenter's
name/bio/text) appended to the actual post body — see doc 9347. This is a
Python port of the same trimAtEngagementBoundary() logic now applied
client-side at capture time, run once against the already-imported rows.

Only touches documents without embeddings yet (document_has_embeddings guard)
— a document with embeddings must be reopened for editing first, same rule
POST /document/<id>/analyze_chunks already enforces.

Usage:
    cd backend
    .venv/Scripts/python imports/backfill_social_post_text_cleanup.py            # dry-run (default)
    .venv/Scripts/python imports/backfill_social_post_text_cleanup.py --apply
    .venv/Scripts/python imports/backfill_social_post_text_cleanup.py --id 9347  # single document
"""

import argparse
import logging
import re

from library.config_loader import load_config

cfg = load_config()  # noqa: F841 — side effect: populates os.environ for library modules

from library.db.engine import get_session  # noqa: E402
from library.db.models import Document  # noqa: E402
from library.document_editing import document_has_embeddings  # noqa: E402

logger = logging.getLogger(__name__)

# Kept in sync with web_chrome_extension/popup.js's ENGAGEMENT_STOP_LINES/ENGAGEMENT_COUNT_RE.
_ENGAGEMENT_STOP_LINES = {
    "Like", "Comment", "Repost", "Send", "Show more", "See translation", "Translate",
    "Most relevant", "All comments", "Top comments", "Follow", "Connect",
    "Lubię to!", "Lubię to", "Skomentuj", "Komentarz", "Udostępnij", "Wyślij",
    "Najtrafniejsze", "Wszystkie komentarze", "Zobacz tłumaczenie", "Przetłumacz", "Obserwuj",
}
_ENGAGEMENT_COUNT_RE = re.compile(
    r"^\d+\s+(?:reactions?|comments?|reposts?|shares?|repost(?:y|ów)?|"
    r"komentarz(?:e|y)?|reakcj[ei]|udostępnie(?:ń|nia)?)$",
    re.IGNORECASE,
)
_MORE_RE = re.compile(r"^(?:…|\.\.\.)\s*more$", re.IGNORECASE)
_BARE_NUMBER_RE = re.compile(r"^\d{1,4}$")


def trim_at_engagement_boundary(text: str | None) -> str:
    lines = (text or "").split("\n")
    stop_index = None
    numeric_run = 0
    numeric_run_start = None
    for i, raw_line in enumerate(lines):
        line = raw_line.strip()
        if not line:
            continue
        if _MORE_RE.match(line) or line in _ENGAGEMENT_STOP_LINES or _ENGAGEMENT_COUNT_RE.match(line):
            stop_index = i
            break
        if _BARE_NUMBER_RE.match(line):
            if numeric_run == 0:
                numeric_run_start = i
            numeric_run += 1
            if numeric_run >= 2:
                stop_index = numeric_run_start
                break
        else:
            numeric_run = 0
    kept = lines[:stop_index] if stop_index is not None else lines
    return "\n".join(kept).strip()


def find_candidates(session, doc_id: int | None = None) -> list[Document]:
    query = session.query(Document).filter(Document.document_type == "social_media_post")
    if doc_id:
        query = query.filter(Document.id == doc_id)
    return query.order_by(Document.id).all()


def main():
    parser = argparse.ArgumentParser(
        description="Strip trailing comment/reaction noise from already-imported social_media_post text.",
    )
    parser.add_argument("--apply", action="store_true", help="Write changes to the database (default: dry-run)")
    parser.add_argument("--id", type=int, help="Process a single document by id")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    session = get_session()
    try:
        candidates = find_candidates(session, args.id)
        logging.info("Found %d social_media_post document(s)", len(candidates))

        changed = 0
        skipped_embeddings = 0
        for doc in candidates:
            if document_has_embeddings(session, doc.id):
                skipped_embeddings += 1
                logging.warning("doc #%s: has embeddings, skipping (reopen for editing first)", doc.id)
                continue

            new_text = trim_at_engagement_boundary(doc.text)
            new_text_raw = trim_at_engagement_boundary(doc.text_raw)
            removed_text = len(doc.text or "") - len(new_text)
            removed_raw = len(doc.text_raw or "") - len(new_text_raw)
            if removed_text <= 0 and removed_raw <= 0:
                logging.info("doc #%s: nothing to trim", doc.id)
                continue

            changed += 1
            logging.info(
                "doc #%s: text -%d chars, text_raw -%d chars",
                doc.id, removed_text, removed_raw,
            )
            if args.apply:
                doc.text = new_text
                doc.text_raw = new_text_raw
                doc.document_length = len(new_text)
            else:
                session.expunge(doc)  # dry-run: don't let a later commit persist this

        if args.apply:
            session.commit()
            logging.info(
                "Done. Trimmed %d of %d candidate documents (%d skipped: has embeddings).",
                changed, len(candidates), skipped_embeddings,
            )
        else:
            logging.info(
                "Dry-run: %d of %d candidate documents would be trimmed (%d would be skipped: has embeddings). "
                "Re-run with --apply to save.",
                changed, len(candidates), skipped_embeddings,
            )
    finally:
        session.close()


if __name__ == "__main__":
    main()
