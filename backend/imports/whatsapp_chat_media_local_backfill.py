#!/usr/bin/env python3
"""One-off fix: upload chat_messages media files that landed in the wrong
storage backend back to the real one, under their already-recorded key.

Context: the initial full run of imports/whatsapp_chat_import.py (2026-09-20)
was invoked from a dev-machine shell with SECRETS_BACKEND=env (to target the
NAS PostgreSQL directly), which bypasses Vault — the place STORAGE_BACKEND
and MinIO credentials actually live for this project (see
feedback_dev_machine_storage_backend_mismatch.md). storage_from_config()
silently fell back to LocalStorage, so all 973 uploaded attachments landed
on the dev machine's local disk (under /app/data, which on Windows resolves
to C:\\app\\data) instead of the NAS MinIO — while the DB rows'
chat_messages.media_storage_key values are correct (the key is
backend-independent), the referenced bytes were never reachable by the real
backend.

This script re-uploads those same bytes to whatever storage
storage_from_config() resolves to — run it where that's the real backend
(inside the lenie-ai-server container on the NAS, SECRETS_BACKEND=vault by
default there), never from a bare dev-machine shell.

Walks --dir (expected to mirror the chat_media/... key prefix exactly, e.g.
a copy of the dev machine's C:\\app\\data\\chat_media directory placed at
.../chat_media) and uploads each file under its key --key-prefix + relative
path. Skips a key that already exists in the target storage unless --force.

Usage (inside the container, after `docker cp`):
    python imports/whatsapp_chat_media_local_backfill.py --dir /tmp/chat_media_backfill/chat_media --key-prefix chat_media   # dry-run
    python imports/whatsapp_chat_media_local_backfill.py --dir /tmp/chat_media_backfill/chat_media --key-prefix chat_media --apply
"""

import argparse
import logging
import mimetypes
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger("whatsapp_chat_media_local_backfill")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dir", required=True, help="Local directory whose contents mirror the storage key prefix")
    parser.add_argument("--key-prefix", required=True, help="Storage key prefix these files belong under, e.g. 'chat_media'")
    parser.add_argument("--force", action="store_true", help="Re-upload even if the key already exists in the target storage")
    parser.add_argument("--apply", action="store_true", help="Actually upload (default: dry-run, lists what would be uploaded)")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(message)s")

    storage = None
    if args.apply:
        from library.config_loader import load_config
        from library.storage import storage_from_config

        storage = storage_from_config(load_config())
        logger.info("Target storage: %s", type(storage).__name__)

    uploaded = skipped_existing = failed = 0
    total_bytes = 0

    for root, _dirs, files in os.walk(args.dir):
        for filename in files:
            local_path = os.path.join(root, filename)
            rel_path = os.path.relpath(local_path, args.dir).replace(os.sep, "/")
            key = f"{args.key_prefix}/{rel_path}"

            if args.apply and not args.force and storage.exists(key):
                skipped_existing += 1
                logger.debug("Już istnieje w storage, pomijam: %s", key)
                continue

            size = os.path.getsize(local_path)
            total_bytes += size
            content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

            if not args.apply:
                uploaded += 1
                continue

            try:
                with open(local_path, "rb") as f:
                    storage.put_bytes(key, f.read(), content_type)
                uploaded += 1
                logger.debug("Wgrano: %s (%d bajtów)", key, size)
            except Exception:
                failed += 1
                logger.exception("Błąd wgrywania: %s", key)

    print()
    print(f"Plików do wgrania/wgranych: {uploaded}")
    print(f"Pominiętych (już istniały w storage): {skipped_existing}")
    print(f"Błędów: {failed}")
    print(f"Łączny rozmiar: {total_bytes / 1024 / 1024:.1f} MB")
    if not args.apply:
        print("[DRY-RUN] Nic nie wgrano — użyj --apply.")


if __name__ == "__main__":
    main()
