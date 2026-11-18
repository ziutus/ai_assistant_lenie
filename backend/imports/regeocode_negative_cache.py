"""Recheck legacy JSON-null negative geocodes, preserving IDs. Dry-run by default.

Run from backend with PYTHONPATH=.: python imports/regeocode_negative_cache.py
Dry-run calls the geocoder but does not update the database.
"""

import argparse
from datetime import date
import math
import time

from sqlalchemy import text

from library.db.engine import get_session
from library.db.models import GeocodeCache
from library.locationiq_client import GeocodeUnavailable
from library.place_verification import resolve_geocode


def repair(session, *, apply=False, limit=None, sleep=1.0, created_before=None):
    """Recheck candidates sequentially; commit each successful repair only in apply mode."""
    candidates = session.query(GeocodeCache).filter(text("raw::text = 'null' AND NOT resolved"))
    if created_before is not None:
        candidates = candidates.filter(GeocodeCache.created_at < created_before)
    candidates = candidates.order_by(GeocodeCache.id)
    if limit is not None:
        candidates = candidates.limit(limit)
    # Snapshot IDs so committing a repair does not disturb candidate selection.
    ids = [row.id for row in candidates.all()]
    summary = {"checked": 0, "newly resolved": 0, "still unresolved (clean miss)": 0, "failed": 0}
    for index, row_id in enumerate(ids):
        if index:
            time.sleep(sleep)
        row = session.get(GeocodeCache, row_id)
        summary["checked"] += 1
        try:
            fields = resolve_geocode(row.query)
        except GeocodeUnavailable as exc:
            summary["failed"] += 1
            print(f"Stopped at id={row.id}, query={row.query!r}: {exc}")
            break
        category = "newly resolved" if fields["resolved"] else "still unresolved (clean miss)"
        print(f"id={row.id}, query={row.query!r}: {category}")
        if apply:
            for field, value in fields.items():
                setattr(row, field, value)
            session.commit()
        summary[category] += 1
    print(("APPLY" if apply else "DRY RUN") + ": " + " / ".join(f"{k}: {v}" for k, v in summary.items()))
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--sleep", type=float, default=1.0, metavar="SECONDS")
    parser.add_argument("--created-before", type=date.fromisoformat, metavar="DATE")
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    if not math.isfinite(args.sleep) or args.sleep < 0:
        parser.error("--sleep must be finite and non-negative")
    with get_session() as session:
        summary = repair(session, apply=args.apply, limit=args.limit, sleep=args.sleep,
                         created_before=args.created_before)
    return int(bool(summary["failed"]))


if __name__ == "__main__":
    raise SystemExit(main())
