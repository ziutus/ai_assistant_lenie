"""LLM-assisted proposal of geopolitical events (and their effect on country relations) from a document.

ADR-033. Everything this module writes is ``proposed``: a reader confirms it in the queue.
The model may answer "no relevant event" and may omit the ``relation`` of any event; a
relation is only kept when both countries are participants of the same event, the quote is
found verbatim in the document and the score is in range. One event never yields a
confidence above ``SINGLE_EVENT_CONFIDENCE_CAP``.
"""

import datetime
import json
import logging
import re

from library import app_settings, prompt_templates
from library.ai import ai_ask
from library.country_gazetteer import detect_countries
from library.db.models import Document
from library.llm_usage.report import combine_usage_reports, usage_report
from library.geopolitics_service import (
    AXES,
    ROLES,
    GeopoliticsError,
    create_event,
    propose_assessment,
    normalize_text,
    parse_event_date,
)

logger = logging.getLogger(__name__)

TASK = "geopolitics"  # model allowlist of library/llm_model_registry.py
SETTING_KEY = "geopolitics_model"  # household default in app_settings
DEFAULT_MODEL = "Bielik-11B-v3.0-Instruct"
VARIANT = "event_extraction"  # (task, variant) of the prompt in library/prompt_templates.py
MAX_FRAGMENT_CHARS = 10_000
MAX_FRAGMENTS = 4
MAX_EVENTS_PER_FRAGMENT = 6


def default_model(session) -> str | None:
    """The saved household choice while it is still allowed, else Bielik, else the first available model."""
    from library.llm_model_registry import is_selectable, selectable_models

    saved = app_settings.get_setting(session, SETTING_KEY)
    if isinstance(saved, str) and is_selectable(saved, TASK):
        return saved
    if is_selectable(DEFAULT_MODEL, TASK):
        return DEFAULT_MODEL
    ids = [item["id"] for item in selectable_models(TASK) if item["available"]]
    return ids[0] if ids else None


def split_fragments(text: str, size: int = MAX_FRAGMENT_CHARS, limit: int = MAX_FRAGMENTS) -> list[str]:
    """Cut at paragraph boundaries; the first ``limit`` fragments only (cost cap)."""
    fragments: list[str] = []
    current = ""
    for paragraph in re.split(r"\n\s*\n", text):
        if current and len(current) + len(paragraph) + 2 > size:
            fragments.append(current)
            current = ""
            if len(fragments) >= limit:
                return fragments
        while len(paragraph) > size:  # a single oversize paragraph
            fragments.append(paragraph[:size])
            paragraph = paragraph[size:]
            if len(fragments) >= limit:
                return fragments
        current = f"{current}\n\n{paragraph}" if current else paragraph
    if current and len(fragments) < limit:
        fragments.append(current)
    return fragments


def analysis_input(session, doc) -> tuple[str, list[str]]:
    """The text the model reads and the countries it may name.

    The text is the one NER uses (``entity_text.document_ner_text``): a transcript's advertisement, noise and
    source chapters are left out, so a sponsor read-out cannot become an "event". The countries come from a copy
    with the channel glossary applied ("państwo z gwiazdką" = Izrael); the prompt and the quote check keep the
    original text, so a quote stays verbatim in the stored document.
    """
    from library.entity_service import apply_channel_glossary_text
    from library.entity_text import document_ner_text

    text = document_ner_text(doc)
    repaired = apply_channel_glossary_text(session, doc.id, text) if text.strip() else text
    return text, [entry.slug for entry in detect_countries(repaired)]


def prompt_variables(fragment: str, slugs: list[str], published: str | None) -> dict:
    """The closed set of variables a prompt template may use (``prompt_templates.VARIABLES``)."""
    return {
        "fragment": fragment,
        "countries": ", ".join(slugs) if slugs else "(brak kandydatów)",
        "reference_date": published or "nieznana",
        "axes": "; ".join(f"{key} ({value['label']})" for key, value in AXES.items()),
        "max_events": MAX_EVENTS_PER_FRAGMENT,
    }


