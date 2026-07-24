#!/usr/bin/env python3
"""One-off backfill: tag documents whose single-chunk run never got tagged.

document_analysis_service.create_run()'s tagging step (11b) used to derive its
input text only from `synthesis` or `topic_sections_data` — both of which end
up empty for a run with exactly one TEMAT chunk (grouping one fragment into
"logical sections" is meaningless, so _merge_topics tends to return no valid
group). The fix (same commit) skips _merge_topics for single-chunk runs and
adds a fallback straight to the chunk's own summary, but documents analyzed
before the fix are stuck with tags=NULL and are invisible to anything gated on
tags (e.g. the /obsidian-note control-questions step). This script re-tags
them using the same _apply_tags() pipeline, from the chunk summary already on
file — no LLM re-analysis of the article itself needed.

Usage:
    cd backend
    .venv/Scripts/python imports/backfill_missing_tags.py            # dry-run (default)
    .venv/Scripts/python imports/backfill_missing_tags.py --apply
    .venv/Scripts/python imports/backfill_missing_tags.py --id 9256  # single document
"""

import argparse
import logging

from library.config_loader import load_config

cfg = load_config()  # noqa: F841 — side effect: populates os.environ for library modules

from library.db.engine import get_session  # noqa: E402
from library.db.models import Document, DocumentAnalysisRun  # noqa: E402
from library.document_analysis_service import _apply_tags  # noqa: E402

logger = logging.getLogger(__name__)


# Known STI polymorphic_identity values (db/models.py) — the query is
# restricted to these because at least one stray row in the NAS DB carries a
# document_type ("email") with no matching subclass, which makes SQLAlchemy's
# polymorphic loader raise on the whole result set rather than just that row.
_KNOWN_DOCUMENT_TYPES = ("link", "youtube", "movie", "webpage", "text_message", "text", "social_media_post")


def find_candidates(session, doc_id: int | None = None) -> list[tuple[Document, str]]:
    """Documents with empty tags whose only reviewed run has exactly one
    TEMAT chunk with a summary. Returns (document, tagging_text) pairs."""
    query = (
        session.query(Document)
        .filter((Document.tags.is_(None)) | (Document.tags == ""))
        .filter(Document.document_type.in_(_KNOWN_DOCUMENT_TYPES))
    )
    if doc_id:
        query = query.filter(Document.id == doc_id)

    candidates = []
    for doc in query.order_by(Document.id).all():
        runs = (
            session.query(DocumentAnalysisRun)
            .filter(
                DocumentAnalysisRun.document_id == doc.id,
                DocumentAnalysisRun.status != "superseded",
            )
            .all()
        )
        for run in runs:
            temat_chunks = [c for c in run.chunks if c.type == "TEMAT"]
            if len(temat_chunks) != 1:
                continue
            summary = temat_chunks[0].summary
            if summary:
                candidates.append((doc, summary))
            break
    return candidates


def main():
    parser = argparse.ArgumentParser(
        description="Tag documents whose single-chunk run never got tagged (missing synthesis/topic_sections fallback).",
    )
    parser.add_argument("--apply", action="store_true", help="Write changes to the database (default: dry-run)")
    parser.add_argument("--id", type=int, help="Process a single document by id")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    session = get_session()
    try:
        candidates = find_candidates(session, args.id)
        logging.info("Found %d candidate documents with a single-chunk run and no tags", len(candidates))

        tagged = 0
        for doc, summary in candidates:
            _apply_tags(doc, summary)
            if not doc.tags:
                logging.info("doc #%s: LLM found no applicable tags", doc.id)
                continue
            tagged += 1
            logging.info("doc #%s: tags -> %s", doc.id, doc.tags)
            if not args.apply:
                session.expunge(doc)  # dry-run: don't let a later commit persist this

        if args.apply:
            session.commit()
            logging.info("Done. Tagged %d of %d candidate documents.", tagged, len(candidates))
        else:
            logging.info(
                "Dry-run: %d of %d candidate documents would be tagged. Re-run with --apply to save.",
                tagged, len(candidates),
            )
    finally:
        session.close()


if __name__ == "__main__":
    main()
