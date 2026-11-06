"""LLM-assisted classification of a chapter's emotional tone and language register.

Emotion and register are deliberately two separate axes: a text full of joy
written in childish language is emotion "radosny" + register "dziecinny" —
mixing them into one label made the LLM drop the register (see the /read
tone panel feasibility test, 2026-07-17).
"""

import datetime
import json
import logging
import re

from sqlalchemy import delete
from unidecode import unidecode

from library.ai import ai_ask
from library.chapter_fragments import chapter_fragments, merge_fragment_reports
from library.config_loader import load_config
from library.db.models import DocumentTone
from library.llm_usage.report import usage_report
from library.timeline_events import _chapters_for_document

logger = logging.getLogger(__name__)

DEFAULT_TONE_MODEL = "Bielik-11B-v3.0-Instruct"
MAX_FRAGMENT_CHARS = 8_000  # one model call; a longer chapter is split (``chapter_fragments``), never cut
DOMINANT_SENTIMENT_SHARE = 0.7  # share of the text one sentiment needs, else the chapter is "mieszane"
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


def classify_fragment(fragment: str, model: str, *, document_id: int | None = None) -> tuple[dict | None, dict]:
    """Make one LLM call and return the validated tone (or None) with a report."""
    response = ai_ask(
        _tone_prompt(fragment), model=model, temperature=0.1, max_token_count=500,
        operation="tone_classification",
        document_id=document_id,
    )
    candidate = parse_tone_response(response.response_text)
    tone = normalize_tone(candidate) if candidate is not None else None
    return tone, {
        "invalid_json": int(candidate is None),
        "rejected_invalid": int(candidate is not None and tone is None),
        **usage_report(response.usage).as_dict(),
    }


def _split_labels(value: str | None) -> list[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def _top(weights: dict[str, int], limit: int) -> list[str]:
    """Keys by descending weight; equal weights keep the order of first appearance."""
    return sorted(weights, key=lambda key: -weights[key])[:limit]


def merge_tones(weighted: list[tuple[dict, int]]) -> dict | None:
    """One tone for a chapter from the tones of its fragments (weight = fragment length in characters).

    The emotion is the one covering most text; the sentiment is kept when it covers at least
    ``DOMINANT_SENTIMENT_SHARE`` of the text, otherwise it is "mieszane"; the intensity is the highest seen
    (a short outburst still characterises the chapter); secondary emotions and registers are the most frequent
    labels of the other fragments. A single fragment is returned unchanged.
    """
    if not weighted:
        return None
    if len(weighted) == 1:
        return weighted[0][0]

    emotion_weight: dict[str, int] = {}
    for tone, weight in weighted:
        emotion_weight[tone["emotion"]] = emotion_weight.get(tone["emotion"], 0) + weight
    emotion = max(emotion_weight, key=lambda key: emotion_weight[key])  # a tie keeps the earlier fragment

    others: dict[str, int] = {}
    registers: dict[str, int] = {}
    sentiment_weight: dict[str, int] = {}
    for tone, weight in weighted:
        if tone["emotion"] != emotion:
            others[tone["emotion"]] = others.get(tone["emotion"], 0) + weight
        for label in _split_labels(tone.get("secondary_emotions")):
            if label != emotion:
                others[label] = others.get(label, 0) + max(1, weight // 2)
        for label in _split_labels(tone.get("registers")):
            registers[label] = registers.get(label, 0) + weight
        sentiment_weight[tone["sentiment"]] = sentiment_weight.get(tone["sentiment"], 0) + weight

    total = sum(sentiment_weight.values())
    top_sentiment = max(sentiment_weight, key=lambda key: sentiment_weight[key])
    sentiment = top_sentiment if total and sentiment_weight[top_sentiment] / total >= DOMINANT_SENTIMENT_SHARE else "mieszane"
    intensity = max((tone["intensity"] for tone, _ in weighted), key=INTENSITIES.index)
    heaviest = max((item for item in weighted if item[0]["emotion"] == emotion), key=lambda item: item[1])[0]
    return {
        "emotion": emotion,
        "secondary_emotions": ", ".join(_top(others, MAX_SECONDARY_EMOTIONS)) or None,
        "sentiment": sentiment,
        "intensity": intensity,
        "registers": ", ".join(_top(registers, MAX_REGISTERS)) or None,
        "evidence": heaviest.get("evidence"),
    }


def classify_chapter(text: str, model: str, *, document_id: int | None = None) -> tuple[dict | None, dict]:
    """Classify the tone of a WHOLE chapter: one model call per fragment, merged by ``merge_tones``."""
    fragments, skipped = chapter_fragments(text, MAX_FRAGMENT_CHARS)
    weighted: list[tuple[dict, int]] = []
    reports: list[dict] = []
    for fragment in fragments:
        tone, report = classify_fragment(fragment, model, document_id=document_id)
        reports.append(report)
        if tone is not None:
            weighted.append((tone, len(fragment)))
    merged_report = merge_fragment_reports(
        reports, counters=("invalid_json", "rejected_invalid"), fragments=len(fragments), skipped=skipped,
    )
    return merge_tones(weighted), merged_report


def extract_document_tones(session, doc, model: str | None = None, *, chapter_position: int | None = None) -> dict:
    """Classify tone per reader chapter (whole document when it has no chapters)."""
    del session  # Kept in the public API for symmetry with refresh_document_tones.
    selected_model = model or load_config().get("TONE_MODEL") or DEFAULT_TONE_MODEL
    tones: list[dict] = []
    chapter_reports: list[dict] = []
    for chapter in _chapters_for_document(doc, chapter_position):
        tone, report = classify_chapter(chapter["text"], selected_model, document_id=getattr(doc, "id", None))
        if tone is not None:
            tones.append({"chapter_position": chapter["position"], **tone})
        chapter_reports.append({
            "chapter_position": chapter["position"],
            "chapter_title": chapter["title"],
            "tones": int(tone is not None),
            **report,
        })
    return {"model": selected_model, "tones": tones, "chapters": chapter_reports}


def refresh_document_tones(
    session, doc, model: str | None = None, *, chapter_position: int | None = None, keep_previous_on_failure: bool = False,
) -> dict:
    """Replace stored tones for a document, or one explicitly selected chapter.

    Every analysed chapter gets exactly one tone, so an empty result means the model failed (invalid JSON, labels
    outside the closed lists). With ``keep_previous_on_failure`` a single-chapter refresh then leaves the stored tone
    alone instead of deleting it (``kept_previous`` in the result).
    """
    result = extract_document_tones(session, doc, model, chapter_position=chapter_position)
    if keep_previous_on_failure and not result["tones"]:
        result["rows"] = []
        result["kept_previous"] = True
        return result
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
    doc.enrichment_run_at = datetime.datetime.now()
    logger.info("tones doc=%s: classified %d chapters", doc.id, len(rows))
    return result
