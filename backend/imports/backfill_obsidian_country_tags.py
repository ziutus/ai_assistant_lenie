#!/usr/bin/env python3
"""One-off backfill: ``kraj-*`` tags for existing obsidian_note documents, so the
reader's country map (CountryMap, rendered only for ``kraj-*`` tags) appears on
notes such as "Sudan". New/changed notes get the same tags at reimport time
(obsidian_reimport_service.detect_country_tags); this covers notes that were
imported unchanged before that. Gazetteer only — no LLM, no embeddings, so it is
cheap; it still works in small batches per docs/deployment/nas/obsidian-batch-backfill.md.

Tags are only added, never removed.

Usage:
    cd backend
    .venv/Scripts/python imports/backfill_obsidian_country_tags.py                    # dry-run
    .venv/Scripts/python imports/backfill_obsidian_country_tags.py --apply --limit 100
    .venv/Scripts/python imports/backfill_obsidian_country_tags.py --apply --id 10058
"""

import argparse

from library.config_loader import load_config

load_config()  # side effect: populates os.environ for library modules

from sqlalchemy import select  # noqa: E402

from library.db.engine import get_session  # noqa: E402
from library.db.models import Document  # noqa: E402
from library.obsidian_reimport_service import _merge_tags, detect_country_tags  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--apply", action="store_true", help="write tags (default: dry-run)")
    parser.add_argument("--limit", type=int, default=100, help="max documents to change (default 100)")
    parser.add_argument("--id", type=int, help="only this document id")
    args = parser.parse_args()

    changed = 0
    with get_session() as session:
        query = select(Document).where(Document.document_type == "obsidian_note").order_by(Document.id)
        if args.id:
            query = query.where(Document.id == args.id)
        for doc in session.scalars(query):
            if changed >= args.limit:
                break
            new_tags = detect_country_tags(doc.title or "", doc.text_md or doc.text or "")
            merged = _merge_tags(doc.tags, new_tags)
            if merged == doc.tags:
                continue
            changed += 1
            print(f"{doc.id}\t{doc.title}\t+{[t for t in new_tags if t not in (doc.tags or '')]}")
            if args.apply:
                doc.tags = merged
        if args.apply:
            session.commit()
    print(f"{'applied' if args.apply else 'dry-run'}: {changed} document(s)")


if __name__ == "__main__":
    main()
