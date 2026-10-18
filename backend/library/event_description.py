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
