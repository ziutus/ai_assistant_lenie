#!/usr/bin/env python3
"""Return control questions filtered by thematic tags.

Usage:
    python imports/control_questions.py --tags wojsko,gospodarka,sojusze
    python imports/control_questions.py --tags geopolityka --file path/to/questions.md
    python imports/control_questions.py --list-tags
"""

import argparse
import os
import re
import sys

DEFAULT_QUESTIONS_FILE = (
    r"C:\Users\ziutus\Obsydian\personal\02-wiedza"
    r"\Geopolityka i polityka\_pytania_kontrolne"
    r"\_Pytania do każdego kraju czy obszaru.md"
)

# Mapping: tag → substrings to match in ## / # section headers (case-insensitive)
TAG_TO_HEADERS: dict[str, list[str]] = {
    "wojsko": [
        "jaką ma armię",
        "w razie ataku może oddać",
        "agresywne czy pasywne",
        "prowadzi konflikty",
    ],
    "gospodarka": [
        "stan finansów",
        "model ekonomiczny",
        "gospodarka internetowa",
    ],
    "geopolityka": [
        "poziom ważności",
        "rolę pełni w systemie",
        "strefy buforowe",
        "dystrybucja prestiżu",
        "powiązane jest państwo",
        "aspiracje",
        "cele strategiczne",
        "jakie nianie dominują",
    ],
    "ideologia": [
        "jaka panuje ideologia",
        "aspiracje",
        "cele strategiczne",
    ],
    "religia": [
        "rola religii",
    ],
    "demografia": [
        "demografia",
    ],
    "etniczne": [
        "podziały etniczne",
    ],
    "soft-power-religijny": [
        "podmiotem lub obiektem religijnego",
    ],
    "ustroj": [
        "faktyczny ustrój polityczny",
        "bliski rewolucji",
        "politykę da się ukryć",
        "status państwa",
        "rząd centralny kontroluje",
        "bloku politycznego",
        "bloku mentalnych",
        "regionalnym hegemonem",
    ],
    "sluzby-specjalne": [
        "służby specjalne kontrolują",
    ],
    "technologia": [
        "czyjej technologii używa",
    ],
    "internet": [
        "internet i gospodarka internetowa",
    ],
    "finanse-publiczne": [
        "stan finansów",
    ],
    "sojusze": [
        "bloku politycznego",
        "bloku mentalnych",
        "rolę pełni w systemie",
        "jakie ma sojusze",
    ],
}

ALL_TAGS = sorted(TAG_TO_HEADERS.keys())


def parse_sections(text: str) -> list[tuple[str, str]]:
    """Split markdown into (header, body) pairs for ## and # sections."""
    sections = []
    current_header = ""
    current_lines: list[str] = []

    for line in text.splitlines():
        if re.match(r"^#{1,2} ", line):
            if current_header or current_lines:
                sections.append((current_header, "\n".join(current_lines).strip()))
            current_header = line
            current_lines = []
        else:
            current_lines.append(line)

    if current_header or current_lines:
        sections.append((current_header, "\n".join(current_lines).strip()))

    return sections


def sections_for_tags(sections: list[tuple[str, str]], tags: list[str]) -> list[tuple[str, str]]:
    """Return deduplicated sections matching any of the requested tags."""
    needles: list[str] = []
    for tag in tags:
        needles.extend(TAG_TO_HEADERS.get(tag, []))

    seen: set[str] = set()
    result: list[tuple[str, str]] = []
    for header, body in sections:
        header_lower = header.lower()
        if any(n in header_lower for n in needles):
            if header not in seen:
                seen.add(header)
                result.append((header, body))

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Return control questions filtered by tags")
    parser.add_argument("--tags", help="Comma-separated tags, e.g. wojsko,gospodarka")
    parser.add_argument("--file", default=DEFAULT_QUESTIONS_FILE,
                        help="Path to the markdown questions file")
    parser.add_argument("--list-tags", action="store_true",
                        help="List all available tags and exit")
    args = parser.parse_args()

    if args.list_tags:
        print("Available tags:")
        for tag in ALL_TAGS:
            print(f"  {tag}")
        return

    if not args.tags:
        parser.error("--tags is required (or use --list-tags)")

    if not os.path.isfile(args.file):
        print(f"ERROR: questions file not found: {args.file}", file=sys.stderr)
        sys.exit(1)

    with open(args.file, encoding="utf-8") as f:
        text = f.read()

    tags = [t.strip() for t in args.tags.split(",") if t.strip()]
    unknown = [t for t in tags if t not in TAG_TO_HEADERS]
    if unknown:
        print(f"WARNING: unknown tags (ignored): {', '.join(unknown)}", file=sys.stderr)

    sections = parse_sections(text)
    matched = sections_for_tags(sections, tags)

    if not matched:
        print(f"# Brak pytań dla tagów: {', '.join(tags)}", file=sys.stderr)
        sys.exit(0)

    sys.stdout.reconfigure(encoding="utf-8")
    print(f"# Pytania kontrolne dla: {', '.join(tags)}\n")
    for header, body in matched:
        print(header)
        if body:
            print(body)
        print()


if __name__ == "__main__":
    main()
