"""Passages that stand out from a chapter's tone, or carry its substance, found ON REQUEST.

A single tone per chapter hides two things. A malicious remark can drag the whole chapter's tone down, and a neutral
sentence inside such a remark may be the most valuable one in the text. This module asks a model for the passages
themselves, as verbatim quotes, so they can be highlighted in the reader and judged by a human:

* ``outlier`` - a passage whose tone clearly differs from the rest (``OUTLIER_LABELS``: malicious, insulting, ironic…);
* ``key`` - the passage that states the substance (the problem, the claim), whatever its tone; it may sit INSIDE an
  outlier passage.

Nothing here runs by itself: no pipeline, enrichment stage or import calls it. A quote the model invents is dropped
(it must occur in the analysed text), and a reviewer settles each passage (``proposed`` / ``confirmed`` /
``rejected``); a settled passage survives a re-detection. ``recompute_core_tone`` classifies the chapter again
without its outlier passages, so the overall tone is not set by them.
"""

from __future__ import annotations

import json
import logging
import re

from sqlalchemy import delete, select
from unidecode import unidecode

from library.ai import ai_ask
from library.chapter_fragments import chapter_fragments, merge_fragment_reports
from library.db.models import DocumentTone, DocumentToneSpan
from library.llm_usage.report import usage_report
from library.timeline_events import _chapters_for_document, _complete_array_prefix, _quote_is_grounded
from library.tones import classify_chapter

logger = logging.getLogger(__name__)

OUTLIER_LABELS = ("złośliwy", "obraźliwy", "ironiczny", "wulgarny", "agresywny", "pogardliwy", "manipulacyjny")
KEY_LABEL = "kluczowy"
ROLES = ("outlier", "key")
STATUSES = ("proposed", "confirmed", "rejected")

MAX_FRAGMENT_CHARS = 8_000  # one model call; a longer chapter is read in fragments
MAX_KEY_PER_FRAGMENT = 1
MAX_KEY_PER_CHAPTER = 5
MAX_OUTLIERS_PER_FRAGMENT = 5
MIN_QUOTE_CHARS = 15
MAX_QUOTE_CHARS = 500
MAX_NOTE_CHARS = 300
# Below this many characters left after cutting out the outliers there is nothing worth classifying.
MIN_CORE_TEXT_CHARS = 200

_OUTLIER_LOOKUP = {unidecode(label).casefold(): label for label in OUTLIER_LABELS}
_ROLE_LOOKUP = {
    "odstaje": "outlier", "odstajacy": "outlier", "outlier": "outlier",
    "kluczowy": "key", "klucz": "key", "key": "key",
}


def _span_prompt(fragment: str) -> str:
    return f"""Przeanalizuj poniższy fragment tekstu (artykułu albo wypowiedzi z nagrania) i wskaż w nim KRÓTKIE
fragmenty dwojakiego rodzaju. Ocena całego tekstu jednym tonem zaciera te fragmenty, a one są najważniejsze.

1. "odstaje" - fragment, którego ton wyraźnie odbiega od reszty: {" | ".join(OUTLIER_LABELS)}.
   To NIE jest zwykła krytyczna opinia o temacie ani emocjonalny, ale rzeczowy opis. Szukaj docinków, kpiny,
   obelg, pogardy wobec osób, prób manipulowania czytelnikiem. Maksymalnie {MAX_OUTLIERS_PER_FRAGMENT} fragmentów.
2. "kluczowy" - najwyżej {MAX_KEY_PER_FRAGMENT} zdanie (lub dwa sąsiednie), które najlepiej oddaje sedno: opisuje
   problem, główną tezę albo najważniejszy fakt, bez względu na ton. Może leżeć wewnątrz fragmentu "odstaje" -
   wtedy zwróć je osobno, jako własny wpis. Pole "waga": 1-3 (3 = bez tego zdania tekst traci sens).

Zwróć WYŁĄCZNIE poprawny JSON: listę obiektów (pustą [], jeśli nic się nie kwalifikuje):
[
  {{"rola": "odstaje" albo "kluczowy",
    "etykieta": "dla odstaje: dokładnie jedna z listy powyżej; dla kluczowy: kluczowy",
    "cytat": "DOSŁOWNY cytat z tekstu, od {MIN_QUOTE_CHARS} do {MAX_QUOTE_CHARS} znaków, nic nie zmieniaj ani nie skracaj w środku",
    "uzasadnienie": "jedno zdanie po polsku",
    "waga": 1-3 tylko dla kluczowy}}
]

Cytat musi występować w tekście słowo w słowo. Nie wymyślaj fragmentów.

TEKST:
{fragment}
"""


