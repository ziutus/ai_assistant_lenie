"""Project cards: structured hands-on project cards filterable by child age.

A card (``ProjectCard``) is one project of a printed series such as
"Niesamowite Maszyny" (Robotyka – 100 projektów). It is identified by
``(series, number)``, so re-running the import updates the same row instead of
duplicating it. Cards a human already reviewed are never overwritten by an
import of the raw, unreviewed source (see ``upsert_cards``).

Age filtering: a card is printed with a suitable range (``age_min``–``age_max``).
``age=5`` returns cards whose range contains 5; ``stretch=N`` additionally
returns cards starting up to N years above the child's age, flagged
``age_fit="stretch"`` so the UI can show them as "do spróbowania z dorosłym".
"""

from __future__ import annotations

import datetime
import re
from dataclasses import dataclass

from sqlalchemy import and_, func, or_, select
from unidecode import unidecode

from library.db.models import ProjectCard

REVIEW_STATUSES = ("imported", "needs_review", "reviewed")
DEFAULT_SERIES = "Niesamowite Maszyny"

# Footer group names in the source PDFs are letter-spaced and run together after
# parsing ("SIŁASPRĘŻYSTOŚCII"); map them to readable labels.
GROUP_LABELS = {
    "DŹWIGNIEIKOŁYSKI": "Dźwignie i kołyski",
    "BLOCZKIIDŹWIGI": "Bloczki i dźwigi",
    "PRZEKŁADNIEIKOŁA": "Przekładnie i koła",
    "SIŁASPRĘŻYSTOŚCII": "Siła sprężystości i powietrze (wyrzutnie, balony)",
    "MASZYNYZSILNIKIEM": "Maszyny z silnikiem (wózki, winda, schody)",
    "PODSTAWOWEOBWODYI": "Podstawowe obwody i światła",
}

_TEXT_FIELDS = ("title", "topic", "group_name", "tagline", "description", "mechanism", "how_it_works", "safety",
                "review_notes")
_INT_RANGES = {"age_min": (0, 18), "age_max": (0, 18), "time_min": (0, 1440), "time_max": (0, 1440),
               "difficulty": (1, 3), "source_page": (1, 5000)}
_STRING_LIST_FIELDS = ("tools", "variants", "what_child_does", "what_adult_does", "safety_checklist", "steps")
EDITABLE_FIELDS = (*_TEXT_FIELDS, *_INT_RANGES, "needs_adult", *_STRING_LIST_FIELDS, "materials",
                   "troubleshooting", "review_status", "illustration_svg", "kind", "sections")

# What a card is: a hands-on build, a kitchen-science experiment, a toddler craft or a brain teaser.
KINDS = ("project", "experiment", "craft", "puzzle")
# Roles of the free-form ``sections`` (everything a card has beyond the dedicated fields). Unknown
# roles from a parser are stored as "other"; the UI hides ``hidden`` sections (puzzle answers).
SECTION_ROLES = ("explanation", "puzzle", "analysis", "hint", "solution", "answer", "tip", "key_tip",
                 "how_to_play", "other")
SECTION_FORMATS = ("text", "list", "steps")
MAX_SECTIONS = 30
MAX_SECTION_CHARS = 20_000

MAX_SVG_BYTES = 100_000
# The SVG is rendered by the browser through <img src="data:..."> (scripts never run there),
# but it is still stored from a request body, so keep it passive: no scripting, embedded
# documents, event handlers or external references.
_SVG_FORBIDDEN = re.compile(
    r"<\s*(?:script|foreignObject|iframe|object|embed|style|image|use)\b|(?<![\w-])on[a-z]+\s*=|javascript:|"
    r"<!ENTITY|<!DOCTYPE|href\s*=",
    re.IGNORECASE,
)


class ProjectCardError(ValueError):
    """Invalid card payload."""


MAX_PDF_BYTES = 60 * 1024 * 1024


def source_pdf_key(series: str, number: int) -> str:
    """Object-storage key of a card's original PDF, stable per (series, number)."""
    slug = re.sub(r"[^a-z0-9]+", "-", unidecode(series).lower()).strip("-") or "series"
    return f"project_cards/{slug}/{number:03d}.pdf"


