"""Load a region dictionary (data/region_corrections/<kraj-slug>.json) into transcript_corrections.

Idempotent: a rule that already exists (same pattern ignoring case, same country, same channel) is skipped,
an existing rule is never changed. Dry-run by default.

    cd backend
    PYTHONPATH=. python -X utf8 imports/seed_region_corrections.py data/region_corrections/kraj-jemen.json
    PYTHONPATH=. python -X utf8 imports/seed_region_corrections.py data/region_corrections/kraj-jemen.json --apply

Against the NAS database see "Running scripts against the NAS production DB" in imports/CLAUDE.md.
"""

import argparse
import json
import sys
from pathlib import Path

from sqlalchemy import func, select

from library.db.engine import get_session
from library.db.models import TranscriptCorrection
from library.transcript_corrections import (
    TranscriptCorrectionValidationError, bust_cache, normalize_author, validate_rule,
)

CREATED_BY = "seed_region_corrections"


def load_dictionary(path: Path) -> tuple[str, list[dict]]:
    """Read and validate a dictionary file; raises ValueError listing every invalid rule."""
    data = json.loads(path.read_text(encoding="utf-8"))
    slug = str(data.get("country_slug", "")).strip().casefold()
    rules, problems = [], []
    seen = set()
    for index, raw in enumerate(data.get("rules", []), start=1):
        author = raw.get("author")
        try:
            validate_rule(pattern=raw.get("pattern"), replacement=raw.get("replacement"), scope="region",
                          author=author, country_slug=slug)
        except TranscriptCorrectionValidationError as exc:
            problems.append(f"#{index} {raw.get('pattern')!r}: {exc}")
            continue
        key = (raw["pattern"].strip().casefold(), normalize_author(author) or "")
        if key in seen:
            problems.append(f"#{index} {raw['pattern']!r}: duplicate in the file")
            continue
        seen.add(key)
        rules.append({"pattern": raw["pattern"].strip(), "replacement": raw["replacement"],
                      "author": normalize_author(author), "note": raw.get("note")})
    if problems:
        raise ValueError("Invalid dictionary:\n" + "\n".join(problems))
    return slug, rules


def seed(session, slug: str, rules: list[dict], *, apply: bool) -> dict:
    existing = {
        (pattern.casefold(), author or "")
        for pattern, author in session.execute(
            select(func.lower(TranscriptCorrection.pattern), TranscriptCorrection.author)
            .where(TranscriptCorrection.scope == "region", TranscriptCorrection.country_slug == slug)
        )
    }
    added, skipped = [], []
    for rule in rules:
        if (rule["pattern"].casefold(), rule["author"] or "") in existing:
            skipped.append(rule["pattern"])
            continue
        added.append(rule["pattern"])
        if apply:
            session.add(TranscriptCorrection(
                pattern=rule["pattern"], replacement=rule["replacement"], scope="region", country_slug=slug,
                author=rule["author"], note=rule["note"], created_by=CREATED_BY, active=True, hit_count=0,
            ))
    if apply:
        session.commit()
        bust_cache()
    return {"country_slug": slug, "added": added, "skipped_existing": skipped, "applied": apply}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("file", type=Path)
    parser.add_argument("--apply", action="store_true", help="write the rules (default: dry-run)")
    args = parser.parse_args(argv)
    try:
        slug, rules = load_dictionary(args.file)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2
    session = get_session()
    try:
        result = seed(session, slug, rules, apply=args.apply)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
    mode = "APPLIED" if args.apply else "DRY-RUN"
    print(f"{mode} {slug}: {len(result['added'])} to add, {len(result['skipped_existing'])} already present")
    for pattern in result["added"]:
        print(f"  + {pattern}")
    for pattern in result["skipped_existing"]:
        print(f"  = {pattern}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