def parse_spans_response(raw_response: str) -> tuple[list[dict], bool]:
    """Parse the model's list of passages; the flag tells that the JSON was invalid (a prefix may be recovered)."""
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
            logger.warning("tone span LLM returned invalid JSON that could not be recovered")
            return [], True
    if isinstance(payload, dict):
        payload = payload.get("fragmenty", payload.get("spans", payload.get("items", [])))
    if not isinstance(payload, list):
        return [], invalid_json
    return [item for item in payload if isinstance(item, dict)], invalid_json


def locate_quote(quote: str, text: str) -> str | None:
    """The quote exactly as it stands in ``text`` (so the reader can find it), or None when it is not there.

    Exact occurrence first; then the same words separated by any whitespace (the model often joins lines); then
    the typography-tolerant check used for events - the quote is then kept as the model wrote it and the reader tints
    the whole paragraph instead of marking the words.
    """
    quote = quote.strip()
    if not quote:
        return None
    if quote in text:
        return quote
    words = quote.split()
    if len(words) >= 2:
        match = re.search(r"\s+".join(re.escape(word) for word in words), text)
        if match and "\n\n" not in match.group(0):
            return match.group(0)
    return quote if _quote_is_grounded(quote, text) else None


def normalize_span(candidate: dict, text: str) -> tuple[dict | None, str | None]:
    """Validate one model candidate against the closed lists and the text; ``(span, None)`` or ``(None, reason)``."""
    role = _ROLE_LOOKUP.get(unidecode(str(candidate.get("rola") or "")).casefold().strip())
    if role is None:
        return None, "invalid"
    if role == "outlier":
        label = _OUTLIER_LOOKUP.get(unidecode(str(candidate.get("etykieta") or "")).casefold().strip())
        if label is None:
            return None, "invalid"
    else:
        label = KEY_LABEL
    quote = str(candidate.get("cytat") or "").strip()
    if len(quote) < MIN_QUOTE_CHARS or len(quote) > MAX_QUOTE_CHARS:
        return None, "invalid"
    located = locate_quote(quote, text)
    if located is None:
        return None, "no_quote"
    importance = None
    if role == "key":
        try:
            importance = min(3, max(1, int(candidate.get("waga"))))
        except (TypeError, ValueError):
            importance = 2
    note = " ".join(str(candidate.get("uzasadnienie") or "").split())[:MAX_NOTE_CHARS] or None
    return {"role": role, "label": label, "quote": located, "note": note, "importance": importance}, None


def detect_in_fragment(fragment: str, model: str, *, document_id: int | None = None) -> tuple[list[dict], dict]:
    """One model call for one fragment: the validated passages and a report (rejections, usage)."""
    response = ai_ask(
        _span_prompt(fragment), model=model, temperature=0.1, max_token_count=1500,
        operation="tone_span_detection", document_id=document_id,
    )
    candidates, invalid_json = parse_spans_response(response.response_text)
    spans: list[dict] = []
    rejected = {"rejected_no_quote": 0, "rejected_invalid": 0}
    keys = outliers = 0
    for candidate in candidates:
        span, reason = normalize_span(candidate, fragment)
        if span is None:
            rejected["rejected_no_quote" if reason == "no_quote" else "rejected_invalid"] += 1
            continue
        if span["role"] == "key":
            if keys >= MAX_KEY_PER_FRAGMENT:
                continue
            keys += 1
        else:
            if outliers >= MAX_OUTLIERS_PER_FRAGMENT:
                continue
            outliers += 1
        spans.append(span)
    return spans, {"invalid_json": int(invalid_json), **rejected, **usage_report(response.usage).as_dict()}


def _quote_key(quote: str) -> str:
    return " ".join(quote.split()).casefold()


def select_spans(spans: list[dict]) -> list[dict]:
    """Drop repeats (same role and words) and keep the heaviest ``MAX_KEY_PER_CHAPTER`` key passages."""
    seen: set[tuple[str, str]] = set()
    unique: list[dict] = []
    for span in spans:
        marker = (span["role"], _quote_key(span["quote"]))
        if marker in seen:
            continue
        seen.add(marker)
        unique.append(span)
    keys = [span for span in unique if span["role"] == "key"]
    if len(keys) > MAX_KEY_PER_CHAPTER:
        heaviest = sorted(keys, key=lambda span: -(span["importance"] or 0))[:MAX_KEY_PER_CHAPTER]
        unique = [span for span in unique if span["role"] != "key" or any(span is kept for kept in heaviest)]
    return unique


