"""LLM-assisted classification of the historical period a document's content is about."""

import json
import logging
import re

from sqlalchemy import delete

from library.ai import ai_ask
from library.config_loader import load_config
from library.db.models import DocumentTimePeriod
from library.llm_usage.report import usage_report
from library.timeline_events import _chapters_for_document, _complete_array_prefix

logger = logging.getLogger(__name__)

DEFAULT_TIME_PERIOD_MODEL = "Bielik-11B-v3.0-Instruct"
MAX_FRAGMENT_CHARS = 8_000
MAX_PERIODS_PER_CHAPTER = 3
MIN_YEAR = -10_000
MAX_YEAR = 2_100
_CONFIDENCE_LEVELS = {"high", "medium", "low"}


def _time_period_prompt(fragment: str) -> str:
    return f"""Przeanalizuj poniższy tekst i określ, jakiego okresu czasowego dotyczy jego treść
(o jakim czasie opowiada tekst, a nie kiedy został napisany).

Zwróć WYŁĄCZNIE poprawny JSON: listę od 1 do {MAX_PERIODS_PER_CHAPTER} okresów, główny okres jako pierwszy:
[
  {{"period_label": "krótka nazwa okresu po polsku, np. 'współczesność', 'zimna wojna', 'starożytny Egipt', 'II wojna światowa', 'średniowiecze'",
    "period_start_year": <rok początkowy jako liczba całkowita; lata p.n.e. zapisuj jako liczby ujemne, np. panowanie Ramzesa II zaczęło się w -1279; null tylko gdy nie da się oszacować>,
    "period_end_year": <rok końcowy jako liczba całkowita (p.n.e. ujemnie); dla współczesności użyj bieżącego roku; null tylko gdy nie da się oszacować>,
    "confidence": "high|medium|low",
    "evidence": "jedno zdanie: na jakiej podstawie z tekstu to określono"}}
]

Podawaj przybliżone lata także dla epok dawnych (np. Nowe Państwo w Egipcie: -1550 do -1070, średniowiecze: 476 do 1492).
Jeśli tekst nie opowiada o żadnym okresie (np. poradnik techniczny, tekst ponadczasowy), zwróć [].

TEKST:
{fragment}
"""


def _parse_periods_response(raw_response: str) -> tuple[list[dict], bool]:
    """Parse a period list and report whether the original JSON was invalid."""
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
            logger.warning("time period LLM returned invalid JSON that could not be recovered")
            return [], True
    if isinstance(payload, dict):
        payload = payload.get("periods", payload.get("okresy", []))
    if not isinstance(payload, list):
        return [], invalid_json
    return [item for item in payload if isinstance(item, dict)], invalid_json


def parse_periods_response(raw_response: str) -> list[dict]:
    """Parse a JSON period list, recovering complete objects from a truncated array."""
    periods, _invalid_json = _parse_periods_response(raw_response)
    return periods


def _coerce_year(value) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        year = value
    elif isinstance(value, str) and re.fullmatch(r"-?\d{1,5}", value.strip()):
        year = int(value.strip())
    else:
        return None
    return year if MIN_YEAR <= year <= MAX_YEAR else None


def normalize_period(candidate: dict) -> dict | None:
    """Validate one LLM period candidate; BCE years are negative integers."""
    label = " ".join(str(candidate.get("period_label") or "").split())
    if not label:
        return None
    start = _coerce_year(candidate.get("period_start_year"))
    end = _coerce_year(candidate.get("period_end_year"))
    if start is not None and end is not None and start > end:
        start, end = end, start
    confidence = str(candidate.get("confidence") or "").strip().lower()
    if confidence not in _CONFIDENCE_LEVELS:
        confidence = "low"
    evidence = str(candidate.get("evidence") or "").strip() or None
    return {
        "period_label": label[:100],
        "period_start_year": start,
        "period_end_year": end,
        "confidence": confidence,
        "evidence": evidence,
    }


def classify_fragment(fragment: str, model: str) -> tuple[list[dict], dict]:
    """Make one LLM call and retain valid, de-duplicated periods (main period first)."""
    response = ai_ask(
        _time_period_prompt(fragment), model=model, temperature=0.1, max_token_count=800,
        operation="time_period_classification",
    )
    candidates, invalid_json = _parse_periods_response(response.response_text)
    periods: list[dict] = []
    seen_labels: set[str] = set()
    rejected = 0
    for candidate in candidates:
        normalized = normalize_period(candidate)
        if normalized is None:
            rejected += 1
            continue
        label_key = normalized["period_label"].casefold()
        if label_key in seen_labels:
            continue
        seen_labels.add(label_key)
        periods.append(normalized)
        if len(periods) == MAX_PERIODS_PER_CHAPTER:
            break
    return periods, {
        "rejected_invalid": rejected,
        "invalid_json": int(invalid_json),
        **usage_report(response.usage).as_dict(),
    }


def extract_document_periods(session, doc, model: str | None = None, *, chapter_position: int | None = None) -> dict:
    """Classify periods per reader chapter (whole document when it has no chapters)."""
    del session  # Kept in the public API for symmetry with refresh_document_periods.
    selected_model = model or load_config().get("TIME_PERIOD_MODEL") or DEFAULT_TIME_PERIOD_MODEL
    periods: list[dict] = []
    chapter_reports: list[dict] = []
    for chapter in _chapters_for_document(doc, chapter_position):
        extracted, report = classify_fragment(chapter["text"][:MAX_FRAGMENT_CHARS], selected_model)
        for position, period in enumerate(extracted):
            periods.append({
                "chapter_position": chapter["position"],
                "position": position,
                **period,
            })
        chapter_reports.append({
            "chapter_position": chapter["position"],
            "chapter_title": chapter["title"],
            "periods": len(extracted),
            **report,
        })
    return {"model": selected_model, "periods": periods, "chapters": chapter_reports}


def refresh_document_periods(session, doc, model: str | None = None, *, chapter_position: int | None = None) -> dict:
    """Replace stored periods for a document, or one explicitly selected chapter."""
    result = extract_document_periods(session, doc, model, chapter_position=chapter_position)
    statement = delete(DocumentTimePeriod).where(DocumentTimePeriod.document_id == doc.id)
    if chapter_position is not None:
        statement = statement.where(DocumentTimePeriod.chapter_position == chapter_position)
    session.execute(statement)
    rows = [
        DocumentTimePeriod(document_id=doc.id, **period)
        for period in result["periods"]
    ]
    session.add_all(rows)
    result["rows"] = rows
    logger.info("time periods doc=%s: classified %d periods", doc.id, len(rows))
    return result
