#!/usr/bin/env python3
"""Compatibility wrapper for the temporary NAS legacy-AWS pull bridge.

All synchronization behaviour lives in ``library.legacy_aws_pull_service``.
This command remains only as an operator fallback until the AWS buffer is
explicitly retired.
"""

from __future__ import annotations

import argparse
import json

from library.config_loader import load_config
from library.db.engine import get_session
from library.legacy_aws_pull_service import LegacyAwsPullService
from library.storage import storage_from_config


def main() -> int:
    parser = argparse.ArgumentParser(description="Pull legacy AWS DynamoDB/S3 sources through DocumentIngestService")
    parser.add_argument("--since", help="required ISO-8601 timestamp until the bridge has a successful run")
    parser.add_argument("--dry-run", action="store_true", help="query DynamoDB only; do not use PostgreSQL or MinIO")
    parser.add_argument("--limit", type=int, default=0, help="diagnostic maximum (0 = unlimited)")
    args = parser.parse_args()
    parameters = {"since": args.since, "dry_run": args.dry_run, "limit": args.limit}
    cfg = load_config()
    session = None if args.dry_run else get_session()
    try:
        storage = None if args.dry_run else storage_from_config(cfg)
        result = LegacyAwsPullService(session, storage, cfg).run(parameters)
    finally:
        if session is not None:
            session.close()
    print(json.dumps(result, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
