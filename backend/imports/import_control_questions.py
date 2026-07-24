#!/usr/bin/env python3
"""Import control questions from the Obsidian vault into the control_questions DB table.

The backend (NAS) has no runtime access to the Obsidian vault (local to the
user's machine) — this is the one-way sync: edit questions in Obsidian, then
re-run this script to refresh the DB copy that
library/control_question_selection.py reads at runtime. Replace semantics per
source file (safe to re-run after editing).

Examples:
    python imports/import_control_questions.py                # dry-run preview
    python imports/import_control_questions.py --apply
    python imports/import_control_questions.py --dir "C:\\...\\_pytania_kontrolne" --apply
"""

import argparse
import os
import re
import sys

from imports.control_questions import TAG_TO_HEADERS, parse_sections

DEFAULT_QUESTIONS_DIR = (
    r"C:\Users\ziutus\Obsydian\personal\02-wiedza"
    r"\Geopolityka i polityka\_pytania_kontrolne"
)

# Navigation/README file for the vault directory, not a question bank itself.
SKIPPED_FILENAMES = {"_index.md"}


def _tags_for_header(header: str) -> str | None:
    header_lower = header.lower()
    matched = sorted(
        tag for tag, needles in TAG_TO_HEADERS.items() if any(needle in header_lower for needle in needles)
    )
    return ",".join(matched) or None


def _clean_header(header: str) -> str:
    return header.lstrip("#").strip()


def _paragraph_fallback_rows(text: str, filename: str) -> list[dict]:
    """Some files (e.g. the conflict/negotiation one) have no ##/# headings at all —
    just questions separated by blank lines. Treat each paragraph's first line as
    the question, the rest as body, so this content isn't silently dropped."""
    rows: list[dict] = []
    position = 0
    for paragraph in re.split(r"\n\s*\n", text.strip()):
        lines = [line.strip() for line in paragraph.strip().splitlines() if line.strip()]
        if not lines:
            continue
        rows.append({
            "source_file": filename,
            "section_header": lines[0],
            "body": "\n".join(lines[1:]) or None,
            "tags": _tags_for_header(lines[0]),
            "position": position,
        })
        position += 1
    return rows


def load_questions_from_dir(dir_path: str) -> list[dict]:
    """Parse every .md file in dir_path into question rows (source_file, section_header, body, tags, position).

    Two source formats coexist in the vault: most files use one ##/# heading per
    question (body = context/examples); a file with no headings at all falls back
    to paragraph splitting (see _paragraph_fallback_rows). A file whose headings
    group several bulleted questions under one category title (e.g. the propaganda
    checklist) is still imported one row per heading — coarser than the country
    file, but not silently dropped.
    """
    rows: list[dict] = []
    for filename in sorted(os.listdir(dir_path)):
        if not filename.endswith(".md") or filename in SKIPPED_FILENAMES:
            continue
        with open(os.path.join(dir_path, filename), encoding="utf-8") as f:
            text = f.read()
        sections = parse_sections(text)
        headed = [(header, body) for header, body in sections if header.strip()]
        if not headed:
            rows.extend(_paragraph_fallback_rows(text, filename))
            continue
        for position, (header, body) in enumerate(headed):
            rows.append({
                "source_file": filename,
                "section_header": _clean_header(header),
                "body": body or None,
                "tags": _tags_for_header(header),
                "position": position,
            })
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Import control questions into the DB lookup table")
    parser.add_argument("--dir", default=DEFAULT_QUESTIONS_DIR, help="Directory with control-question .md files")
    parser.add_argument("--apply", action="store_true", help="Write to the database (default: dry-run preview)")
    args = parser.parse_args()

    if not os.path.isdir(args.dir):
        print(f"ERROR: questions directory not found: {args.dir}", file=sys.stderr)
        return 1

    rows = load_questions_from_dir(args.dir)
    if not rows:
        print(f"WARNING: no questions found in {args.dir}", file=sys.stderr)
        return 0

    by_file: dict[str, int] = {}
    for row in rows:
        by_file[row["source_file"]] = by_file.get(row["source_file"], 0) + 1
    for source_file, count in by_file.items():
        untagged = sum(1 for r in rows if r["source_file"] == source_file and not r["tags"])
        print(f"{source_file}: {count} questions ({untagged} without a matching tag)")
    print(f"Total: {len(rows)} questions across {len(by_file)} file(s)")

    if not args.apply:
        print("\nDry-run only — pass --apply to write to the database.")
        return 0

    from library.config_loader import load_config
    load_config()  # populates configuration for DB clients
    from library.db.engine import get_session
    from library.db.models import ControlQuestion

    session = get_session()
    try:
        for source_file in by_file:
            session.query(ControlQuestion).filter_by(source_file=source_file).delete()
        session.add_all([ControlQuestion(**row) for row in rows])
        session.commit()
        print(f"Imported {len(rows)} questions.")
        return 0
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
