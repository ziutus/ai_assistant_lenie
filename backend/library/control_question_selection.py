"""Cheap-LLM (Bielik) router that narrows control questions down to the ones a document answers.

Two-stage pipeline (brainstorming session 2026-07-24): today's `/obsidian-note`
skill fetches the *entire* tag-matched set of control questions and asks the
strong note-writing model to judge which ones are actually answered. This
module is stage 1 — a cheap router that does that judgment call itself, so
the strong model starts from an already-narrowed list. Candidate questions
come from the `control_questions` DB table (imports/import_control_questions.py
— the backend has no runtime access to the Obsidian vault where the question
bank is authored).
"""

import json
import logging
import re

from sqlalchemy import delete, select

from library.ai import ai_ask
from library.config_loader import load_config
from library.db.models import ControlQuestion, DocumentControlAnswer
from library.llm_usage.report import usage_report
from library.timeline_events import _chapters_for_document, _complete_array_prefix

logger = logging.getLogger(__name__)

DEFAULT_CONTROL_QUESTIONS_MODEL = "Bielik-11B-v3.0-Instruct"
MAX_FRAGMENT_CHARS = 8_000
# Keeps the router prompt small even when a document carries many geopolitical tags.
MAX_QUESTIONS_PER_CALL = 40


def load_candidate_questions(session, tags: list[str]) -> list[ControlQuestion]:
    """Active control questions whose tags overlap the document's tags."""
    wanted = {t.strip() for t in tags if t.strip()}
    if not wanted:
        return []
    rows = session.scalars(
        select(ControlQuestion).where(ControlQuestion.active.is_(True)).order_by(ControlQuestion.position),
    ).all()
    matched = [row for row in rows if wanted.intersection((row.tags or "").split(","))]
    return matched[:MAX_QUESTIONS_PER_CALL]


def _selection_prompt(fragment: str, candidates: list[ControlQuestion]) -> str:
    numbered = "\n".join(f"{i}. {q.section_header}" for i, q in enumerate(candidates))
    return f"""Poniżej jest lista ponumerowanych pytań analitycznych oraz fragment artykułu.
Wskaż WYŁĄCZNIE te pytania, na które ten konkretny fragment daje faktyczną, konkretną
odpowiedź (nie ogólnikową) popartą treścią fragmentu — pomiń pytania, których fragment
nie porusza.

PYTANIA:
{numbered}

Zwróć WYŁĄCZNIE poprawny JSON (tablica obiektów; pusta tablica [] jeśli żadne pytanie
nie pasuje). Bądź maksymalnie zwięzły — to ma zmieścić się w limicie odpowiedzi:
[
  {{"index": <numer pytania z listy powyżej>,
    "answer_summary": "JEDNO krótkie zdanie po polsku, maksymalnie ~20 słów",
    "evidence": "krótki cytat, max ~15 słów (opcjonalne, pomiń jeśli zbędne)"}}
]

FRAGMENT:
{fragment}
"""


def _parse_selection_response(raw_response: str) -> tuple[list | None, bool]:
    """Parse the JSON array of selected question indices.

    Recovers complete objects from a truncated array (many verbose selections
    can outrun the response token budget) — same approach as
    library/timeline_events.py's _complete_array_prefix(). Returns
    (payload_or_none, invalid_json) — invalid_json is True whenever the raw
    response needed repair, even if recovery succeeded.
    """
    raw = (raw_response or "").strip()
    fence = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", raw, re.IGNORECASE | re.DOTALL)
    if fence:
        raw = fence.group(1).strip()
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        repaired = _complete_array_prefix(raw)
        try:
            payload = json.loads(repaired) if repaired is not None else None
        except (json.JSONDecodeError, TypeError):
            payload = None
        if payload is None:
            logger.warning("control question router returned invalid JSON that could not be recovered")
            return None, True
        return (payload if isinstance(payload, list) else None), True
    return (payload if isinstance(payload, list) else None), False


def select_fragment(
    fragment: str, candidates: list[ControlQuestion], model: str, *, document_id: int | None = None,
) -> tuple[list[dict], dict]:
    """Make one LLM call selecting which candidate questions this fragment answers.

    Zero candidates short-circuits before any ai_ask() call — this is the
    mechanism that keeps cost at zero for documents with no matching tag.
    """
    if not candidates:
        return [], {"invalid_json": 0, "rejected_invalid": 0, "skipped_no_candidates": 1}

    response = ai_ask(
        _selection_prompt(fragment, candidates), model=model, temperature=0.1, max_token_count=3000,
        operation="control_question_selection",
        document_id=document_id,
    )
    payload, invalid_json = _parse_selection_response(response.response_text)
    selections: list[dict] = []
    rejected = 0
    if payload is not None:
        for item in payload:
            if not isinstance(item, dict):
                rejected += 1
                continue
            index = item.get("index")
            answer_summary = str(item.get("answer_summary") or "").strip()
            if not isinstance(index, int) or isinstance(index, bool) or not (0 <= index < len(candidates)) \
                    or not answer_summary:
                rejected += 1
                continue
            question = candidates[index]
            selections.append({
                "question_id": question.id,
                "question_header": question.section_header,
                "tags": question.tags,
                "answer_summary": answer_summary,
                "evidence": str(item.get("evidence") or "").strip() or None,
            })
    return selections, {
        "invalid_json": int(invalid_json),
        "rejected_invalid": rejected,
        "skipped_no_candidates": 0,
        **usage_report(response.usage).as_dict(),
    }


def extract_document_control_answers(
    session, doc, model: str | None = None, *, chapter_position: int | None = None,
) -> dict:
    """Select control-question answers per reader chapter (whole document when it has no chapters)."""
    selected_model = model or load_config().get("CONTROL_QUESTIONS_MODEL") or DEFAULT_CONTROL_QUESTIONS_MODEL
    doc_tags = [t.strip() for t in (doc.tags or "").split(",") if t.strip()]
    candidates = load_candidate_questions(session, doc_tags)

    answers: list[dict] = []
    chapter_reports: list[dict] = []
    if not candidates:
        return {"model": selected_model, "answers": answers, "chapters": chapter_reports}

    for chapter in _chapters_for_document(doc, chapter_position):
        selections, report = select_fragment(
            chapter["text"][:MAX_FRAGMENT_CHARS], candidates, selected_model,
            document_id=getattr(doc, "id", None),
        )
        for selection in selections:
            answers.append({"chapter_position": chapter["position"], **selection})
        chapter_reports.append({
            "chapter_position": chapter["position"],
            "chapter_title": chapter["title"],
            "answers": len(selections),
            **report,
        })
    return {"model": selected_model, "answers": answers, "chapters": chapter_reports}


def refresh_document_control_answers(
    session, doc, model: str | None = None, *, chapter_position: int | None = None,
) -> dict:
    """Replace stored control-question answers for a document, or one explicitly selected chapter."""
    result = extract_document_control_answers(session, doc, model, chapter_position=chapter_position)
    statement = delete(DocumentControlAnswer).where(DocumentControlAnswer.document_id == doc.id)
    if chapter_position is not None:
        statement = statement.where(DocumentControlAnswer.chapter_position == chapter_position)
    session.execute(statement)
    rows = [
        DocumentControlAnswer(document_id=doc.id, **answer)
        for answer in result["answers"]
    ]
    session.add_all(rows)
    result["rows"] = rows
    logger.info("control questions doc=%s: %d answers", doc.id, len(rows))
    return result