def build_prompt(fragment: str, slugs: list[str], published: str | None, template=None) -> str:
    """Render the prompt: ``template`` (a resolved ``prompt_templates`` row) or the built-in text."""
    template = template or prompt_templates.builtin(prompt_templates.TASK_GEOPOLITICS, VARIANT)
    return prompt_templates.render(template.user, **prompt_variables(fragment, slugs, published))


def preview_variables(session, document_id: int | None) -> tuple[dict, int | None]:
    """Variables for the `/prompt-templates` preview: the first fragment of a real document, else a sample."""
    doc = Document.get_by_id(session, document_id) if isinstance(document_id, int) else None
    text, slugs = analysis_input(session, doc) if doc is not None else ("", [])
    if not text.strip():
        sample = "Przykładowy fragment: Rząd A wprowadził sankcje wobec kraju B."
        return prompt_variables(sample, ["polska", "niemcy"], "2026-01-01"), None
    reference = _reference_date(doc)
    fragment = (split_fragments(text, limit=1) or [text])[0]
    return prompt_variables(fragment, slugs, reference.isoformat() if reference else None), doc.id


def parse_response(raw: str) -> list[dict]:
    """Tolerate code fences and prose around the JSON array; anything unusable gives []."""
    text = (raw or "").strip()
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end <= start:
        return []
    try:
        data = json.loads(text[start : end + 1])
    except (ValueError, TypeError):
        return []
    return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []


def _quote_in_text(quote: str, haystack: str) -> bool:
    needle = normalize_text(quote).casefold()
    return len(needle) >= 12 and needle in haystack


def detect_for_document(session, doc_id: int, *, model: str | None = None, user_id: int | None = None) -> dict:
    doc = Document.get_by_id(session, doc_id)
    if doc is None:
        raise GeopoliticsError("Document not found", 404)
    text, slugs = analysis_input(session, doc)
    if not text.strip():
        raise GeopoliticsError(
            "Document has no text content to analyse (all chapters are advertisement, noise or sources)"
        )
    model = model or default_model(session) or DEFAULT_MODEL
    usage_reports: list[dict] = []
    template = prompt_templates.get_active(session, prompt_templates.TASK_GEOPOLITICS, VARIANT)
    haystack = normalize_text(text).casefold()
    reference = _reference_date(doc)
    published_text = reference.isoformat() if reference else None

    summary = {
        "document_id": doc_id,
        "model": model,
        "prompt_version": template.label,
        "fragments": 0,
        "candidates": 0,
        "events_created": 0,
        "events_existing": 0,
        "assessments_proposed": 0,
        "assessments_merged": 0,
        "usage": None,
        "dated_from_reference": 0,
        "rejected": {"quote_not_found": 0, "bad_date": 0, "bad_participants": 0, "bad_relation": 0},
        "event_ids": [],
        "assessment_ids": [],
    }
    if not slugs:
        return summary

    for fragment in split_fragments(text):
        summary["fragments"] += 1
        try:
            prompt = build_prompt(fragment, slugs, published_text, template)
        except Exception as exc:  # a saved template is validated, but the built-in/DB text may still fail to render
            raise GeopoliticsError(f"Szablon promptu {template.label} nie renderuje się: {exc}") from exc
        extra = (
            {
                "system_prompt": prompt_templates.render(
                    template.system, **prompt_variables(fragment, slugs, published_text)
                )
            }
            if template.system
            else {}
        )
        response = ai_ask(
            prompt,
            model=model,
            temperature=0.1,
            max_token_count=3000,
            operation="geopolitics_event_extraction",
            document_id=doc_id,
            **extra,
        )
        usage_reports.append(usage_report(getattr(response, "usage", None)).as_dict())
        summary["usage"] = combine_usage_reports(usage_reports)
        for item in parse_response(response.response_text)[:MAX_EVENTS_PER_FRAGMENT]:
            summary["candidates"] += 1
            _store_candidate(session, doc_id, item, haystack, model, user_id, summary, reference, template.label)
    return summary


