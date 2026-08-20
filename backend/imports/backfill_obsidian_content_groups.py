#!/usr/bin/env python3
"""One-off backfill: request content-group (Tematy) classification for
already-imported Obsidian notes.

obsidian_reimport_service.py now enqueues a content_group_suggest job for
every note it creates/updates (see request_suggestions() there), but that
only covers notes imported/edited after that change shipped. This script
retroactively enqueues the same job for the ~900 obsidian_note documents
already in the pilot vault subfolders (Informatyka, Geopolityka i polityka)
-- e.g. document 9922 ("jq"), which has the "linux" tag but no "Linux"
content group membership because it predates the auto-classification hook.

This script only ENQUEUES content_group_suggest jobs -- it does not call the
LLM itself. Actual classification (and, above CONTENT_GROUP_AUTO_APPLY_MIN_
CONFIDENCE, auto-assignment) happens asynchronously via the worker already
running on the NAS (worker.py handles content_group_suggest by default).

Usage:
    cd backend
    .venv/Scripts/python imports/backfill_obsidian_content_groups.py               # dry-run (default)
    .venv/Scripts/python imports/backfill_obsidian_content_groups.py --apply
    .venv/Scripts/python imports/backfill_obsidian_content_groups.py --apply --id 9922
    .venv/Scripts/python imports/backfill_obsidian_content_groups.py --apply --limit 20
    .venv/Scripts/python imports/backfill_obsidian_content_groups.py --apply --force  # also re-enqueue already-classified notes
"""

import argparse
import logging

from library.config_loader import load_config

cfg = load_config()  # noqa: F841 — side effect: populates os.environ for library modules

from library.content_group_suggestion_service import request_suggestions  # noqa: E402
from library.db.engine import get_session  # noqa: E402
from library.db.models import Document  # noqa: E402

logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Enqueue content-group suggestions for existing obsidian_note documents.")
    parser.add_argument("--apply", action="store_true", help="Enqueue jobs (default: dry-run, list candidates only)")
    parser.add_argument("--id", type=int, help="Process a single document by id")
    parser.add_argument("--limit", type=int, help="Max number of documents to process")
    parser.add_argument("--force", action="store_true", help="Include documents that already have a content group membership")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    session = get_session()
    try:
        query = session.query(Document).filter(Document.document_type == "obsidian_note")
        if args.id:
            query = query.filter(Document.id == args.id)
        elif not args.force:
            query = query.filter(~Document.group_memberships.any())
        query = query.order_by(Document.id)
        if args.limit:
            query = query.limit(args.limit)
        docs = query.all()
        logging.info("Found %d obsidian_note document(s) to classify", len(docs))

        for doc in docs:
            logging.info("doc #%s: %s", doc.id, doc.title)
            if args.apply:
                job, run = request_suggestions(session, "document", doc.id, user_id=None)
                logging.info("  -> job=%s run=%s status=%s", job.id if job else None, run.id, run.status)

        if not args.apply:
            logging.info("Dry-run: %d document(s) would be enqueued. Re-run with --apply to submit.", len(docs))
    finally:
        session.close()


if __name__ == "__main__":
    main()
