#!/usr/bin/env python3
"""One-time migration: move S3 files from data/ to CACHE_DIR/{doc_id}/{doc_id}.ext

Reads UUID-named files from data/, queries PostgreSQL for doc.id by s3_uuid,
and moves files to the cache directory convention used by document_prepare.py.

Usage:
    cd backend
    python imports/migrate_data_to_cache.py
    python imports/migrate_data_to_cache.py --dry-run
    python imports/migrate_data_to_cache.py --source-dir data --target-dir tmp/markdown
"""

import argparse
import os
import shutil
import sys
from glob import glob

from sqlalchemy import select

from library.config_loader import load_config
from library.db.models import WebDocument
from library.db.engine import get_session

cfg = load_config()


def get_s3_uuid_to_doc_id_map(session, s3_uuids: list[str]) -> dict[str, int]:
    """Query DB for doc.id by s3_uuid. Returns {s3_uuid: doc_id} mapping."""
    stmt = select(WebDocument.id, WebDocument.s3_uuid).where(WebDocument.s3_uuid.in_(s3_uuids))
    rows = session.execute(stmt).all()
    return {row.s3_uuid: row.id for row in rows}


def main():
    parser = argparse.ArgumentParser(description="Migrate S3 files from data/ to cache dir")
    parser.add_argument("--source-dir", default="data", help="Source directory with UUID-named files (default: data)")
    parser.add_argument("--target-dir", default=None, help="Target cache dir (default: CACHE_DIR config or tmp/markdown)")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no file moves")
    parser.add_argument("--delete-source", action="store_true", help="Delete source files after successful move")
    args = parser.parse_args()

    if args.target_dir is None:
        args.target_dir = cfg.get("CACHE_DIR") or "tmp/markdown"

    if not os.path.isdir(args.source_dir):
        print(f"ERROR: source directory '{args.source_dir}' does not exist")
        sys.exit(1)

    # Find all UUID-named files (html and txt)
    files = glob(os.path.join(args.source_dir, "*.html")) + glob(os.path.join(args.source_dir, "*.txt"))
    if not files:
        print(f"No .html/.txt files found in {args.source_dir}")
        return

    # Extract unique s3_uuids from filenames
    s3_uuids = set()
    for f in files:
        basename = os.path.basename(f)
        s3_uuid = os.path.splitext(basename)[0]
        s3_uuids.add(s3_uuid)

    print(f"Found {len(files)} files ({len(s3_uuids)} unique UUIDs) in {args.source_dir}")
    print(f"Target: {args.target_dir}")
    if args.dry_run:
        print("Mode: DRY-RUN")
    print()

    # Query DB for mapping
    session = get_session()
    try:
        uuid_to_id = get_s3_uuid_to_doc_id_map(session, list(s3_uuids))
    finally:
        session.close()

    print(f"DB mapping: {len(uuid_to_id)}/{len(s3_uuids)} UUIDs found in database\n")

    moved = 0
    skipped = 0
    not_found = 0

    for s3_uuid in sorted(s3_uuids):
        doc_id = uuid_to_id.get(s3_uuid)
        if doc_id is None:
            print(f"  SKIP: {s3_uuid} — not found in database")
            not_found += 1
            continue

        doc_dir = os.path.join(args.target_dir, str(doc_id))

        for ext in [".html", ".txt"]:
            src = os.path.join(args.source_dir, f"{s3_uuid}{ext}")
            if not os.path.isfile(src):
                continue

            dst = os.path.join(doc_dir, f"{doc_id}{ext}")

            if os.path.isfile(dst):
                print(f"  SKIP: {dst} already exists")
                skipped += 1
                continue

            if args.dry_run:
                print(f"  DRY-RUN: {src} -> {dst}")
                moved += 1
            else:
                os.makedirs(doc_dir, exist_ok=True)
                shutil.copy2(src, dst)
                print(f"  MOVED: {src} -> {dst}")
                moved += 1

                if args.delete_source:
                    os.remove(src)
                    print(f"  DELETED: {src}")

    print("\n=== Summary ===")
    print(f"Moved: {moved}")
    print(f"Skipped (already exist): {skipped}")
    print(f"Not found in DB: {not_found}")

    if not args.dry_run and not args.delete_source and moved > 0:
        print(f"\nSource files kept in {args.source_dir}. Use --delete-source to remove them after migration.")


if __name__ == "__main__":
    main()
