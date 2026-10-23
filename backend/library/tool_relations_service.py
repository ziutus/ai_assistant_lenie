"""Auto-proposed relations between radar entries (tool A ``works_with`` tool B).

A new radar entry usually arrives with a document that names the tools it is
used with ("emulators of AWS, Azure, GCP ... works with Terraform"). Matching
those names against the entries already on the radar proposes the edges, so
nobody links each tool by hand. Humans confirm or reject; a rejected edge is
never revived. No LLM and no network: whole-word name matching only.
"""

import re

from sqlalchemy import select

from library.db.models import Document, ToolRecommendation, ToolRelation

RELATIONS = {"works_with", "emulates", "alternative_to"}
STATUSES = {"proposed", "confirmed", "rejected"}
MIN_NAME_LENGTH = 3
CASE_INSENSITIVE_FROM = 5  # shorter names (AWS, GCP, Go) must match with the same case
CONTEXT_RADIUS = 80
ALTERNATIVE_RADIUS = 50
IGNORED_STATUSES = {"rejected", "archived"}


# Polish case endings after a foreign name: "konkurent Jeva", "z Terraformem", "w Flociem".
_POLISH_SUFFIX = r"(?:e?m|owi|ie|ów|ach|ami|om|[auy])?"
ALTERNATIVE_HINTS = re.compile(
    r"konkurent|alternatyw|zamiennik|zamiast|competitor|alternative|replacement|instead of", re.IGNORECASE,
)


def name_pattern(name: str) -> re.Pattern | None:
    name = name.strip()
    if len(name) < MIN_NAME_LENGTH:
        return None
    flags = re.IGNORECASE if len(name) >= CASE_INSENSITIVE_FROM else 0
    return re.compile(r"(?<![\w-])" + re.escape(name) + _POLISH_SUFFIX + r"(?![\w-])", flags)


_name_pattern = name_pattern  # kept for the unit tests written against the private name


def _source_text(session, item: ToolRecommendation) -> str:
    parts = [item.description or "", item.source_context or ""]
    if item.source_document_id is not None:
        document = session.get(Document, item.source_document_id)
        if document is not None:
            parts += [document.title or "", document.summary or "", document.text_md or document.text or ""]
    return "\n".join(part for part in parts if part)


def _snippet(text: str, match: re.Match) -> str:
    start, end = max(0, match.start() - CONTEXT_RADIUS), min(len(text), match.end() + CONTEXT_RADIUS)
    return " ".join(text[start:end].split())


def _one_per_name(entries) -> list:
    """The radar can hold several entries with one name (imported lists); link to one: adopted first, then lowest id."""
    best: dict[str, ToolRecommendation] = {}
    for entry in sorted(entries, key=lambda e: (e.status != "adopted", e.id)):
        best.setdefault(entry.name.strip().lower(), entry)
    return list(best.values())


def detect_relations(session, item: ToolRecommendation) -> dict:
    """Propose edges from ``item`` to every other radar entry its source text names.

    ``alternative_to`` when a wording like "konkurent"/"alternatywa" sits next to the name, else ``works_with``.

    Idempotent: an existing edge (any relation, status or direction) is left alone, so a rejected one stays rejected.
    """
    text = _source_text(session, item)
    created, existing = [], 0
    if not text:
        return {"created": created, "existing": existing}
    others = session.execute(
        select(ToolRecommendation).where(
            ToolRecommendation.id != item.id, ToolRecommendation.status.notin_(IGNORED_STATUSES),
        )
    ).scalars().all()
    for other in _one_per_name(others):
        pattern = name_pattern(other.name)
        matches = list(pattern.finditer(text)) if pattern else []
        if not matches:
            continue
        match, relation_kind = matches[0], "works_with"
        for candidate in matches:
            if ALTERNATIVE_HINTS.search(text[max(0, candidate.start() - ALTERNATIVE_RADIUS):candidate.end() + ALTERNATIVE_RADIUS]):
                match, relation_kind = candidate, "alternative_to"
                break
        found = session.execute(
            select(ToolRelation).where(
                ((ToolRelation.from_tool_id == item.id) & (ToolRelation.to_tool_id == other.id))
                | ((ToolRelation.from_tool_id == other.id) & (ToolRelation.to_tool_id == item.id)),
            ).limit(1)
        ).scalars().first()
        if found is not None:
            existing += 1
            continue
        session.add(ToolRelation(
            from_tool_id=item.id, to_tool_id=other.id, relation=relation_kind, status="proposed",
            detected_by="name_match", context=_snippet(text, match), source_document_id=item.source_document_id,
        ))
        created.append(other.name)
    session.flush()
    return {"created": created, "existing": existing}


def relations_for(session, item_ids: list[int]) -> dict[int, list[dict]]:
    """Non-rejected relations per radar entry, rendered from that entry's perspective."""
    if not item_ids:
        return {}
    own = set(item_ids)
    rows = session.execute(
        select(ToolRelation).where(
            ToolRelation.status != "rejected",
            (ToolRelation.from_tool_id.in_(own)) | (ToolRelation.to_tool_id.in_(own)),
        ).order_by(ToolRelation.id)
    ).scalars().all()
    related_ids = {r.from_tool_id for r in rows} | {r.to_tool_id for r in rows}
    entries = {
        e.id: e for e in session.execute(
            select(ToolRecommendation).where(ToolRecommendation.id.in_(related_ids))
        ).scalars().all()
    } if related_ids else {}
    result: dict[int, list[dict]] = {}
    for r in rows:
        for own_id, other_id in ((r.from_tool_id, r.to_tool_id), (r.to_tool_id, r.from_tool_id)):
            if own_id not in own or other_id not in entries:
                continue
            other = entries[other_id]
            result.setdefault(own_id, []).append({
                "id": r.id, "relation": r.relation, "status": r.status, "detected_by": r.detected_by,
                "context": r.context, "other_id": other.id, "other_name": other.name,
                "other_status": other.status, "in_my_stack": other.status == "adopted",
            })
    return result
