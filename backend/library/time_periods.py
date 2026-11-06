"""LLM-assisted classification of the historical period a document's content is about."""

import datetime
import json
import logging
import re

from sqlalchemy import delete

from library.ai import ai_ask
from library.chapter_fragments import chapter_fragments, merge_fragment_reports
from library.config_loader import load_config
from library.db.models import DocumentTimePeriod
from library.llm_usage.report import usage_report
from library.timeline_events import _chapters_for_document, _complete_array_prefix
from library.year_normalization import coerce_year

logger = logging.getLogger(__name__)

DEFAULT_TIME_PERIOD_MODEL = "Bielik-11B-v3.0-Instruct"
MAX_FRAGMENT_CHARS = 8_000  # one model call; a longer chapter is split (``chapter_fragments``), never cut
MAX_PERIODS_PER_CHAPTER = 3
_CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}
MIN_YEAR = -10_000
MAX_YEAR = 2_100
_CONFIDENCE_LEVELS = {"high", "medium", "low"}


def _time_period_prompt(fragment: str) -> str:
    return f"""Przeanalizuj poniższy tekst i określ, jakiego okresu czasowego dotyczy jego treść
(o jakim czasie opowiada tekst, a nie kiedy został napisany).

Zwróć WYŁĄCZNIE poprawny JSON: listę od 1 do {MAX_PERIODS_PER_CHAPTER} okresów, główny okres jako pierwszy:
[
  {{"subject_period_label": "krótka nazwa okresu po polsku, np. 'współczesność', 'zimna wojna', 'starożytny Egipt', 'II wojna światowa', 'średniowiecze'",
    "subject_period_start_year": <rok początkowy jako liczba całkowita; lata p.n.e. zapisuj jako liczby ujemne, np. panowanie Ramzesa II zaczęło się w -1279; null tylko gdy nie da się oszacować>,
    "subject_period_end_year": <rok końcowy jako liczba całkowita (p.n.e. ujemnie); dla współczesności użyj bieżącego roku; null tylko gdy nie da się oszacować>,
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


def normalize_period(candidate: dict) -> dict | None:
    """Validate one LLM period candidate; BCE years are negative integers."""
    label = " ".join(str(candidate.get("subject_period_label") or "").split())
    if not label:
        return None
    start = coerce_year(candidate.get("subject_period_start_year"), minimum=MIN_YEAR, maximum=MAX_YEAR)
    end = coerce_year(candidate.get("subject_period_end_year"), minimum=MIN_YEAR, maximum=MAX_YEAR)
    if start is not None and end is not None and start > end:
        start, end = end, start
    confidence = str(candidate.get("confidence") or "").strip().lower()
    if confidence not in _CONFIDENCE_LEVELS:
        confidence = "low"
    evidence = str(candidate.get("evidence") or "").strip() or None
    return {
        "subject_period_label": label[:100],
        "subject_period_start_year": start,
        "subject_period_end_year": end,
        "confidence": confidence,
        "evidence": evidence,
    }


def classify_fragment(fragment: str, model: str, *, document_id: int | None = None) -> tuple[list[dict], dict]:
    """Make one LLM call and retain valid, de-duplicated periods (main period first)."""
    response = ai_ask(
        _time_period_prompt(fragment), model=model, temperature=0.1, max_token_count=800,
        operation="time_period_classification",
        document_id=document_id,
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
        label_key = normalized["subject_period_label"].casefold()
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


def merge_periods(weighted: list[tuple[list[dict], int]]) -> list[dict]:
    """One period list for a chapter from the lists of its fragments (weight = fragment length in characters).

    The same label (case-insensitive) is one period: its years are widened to cover every fragment that named it,
    the best confidence (and the evidence that goes with it) is kept. Periods are ordered by the amount of text
    that names them, so the main period of the chapter comes first, and capped at ``MAX_PERIODS_PER_CHAPTER``.
    A single fragment is returned unchanged.
    """
    if len(weighted) == 1:
        return weighted[0][0]
    merged: dict[str, dict] = {}
    for periods, weight in weighted:
        for period in periods:
            key = period["subject_period_label"].casefold()
            entry = merged.get(key)
            if entry is None:
                merged[key] = {"period": dict(period), "weight": weight, "order": len(merged)}
                continue
            entry["weight"] += weight
            current = entry["period"]
            for field, pick in (("subject_period_start_year", min), ("subject_period_end_year", max)):
                values = [value for value in (current[field], period[field]) if value is not None]
                current[field] = pick(values) if values else None
            if _CONFIDENCE_RANK[period["confidence"]] > _CONFIDENCE_RANK[current["confidence"]]:
                current["confidence"] = period["confidence"]
                current["evidence"] = period["evidence"]
    ranked = sorted(merged.values(), key=lambda entry: (-entry["weight"], entry["order"]))
    return [entry["period"] for entry in ranked[:MAX_PERIODS_PER_CHAPTER]]


def classify_chapter(text: str, model: str, *, document_id: int | None = None) -> tuple[list[dict], dict]:
    """Classify the periods of a WHOLE chapter: one model call per fragment, merged by ``merge_periods``."""
    fragments, skipped = chapter_fragments(text, MAX_FRAGMENT_CHARS)
    weighted: list[tuple[list[dict], int]] = []
    reports: list[dict] = []
    for fragment in fragments:
        extracted, report = classify_fragment(fragment, model, document_id=document_id)
        reports.append(report)
        weighted.append((extracted, len(fragment)))
    merged_report = merge_fragment_reports(
        reports, counters=("rejected_invalid", "invalid_json"), fragments=len(fragments), skipped=skipped,
    )
    return (merge_periods(weighted) if weighted else []), merged_report


def extract_document_periods(session, doc, model: str | None = None, *, chapter_position: int | None = None) -> dict:
    """Classify periods per reader chapter (whole document when it has no chapters)."""
    del session  # Kept in the public API for symmetry with refresh_document_periods.
    selected_model = model or load_config().get("TIME_PERIOD_MODEL") or DEFAULT_TIME_PERIOD_MODEL
    periods: list[dict] = []
    chapter_reports: list[dict] = []
    for chapter in _chapters_for_document(doc, chapter_position):
        extracted, report = classify_chapter(chapter["text"], selected_model, document_id=getattr(doc, "id", None))
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


def refresh_document_periods(
    session, doc, model: str | None = None, *, chapter_position: int | None = None, keep_previous_on_failure: bool = False,
) -> dict:
    """Replace stored periods for a document, or one explicitly selected chapter.

    No period is a legitimate answer for a timeless text, but not when the model's JSON was unusable. With
    ``keep_previous_on_failure`` a single-chapter refresh that found nothing AND had an invalid answer leaves the
    stored periods alone instead of deleting them (``kept_previous`` in the result).
    """
    result = extract_document_periods(session, doc, model, chapter_position=chapter_position)
    failed = any(report.get("invalid_json") for report in result["chapters"])
    if keep_previous_on_failure and not result["periods"] and failed:
        result["rows"] = []
        result["kept_previous"] = True
        return result
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
    doc.enrichment_run_at = datetime.datetime.now()
    logger.info("time periods doc=%s: classified %d periods", doc.id, len(rows))
    return result
