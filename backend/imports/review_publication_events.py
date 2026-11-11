#!/usr/bin/env python3
"""One-off review: timeline entries and registry events that only report a publication.

A sentence such as "w 2015 roku opublikowano badanie Towers i in. o zarażaniu przemocą" says when a study appeared;
it is a source of information, not an event of the world. Before the timeline extractor learned to skip such
statements (`timeline_events.PUBLICATION_RULE`), they were stored in `document_events` and some were promoted to
`geo_events` (kind `other`). This script finds them and moves them over to information sources
(`library/document_event_sources.py`):

* a timeline entry becomes an approved `cited` source of its document and leaves the timeline;
* a registry event becomes sources of the documents that cite it and is `rejected` (never revived by a repeated
  report) - only when nothing depends on it: still `proposed`, kind `other`, no participants, no assessment resting
  on it. Anything else is listed under "skipped" for a human.

Usage:
    cd backend
    PYTHONPATH=. .venv/Scripts/python -X utf8 imports/review_publication_events.py            # dry-run (default)
    PYTHONPATH=. .venv/Scripts/python -X utf8 imports/review_publication_events.py --apply
    PYTHONPATH=. .venv/Scripts/python -X utf8 imports/review_publication_events.py --limit 50
"""

import argparse
import logging

from library.config_loader import load_config

cfg = load_config()  # noqa: F841 - side effect: populates os.environ for library modules

from library.db.engine import get_session  # noqa: E402
from library.document_event_sources import review_publication_entries  # noqa: E402

logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(
        description="Move publication statements from the timeline / world-event registry to information sources.",
    )
    parser.add_argument("--apply", action="store_true", help="Write changes to the database (default: dry-run)")
    parser.add_argument("--limit", type=int, default=500, help="Maximum timeline entries to handle (default 500)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    session = get_session()
    try:
        report = review_publication_entries(session, apply=args.apply, limit=args.limit)
        if args.apply:
            session.commit()
        else:
            session.rollback()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    mode = "APPLIED" if args.apply else "DRY-RUN"
    print(f"[{mode}] timeline entries: {len(report['timeline'])}, registry events: {len(report['registry'])}, "
          f"registry skipped: {len(report['skipped'])}")
    for item in report["timeline"]:
        note = f"  ERROR: {item['error']}" if item.get("error") else ""
        print(f"  timeline #{item['document_event_id']} (doc {item['document_id']}): {item['description'][:110]}{note}")
    for item in report["registry"]:
        note = f"  ERROR: {item['error']}" if item.get("error") else ""
        print(f"  event #{item['event_id']} (docs {item['documents']}): {item['title'][:110]}{note}")
    for item in report["skipped"]:
        print(f"  SKIPPED event #{item['event_id']} ({item['skipped']}): {item['title'][:110]}")


if __name__ == "__main__":
    main()
