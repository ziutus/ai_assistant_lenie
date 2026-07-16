#!/usr/bin/env python3
"""One-off cleanup: supersede abandoned duplicate analysis runs.

Before document_analysis_service.create_run() started superseding unfinished
sibling runs, an accidental second /analyze_chunks call for the same
document+scope (double click, retry after an error) left the first run behind
in status "created" forever — its pending chunks kept showing up in the
"missing Obsidian notes" filter on /list (the case behind document 9245:
run #32 abandoned, run #33 actually used for notes).

This script finds every (document_id, scope) group with more than one run,
marks each run that is not the newest of its group and never reached
"reviewed" as status="superseded", and flips its still-open chunks
(pending / needs_reanalysis / split_requested) to "skipped". Approved/split
chunks and recorded note paths stay untouched; nothing is deleted. A run
whose chunks already carry Obsidian notes is reported but never touched.

Usage:
    cd backend
    .venv/Scripts/python imports/fix_duplicate_analysis_runs.py            # dry-run (default)
    .venv/Scripts/python imports/fix_duplicate_analysis_runs.py --apply
    .venv/Scripts/python imports/fix_duplicate_analysis_runs.py --id 9245  # single document
"""

import argparse
import logging
from collections import defaultdict

from library.config_loader import load_config

cfg = load_config()  # noqa: F841 — side effect: populates os.environ for library modules

from sqlalchemy import func, select  # noqa: E402

from library.db.engine import get_session  # noqa: E402
from library.db.models import DocumentAnalysisRun, DocumentChunk  # noqa: E402
from library.document_analysis_service import OPEN_CHUNK_STATUSES, stale_duplicate_runs  # noqa: E402

logger = logging.getLogger(__name__)


def runs_with_notes(session) -> set[int]:
    """IDs of runs that have at least one chunk with an Obsidian note recorded."""
    return set(session.scalars(
        select(DocumentChunk.run_id)
        .where(func.coalesce(func.array_length(DocumentChunk.obsidian_note_paths, 1), 0) > 0)
        .distinct()
    ).all())


def main():
    parser = argparse.ArgumentParser(
        description="Supersede abandoned duplicate analysis runs (same document_id+scope, never reviewed).",
    )
    parser.add_argument("--apply", action="store_true", help="Write changes to the database (default: dry-run)")
    parser.add_argument("--id", type=int, help="Process a single document by id")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    session = get_session()
    try:
        query = session.query(DocumentAnalysisRun)
        if args.id:
            query = query.filter(DocumentAnalysisRun.document_id == args.id)
        runs = query.order_by(DocumentAnalysisRun.document_id, DocumentAnalysisRun.id).all()

        groups: dict[tuple[int, str | None], list[DocumentAnalysisRun]] = defaultdict(list)
        for run in runs:
            groups[(run.document_id, run.scope)].append(run)

        noted_run_ids = runs_with_notes(session)

        superseded = 0
        chunks_skipped = 0
        for (doc_id, scope), group in sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1] or "")):
            stale = stale_duplicate_runs(group)
            if not stale:
                continue
            newest = max(group, key=lambda r: (r.created_at, r.id))
            for run in stale:
                if run.id in noted_run_ids:
                    logging.warning(
                        "doc #%d scope=%r: run #%d has chunks with Obsidian notes — NOT touched",
                        doc_id, scope, run.id,
                    )
                    continue
                open_chunks = [c for c in run.chunks if c.status in OPEN_CHUNK_STATUSES]
                logging.info(
                    "doc #%d scope=%r: run #%d (%s, %d open chunks) superseded by run #%d (+%s)",
                    doc_id, scope, run.id, run.status, len(open_chunks),
                    newest.id, newest.created_at - run.created_at,
                )
                superseded += 1
                chunks_skipped += len(open_chunks)
                if args.apply:
                    run.status = "superseded"
                    for chunk in open_chunks:
                        chunk.status = "skipped"

        if args.apply:
            session.commit()
            logging.info("Done. Superseded %d runs, skipped %d chunks.", superseded, chunks_skipped)
        else:
            logging.info(
                "Dry-run: %d runs would be superseded (%d chunks skipped). Re-run with --apply to save.",
                superseded, chunks_skipped,
            )
    finally:
        session.close()


if __name__ == "__main__":
    main()
