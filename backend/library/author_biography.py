"""Detection and review of trailing article-author biographies."""

import datetime
import json
import logging
import re

from sqlalchemy import select

from library.db.models import DocumentPerson, Person

logger = logging.getLogger(__name__)

BIO_SIGNALS_RE = re.compile(
    r"\b(jest|by\w*|prac\w*|zacz\w*|zajm\w*|specjaliz\w*|"
    r"dziennikar\w*|autor\w*|uko\w*|redakcj\w*|studiach)\b",
    re.IGNORECASE,
)


def extract_trailing_author_biography(text: str, author: str | None) -> tuple[str, str | None]:
    """Return (article body, trailing author block).

    Detection is deliberately conservative: the known author name must occur
    near the beginning of a paragraph in the final 35% of the document and
    biographical language must occur in that paragraph or one of the next four.
    Portals commonly split the byline, role and biography into separate
    paragraphs. The whole trailing block is returned so footer artifacts can
    be classified as SZUM together with the biography.
    """
    author = (author or "").strip()
    if not text or len(author.split()) < 2:
        return text, None

    paragraphs = list(re.finditer(r"\S(?:.*?\S)?(?=\n\s*\n|\Z)", text, re.DOTALL))
    lower_bound = int(len(text) * 0.65)
    author_re = re.compile(re.escape(author), re.IGNORECASE)
    for index in range(len(paragraphs) - 1, -1, -1):
        paragraph = paragraphs[index]
        value = paragraph.group().strip()
        if paragraph.start() < lower_bound:
            break
        name_match = author_re.search(value)
        if not name_match or name_match.start() > 80:
            continue

        # Compact biographies already contain the author and biographical
        # language in one paragraph. Preserve the historical behavior and do
        # not absorb an unrelated source/provenance label that follows it.
        if len(value) > 80 and BIO_SIGNALS_RE.search(value):
            return text[:paragraph.start()].rstrip(), value

        # WP/o2 and similar portals often render e.g. "Jan Kowalski,
        # Dziennikarz" separately from the actual biography. Limit the lookup
        # window so an ordinary author mention cannot consume a distant footer.
        bio_window = "\n\n".join(
            item.group().strip() for item in paragraphs[index:index + 5]
        )
        if BIO_SIGNALS_RE.search(bio_window):
            return text[:paragraph.start()].rstrip(), text[paragraph.start():].strip()
    return text, None


def _json_object(raw: str) -> dict:
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ValueError("LLM response contains no JSON object")
    value = json.loads(match.group())
    if not isinstance(value, dict):
        raise ValueError("LLM response is not a JSON object")
    return value


def _evaluate_biography(person: Person, excerpt: str, model: str) -> dict:
    from library.chunk_llm_analysis import call_model

    if not (person.description or "").strip():
        prompt = f"""Utwórz zwięzły, faktograficzny opis osoby na podstawie notki źródłowej.
Nie dopowiadaj faktów. Zwróć wyłącznie JSON:
{{"description": "opis w 1-3 zdaniach"}}

Osoba: {person.canonical_name}
Notka źródłowa:
{excerpt}"""
        raw, _ = call_model(prompt, model, max_tokens=350, operation="author_biography_extract")
        result = _json_object(raw)
        description = str(result.get("description") or "").strip()
        if not description:
            raise ValueError("LLM returned an empty description")
        return {"decision": "auto_applied", "proposed_description": description}

    prompt = f"""Porównaj nową notkę biograficzną z obecnym opisem osoby.
Oceń fakty, nie podobieństwo brzmienia. Zwróć wyłącznie JSON:
{{"decision": "no_new_information|new_information|conflicting_information",
  "new_facts": [], "conflicts": [], "proposed_description": null, "reason": "krótko"}}
Pole proposed_description uzupełnij kompletnym scalonym opisem tylko przy nowych lub sprzecznych informacjach.
Nie dopowiadaj faktów.

Osoba: {person.canonical_name}
Obecny opis: {person.description}
Nowa notka źródłowa:
{excerpt}"""
    raw, _ = call_model(prompt, model, max_tokens=600, operation="author_biography_merge")
    result = _json_object(raw)
    allowed = {"no_new_information", "new_information", "conflicting_information"}
    if result.get("decision") not in allowed:
        raise ValueError("LLM returned an unsupported decision")
    return result


def process_author_biography(session, doc, excerpt: str, model: str) -> dict:
    """Attach an author biography to its person and evaluate it with the LLM."""
    from library.person_registry import find_by_alias

    author = (doc.byline or "").strip()
    person = find_by_alias(session, author)
    if person is None:
        person = Person(canonical_name=author)
        session.add(person)
        session.flush()

    link = session.execute(select(DocumentPerson).where(
        DocumentPerson.document_id == doc.id,
        DocumentPerson.person_id == person.id,
    )).scalars().first()
    if link is None:
        link = DocumentPerson(
            document_id=doc.id, person_id=person.id, raw_mention=author,
            confidence="alias_matched", role="author",
        )
        session.add(link)

    link.role = "author"
    link.source_excerpt = excerpt
    try:
        result = _evaluate_biography(person, excerpt, model)
        decision = result["decision"]
        if decision == "auto_applied":
            person.description = result["proposed_description"]
            link.bio_review_status = "auto_applied"
        elif decision == "no_new_information":
            link.bio_review_status = "no_new_information"
        elif decision == "new_information":
            link.bio_review_status = "needs_review"
        else:
            link.bio_review_status = "conflict"
        link.bio_review_result = result
    except Exception as exc:
        logger.exception("author biography evaluation failed for document %s", doc.id)
        link.bio_review_status = "needs_review"
        link.bio_review_result = {"decision": "evaluation_failed", "reason": str(exc)}
    return {"person_id": person.id, "status": link.bio_review_status}


def list_biography_review(session) -> list[dict]:
    rows = session.scalars(select(DocumentPerson).where(
        DocumentPerson.bio_review_status.in_(("needs_review", "conflict"))
    ).order_by(DocumentPerson.created_at)).all()
    return [{
        "link_id": row.id,
        "document_id": row.document_id,
        "document_title": row.document.title if row.document else None,
        "person_id": row.person_id,
        "canonical_name": row.person.canonical_name,
        "current_description": row.person.description,
        "source_excerpt": row.source_excerpt,
        "status": row.bio_review_status,
        "result": row.bio_review_result,
    } for row in rows]


def decide_biography_review(link: DocumentPerson, action: str) -> dict:
    if link.bio_review_status not in ("needs_review", "conflict"):
        raise ValueError("Biography is not awaiting review")
    if action == "approve":
        proposed = (link.bio_review_result or {}).get("proposed_description")
        if not proposed:
            raise ValueError("Review has no proposed description")
        link.person.description = proposed
        link.bio_review_status = "approved"
    elif action == "reject":
        link.bio_review_status = "rejected"
    else:
        raise ValueError("action must be approve or reject")
    link.bio_reviewed_at = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    return {"link_id": link.id, "status": link.bio_review_status, "person_id": link.person_id}