def detect_spans(doc, model: str, *, chapter_position: int | None = None) -> dict:
    """Find the passages of one chapter (or of the whole document when ``chapter_position`` is None).

    Returns ``{"model", "spans": [...with chapter_position...], "chapters": [report per chapter]}``; nothing is stored.
    """
    document_id = getattr(doc, "id", None)
    spans: list[dict] = []
    chapter_reports: list[dict] = []
    for chapter in _chapters_for_document(doc, chapter_position):
        fragments, skipped = chapter_fragments(chapter["text"], MAX_FRAGMENT_CHARS)
        found: list[dict] = []
        reports: list[dict] = []
        for fragment in fragments:
            fragment_spans, report = detect_in_fragment(fragment, model, document_id=document_id)
            found.extend(fragment_spans)
            reports.append(report)
        chosen = select_spans(found)
        spans.extend({"chapter_position": chapter["position"], **span} for span in chosen)
        chapter_reports.append({
            "chapter_position": chapter["position"],
            "chapter_title": chapter["title"],
            "spans": len(chosen),
            **merge_fragment_reports(
                reports, counters=("invalid_json", "rejected_no_quote", "rejected_invalid"),
                fragments=len(fragments), skipped=skipped,
            ),
        })
    return {"model": model, "spans": spans, "chapters": chapter_reports}


def span_to_dict(row: DocumentToneSpan) -> dict:
    return {
        "id": row.id,
        "chapter_position": row.chapter_position,
        "role": row.role,
        "label": row.label,
        "quote": row.quote,
        "note": row.note,
        "importance": row.importance,
        "status": row.status,
        "model": row.model,
    }


def refresh_document_tone_spans(session, doc, model: str, *, chapter_position: int | None = None) -> dict:
    """Detect and store the passages of one chapter (or the whole document), keeping what a reviewer settled.

    Earlier ``proposed`` rows of the scope are replaced; ``confirmed`` / ``rejected`` rows stay, and a newly found
    passage identical to one of them is not added again (a rejected passage must not come back as a proposal).
    ``result["all"]`` is every stored passage of the scope, in text order of detection.
    """
    result = detect_spans(doc, model, chapter_position=chapter_position)
    scope = [DocumentToneSpan.document_id == doc.id]
    if chapter_position is not None:
        scope.append(DocumentToneSpan.chapter_position == chapter_position)
    session.execute(delete(DocumentToneSpan).where(*scope, DocumentToneSpan.status == "proposed"))
    settled = session.execute(select(DocumentToneSpan).where(*scope)).scalars().all()
    taken = {(row.chapter_position, row.role, _quote_key(row.quote)) for row in settled}
    rows: list[DocumentToneSpan] = []
    for span in result["spans"]:
        marker = (span["chapter_position"], span["role"], _quote_key(span["quote"]))
        if marker in taken:
            continue
        taken.add(marker)
        rows.append(DocumentToneSpan(document_id=doc.id, model=model, **span))
    session.add_all(rows)
    result["rows"] = rows
    result["all"] = list(settled) + rows
    logger.info("tone spans doc=%s: %d new, %d settled kept", doc.id, len(rows), len(settled))
    return result


def _remove_quotes(text: str, quotes: list[str]) -> tuple[str, int]:
    """``text`` without the quoted passages, and how many were found."""
    removed = 0
    for quote in quotes:
        if quote in text:
            text = text.replace(quote, " ", 1)
            removed += 1
            continue
        words = quote.split()
        if len(words) >= 2:
            match = re.search(r"\s+".join(re.escape(word) for word in words), text)
            if match:
                text = text[:match.start()] + " " + text[match.end():]
                removed += 1
    return text, removed


def recompute_core_tone(session, doc, model: str, *, chapter_position: int | None = None) -> dict:
    """Classify the chapter's tone again WITHOUT its outlier passages and store it as ``core_tone``.

    Uses the ``proposed`` and ``confirmed`` outliers (a rejected one is, by the reviewer's decision, not an outlier).
    Raises ``ValueError`` with a reason code when there is nothing to recompute: ``no_outliers``,
    ``no_tone`` (the chapter has no stored tone to attach it to), ``text_too_short``, ``failed`` (unusable answer).
    """
    chapter = _chapters_for_document(doc, chapter_position)[0]
    outliers = session.execute(select(DocumentToneSpan).where(
        DocumentToneSpan.document_id == doc.id, DocumentToneSpan.role == "outlier",
        DocumentToneSpan.status != "rejected",
        *([DocumentToneSpan.chapter_position == chapter_position] if chapter_position is not None else []),
    )).scalars().all()
    if not outliers:
        raise ValueError("no_outliers")
    tone_row = session.execute(select(DocumentTone).where(
        DocumentTone.document_id == doc.id,
        DocumentTone.chapter_position == chapter_position if chapter_position is not None
        else DocumentTone.chapter_position.is_(None),
    )).scalars().first()
    if tone_row is None:
        raise ValueError("no_tone")
    remaining, removed = _remove_quotes(chapter["text"], [row.quote for row in outliers])
    if removed == 0:
        raise ValueError("no_outliers")
    if len(remaining.strip()) < MIN_CORE_TEXT_CHARS:
        raise ValueError("text_too_short")
    tone, report = classify_chapter(remaining, model, document_id=getattr(doc, "id", None))
    if tone is None:
        raise ValueError("failed")
    tone_row.core_tone = {**tone, "excluded": removed, "model": model}
    return {"model": model, "core_tone": tone_row.core_tone, "report": report}
