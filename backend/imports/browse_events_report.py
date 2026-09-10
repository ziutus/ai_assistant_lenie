#!/usr/bin/env python
"""Read-only panel usage report: python imports/browse_events_report.py --days 30."""

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import json
import sys

sys.path.insert(0, ".")

from sqlalchemy import select, text  # noqa: E402
from library.db.engine import get_session  # noqa: E402
from library.db.models import DocumentBrowseEvent  # noqa: E402


def normalize(value):
    if isinstance(value, str):
        return " ".join(value.casefold().split())
    if isinstance(value, dict):
        return {key: normalize(item) for key, item in sorted(value.items())}
    if isinstance(value, list):
        return sorted((normalize(item) for item in value), key=str)
    return value


def aggregate_events(rows):
    """Dedup transmissions and browse + applied criteria, excluding passive actions from rankings.

    Null/false/empty values stay explicit: clearing a filter is a deliberate
    choice, and topic_filter_active distinguishes all topics from an empty selection.
    """
    counters = {
        key: Counter()
        for key in (
            "opens",
            "restored",
            "phrases",
            "words",
            "filters",
            "cooccurrence",
            "sort_changes",
            "outcomes",
            "page_sizes",
            "depth",
            "sessions_by_panel",
            "modes",
        )
    }
    sessions = set()
    panel_sessions = defaultdict(set)
    depth = defaultdict(int)
    seen_events, seen_phrases, seen_filters, seen_sets, seen_corrections, seen_empty = (set() for _ in range(6))
    seen_sorts = set()
    for row in rows:
        if row.event_id in seen_events:
            continue
        seen_events.add(row.event_id)
        sessions.add(row.session_id)
        panel_sessions[row.source_view].add(row.session_id)
        panel = row.source_view
        mode = (panel, row.requested_mode, row.execution_mode)
        counters["modes"][mode] += 1
        filters = normalize(row.filters or {})
        phrase = normalize(row.query_text or "")
        key = (str(row.browse_id), json.dumps(filters, sort_keys=True), phrase)
        if row.action == "initial_load":
            counters["opens"][panel] += 1
            for field, origin in (row.criteria_origin or {}).items():
                if origin in {"url", "remembered"}:
                    counters["restored"][(panel, field, origin)] += 1
        if row.page_size:
            counters["page_sizes"][(panel, row.page_size)] += 1
            depth[(panel, str(row.browse_id))] = max(
                depth[(panel, str(row.browse_id))],
                row.offset // row.page_size + 1,
            )
        if row.outcome == "success" and row.offset == 0 and row.returned_count == 0 and key not in seen_empty:
            counters["outcomes"][(panel, "empty_first_page")] += 1
            seen_empty.add(key)
        if row.outcome != "success":
            counters["outcomes"][(panel, row.outcome)] += 1
        if row.action == "correction" and key not in seen_corrections:
            counters["outcomes"][(panel, "correction")] += 1
            seen_corrections.add(key)
        if row.action == "sort_change" or "sort" in (row.changed_fields or []):
            sort_key = (*key, row.sort)
            if sort_key not in seen_sorts:
                counters["sort_changes"][(panel, row.sort)] += 1
                seen_sorts.add(sort_key)
        if row.action in {"initial_load", "page_change", "page_size_change", "refresh"}:
            continue
        if phrase and key not in seen_phrases:
            counters["phrases"][(*mode, phrase)] += 1
            counters["words"].update((*mode, word) for word in phrase.split())
            seen_phrases.add(key)
        deliberate = sorted(
            field
            for field in row.changed_fields or []
            if field in filters and (row.criteria_origin or {}).get(field) == "manual"
        )
        for field in deliberate:
            filter_key = (*key, field)
            if filter_key not in seen_filters:
                counters["filters"][(panel, field, json.dumps(filters[field], ensure_ascii=False))] += 1
                seen_filters.add(filter_key)
        if deliberate and key not in seen_sets:
            active = tuple(
                sorted(field for field, value in filters.items() if value not in (None, False, [], "", "ALL"))
            )
            counters["cooccurrence"][(panel, active)] += 1
            seen_sets.add(key)
    for (panel, _), maximum in depth.items():
        counters["depth"][(panel, maximum)] += 1
    counters["sessions_by_panel"].update({panel: len(ids) for panel, ids in panel_sessions.items()})
    return {"events": len(seen_events), "sessions": len(sessions), **counters}


def print_report(session, days=30):
    session.execute(text("SET TRANSACTION READ ONLY"))
    rows = session.scalars(
        select(DocumentBrowseEvent)
        .where(
            DocumentBrowseEvent.created_at >= datetime.now(timezone.utc) - timedelta(days=days),
        )
        .order_by(DocumentBrowseEvent.created_at, DocumentBrowseEvent.id)
        .execution_options(yield_per=500)
    )
    report = aggregate_events(rows)
    print(f"Events: {report['events']}; sessions: {report['sessions']}; window: {days} days")
    print("Opens count initial executions only; opening Search without executing sends no event.")
    for name, counts in report.items():
        if isinstance(counts, Counter):
            print(f"\n{name}:")
            for key, count in counts.most_common(30):
                print(f"  {key}: {count}")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=30)
    args = parser.parse_args()
    if args.days < 1:
        parser.error("--days must be positive")
    session = get_session()
    try:
        print_report(session, args.days)
    finally:
        session.close()


if __name__ == "__main__":
    main()
