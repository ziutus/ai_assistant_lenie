"""LLM-assisted extraction of dated events discussed in documents."""

import calendar
import datetime
import json
import logging
import re
from collections.abc import Iterable

import dateparser
from sqlalchemy import delete
from unidecode import unidecode

from library.ai import ai_ask
from library.config_loader import load_config
from library.db.models import DocumentEvent
from library.text_functions import detect_chapters

logger = logging.getLogger(__name__)

DEFAULT_TIMELINE_MODEL = "Bielik-11B-v3.0-Instruct"
MAX_FRAGMENT_CHARS = 10_000

_MONTHS = {
    "stycznia": 1,
    "styczniu": 1,
    "lutego": 2,
    "lutym": 2,
    "marca": 3,
    "marcu": 3,
    "kwietnia": 4,
    "kwietniu": 4,
    "maja": 5,
    "maju": 5,
    "czerwca": 6,
    "czerwcu": 6,
    "lipca": 7,
    "lipcu": 7,
    "sierpnia": 8,
    "sierpniu": 8,
    "wrzesnia": 9,
    "wrzesniu": 9,
    "pazdziernika": 10,
    "pazdzierniku": 10,
    "listopada": 11,
    "listopadzie": 11,
    "grudnia": 12,
    "grudniu": 12,
}
_MONTH_PATTERN = "|".join(sorted(_MONTHS, key=len, reverse=True))
_DECADE_WORDS = {
    "dziesiate": 10,
    "dwudzieste": 20,
    "trzydzieste": 30,
    "czterdzieste": 40,
    "piecdziesiate": 50,
    "szescdziesiate": 60,
    "siedemdziesiate": 70,
    "osiemdziesiate": 80,
    "dziewiecdziesiate": 90,
}
_ERA_PATTERNS = (
    (re.compile(r"\bpo\s+ii\s+wojnie\s+swiatowej\b", re.IGNORECASE), 1945),
    (re.compile(r"\bpo\s+i\s+wojnie\s+swiatowej\b", re.IGNORECASE), 1918),
    (re.compile(r"\bprzed\s+ii\s+wojna\s+swiatowa\b", re.IGNORECASE), 1939),
    (re.compile(r"\b(?:w\s+)?okresie\s+prl\b", re.IGNORECASE), 1945),
    (re.compile(r"\b(?:podczas|w\s+czasie)\s+zimnej\s+wojny\b", re.IGNORECASE), 1947),
)
_YEAR_RANGE_RE = re.compile(r"(?:w\s+latach\s+)?(\d{3,4})\s*[-‐‑‒–—−]\s*(\d{3,4})")
_TYPOGRAPHY_TRANSLATION = str.maketrans({
    **dict.fromkeys("‐‑‒–—−", "-"),
    **dict.fromkeys("“”„‟«»", '"'),
    **dict.fromkeys("‘’‚‛", "'"),
})


def _date_result(
    precision: str,
    sort_year: int | None,
    start: datetime.date | None = None,
    end: datetime.date | None = None,
) -> dict:
    return {
        "event_date": start,
        "event_date_end": end,
        "date_precision": precision,
        "sort_year": sort_year,
    }


def _roman_to_int(value: str) -> int | None:
    values = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    total = previous = 0
    for character in reversed(value.upper()):
        current = values.get(character)
        if current is None:
            return None
        total += -current if current < previous else current
        previous = max(previous, current)
    return total or None


