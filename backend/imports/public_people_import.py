#!/usr/bin/env python3
"""Import the vault notes about public people into the person registry.

Reads every ``.md`` under ``people i firmy/public`` (and the extra notes named in the overrides file),
and for each person: finds or creates the registry person (``persons``, ``kind='public'`` - NOT the
private contact book), fills the still-empty description / long description / role, merges the links
(YouTube channel, home page, LinkedIn, newsletter...), stores the note path, and links the person to
the knowledge sources they stand behind - courses named by ``[[wikilinks]]`` in the note plus the
sources the overrides name (a channel the person hosts).

The note names are free-form ("Claudowski - Tomasz Cholewa", "Górczyk Przemek"), so a name that looks
wrong is fixed with an overrides JSON file (a list of entries):

    [{"note": "IT/Kadysz Paweł - szkolenie 'sztuka notowania'.md", "name": "Paweł Kadysz",
      "aliases": ["Kadysz Paweł"], "role": "autor szkoleń",
      "sources": [{"name": "Na Wschód od Bliskiego Wschodu", "kind": "channel", "role": "host"}]},
     {"note": "IT/talkpython.md", "skip": true},
     {"name": "Wojciech Szewko", "note": "02-wiedza/Geopolityka .../Szewko.md", "role": "prowadzący kanał",
      "sources": [{"name": "Na Wschód od Bliskiego Wschodu", "role": "host"}]}]

``note`` is the path relative to the public folder, relative to the vault, or just the file name; an
entry without a matching file still creates the person (and links its sources). Notes whose name is
not a person are listed and skipped until an override names them.

Usage:
    cd backend
    python -X utf8 imports/public_people_import.py --overrides ../tmp/people.json          # dry-run (default)
    python -X utf8 imports/public_people_import.py --overrides ../tmp/people.json --apply
"""

import argparse
import json
import logging
import os
from pathlib import Path

from library.config_loader import load_config

cfg = load_config()  # noqa: F841 — side effect: populates os.environ for library modules

from library import knowledge_sources  # noqa: E402
from library.db.engine import get_session  # noqa: E402
from library.db.models import Person  # noqa: E402
from library.person_registry import add_person_alias, normalize_person_links  # noqa: E402
from library.public_person_notes import derive_identity, parse_person_note, role_from_folder  # noqa: E402

DEFAULT_VAULT = os.environ.get("OBSIDIAN_VAULT_PATH", r"C:\Users\ziutus\Obsydian\personal")
DEFAULT_FOLDER = "02-wiedza/people i firmy/public"


def load_overrides(path: str | None) -> list[dict]:
    if not path:
        return []
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit("The overrides file must hold a JSON list of entries")
    return data


def matches(entry_note: str, relative_to_folder: str, relative_to_vault: str) -> bool:
    note = entry_note.replace("\\", "/").strip("/")
    return note in (relative_to_folder, relative_to_vault, Path(relative_to_vault).name)


def plan(vault: Path, folder: Path, overrides: list[dict]) -> list[dict]:
    """One work item per person: the note it comes from (if any), its parsed content and the final identity."""
    items: list[dict] = []
    used: set[int] = set()
    for path in sorted(folder.rglob("*.md")):
        rel_folder = path.relative_to(folder).as_posix()
        rel_vault = path.relative_to(vault).as_posix()
        override_index = next((i for i, entry in enumerate(overrides)
                               if entry.get("note") and matches(entry["note"], rel_folder, rel_vault)), None)
        override = overrides[override_index] if override_index is not None else {}
        if override_index is not None:
            used.add(override_index)
        if override.get("skip"):
            items.append({"skipped": True, "note": rel_vault, "reason": "skipped by override"})
            continue
        identity = derive_identity(path.stem)
        parent = Path(rel_folder).parent.as_posix()
        name = override.get("name") or identity["name"]
        if not name:
            items.append({"skipped": True, "note": rel_vault, "reason": "not a person name - add an override"})
            continue
        items.append({
            "note": rel_vault, "name": name, "path": path, "override": override,
            "aliases": [*identity["aliases"], *override.get("aliases", [])],
            "role": override.get("role") or role_from_folder("" if parent == "." else parent),
            "hint": identity["hint"],
        })
    for index, entry in enumerate(overrides):
        if index in used or entry.get("skip") or not entry.get("name"):
            continue
        note_path = None
        if entry.get("note"):
            candidate = (vault / entry["note"]).resolve()
            if candidate.is_file() and vault.resolve() in candidate.parents:
                note_path = candidate
        items.append({
            "note": note_path.relative_to(vault.resolve()).as_posix() if note_path else None, "name": entry["name"],
            "path": note_path, "override": entry, "aliases": entry.get("aliases", []), "role": entry.get("role"), "hint": None,
        })
    return items


