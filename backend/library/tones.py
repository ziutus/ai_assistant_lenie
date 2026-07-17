"""LLM-assisted classification of a chapter's emotional tone and language register.

Emotion and register are deliberately two separate axes: a text full of joy
written in childish language is emotion "radosny" + register "dziecinny" —
mixing them into one label made the LLM drop the register (see the /read
tone panel feasibility test, 2026-07-17).
"""

import json
import logging
import re

from sqlalchemy import delete
from unidecode import unidecode

from library.ai import ai_ask
from library.config_loader import load_config
from library.db.models import DocumentTone
from library.timeline_events import _chapters_for_document, _response_usage

logger = logging.getLogger(__name__)

DEFAULT_TONE_MODEL = "Bielik-11B-v3.0-Instruct"
MAX_FRAGMENT_CHARS = 8_000
MAX_SECONDARY_EMOTIONS = 2
MAX_REGISTERS = 2

EMOTIONS = ("neutralny", "radosny", "smutny", "gniewny", "alarmistyczny", "podniosły", "refleksyjny")
SENTIMENTS = ("pozytywne", "negatywne", "neutralne", "mieszane")
INTENSITIES = ("niska", "średnia", "wysoka")
REGISTERS = ("formalny", "potoczny", "dziecinny", "wulgarny", "obraźliwy", "ironiczny")

# LLM output arrives with inconsistent diacritics ("podniosly", "srednia") —
# match on the unidecoded, casefolded form and store the canonical spelling.
_EMOTION_LOOKUP = {unidecode(value).casefold(): value for value in EMOTIONS}
_SENTIMENT_LOOKUP = {unidecode(value).casefold(): value for value in SENTIMENTS}
_INTENSITY_LOOKUP = {unidecode(value).casefold(): value for value in INTENSITIES}
_REGISTER_LOOKUP = {unidecode(value).casefold(): value for value in REGISTERS}


def _tone_prompt(fragment: str) -> str:
    return f"""Przeanalizuj poniższy tekst i określ jego ton emocjonalny oraz rejestr językowy.

Zwróć WYŁĄCZNIE poprawny JSON (pojedynczy obiekt):
{{
  "emocja": "dokładnie jedna z: {" | ".join(EMOTIONS)}",
  "emocje_dodatkowe": ["0-{MAX_SECONDARY_EMOTIONS} dodatkowe etykiety z tej samej listy"],
  "nacechowanie": "{" | ".join(SENTIMENTS)}",
  "intensywnosc": "{" | ".join(INTENSITIES)}",
  "rejestry": ["0-{MAX_REGISTERS} z listy: {" | ".join(REGISTERS)}"],
  "uzasadnienie": "jedno zdanie po polsku"
}}

Emocja opisuje, co tekst wyraża; rejestr — jakim językiem jest napisany. Przykład: wesoła relacja
pisana językiem małego dziecka to emocja "radosny" i rejestr "dziecinny". Rzeczowy tekst bez
szczególnego stylu: rejestry []. Rzeczowy reportaż o trudnych wydarzeniach może być emocjonalnie
"neutralny" przy wysokiej intensywności opisywanych treści.

TEKST:
{fragment}
"""


def parse_tone_response(raw_response: str) -> dict | None:
    """Parse the single-object JSON tone answer; None when it cannot be parsed."""
    raw = (raw_response or "").strip()
    fence = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", raw, re.IGNORECASE | re.DOTALL)
    if fence:
        raw = fence.group(1).strip()
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        logger.warning("tone LLM returned invalid JSON")
        return None
    return payload if isinstance(payload, dict) else None


def _canonical(value, lookup: dict[str, str]) -> str | None:
    if not isinstance(value, str):
        return None
    return lookup.get(unidecode(value).casefold().strip())


def _canonical_list(values, lookup: dict[str, str], exclude: set[str], limit: int) -> list[str]:
    if not isinstance(values, list):
        return []
    result: list[str] = []
    for value in values:
        canonical = _canonical(value, lookup)
        if canonical and canonical not in exclude and canonical not in result:
            result.append(canonical)
        if len(result) == limit:
            break
    return result


def normalize_tone(candidate: dict) -> dict | None:
    """Validate one LLM tone answer against the closed label lists."""
    emotion = _canonical(candidate.get("emocja"), _EMOTION_LOOKUP)
    sentiment = _canonical(candidate.get("nacechowanie"), _SENTIMENT_LOOKUP)
    intensity = _canonical(candidate.get("intensywnosc"), _INTENSITY_LOOKUP)
    if emotion is None or sentiment is None or intensity is None:
        return None
    secondary = _canonical_list(
        candidate.get("emocje_dodatkowe"), _EMOTION_LOOKUP, {emotion}, MAX_SECONDARY_EMOTIONS,
    )
    registers = _canonical_list(candidate.get("rejestry"), _REGISTER_LOOKUP, set(), MAX_REGISTERS)
    evidence = str(candidate.get("uzasadnienie") or "").strip() or None
    return {
        "emotion": emotion,
        "secondary_emotions": ", ".join(secondary) or None,
        "sentiment": sentiment,
        "intensity": intensity,
        "registers": ", ".join(registers) or None,
        "evidence": evidence,
    }


def classify_fragment(fragment: str, model: str) -> tuple[dict | None, dict]:
    """Make one LLM call and return the validated tone (or None) with a report."""
    response = ai_ask(_tone_prompt(fragment), model=model, temperature=0.1, max_token_count=500)
    tokens, cost = _response_usage(response)
    candidate = parse_tone_response(response.response_text)
    tone = normalize_tone(candidate) if candidate is not None else None
    return tone, {
        "invalid_json": int(candidate is None),
        "rejected_invalid": int(candidate is not None and tone is None),
        "llm_calls": 1,
        "llm_tokens": tokens,
        "llm_cost": cost,
    }


def extract_document_tones(session, doc, model: str | None = None, *, chapter_position: int | None = None) -> dict:
    """Classify tone per reader chapter (whole document when it has no chapters)."""
    del session  # Kept in the public API for symmetry with refresh_document_tones.
    selected_model = model or load_config().get("TONE_MODEL") or DEFAULT_TONE_MODEL
    tones: list[dict] = []
    chapter_reports: list[dict] = []
    for chapter in _chapters_for_document(doc, chapter_position):
        tone, report = classify_fragment(chapter["text"][:MAX_FRAGMENT_CHARS], selected_model)
        if tone is not None:
            tones.append({"chapter_position": chapter["position"], **tone})
        chapter_reports.append({
            "chapter_position": chapter["position"],
            "chapter_title": chapter["title"],
            "tones": int(tone is not None),
            **report,
        })
    return {"model": selected_model, "tones": tones, "chapters": chapter_reports}


def refresh_document_tones(session, doc, model: str | None = None, *, chapter_position: int | None = None) -> dict:
    """Replace stored tones for a document, or one explicitly selected chapter."""
    result = extract_document_tones(session, doc, model, chapter_position=chapter_position)
    statement = delete(DocumentTone).where(DocumentTone.document_id == doc.id)
    if chapter_position is not None:
        statement = statement.where(DocumentTone.chapter_position == chapter_position)
    session.execute(statement)
    rows = [
        DocumentTone(document_id=doc.id, **tone)
        for tone in result["tones"]
    ]
    session.add_all(rows)
    result["rows"] = rows
    logger.info("tones doc=%s: classified %d chapters", doc.id, len(rows))
    return result