def normalize_date_text(date_text: str) -> dict | None:
    """Normalize Polish exact and coarse date expressions for storage and sorting."""
    original = " ".join((date_text or "").split())
    if not original:
        return None
    plain = unidecode(original).casefold()

    century_match = re.search(r"\b([ivxlcdm]+)\s+(?:wiek|wieku|w\.)\b", plain, re.IGNORECASE)
    if century_match:
        century = _roman_to_int(century_match.group(1))
        if century and 1 <= century <= 30:
            first_year = (century - 1) * 100 + 1
            last_year = century * 100
            return _date_result(
                "century",
                first_year + 49,
                datetime.date(first_year, 1, 1),
                datetime.date(last_year, 12, 31),
            )

    decade_match = re.search(r"\blata\s+(\d{2})\.?\b", plain)
    if decade_match:
        first_year = 1900 + int(decade_match.group(1))
        return _date_result(
            "decade",
            first_year,
            datetime.date(first_year, 1, 1),
            datetime.date(first_year + 9, 12, 31),
        )
    word_decade_match = re.search(r"\blata\s+([a-z]+)\b", plain)
    if word_decade_match and word_decade_match.group(1) in _DECADE_WORDS:
        first_year = 1900 + _DECADE_WORDS[word_decade_match.group(1)]
        return _date_result(
            "decade",
            first_year,
            datetime.date(first_year, 1, 1),
            datetime.date(first_year + 9, 12, 31),
        )

    for pattern, sort_year in _ERA_PATTERNS:
        if pattern.search(plain):
            return _date_result("era", sort_year)

    day_match = re.search(rf"\b([0-3]?\d)\s+({_MONTH_PATTERN})\s+(\d{{4}})(?:\s*r\.?\b)?", plain)
    if day_match:
        day, month, year = int(day_match.group(1)), _MONTHS[day_match.group(2)], int(day_match.group(3))
        try:
            parsed = datetime.date(year, month, day)
        except ValueError:
            return None
        return _date_result("day", year, parsed, parsed)

    month_match = re.search(rf"\b(?:w\s+)?({_MONTH_PATTERN})\s+(\d{{4}})(?:\s*r\.?\b)?", plain)
    if month_match:
        month, year = _MONTHS[month_match.group(1)], int(month_match.group(2))
        return _date_result(
            "month",
            year,
            datetime.date(year, month, 1),
            datetime.date(year, month, calendar.monthrange(year, month)[1]),
        )

    year_range_match = re.fullmatch(rf"\s*{_YEAR_RANGE_RE.pattern}\s*", plain)
    if year_range_match:
        first_year, last_year = int(year_range_match.group(1)), int(year_range_match.group(2))
        if first_year > last_year:
            return None
        try:
            start = datetime.date(first_year, 1, 1)
            end = datetime.date(last_year, 12, 31)
        except ValueError:
            return None
        return _date_result("year", first_year, start, end)

    year_match = re.fullmatch(r"\s*(?:w\s+)?(\d{3,4})\s*(?:r\.?|roku|rok)?\s*", plain)
    if year_match:
        year = int(year_match.group(1))
        try:
            start = datetime.date(year, 1, 1)
            end = datetime.date(year, 12, 31)
        except ValueError:
            return None
        return _date_result("year", year, start, end)

    parsed = dateparser.parse(
        original,
        languages=["pl"],
        settings={"DATE_ORDER": "DMY", "REQUIRE_PARTS": ["year"], "STRICT_PARSING": True},
    )
    if parsed is None:
        return None
    value = parsed.date()
    if not 500 <= value.year <= 2100:
        return None
    if re.search(rf"(?<!\d){value.year}(?!\d)", plain) is None:
        return None
    return _date_result("unknown", value.year, value, value)


def _complete_array_prefix(raw: str) -> str | None:
    """Return a JSON array containing all complete top-level objects in a truncated array."""
    array_start = raw.find("[")
    if array_start < 0:
        return None

    in_string = escaped = False
    array_depth = object_depth = 0
    last_complete_object = None
    for position, character in enumerate(raw[array_start:], start=array_start):
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character == "[":
            array_depth += 1
        elif character == "]":
            array_depth -= 1
        elif character == "{":
            object_depth += 1
        elif character == "}":
            object_depth -= 1
            if array_depth == 1 and object_depth == 0:
                last_complete_object = position

    if last_complete_object is None:
        return None
    return raw[array_start:last_complete_object + 1].rstrip().rstrip(",") + "]"


