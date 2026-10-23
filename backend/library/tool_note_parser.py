"""Read the Obsidian "application description" note template into catalog fields.

The template (``templates/appliaction description.md`` in the vault) is a block of bold ``Label:`` lines
(Purpose, Type of application, Licence, homepage, Works on, ...) followed by ``### Key Points``,
``### Important Commands`` and ``### Additional Notes`` sections. Many notes keep the template's
placeholders (``point1``, ``poin2``, an empty code block); those count as empty, never as content.

``parse_tool_note()`` is pure; ``apply_note_to_tool()`` fills a ``Tool`` and by default touches only
fields that are still empty, so a value edited in Lenie is never overwritten by an older note.
"""

import re

from library import github_repo_stats

# Label (lower-cased, bold markers stripped) -> catalog field.
_LABELS = {
    "purpose": "purpose",
    "podstawowe zadanie": "purpose",
    "type of application": "app_type",
    "licence": "license",
    "license": "license",
    "homepage": "homepage_url",
    "home page": "homepage_url",
    "wikipedia page": "wikipedia_url",
    "wikipedia": "wikipedia_url",
    "github page": "github_url",
    "github": "github_url",
    "pricing type": "pricing_type",
    "pricing page": "pricing_url",
    "pricing": "pricing_url",
    "works on": "works_on",
    "platform": "works_on",
    "platforms": "works_on",
}

# Parsed keys that are not columns of the tool itself (the "Source of note" entries become linked knowledge sources).
NON_COLUMN_FIELDS = ("sources",)
_WIKILINK = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")
_DATE_LINE = re.compile(r"^(creation|modification) date\b", re.IGNORECASE)
_PLACEHOLDER_POINT = re.compile(r"^poin?t?\d+$", re.IGNORECASE)  # "point1" / the template's typo "poin2"
# How a link field is called on the card; a link that cannot go into its own field is kept under this label.
LINK_FIELD_LABELS = {
    "homepage_url": "Strona", "wikipedia_url": "Wikipedia", "github_url": "GitHub", "pricing_url": "Cennik",
}
MAX_LINKS = 20
_URL = re.compile(r"https?://[^\s)>\]]+")
_HEADING = re.compile(r"^(#{1,6})\s*(.*?)\s*:?\s*$")
_SECTION_TITLES = {
    "key points": "key_points",
    "important commands": "important_commands",
    "additional notes": "additional_notes",
}
# Headings that end the note body (everything after is bookkeeping, not content).
_TAIL_TITLES = {"connected notes", "external links", "metadata"}
_SOURCE_TITLE = "source of note"

MAX_KEY_POINTS = 50
MAX_KEY_POINT_LENGTH = 500
SHORT_FIELD_LIMITS = {"license": 100, "app_type": 100}


def _clean(value: str) -> str:
    return value.replace("*", "").strip()


def _first_url(value: str) -> str | None:
    match = _URL.search(value)
    return match.group(0).rstrip(".,;") if match else None


def _all_urls(value: str) -> list[str]:
    return [match.rstrip(".,;") for match in _URL.findall(value)]


def pricing_type_from_text(text: str) -> str | None:
    """Map the free text of ``Pricing type`` ("free / paid pro version") onto the catalog's closed list."""
    low = text.lower()
    if not low.strip():
        return None
    if "freemium" in low:
        return "freemium"
    if "open core" in low or "open-core" in low:
        return "open_core"
    if "subscription" in low or "subskrypc" in low:
        return "subscription"
    if "usage" in low or "pay as you go" in low:
        return "usage_based"
    has_free = "free" in low or "darmow" in low or "open source" in low or "opensource" in low
    has_paid = any(word in low for word in ("paid", "pro ", "commercial", "płatn", "platn", "enterprise"))
    if has_free and has_paid:
        return "freemium"
    if has_paid or "commercial" in low:
        return "paid"
    if has_free:
        return "free"
    return None


