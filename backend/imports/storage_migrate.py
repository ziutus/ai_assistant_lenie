#!/usr/bin/env python3
"""Copy a local file tree to configured storage and report storage usage.

Examples:
  python imports/storage_migrate.py usage
  python imports/storage_migrate.py upload --source tmp --prefix cache --dry-run
  python imports/storage_migrate.py upload --source data --prefix documents
"""

from __future__ import annotations

import argparse
import mimetypes
from pathlib import Path

from library.config_loader import load_config
from library.storage import storage_from_config, usage


def human_size(value: int) -> str:
    size = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024 or unit == "TiB":
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} TiB"


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate local files to local/S3/MinIO storage")
    sub = parser.add_subparsers(dest="command", required=True)
    usage_parser = sub.add_parser("usage", help="Count objects and bytes in configured storage")
    usage_parser.add_argument("--prefix", default="")
    upload = sub.add_parser("upload", help="Upload a local directory recursively")
    upload.add_argument("--source", required=True)
    upload.add_argument("--prefix", default="")
    upload.add_argument("--dry-run", action="store_true")
    upload.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    store = storage_from_config(load_config())
    if args.command == "usage":
        count, total = usage(store, args.prefix)
        print(f"Objects: {count}\nBytes: {total}\nSize: {human_size(total)}")
        return

    source = Path(args.source).resolve()
    if not source.is_dir():
        parser.error(f"source is not a directory: {source}")
    copied = skipped = bytes_copied = 0
    for path in source.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(source).as_posix()
        key = "/".join(part for part in (args.prefix.strip("/"), relative) if part)
        if not args.overwrite and store.exists(key):
            skipped += 1
            continue
        size = path.stat().st_size
        print(f"{'DRY-RUN ' if args.dry_run else ''}{path} -> {key} ({human_size(size)})")
        if not args.dry_run:
            store.put_bytes(key, path.read_bytes(), mimetypes.guess_type(path.name)[0])
        copied += 1
        bytes_copied += size
    print(f"Copied: {copied} ({human_size(bytes_copied)}), skipped: {skipped}")


if __name__ == "__main__":
    main()