def _parse_events_response(raw_response: str) -> tuple[list[dict], bool]:
    """Parse an event list and report whether the original JSON was invalid."""
    raw = (raw_response or "").strip()
    fence = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", raw, re.IGNORECASE | re.DOTALL)
    if fence:
        raw = fence.group(1).strip()
    invalid_json = False
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        invalid_json = True
        repaired = _complete_array_prefix(raw)
        try:
            payload = json.loads(repaired) if repaired is not None else None
        except (json.JSONDecodeError, TypeError):
            payload = None
        if payload is None:
            logger.warning("timeline LLM returned invalid JSON that could not be recovered")
            return [], True
    if isinstance(payload, dict):
        payload = payload.get("events", payload.get("wydarzenia", []))
    if not isinstance(payload, list):
        return [], invalid_json
    return [item for item in payload if isinstance(item, dict)], invalid_json


def parse_events_response(raw_response: str) -> list[dict]:
    """Parse a JSON event list, recovering complete objects from a truncated array."""
    events, _invalid_json = _parse_events_response(raw_response)
    return events


def _normalize_quote_typography(value: str) -> str:
    return " ".join(value.translate(_TYPOGRAPHY_TRANSLATION).split())


def _quote_is_grounded(quote: str, fragment: str) -> bool:
    return bool(quote.strip()) and _normalize_quote_typography(quote) in _normalize_quote_typography(fragment)


def split_timeline_fragments(text: str, max_chars: int = MAX_FRAGMENT_CHARS) -> list[str]:
    """Split long chapters at paragraph boundaries, hard-splitting only oversized paragraphs."""
    paragraphs = re.split(r"\n\s*\n", text.strip())
    fragments: list[str] = []
    current: list[str] = []
    current_length = 0
    for paragraph in paragraphs:
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        if len(paragraph) > max_chars:
            if current:
                fragments.append("\n\n".join(current))
                current, current_length = [], 0
            fragments.extend(paragraph[start:start + max_chars] for start in range(0, len(paragraph), max_chars))
            continue
        separator = 2 if current else 0
        if current and current_length + separator + len(paragraph) > max_chars:
            fragments.append("\n\n".join(current))
            current, current_length = [], 0
            separator = 0
        current.append(paragraph)
        current_length += separator + len(paragraph)
    if current:
        fragments.append("\n\n".join(current))
    return fragments


def _timeline_prompt(fragment: str) -> str:
    return f"""Przeanalizuj poniższy fragment dokumentu i wyodrębnij wyłącznie wydarzenia opisywane w tekście,
którym tekst przypisuje datę albo okres. Nie dodawaj wiedzy zewnętrznej ani nie zgaduj dat.

Zwróć WYŁĄCZNIE poprawny JSON: listę obiektów:
[
  {{"date_text": "oryginalny zapis daty z tekstu", "description": "jedno rzeczowe zdanie",
    "quote": "dokładny krótki cytat z fragmentu, maksymalnie około 200 znaków"}}
]

Pole quote musi być dosłownym cytatem obecnym w przekazanym fragmencie. Jeśli nie ma wydarzeń, zwróć [].

FRAGMENT:
{fragment}
"""


def _response_usage(response) -> tuple[int, float | None]:
    tokens = getattr(response, "total_tokens", None)
    if tokens is None:
        tokens = sum(
            int(getattr(response, name, 0) or 0)
            for name in ("prompt_tokens", "completion_tokens", "input_tokens", "output_tokens")
        )
    for name in ("cost_usd", "cost", "credits_used"):
        value = getattr(response, name, None)
        if value is not None:
            return int(tokens or 0), float(value)
    return int(tokens or 0), None


