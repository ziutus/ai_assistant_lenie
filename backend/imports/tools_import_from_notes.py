#!/usr/bin/env python3
"""Fill the tool catalog from the Obsidian "application description" notes.

For every catalog tool the script reads its vault note, parses the template
(``library/tool_note_parser.py``: Purpose, Type of application, Licence, links, Pricing, Works on,
Key Points, Important Commands, Additional Notes) and fills the fields that are still empty. A tool
without ``obsidian_note_path`` is matched to a vault note by name (file name = tool name, or
"<name> - ..."); an ambiguous match is reported and skipped. Template placeholders ("point1", an
empty code block) are never imported.

Reads the vault from a local directory (``--vault``) and writes to the database the Lenie
configuration points at (see "Running scripts against the NAS production DB" in imports/CLAUDE.md).
The same logic runs on the NAS through ``POST /tools/<id>/import_note``.

Usage:
    cd backend
    python -X utf8 imports/tools_import_from_notes.py                 # dry-run (default)
    python -X utf8 imports/tools_import_from_notes.py --apply
    python -X utf8 imports/tools_import_from_notes.py --id 52 --apply
    python -X utf8 imports/tools_import_from_notes.py --apply --overwrite   # replace existing values too
"""

import argparse
import logging
import os
import re
import unicodedata
from pathlib import Path

from library.config_loader import load_config

cfg = load_config()  # noqa: F841 — side effect: populates os.environ for library modules

from library.db.engine import get_session  # noqa: E402
from library.db.models import Tool  # noqa: E402
from library.tool_note_parser import apply_note_to_tool, parse_tool_note  # noqa: E402

DEFAULT_VAULT = os.environ.get("OBSIDIAN_VAULT_PATH", r"C:\Users\ziutus\Obsydian\personal")
TEMPLATE_MARKERS = ("Key Points", "Important Commands")


def normalize(name: str) -> str:
    folded = unicodedata.normalize("NFKD", name.lower())
    folded = "".join(char for char in folded if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", "", folded)


def template_notes(vault: Path) -> dict[str, list[Path]]:
    """Vault notes written with the application template, indexed by normalized file name."""
    index: dict[str, list[Path]] = {}
    for path in vault.rglob("*.md"):
        if "templates" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if all(marker in text for marker in TEMPLATE_MARKERS):
            index.setdefault(normalize(path.stem), []).append(path)
    return index


def find_note(tool_name: str, index: dict[str, list[Path]]) -> tuple[Path | None, str]:
    key = normalize(tool_name)
    hits = list(index.get(key, []))
    if not hits:  # "Trivy - Security scan of docker images" for the tool "Trivy"
        hits = [path for stem, paths in index.items() if stem.startswith(key) and len(key) >= 3 for path in paths
                if re.match(rf"^{re.escape(tool_name)}\s*[-–:(]", path.stem, re.IGNORECASE)]
    if len(hits) == 1:
        return hits[0], ""
    if hits:
        return None, "ambiguous: " + ", ".join(str(path.name) for path in hits)
    return None, "no note"


def main():
    parser = argparse.ArgumentParser(description="Fill empty catalog fields from the tools' Obsidian notes.")
    parser.add_argument("--vault", default=DEFAULT_VAULT, help="Vault root directory")
    parser.add_argument("--apply", action="store_true", help="Write to the database (default: dry-run)")
    parser.add_argument("--overwrite", action="store_true", help="Also replace fields that already have a value")
    parser.add_argument("--id", type=int, help="Process a single tool")
    parser.add_argument("--no-name-match", action="store_true", help="Only tools that already have obsidian_note_path")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    vault = Path(args.vault)
    if not vault.is_dir():
        raise SystemExit(f"Vault directory not found: {vault}")
    index = {} if args.no_name_match else template_notes(vault)

    session = get_session()
    try:
        query = session.query(Tool).order_by(Tool.name)
        if args.id:
            query = query.filter(Tool.id == args.id)
        tools = query.all()
        updated = 0
        for tool in tools:
            note, reason = None, ""
            if tool.obsidian_note_path:
                note = vault / tool.obsidian_note_path
                if not note.is_file():
                    logging.info("%-28s note missing: %s", tool.name, tool.obsidian_note_path)
                    continue
            elif not args.no_name_match:
                note, reason = find_note(tool.name, index)
            if note is None:
                logging.info("%-28s skipped (%s)", tool.name, reason or "no obsidian_note_path")
                continue
            parsed = parse_tool_note(note.read_text(encoding="utf-8"))
            changed = apply_note_to_tool(tool, parsed, overwrite=args.overwrite)
            if not tool.obsidian_note_path:
                tool.obsidian_note_path = note.relative_to(vault).as_posix()
                changed.append("obsidian_note_path")
            if changed:
                updated += 1
            logging.info("%-28s %s -> %s", tool.name, note.relative_to(vault).as_posix(), ", ".join(changed) or "nothing new")
        if args.apply:
            session.commit()
            logging.info("Done. Updated %d of %d tools.", updated, len(tools))
        else:
            session.rollback()
            logging.info("Dry-run: %d of %d tools would change. Re-run with --apply to save.", updated, len(tools))
    finally:
        session.close()


if __name__ == "__main__":
    main()