def _reference_date(doc) -> datetime.date | None:
    """When the text was written: its publication date, else the day it was ingested."""
    for name in ("published_on", "ingested_at"):
        value = getattr(doc, name, None)
        if isinstance(value, datetime.datetime):
            return value.date()
        if isinstance(value, datetime.date):
            return value
    return None


def _resolve_date(item, reference) -> tuple[object, str | None, str | None]:
    """The model's own date when it parses; else the article date, noted in the description.

    Returns (date, precision override, note). Without a reference date an unusable date
    stays unusable (the caller rejects the candidate).
    """
    try:
        parse_event_date(item.get("date"))
        return item.get("date"), None, None
    except GeopoliticsError:
        pass
    if reference is None:
        raise GeopoliticsError("event date could not be determined")
    phrase = normalize_text(str(item.get("date_text") or item.get("date") or ""))
    note = f"Data w tekście: „{phrase}”; przyjęto datę artykułu." if phrase else "Przyjęto datę artykułu."
    return reference, "month", note


def _store_candidate(
    session, doc_id, item, haystack, model, user_id, summary, reference=None, prompt_version=None
) -> None:
    rejected = summary["rejected"]
    quote = normalize_text(str(item.get("quote") or ""))
    if not _quote_in_text(quote, haystack):
        rejected["quote_not_found"] += 1
        return
    try:
        event_date, precision, date_note = _resolve_date(item, reference)
    except GeopoliticsError:
        rejected["bad_date"] += 1
        return
    if date_note:
        summary["dated_from_reference"] += 1
        item = {**item, "description": normalize_text(f"{item.get('description') or ''} {date_note}")}
    participants = []
    for entry in item.get("participants") or []:
        if isinstance(entry, dict) and entry.get("role") in ROLES and isinstance(entry.get("country"), str):
            participants.append((entry["country"], entry["role"]))
    if not participants:
        rejected["bad_participants"] += 1
        return
    try:
        event, created = create_event(
            session,
            title=str(item.get("title") or ""),
            description=item.get("description"),
            event_date=event_date,
            date_precision=precision,
            participants=participants,
            source={"document_id": doc_id, "quote": quote},
            detection_method="llm",
            model=model,
            prompt_version=prompt_version,
            user_id=user_id,
        )
    except GeopoliticsError as exc:
        logger.info("geopolitics: candidate rejected: %s", exc.message)
        rejected["bad_participants"] += 1
        return
    summary["event_ids"].append(event.id)
    if not created:
        summary["events_existing"] += 1
        return
    summary["events_created"] += 1

    relation = item.get("relation")
    if not isinstance(relation, dict):
        return
    in_event = {slug for slug, _ in participants}
    if relation.get("from") not in in_event or relation.get("to") not in in_event:
        rejected["bad_relation"] += 1
        return
    try:
        assessment, assessment_created = propose_assessment(
            session,
            from_country=relation["from"],
            to_country=relation["to"],
            axis=relation.get("axis"),
            score=relation.get("score"),
            confidence=relation.get("confidence"),
            valid_from=event.event_date,
            rationale=relation.get("rationale"),
            event_ids=[event.id],
            detection_method="llm",
            model=model,
            prompt_version=prompt_version,
            user_id=user_id,
        )
    except GeopoliticsError as exc:
        logger.info("geopolitics: relation rejected: %s", exc.message)
        rejected["bad_relation"] += 1
        return
    if assessment_created:
        summary["assessments_proposed"] += 1
    else:
        summary["assessments_merged"] += 1
    if assessment.id not in summary["assessment_ids"]:
        summary["assessment_ids"].append(assessment.id)
