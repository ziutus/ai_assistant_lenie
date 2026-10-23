"""Knowledge sources: where the user learned about things (a course, a newsletter, a channel...).

A knowledge source is a ``discovery_sources`` row - the same lookup documents use for "how I found
it" - extended with a ``kind``, a progress ``status``, dates, a 1-5 ``rating`` and a review note, so
one place can answer "is this course worth it" for documents and for tools. ``tool_sources`` links a
catalog tool to the sources it came from.

Pure helpers (validation, name matching, kind guessing) plus the few queries the routes and the
note import share. Nothing here commits.
"""

import datetime
import re
import unicodedata

from sqlalchemy import select

from library.db.models import DiscoverySource, Document, Tool, ToolSource

KINDS = ("course", "training", "newsletter", "channel", "book", "person", "community", "website", "other")
STATUSES = ("planned", "in_progress", "finished", "dropped")
MAX_REVIEW_NOTE = 4000

_COURSE_WORDS = ("kurs", "course", "udemy", "coursera", "academy", "akademia", "lekcj", "ai devs")
_TRAINING_WORDS = ("szkolenie", "training", "warsztat", "workshop", "bootcamp")


def normalize_name(name: str) -> str:
    folded = unicodedata.normalize("NFKD", name.lower())
    folded = "".join(char for char in folded if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", folded).strip()


def guess_kind(name: str) -> str:
    """A first guess from the wording of the name; the user corrects it on the sources page."""
    low = name.lower()
    if any(word in low for word in _TRAINING_WORDS):
        return "training"
    if any(word in low for word in _COURSE_WORDS):
        return "course"
    return "other"


def _optional_text(data: dict, field: str, limit: int | None = None) -> tuple[bool, str | None]:
    if field not in data:
        return False, None
    value = data[field]
    if value is not None and not isinstance(value, str):
        raise ValueError(f"{field} must be a string or null")
    text = (value or "").strip()
    if limit and len(text) > limit:
        raise ValueError(f"{field} is too long (max {limit} characters)")
    return True, text or None


def _optional_date(data: dict, field: str) -> tuple[bool, datetime.date | None]:
    present, text = _optional_text(data, field)
    if not present or text is None:
        return present, None
    try:
        return True, datetime.date.fromisoformat(text)
    except ValueError:
        raise ValueError(f"{field} must be an ISO date (YYYY-MM-DD)") from None


def validate_fields(data: dict) -> dict:
    """The knowledge-source fields present in ``data``, cleaned; raises ``ValueError`` with a user-facing message.

    Keys that are absent stay absent (so a PATCH leaves them alone); an empty string / null clears a field.
    """
    cleaned: dict = {}
    for field, allowed in (("kind", KINDS), ("status", STATUSES)):
        present, value = _optional_text(data, field)
        if present:
            if value is not None and value not in allowed:
                raise ValueError(f"{field} must be one of: {', '.join(allowed)}")
            cleaned[field] = value
    for field in ("started_on", "finished_on"):
        present, value = _optional_date(data, field)
        if present:
            cleaned[field] = value
    started, finished = cleaned.get("started_on"), cleaned.get("finished_on")
    if started and finished and finished < started:
        raise ValueError("finished_on cannot be earlier than started_on")
    if "rating" in data:
        rating = data["rating"]
        if rating is not None and rating != "":
            if isinstance(rating, bool) or not isinstance(rating, int) or not 1 <= rating <= 5:
                raise ValueError("rating must be a whole number from 1 to 5")
        cleaned["rating"] = rating if isinstance(rating, int) and not isinstance(rating, bool) else None
    present, note = _optional_text(data, "review_note", MAX_REVIEW_NOTE)
    if present:
        cleaned["review_note"] = note
    present, path = _optional_text(data, "obsidian_note_path")
    if present:
        cleaned["obsidian_note_path"] = path
    present, url = _optional_text(data, "url")
    if present:
        if url is not None and not url.lower().startswith(("http://", "https://")):
            raise ValueError("url must start with http:// or https://")
        cleaned["url"] = url
    return cleaned


def source_fields(source: DiscoverySource) -> dict:
    """The knowledge-source part of a source's JSON representation."""
    return {
        "kind": source.kind,
        "status": source.status,
        "started_on": source.started_on.isoformat() if source.started_on else None,
        "finished_on": source.finished_on.isoformat() if source.finished_on else None,
        "rating": source.rating,
        "review_note": source.review_note,
        "obsidian_note_path": source.obsidian_note_path,
    }


def find_source(session, name: str) -> DiscoverySource | None:
    """The existing source whose name equals ``name`` ignoring case, diacritics and punctuation."""
    wanted = normalize_name(name)
    if not wanted:
        return None
    for pending in session.new:
        if isinstance(pending, DiscoverySource) and normalize_name(pending.name) == wanted:
            return pending
    for source in session.execute(select(DiscoverySource)).scalars():
        if normalize_name(source.name) == wanted:
            return source
    return None


def note_path_for_title(session, title: str) -> str | None:
    """Vault-relative path of the reimported Obsidian note called ``title``, when exactly one exists."""
    escaped = title.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    urls = session.execute(
        select(Document.url).where(
            Document.document_type == "obsidian_note", Document.url.ilike(f"%/{escaped}.md", escape="\\"),
        )
    ).scalars().all()
    paths = sorted({url[len("obsidian://"):] for url in urls if url.startswith("obsidian://")})
    return paths[0] if len(paths) == 1 else None


def get_or_create_source(session, name: str, *, kind: str | None = None, url: str | None = None) -> tuple[DiscoverySource, bool]:
    """Find a source by (normalized) name or create it with a guessed kind. Returns ``(source, created)``."""
    name = name.strip()
    source = find_source(session, name)
    if source is not None:
        return source, False
    source = DiscoverySource(name=name[:255], kind=kind or guess_kind(name), url=url)
    session.add(source)
    session.flush()
    return source, True


def link_tool(session, tool: Tool, source: DiscoverySource, context: str | None = None) -> tuple[ToolSource, bool]:
    """Attach ``source`` to ``tool`` (idempotent; an existing link only gains a missing context)."""
    link = session.execute(
        select(ToolSource).where(ToolSource.tool_id == tool.id, ToolSource.source_id == source.id)
    ).scalar_one_or_none()
    if link is not None:
        if context and not link.context:
            link.context = context
        return link, False
    link = ToolSource(tool_id=tool.id, source_id=source.id, context=context)
    session.add(link)
    session.flush()
    return link, True


def unlink_tool(session, tool_id: int, source_id: int) -> bool:
    link = session.execute(
        select(ToolSource).where(ToolSource.tool_id == tool_id, ToolSource.source_id == source_id)
    ).scalar_one_or_none()
    if link is None:
        return False
    session.delete(link)
    return True


def sources_for_tools(session, tool_ids: list[int]) -> dict[int, list[dict]]:
    """``{tool_id: [source summary...]}`` for the catalog cards (one query for all tools)."""
    if not tool_ids:
        return {}
    rows = session.execute(
        select(ToolSource, DiscoverySource)
        .join(DiscoverySource, DiscoverySource.id == ToolSource.source_id)
        .where(ToolSource.tool_id.in_(tool_ids))
        .order_by(DiscoverySource.name)
    ).all()
    result: dict[int, list[dict]] = {}
    for link, source in rows:
        result.setdefault(link.tool_id, []).append({
            "id": source.id, "name": source.name, "kind": source.kind, "url": source.url,
            "status": source.status, "rating": source.rating, "context": link.context,
        })
    return result


def tools_for_sources(session) -> dict[int, list[dict]]:
    """``{source_id: [{id, name}...]}`` - the tools each source introduced."""
    rows = session.execute(
        select(ToolSource.source_id, Tool.id, Tool.name)
        .join(Tool, Tool.id == ToolSource.tool_id)
        .order_by(Tool.name)
    ).all()
    result: dict[int, list[dict]] = {}
    for source_id, tool_id, tool_name in rows:
        result.setdefault(source_id, []).append({"id": tool_id, "name": tool_name})
    return result


def link_note_sources(session, tool: Tool, entries: list[dict]) -> dict:
    """Turn the "Source of note" entries of a vault note into knowledge sources linked to ``tool``.

    ``entries`` come from ``tool_note_parser.parse_tool_note()["sources"]``: ``{"label", "url", "wikilink"}``.
    An entry with a label (a ``[[wikilink]]`` or "Label: https://...") becomes a source found or created by
    name; a bare URL is attached to the first labelled source of the note as context, otherwise reported as
    skipped (a documentation link is not a place the knowledge came from).
    """
    linked: list[str] = []
    created: list[str] = []
    skipped: list[str] = []
    first_source: DiscoverySource | None = None
    bare_urls: list[str] = []
    for entry in entries:
        label = (entry.get("label") or "").strip()
        url = entry.get("url")
        if not label:
            if url:
                bare_urls.append(url)
            continue
        if normalize_name(label) == normalize_name(tool.name):  # a note that names itself as its source
            continue
        source, is_new = get_or_create_source(session, label, url=None if entry.get("wikilink") else url)
        if is_new:
            created.append(source.name)
        if entry.get("wikilink") and not source.obsidian_note_path:
            source.obsidian_note_path = note_path_for_title(session, label)
        if not source.url and url and not entry.get("wikilink"):
            source.url = url
        link, is_linked = link_tool(session, tool, source, context=url if not entry.get("wikilink") else None)
        if is_linked:
            linked.append(source.name)
        first_source = first_source or source
    for url in bare_urls:
        if first_source is not None:
            link, _ = link_tool(session, tool, first_source)
            if not link.context:
                link.context = url
        else:
            skipped.append(url)
    return {"linked": linked, "created": created, "skipped_urls": skipped}