def _split_header_and_sections(text: str) -> tuple[list[str], dict[str, list[str]]]:
    """Return (label lines before the first section, the named sections' lines)."""
    header: list[str] = []
    sections: dict[str, list[str]] = {}
    current: str | None = None
    in_fence = False
    stopped = False
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":  # front matter
        end = next((i for i, line in enumerate(lines[1:], start=1) if line.strip() == "---"), None)
        if end is not None:
            lines = lines[end + 1:]
    for line in lines:
        if line.strip().startswith("```"):
            in_fence = not in_fence
        heading = None if in_fence else _HEADING.match(line)
        if heading:
            title = heading.group(2).strip().lower()
            if title == _SOURCE_TITLE:
                current = "source_of_note"
                sections.setdefault(current, [])
                continue
            if title in _TAIL_TITLES:
                stopped = True
                current = None
                continue
            if title in _SECTION_TITLES and not stopped:
                current = _SECTION_TITLES[title]
                sections.setdefault(current, [])
                continue
            if current == "additional_notes" and not stopped:
                sections["additional_notes"].append(line)  # sub-headings belong to the notes
                continue
            if current is None and not stopped:
                continue  # the note title ("## jq")
            if current in ("key_points", "important_commands") and not stopped:
                # An unknown heading inside commands (e.g. "#### example") is part of the commands.
                if current == "important_commands":
                    sections[current].append(line)
                continue
            continue
        if stopped and current != "source_of_note":
            continue
        if current is None:
            header.append(line)
        else:
            sections[current].append(line)
    return header, sections


def _labels(header: list[str]) -> tuple[dict[str, str], list[str]]:
    """The recognised ``Label: value`` lines by catalog field, plus the other ``Label: value`` lines verbatim.

    The extras ("Creating account by: github") carry facts the template has no field for; they are kept
    in the notes instead of being lost.
    """
    found: dict[str, str] = {}
    extras: list[str] = []
    for line in header:
        stripped = line.strip()
        if ":" not in stripped or stripped.startswith(("#", "<%", "---")) or _DATE_LINE.match(stripped):
            continue
        label, _, value = stripped.partition(":")
        key = _clean(label).lower()
        field = _LABELS.get(key)
        if field is None:
            if _clean(value) and len(key) <= 40 and not value.strip().startswith("//"):
                extras.append(_clean(stripped))
            continue
        if field in found:
            continue
        found[field] = value.strip().lstrip("*").strip()
    return found, extras


def _key_points(lines: list[str]) -> list[str]:
    points = []
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith(("-", "*", "•")):
            continue
        point = stripped.lstrip("-*• ").strip()
        if not point or _PLACEHOLDER_POINT.match(point):
            continue
        points.append(point[:MAX_KEY_POINT_LENGTH])
    return points[:MAX_KEY_POINTS]


def _commands(lines: list[str]) -> str | None:
    text = "\n".join(lines).strip()
    if not text:
        return None
    text = re.sub(r"^\s*Example of commands:?\s*$", "", text, flags=re.IGNORECASE | re.MULTILINE)
    text = re.sub(r"```[a-z]*\s*```", "", text)  # empty fenced block
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text or None


def _notes(lines: list[str]) -> str | None:
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    return text or None


def _merge_links(existing: list[dict], extra: list[dict], skip_urls: list | tuple = ()) -> list[dict]:
    """``existing`` plus the ``extra`` links whose URL is new (and not in ``skip_urls``), capped at ``MAX_LINKS``."""
    seen = {item["url"] for item in existing} | {url for url in skip_urls if url}
    merged = list(existing)
    for item in extra:
        url = item.get("url")
        if url and url not in seen and len(merged) < MAX_LINKS:
            seen.add(url)
            merged.append({"url": url, "label": (item.get("label") or "")[:100]})
    return merged