def extract_fragment_events(fragment: str, chapter_position: int | None, model: str) -> tuple[list[dict], dict]:
    """Make one LLM call and retain only grounded events with normalizable dates."""
    response = ai_ask(_timeline_prompt(fragment), model=model, temperature=0.1, max_token_count=4000)
    tokens, cost = _response_usage(response)
    events: list[dict] = []
    rejected_quote = rejected_date = 0
    candidates, invalid_json = _parse_events_response(response.response_text)
    for candidate in candidates:
        date_text = str(candidate.get("date_text") or "").strip()
        description = str(candidate.get("description") or "").strip()
        quote = str(candidate.get("quote") or "").strip()
        if not description or not _quote_is_grounded(quote, fragment):
            rejected_quote += 1
            continue
        normalized_date = normalize_date_text(date_text)
        if normalized_date is None:
            rejected_date += 1
            continue
        events.append({
            "chapter_position": chapter_position,
            "date_text": date_text,
            "description": description,
            "anchor_quote": quote,
            **normalized_date,
        })
    return events, {
        "rejected_without_quote": rejected_quote,
        "rejected_without_date": rejected_date,
        "invalid_json": int(invalid_json),
        "llm_calls": 1,
        "llm_tokens": tokens,
        "llm_cost": cost,
    }


def _chapters_for_document(doc, selected_position: int | None = None) -> list[dict]:
    text = doc.text_md or doc.text or ""
    if not text.strip():
        raise ValueError("document has no usable text")
    chapters = detect_chapters(text)
    if not chapters:
        if selected_position is not None:
            raise ValueError("document has no detectable chapters")
        return [{"position": None, "title": doc.title or "Dokument", "text": text}]
    selected = [chapter for chapter in chapters if selected_position in (None, chapter["position"])]
    if selected_position is not None and not selected:
        raise ValueError(f"chapter {selected_position} not found")
    return [
        {
            "position": chapter["position"],
            "title": chapter["title"],
            "text": text[chapter["char_start"]:chapter["char_end"]],
        }
        for chapter in selected
    ]


def _combine_costs(costs: Iterable[float | None]) -> float | None:
    values = list(costs)
    return sum(value for value in values if value is not None) if values and all(v is not None for v in values) else None


def extract_document_events(session, doc, model: str | None = None, *, chapter_position: int | None = None) -> dict:
    """Extract events without mutating the session; return events and per-chapter reports."""
    del session  # Kept in the public API for symmetry with refresh_document_events.
    selected_model = model or load_config().get("TIMELINE_MODEL") or DEFAULT_TIMELINE_MODEL
    events: list[dict] = []
    chapter_reports: list[dict] = []
    for chapter in _chapters_for_document(doc, chapter_position):
        chapter_events: list[dict] = []
        fragment_reports: list[dict] = []
        for fragment in split_timeline_fragments(chapter["text"]):
            extracted, report = extract_fragment_events(fragment, chapter["position"], selected_model)
            chapter_events.extend(extracted)
            fragment_reports.append(report)
        events.extend(chapter_events)
        chapter_reports.append({
            "chapter_position": chapter["position"],
            "chapter_title": chapter["title"],
            "events": len(chapter_events),
            "rejected_without_quote": sum(r["rejected_without_quote"] for r in fragment_reports),
            "rejected_without_date": sum(r["rejected_without_date"] for r in fragment_reports),
            "invalid_json": sum(r["invalid_json"] for r in fragment_reports),
            "llm_calls": sum(r["llm_calls"] for r in fragment_reports),
            "llm_tokens": sum(r["llm_tokens"] for r in fragment_reports),
            "llm_cost": _combine_costs(r["llm_cost"] for r in fragment_reports),
        })
    return {"model": selected_model, "events": events, "chapters": chapter_reports}


def refresh_document_events(session, doc, model: str | None = None, *, chapter_position: int | None = None) -> dict:
    """Replace stored derived events for a document, or one explicitly selected chapter."""
    result = extract_document_events(session, doc, model, chapter_position=chapter_position)
    statement = delete(DocumentEvent).where(DocumentEvent.document_id == doc.id)
    if chapter_position is not None:
        statement = statement.where(DocumentEvent.chapter_position == chapter_position)
    session.execute(statement)
    rows = [
        DocumentEvent(document_id=doc.id, **event)
        for event in result["events"]
    ]
    session.add_all(rows)
    result["rows"] = rows
    logger.info("timeline doc=%s: extracted %d events", doc.id, len(rows))
    return result