def apply_item(session, item: dict) -> list[str]:
    """Create or update one person; returns what changed."""
    override = item["override"]
    parsed = parse_person_note(item["path"].read_text(encoding="utf-8")) if item["path"] else {
        "description": None, "long_description": None, "links": [], "courses": [],
    }
    changes: list[str] = []
    person = knowledge_sources.find_person(session, item["name"])
    if person is None:
        person = Person(canonical_name=item["name"], links=[])
        session.add(person)
        session.flush()
        changes.append("created")
    if person.kind != "public":
        person.kind = "public"
        changes.append("kind")
    for field, value in (
        ("role", item["role"]), ("description", override.get("description") or parsed["description"] or item["hint"]),
        ("long_description", parsed["long_description"]),
    ):
        if value and not getattr(person, field):
            setattr(person, field, value)
            changes.append(field)
    if item["note"] and not person.obsidian_note_path:
        person.obsidian_note_path = item["note"]
        changes.append("obsidian_note_path")
    known = {link["url"] for link in person.links or []}
    new_links = [link for link in [*parsed["links"], *override.get("links", [])] if link["url"] not in known]
    if new_links:
        person.links = normalize_person_links([*(person.links or []), *new_links])
        changes.append(f"links +{len(new_links)}")
    for alias in item["aliases"]:
        if alias.strip() and add_person_alias(session, person, alias.strip()):
            changes.append(f"alias {alias}")
    wanted = [(course["title"], None, course["role"], True) for course in parsed["courses"]]
    wanted += [(src["name"], src.get("kind"), src.get("role", "host"), False) for src in override.get("sources", [])]
    for source_name, kind, role, from_wikilink in wanted:
        source, created = knowledge_sources.get_or_create_source(session, source_name, kind=kind)
        if from_wikilink and not source.obsidian_note_path:
            source.obsidian_note_path = knowledge_sources.note_path_for_title(session, source_name)
        _, linked = knowledge_sources.link_person(session, source, person, role)
        if created or linked:
            changes.append(f"source {source.name} ({role})")
    return changes


def main():
    parser = argparse.ArgumentParser(description="Import vault notes about public people into the person registry.")
    parser.add_argument("--vault", default=DEFAULT_VAULT, help="Vault root directory")
    parser.add_argument("--folder", default=DEFAULT_FOLDER, help="Folder with the notes, relative to the vault")
    parser.add_argument("--overrides", help="JSON file with names / roles / sources that fix or extend the notes")
    parser.add_argument("--apply", action="store_true", help="Write to the database (default: dry-run)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    vault = Path(args.vault)
    folder = vault / args.folder
    if not folder.is_dir():
        raise SystemExit(f"Folder not found: {folder}")
    items = plan(vault, folder, load_overrides(args.overrides))
    session = get_session()
    try:
        done = 0
        for item in items:
            if item.get("skipped"):
                logging.info("SKIP  %-60s %s", item["note"], item["reason"])
                continue
            changes = apply_item(session, item)
            done += 1
            logging.info("%-28s %s", item["name"], ", ".join(changes) or "nothing new")
        if args.apply:
            session.commit()
            logging.info("Done. Processed %d people.", done)
        else:
            session.rollback()
            logging.info("Dry-run: %d people would be processed. Re-run with --apply to save.", done)
    finally:
        session.close()


if __name__ == "__main__":
    main()
