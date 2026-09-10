#!/usr/bin/env python3
"""List and resolve cleaner-rule candidates collected during chunk review.

Intended for Claude Code/Codex-assisted rule work. Examples::

    PYTHONPATH=. python scripts/review_removed_lines.py --list
    PYTHONPATH=. python scripts/review_removed_lines.py --mark 10,11 \
        --status rule_added --reference "data/site_rules.json:o2.pl" \
        --note "Added during cleanup-rule review"
"""

import argparse
import datetime

from sqlalchemy import select

from library.db.engine import get_session
from library.db.models import DocumentRemovedLine
from library.db.models import CleanupRule
from library.cleanup_rules import CleanupRuleValidationError, bust_cache, validate_rule
from library.publisher_domain import normalize_publisher_domain

TERMINAL_STATUSES = ("rule_added", "rejected", "already_covered")


def parse_ids(value: str) -> list[int]:
    ids = [int(item.strip()) for item in value.split(",") if item.strip()]
    if not ids:
        raise argparse.ArgumentTypeError("provide at least one row ID")
    return ids


def main() -> None:
    parser = argparse.ArgumentParser(description="Review document_removed_lines candidates")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--list", action="store_true", help="List pending candidates")
    action.add_argument("--mark", type=parse_ids, metavar="ID[,ID...]", help="Resolve row IDs")
    action.add_argument("--promote-rule", action="store_true", help="Utwórz regułę cleanup_rules z kandydata")
    parser.add_argument("--removed-line-id", type=int)
    parser.add_argument("--scope", choices=("global", "domain"))
    parser.add_argument("--domain")
    parser.add_argument("--match-type", choices=("literal_line", "contains"))
    parser.add_argument("--pattern")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--status", choices=TERMINAL_STATUSES)
    parser.add_argument("--reference", help="Lokalizacja reguły, np. cleanup_rules:42 lub data/site_rules.json:o2.pl")
    parser.add_argument("--note", help="Reason for the decision")
    args = parser.parse_args()

    if args.promote_rule:
        if not args.removed_line_id or args.removed_line_id <= 0:
            parser.error("--promote-rule wymaga dodatniego --removed-line-id")
        try:
            validate_rule(scope=args.scope, domain=args.domain, match_type=args.match_type, pattern=args.pattern)
        except CleanupRuleValidationError as exc:
            parser.error(str(exc))

    if args.mark and not args.status:
        parser.error("--status is required with --mark")
    if args.status == "rule_added" and not args.reference:
        parser.error("--reference is required for rule_added")

    session = get_session()
    try:
        if args.promote_rule:
            source = session.get(DocumentRemovedLine, args.removed_line_id)
            if source is None:
                parser.error(f"Nie znaleziono kandydata {args.removed_line_id}")
            if source.review_status != "pending":
                parser.error(f"Kandydat {source.id} ma już status {source.review_status}")
            rule = CleanupRule(
                scope=args.scope, domain=normalize_publisher_domain(args.domain),
                match_type=args.match_type, pattern=args.pattern, note=args.note,
                source_removed_line_id=source.id, created_by="review_removed_lines",
            )
            session.add(rule)
            session.flush()
            source.review_status = "rule_added"
            source.rule_reference = f"cleanup_rules:{rule.id}"
            source.reviewed_at = datetime.datetime.now()
            source.review_note = args.note
            session.commit()
            bust_cache()
            print(f"cleanup_rules:{rule.id}")
            return

        if args.list:
            rows = session.scalars(
                select(DocumentRemovedLine)
                .where(DocumentRemovedLine.review_status == "pending")
                .order_by(DocumentRemovedLine.created_at, DocumentRemovedLine.id)
                .limit(args.limit)
            ).all()
            for row in rows:
                print(f"{row.id}\tdoc={row.document_id}\t{row.source}\t{row.line_text}")
            print(f"Pending candidates shown: {len(rows)}")
            return

        rows = session.scalars(
            select(DocumentRemovedLine).where(DocumentRemovedLine.id.in_(args.mark))
        ).all()
        found_ids = {row.id for row in rows}
        missing_ids = sorted(set(args.mark) - found_ids)
        if missing_ids:
            parser.error(f"row IDs not found: {missing_ids}")

        now = datetime.datetime.now()
        for row in rows:
            if row.review_status != "pending":
                parser.error(f"row {row.id} is already {row.review_status}")
            row.review_status = args.status
            row.reviewed_at = now
            row.review_note = args.note
            row.rule_reference = args.reference
        session.commit()
        print(f"Marked {len(rows)} row(s) as {args.status}")
    except (SystemExit, Exception):
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
