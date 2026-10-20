"""LLM-written description of an event entity, grounded in the sentences that mention it.

A reviewer adds an event by hand ("Galanbard 2026") and asks for a description: the sentences of
the document that mention it go to the tagging model (Bielik by default), which may use nothing
else. The result is only a proposal; the REST layer stores it after the reviewer approves it.
"""

import logging
import re

logger = logging.getLogger(__name__)

NO_DESCRIPTION = "BRAK"
MAX_SENTENCES = 4
MAX_SENTENCE_CHARS = 600
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def context_sentences(text: str, forms: list[str], limit: int = MAX_SENTENCES) -> list[str]:
    """Sentences of ``text`` that contain any of ``forms`` (case-insensitive), in text order."""
    needles = [form.strip().casefold() for form in forms if form and form.strip()]
    if not text or not needles:
        return []
    found: list[str] = []
    sentences = _SENTENCE_END.split(text.replace("\n", " "))
    for index, sentence in enumerate(sentences):
        folded = sentence.casefold()
        if any(needle in folded for needle in needles):
            cleaned = sentence.strip()
            # Speech-to-text often ends a sentence early: "...Galanbard 2026. wymierzone w ..." — the
            # continuation starts in lower case and belongs to the same statement.
            following = sentences[index + 1].strip() if index + 1 < len(sentences) else ""
            if following and following[0].islower():
                cleaned = f"{cleaned} {following}"
            cleaned = cleaned[:MAX_SENTENCE_CHARS]
            if cleaned and cleaned not in found:
                found.append(cleaned)
        if len(found) >= limit:
            break
    return found


def describe_event(name: str, sentences: list[str], title: str = "") -> str | None:
    """One or two Polish sentences describing the event, or None when the text does not say enough."""
    from library.ai import ai_ask
    from library.article_tagging import _tagging_model

    if not sentences:
        return None
    fragments = "\n".join(f"- {sentence}" for sentence in sentences)
    prompt = (
        f"Poniżej są zdania z dokumentu, w których pada nazwa wydarzenia „{name}”.\n"
        "Napisz po polsku krótki opis tego wydarzenia (1-2 zdania): czym jest, kto bierze udział, "
        "gdzie i kiedy się odbywa — ale TYLKO jeśli wynika to z poniższych zdań. "
        "Niczego nie dodawaj z własnej wiedzy. Tekst pochodzi czasem z transkrypcji mowy, "
        "więc może zawierać przejęzyczenia. "
        f"Jeśli zdania nie wystarczają do opisu, odpowiedz dokładnie: {NO_DESCRIPTION}\n\n"
        f"TYTUŁ DOKUMENTU: {title}\n\nZDANIA:\n{fragments}"
    )
    try:
        response = ai_ask(prompt, model=_tagging_model(), temperature=0.0, max_token_count=200,
                          operation="event_description")
    except Exception:
        logger.exception("Event description for %r failed", name)
        return None
    description = (response.response_text or "").strip()
    if not description or description.upper().startswith(NO_DESCRIPTION):
        return None
    return description


MAX_CHAPTER_CHARS = 3500
MAX_CUSTOM_PROMPT_CHARS = 16000


def best_chapter(text: str, forms: list[str]) -> tuple[str, str] | None:
    """(title, body) of the chapter that mentions ``forms`` most often, or None when none does.

    Chapters are the ``##`` sections of the document (transcript_chapter_boundaries); a document
    without headings counts as one chapter with an empty title.
    """
    from library.transcript_chapter_boundaries import parse_sections

    needles = [form.strip().casefold() for form in forms if form and form.strip()]
    if not text or not needles:
        return None
    best: tuple[int, str, str] | None = None
    for section in parse_sections(text):
        body = section.body.strip()
        folded = body.casefold()
        mentions = sum(folded.count(needle) for needle in needles)
        if mentions and (best is None or mentions > best[0]):
            best = (mentions, section.heading[3:].strip() if section.heading else "", body)
    return (best[1], best[2]) if best else None


def build_organization_prompt(name: str, chapter_title: str, chapter_text: str, title: str = "") -> str:
    """The exact prompt sent to the model; the chapter is capped at ``MAX_CHAPTER_CHARS``."""
    return (
        f"Poniżej jest rozdział dokumentu, w którym pada nazwa organizacji „{name}”.\n"
        "Napisz po polsku krótki opis tej organizacji (1-2 zdania): czym jest, czym się zajmuje, "
        "w jakim kraju działa — ale TYLKO jeśli wynika to z poniższego rozdziału. "
        "Niczego nie dodawaj z własnej wiedzy. Tekst pochodzi czasem z transkrypcji mowy, "
        "więc może zawierać przejęzyczenia. "
        f"Jeśli rozdział nie wystarcza do opisu, odpowiedz dokładnie: {NO_DESCRIPTION}\n\n"
        f"TYTUŁ DOKUMENTU: {title}\nTYTUŁ ROZDZIAŁU: {chapter_title}\n\nROZDZIAŁ:\n{chapter_text[:MAX_CHAPTER_CHARS]}"
    )


def run_organization_description(prompt: str, model: str | None = None) -> dict:
    """Send ``prompt`` to ``model`` (default: the tagging model) and classify the outcome.

    ``status`` is ``ok``, ``insufficient_context`` (the model answered BRAK or nothing) or ``error``
    (the call failed — kept apart from BRAK so a broken model is not mistaken for thin source text).
    The prompt is never logged.
    """
    import time

    from library.ai import ai_ask
    from library.article_tagging import _tagging_model

    model = model or _tagging_model()
    started = time.monotonic()
    try:
        response = ai_ask(prompt, model=model, temperature=0.0, max_token_count=200,
                          operation="organization_description")
    except Exception as exc:
        logger.error("Organization description failed with model %s: %s", model, type(exc).__name__)
        return {"status": "error", "description": None, "model": model, "error_code": type(exc).__name__,
                "latency_ms": int((time.monotonic() - started) * 1000)}
    latency_ms = int((time.monotonic() - started) * 1000)
    description = (response.response_text or "").strip()
    if not description or description.upper().startswith(NO_DESCRIPTION):
        return {"status": "insufficient_context", "description": None, "model": model, "latency_ms": latency_ms}
    return {"status": "ok", "description": description, "model": model, "latency_ms": latency_ms}


def describe_organization(name: str, chapter_title: str, chapter_text: str, title: str = "") -> str | None:
    """One or two Polish sentences saying what the organization is, or None when nothing usable came back."""
    if not chapter_text.strip():
        return None
    return run_organization_description(build_organization_prompt(name, chapter_title, chapter_text, title))["description"]