def validate_pdf(data: bytes) -> None:
    if not data:
        raise ProjectCardError("file is empty")
    if len(data) > MAX_PDF_BYTES:
        raise ProjectCardError(f"PDF is larger than {MAX_PDF_BYTES // (1024 * 1024)} MB")
    if not data.startswith(b"%PDF-"):
        raise ProjectCardError("file is not a PDF")


def group_label(raw: str | None) -> str | None:
    if not raw:
        return None
    return GROUP_LABELS.get(raw, raw)


def _clean_text(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _string_list(value, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ProjectCardError(f"{field} must be a list of strings")
    return [item.strip() for item in value if item.strip()]


def _materials(value) -> list[dict]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ProjectCardError("materials must be a list of {qty, name}")
    out = []
    for item in value:
        if not isinstance(item, dict) or not _clean_text(item.get("name")):
            raise ProjectCardError("each material needs a name")
        out.append({"qty": _clean_text(item.get("qty")) or "", "name": _clean_text(item["name"])})
    return out


def _troubleshooting(value) -> list[dict]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ProjectCardError("troubleshooting must be a list of {problem, solution}")
    out = []
    for item in value:
        if not isinstance(item, dict) or not _clean_text(item.get("problem")):
            raise ProjectCardError("each troubleshooting entry needs a problem")
        out.append({"problem": _clean_text(item["problem"]), "solution": _clean_text(item.get("solution")) or ""})
    return out


def _sections(value) -> list[dict]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > MAX_SECTIONS:
        raise ProjectCardError(f"sections must be a list of at most {MAX_SECTIONS} objects")
    out = []
    for item in value:
        if not isinstance(item, dict):
            raise ProjectCardError("each section must be an object")
        title = _clean_text(item.get("title"))
        if not title:
            raise ProjectCardError("each section needs a title")
        fmt = item.get("format", "text")
        if fmt not in SECTION_FORMATS:
            raise ProjectCardError(f"section format must be one of {', '.join(SECTION_FORMATS)}")
        content = item.get("content")
        if fmt == "text":
            content = _clean_text(content) or ""
        else:
            content = _string_list(content, "section content")
        if len(content if isinstance(content, str) else " ".join(content)) > MAX_SECTION_CHARS:
            raise ProjectCardError(f"section content is longer than {MAX_SECTION_CHARS} characters")
        role = item.get("role")
        hidden = item.get("hidden", False)
        if not isinstance(hidden, bool):
            raise ProjectCardError("section hidden must be a boolean")
        out.append({"role": role if role in SECTION_ROLES else "other", "title": title, "format": fmt,
                    "content": content, "hidden": hidden})
    return out


def _svg(value) -> str | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if not isinstance(value, str):
        raise ProjectCardError("illustration_svg must be a string")
    svg = value.strip()
    if len(svg.encode("utf-8")) > MAX_SVG_BYTES:
        raise ProjectCardError(f"illustration_svg is larger than {MAX_SVG_BYTES} bytes")
    if not re.match(r"<svg[\s>]", svg, re.IGNORECASE) or not svg.lower().rstrip().endswith("</svg>"):
        raise ProjectCardError("illustration_svg must be a single <svg>...</svg> document")
    if _SVG_FORBIDDEN.search(svg):
        raise ProjectCardError("illustration_svg may not contain scripts, handlers, external references or DTDs")
    return svg


def validate_fields(data: dict) -> dict:
    """Validate a (partial) payload of editable fields; unknown keys are rejected."""
    unknown = sorted(set(data) - set(EDITABLE_FIELDS))
    if unknown:
        raise ProjectCardError(f"unknown or read-only fields: {', '.join(unknown)}")
    out: dict = {}
    for key, value in data.items():
        if key in _TEXT_FIELDS:
            out[key] = _clean_text(value)
            if key == "title" and not out[key]:
                raise ProjectCardError("title cannot be empty")
        elif key in _INT_RANGES:
            if value is None:
                out[key] = None
                continue
            low, high = _INT_RANGES[key]
            if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
                raise ProjectCardError(f"{key} must be an integer between {low} and {high}")
            out[key] = value
        elif key == "needs_adult":
            if not isinstance(value, bool):
                raise ProjectCardError("needs_adult must be a boolean")
            out[key] = value
        elif key in _STRING_LIST_FIELDS:
            out[key] = _string_list(value, key)
        elif key == "materials":
            out[key] = _materials(value)
        elif key == "troubleshooting":
            out[key] = _troubleshooting(value)
        elif key == "illustration_svg":
            out[key] = _svg(value)
        elif key == "sections":
            out[key] = _sections(value)
        elif key == "kind":
            if value not in KINDS:
                raise ProjectCardError(f"kind must be one of {', '.join(KINDS)}")
            out[key] = value
        elif key == "review_status":
            if value not in REVIEW_STATUSES:
                raise ProjectCardError(f"review_status must be one of {', '.join(REVIEW_STATUSES)}")
            out[key] = value
    age_min, age_max = out.get("age_min"), out.get("age_max")
    if age_min is not None and age_max is not None and age_min > age_max:
        raise ProjectCardError("age_min cannot exceed age_max")
    return out


def normalize_import_card(raw: dict, series: str = DEFAULT_SERIES) -> dict:
    """Map one ``cards.json`` record (parser output) onto ProjectCard fields.

    Keys a reviewed record may add (``what_child_does``, ``review_status``, ...)
    are passed through the same validation. ``import_flags`` and ``source_file``
    are import-only metadata.
    """
    try:
        number = int(raw["number"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ProjectCardError("card needs an integer 'number'") from exc
    fields = {key: raw[key] for key in EDITABLE_FIELDS if key in raw}
    if "group_name" not in fields:
        # Robotyka cards carry a letter-spaced footer name, the card-book family a readable chapter title.
        group = group_label(raw["group_raw"]) if raw.get("group_raw") else _clean_text(raw.get("chapter"))
        if group:
            fields["group_name"] = group
    fields.setdefault("kind", "project")
    fields.setdefault("review_status", "needs_review" if raw.get("flags") else "imported")
    cleaned = validate_fields(fields)
    if not cleaned.get("title"):
        raise ProjectCardError(f"card {number} has no title")
    flags = [str(flag) for flag in raw.get("flags", [])]
    if raw.get("age_source") == "cover":
        flags.append("age_from_cover")  # the printed age belongs to the whole book, not to this card
    cleaned.update({
        "series": _clean_text(raw.get("series")) or series,
        "number": number,
        "import_flags": flags,
        "source_file": _clean_text(raw.get("source_file")) or _clean_text(raw.get("file")),
    })
    return cleaned


@dataclass
class ImportResult:
    created: int = 0
    updated: int = 0
    kept_reviewed: int = 0

    def as_dict(self) -> dict:
        return {"created": self.created, "updated": self.updated, "kept_reviewed": self.kept_reviewed}


def upsert_cards(session, cards: list[dict], series: str = DEFAULT_SERIES) -> ImportResult:
    """Insert or update cards by ``(series, number)``.

    An existing ``reviewed`` card is left untouched unless the incoming record
    is itself ``reviewed`` (a reviewed rewrite replaces it).
    """
    result = ImportResult()
    for raw in cards:
        values = normalize_import_card(raw, series=series)
        existing = session.execute(
            select(ProjectCard).where(ProjectCard.series == values["series"], ProjectCard.number == values["number"])
        ).scalar_one_or_none()
        if existing is None:
            session.add(ProjectCard(**values))
            result.created += 1
            continue
        if existing.review_status == "reviewed" and values["review_status"] != "reviewed":
            result.kept_reviewed += 1
            continue
        for key, value in values.items():
            setattr(existing, key, value)
        existing.updated_at = datetime.datetime.now(datetime.timezone.utc)
        result.updated += 1
    session.commit()
    return result


def update_card(session, card: ProjectCard, data: dict) -> ProjectCard:
    for key, value in validate_fields(data).items():
        setattr(card, key, value)
    if (card.age_min is not None and card.age_max is not None) and card.age_min > card.age_max:
        raise ProjectCardError("age_min cannot exceed age_max")
    card.updated_at = datetime.datetime.now(datetime.timezone.utc)
    session.commit()
    return card


def age_fit(card: ProjectCard, age: int, stretch: int = 0) -> str | None:
    """``"ok"`` inside the printed range, ``"stretch"`` a little above it, ``"unknown"`` without a
    printed age, else None."""
    if card.age_min is None:
        return "unknown"
    if card.age_min <= age and (card.age_max is None or card.age_max >= age):
        return "ok"
    if stretch and age < card.age_min <= age + stretch:
        return "stretch"
    return None


def list_cards(
    session,
    *,
    age: int | None = None,
    stretch: int = 0,
    max_difficulty: int | None = None,
    max_time: int | None = None,
    group: str | None = None,
    query: str | None = None,
    review_status: str | None = None,
    needs_adult: bool | None = None,
    kind: str | None = None,
    series: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[ProjectCard], int]:
    """Return one page of matching cards and the total number of matches."""
    stmt = select(ProjectCard)
    if kind:
        stmt = stmt.where(ProjectCard.kind == kind)
    if series:
        stmt = stmt.where(ProjectCard.series == series)
    if age is not None:
        # Cards printed without an age (some card books give none) stay visible, flagged "unknown".
        stmt = stmt.where(or_(
            ProjectCard.age_min.is_(None),
            and_(
                ProjectCard.age_min <= age + max(stretch, 0),
                or_(ProjectCard.age_max.is_(None), ProjectCard.age_max >= age),
            ),
        ))
    if max_difficulty is not None:
        stmt = stmt.where(ProjectCard.difficulty <= max_difficulty)
    if max_time is not None:
        stmt = stmt.where(ProjectCard.time_max <= max_time)
    if group:
        stmt = stmt.where(ProjectCard.group_name == group)
    if review_status:
        stmt = stmt.where(ProjectCard.review_status == review_status)
    if needs_adult is not None:
        stmt = stmt.where(ProjectCard.needs_adult.is_(needs_adult))
    if query:
        like = f"%{query.strip()}%"
        stmt = stmt.where(or_(
            ProjectCard.title.ilike(like), ProjectCard.topic.ilike(like),
            ProjectCard.mechanism.ilike(like), ProjectCard.description.ilike(like),
        ))
    total = session.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    page = stmt.order_by(ProjectCard.series, ProjectCard.number).limit(limit).offset(offset)
    return list(session.execute(page).scalars()), total


def group_counts(session, *, series: str | None = None) -> list[dict]:
    stmt = select(ProjectCard.group_name, func.count()).group_by(ProjectCard.group_name)
    if series:
        stmt = stmt.where(ProjectCard.series == series)
    return [{"name": name, "count": count} for name, count in session.execute(stmt.order_by(ProjectCard.group_name))
            if name]


def series_counts(session) -> list[dict]:
    """Every series with its kind and card count, for the list filters."""
    rows = session.execute(
        select(ProjectCard.series, ProjectCard.kind, func.count())
        .group_by(ProjectCard.series, ProjectCard.kind).order_by(ProjectCard.series)
    ).all()
    return [{"name": name, "kind": kind, "count": count} for name, kind, count in rows]


def series_pdf_key(series: str) -> str:
    """Object-storage key of the one PDF a whole series was printed in (card-book families)."""
    slug = re.sub(r"[^a-z0-9]+", "-", unidecode(series).lower()).strip("-") or "series"
    return f"project_cards/{slug}/book.pdf"


_SUMMARY_FIELDS = (
    "id", "series", "number", "kind", "title", "topic", "group_name", "tagline", "mechanism", "age_min", "age_max",
    "time_min", "time_max", "difficulty", "needs_adult", "review_status", "source_file", "source_page",
)
_DETAIL_FIELDS = (
    *_SUMMARY_FIELDS, "description", "how_it_works", "materials", "tools", "steps", "troubleshooting", "variants",
    "safety", "what_child_does", "what_adult_does", "safety_checklist", "review_notes", "import_flags",
    "illustration_svg", "sections",
)


def card_to_dict(card: ProjectCard, *, detail: bool = False, age: int | None = None, stretch: int = 0) -> dict:
    data = {key: getattr(card, key) for key in (_DETAIL_FIELDS if detail else _SUMMARY_FIELDS)}
    data["has_source_pdf"] = bool(card.source_pdf_key)
    if not detail:
        data["has_illustration"] = bool(card.illustration_svg)
    if age is not None:
        data["age_fit"] = age_fit(card, age, stretch)
    return data
