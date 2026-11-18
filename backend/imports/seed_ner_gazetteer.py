"""Load NER gazetteer additions (data/ner_gazetteer/<name>.json) into ner_gazetteer_entries.

Idempotent: an entry with the same kind and name (case-insensitive) is skipped, an existing one is never changed.
Every entry goes through the same validation as ``POST /ner_gazetteer``. Dry-run by default.

    cd backend
    PYTHONPATH=. python -X utf8 imports/seed_ner_gazetteer.py data/ner_gazetteer/kraj-jemen.json
    PYTHONPATH=. python -X utf8 imports/seed_ner_gazetteer.py data/ner_gazetteer/kraj-jemen.json --apply

Takes effect within the 60 s cache of the running backend, no deploy needed. Against the NAS database see
"Running scripts against the NAS production DB" in imports/CLAUDE.md.
"""

import argparse
import json
import sys
from pathlib import Path

from sqlalchemy import func, select

from library.db.engine import get_session
from library.db.models import NerGazetteerEntry
from library.ner_gazetteer_store import GazetteerValidationError, invalidate_cache, validate_entry

CREATED_BY = "seed_ner_gazetteer"


def load_entries(path: Path) -> tuple[list[dict], int | None]:
    """Read and validate a file; raises ValueError listing every invalid entry."""
    data = json.loads(path.read_text(encoding="utf-8"))
    entries, problems, seen = [], [], set()
    for index, raw in enumerate(data.get("entries", []), start=1):
        try:
            values = validate_entry(kind=raw.get("kind"), name_pl=raw.get("name_pl"),
                                    patterns=raw.get("patterns"), geocode_alias=raw.get("geocode_alias"))
        except GazetteerValidationError as exc:
            problems.append(f"#{index} {raw.get('name_pl')!r}: {exc}")
            continue
        key = (values["kind"], values["name_pl"].casefold())
        if key in seen:
            problems.append(f"#{index} {raw.get('name_pl')!r}: duplicate in the file")
            continue
        seen.add(key)
        values["note"] = raw.get("note")
        entries.append(values)
    if problems:
        raise ValueError("Invalid gazetteer file:\n" + "\n".join(problems))
    return entries, data.get("source_document_id")


def seed(session, entries: list[dict], source_document_id: int | None, *, apply: bool) -> dict:
    existing = {
        (kind, name.casefold())
        for kind, name in session.execute(select(NerGazetteerEntry.kind, func.lower(NerGazetteerEntry.name_pl)))
    }
    added, skipped = [], []
    for values in entries:
        label = f"{values['kind']}:{values['name_pl']}"
        if (values["kind"], values["name_pl"].casefold()) in existing:
            skipped.append(label)
            continue
        added.append(label)
        if apply:
            session.add(NerGazetteerEntry(
                kind=values["kind"], name_pl=values["name_pl"], patterns=values["patterns"],
                geocode_alias=values["geocode_alias"], note=values["note"], created_by=CREATED_BY,
                source_document_id=source_document_id,
            ))
    if apply:
        session.commit()
        invalidate_cache()
    return {"added": added, "skipped_existing": skipped, "applied": apply}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("file", type=Path)
    parser.add_argument("--apply", action="store_true", help="write the entries (default: dry-run)")
    args = parser.parse_args(argv)
    try:
        entries, source_document_id = load_entries(args.file)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2
    session = get_session()
    try:
        result = seed(session, entries, source_document_id, apply=args.apply)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
    print(f"{'APPLIED' if args.apply else 'DRY-RUN'}: {len(result['added'])} to add, "
          f"{len(result['skipped_existing'])} already present")
    for label in result["added"]:
        print(f"  + {label}")
    for label in result["skipped_existing"]:
        print(f"  = {label}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