def _sources(lines: list[str]) -> list[dict]:
    """Entries of the "Source of note" section: ``{"label", "url", "wikilink"}`` in note order, without duplicates.

    ``[[Kurs]]`` is a labelled wikilink, ``AI Devs 3: https://...`` a labelled URL, a bare URL has no label;
    the section's ``creation date`` / ``modification date`` bookkeeping lines are not sources.
    """
    entries: list[dict] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or _DATE_LINE.match(stripped) or stripped.startswith("<%"):
            continue
        links = _WIKILINK.findall(stripped)
        url = _first_url(stripped)
        if links:
            entries.extend({"label": title.strip(), "url": None, "wikilink": True} for title in links if title.strip())
        elif url:
            label = stripped[:stripped.index(url)].strip(" -:*•\t")
            entries.append({"label": label or None, "url": url, "wikilink": False})
        else:
            label = stripped.lstrip("-*• ").strip()
            if label and label.lower() not in ("brak", "none", "n/a"):
                entries.append({"label": label[:200], "url": None, "wikilink": False})
    seen = set()
    unique = []
    for entry in entries:
        key = (entry["label"], entry["url"])
        if key not in seen:
            seen.add(key)
            unique.append(entry)
    return unique


def parse_tool_note(text: str) -> dict:
    """Catalog fields found in a template note. Missing / placeholder values are simply absent."""
    header, sections = _split_header_and_sections(text)
    parsed: dict = {}
    labels, header_extras = _labels(header)
    extra_links: list[dict] = []
    for field, raw in labels.items():
        if field in LINK_FIELD_LABELS:
            urls = _all_urls(raw)
            url = urls[0] if urls else None
            if url and field == "github_url" and github_repo_stats.parse_repo_url(url) is None:
                extra_links.append({"url": url, "label": LINK_FIELD_LABELS[field]})  # a GitHub-ish link that is not a repo
                url = None
            if url:
                parsed[field] = url
            # Further URLs on the same line (two pricing pages) have no field of their own.
            extra_links.extend({"url": other, "label": LINK_FIELD_LABELS[field]} for other in urls[1:])
            if field == "pricing_url" and raw and not urls:
                parsed["pricing"] = _clean(raw)
            continue
        if field == "pricing_type":
            kind = pricing_type_from_text(raw)
            if kind:
                parsed["pricing_type"] = kind
            if raw.strip():
                parsed["pricing"] = _clean(raw)
            continue
        value = _clean(raw) if field != "purpose" else raw.strip()
        if not value:
            continue
        limit = SHORT_FIELD_LIMITS.get(field)
        if limit and len(value) > limit:
            continue
        parsed[field] = value
    points = _key_points(sections.get("key_points", []))
    if points:
        parsed["key_points"] = points
    commands = _commands(sections.get("important_commands", []))
    if commands:
        parsed["important_commands"] = commands
    notes = _notes(sections.get("additional_notes", []))
    if header_extras:
        notes = "\n".join([*header_extras, *([""] if notes else []), *([notes] if notes else [])])
    if notes:
        parsed["personal_notes"] = notes
    if extra_links:
        parsed["links"] = _merge_links([], extra_links)
    sources = _sources(sections.get("source_of_note", []))
    if sources:
        parsed["sources"] = sources
    return parsed


def apply_note_to_tool(tool, parsed: dict, overwrite: bool = False) -> list[str]:
    """Copy ``parsed`` onto ``tool``; returns the names of the fields that changed.

    Without ``overwrite`` only empty fields are filled (empty string, ``None`` or ``[]``).
    """
    changed = []
    own_urls = [getattr(tool, field, None) for field in LINK_FIELD_LABELS]  # pages the tool already has a field for

    def add_links(new_links: list[dict]) -> None:
        current_links = list(getattr(tool, "links", None) or [])
        merged = _merge_links(current_links, new_links, skip_urls=own_urls)
        if merged != current_links:
            tool.links = merged
            if "links" not in changed:
                changed.append("links")

    for field, value in parsed.items():
        if field in NON_COLUMN_FIELDS:
            continue
        if field == "links":
            add_links(value)
            continue
        current = getattr(tool, field, None)
        if field in LINK_FIELD_LABELS and current not in (None, "", []) and current != value and not overwrite:
            add_links([{"url": value, "label": LINK_FIELD_LABELS[field]}])  # the note names another page: keep it
            continue
        if current not in (None, "", []) and not overwrite:
            continue
        if current == value:
            continue
        setattr(tool, field, value)
        changed.append(field)
    return changed
