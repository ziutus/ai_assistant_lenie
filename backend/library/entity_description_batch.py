"""Group descriptions of the organizations and persons a chapter mentions, from one prompt and one quotation.

A reviewer opens a chapter on ``/ner/:id/:chapter``; the organizations and persons of that chapter that have
no description yet are sent to the model together with the chapter text ONCE, and the model answers with one
JSON object. Nothing is stored here: the REST layer returns proposals, the reviewer approves them and the
UI saves them through ``PATCH /organizations/<id>`` / ``PATCH /persons/<id>``.

Entities are addressed by short ids (``o1``, ``p2``) instead of their names, so the answer never depends on the
model repeating a name exactly (Polish inflection, speech-to-text slips). The model may use nothing but the
chapter; an entity the chapter does not describe is answered with ``null``.
"""

import json
import logging
import re
from dataclasses import dataclass
from decimal import Decimal

from library.event_description import MAX_CHAPTER_CHARS, usage_summary

logger = logging.getLogger(__name__)

MAX_ENTITIES_PER_CALL = 6
TOKENS_PER_ENTITY = 120
TOKENS_OVERHEAD = 100
MAX_DESCRIPTION_CHARS = 400
NO_DESCRIPTION = "BRAK"
OPERATION = "entity_description_batch"


@dataclass(frozen=True)
class Candidate:
    """One organization or person of the chapter that still needs a description."""

    key: str  # "o1" / "p3" — what the model sees and answers with
    kind: str  # "organization" | "person"
    entity_id: int | None  # document_entities.id of the chapter item
    registry_id: int  # organizations.id / persons.id — where the approved text is saved
    name: str
    mentions: int


def candidates_for_chapter(chapter_entities: dict) -> list[Candidate]:
    """Organizations and persons of a chapter (``filter_entities_to_text`` output) without a registry description.

    Only entities resolved to the registry qualify, because that is where the description is stored; countries
    are skipped (they have their own pipeline); one registry entry counts once even when several entity rows
    (spelling variants) point to it. The most mentioned come first.
    """
    found: list[Candidate] = []
    seen: set[tuple[str, int]] = set()
    organizations = sorted(chapter_entities.get("orgName") or [], key=lambda item: -(item.get("count") or 0))
    persons = sorted(chapter_entities.get("persName") or [], key=lambda item: -(item.get("count") or 0))
    for item in organizations:
        registry_id = item.get("organization_id")
        if (registry_id is None or item.get("is_country") or (item.get("organization_description") or "").strip()
                or ("organization", registry_id) in seen):
            continue
        seen.add(("organization", registry_id))
        found.append(Candidate(f"o{len([c for c in found if c.kind == 'organization']) + 1}", "organization",
                               item.get("id"), registry_id, item.get("text") or "", item.get("count") or 0))
    for item in persons:
        registry_id = item.get("person_id")
        if registry_id is None or (item.get("person_description") or "").strip() or ("person", registry_id) in seen:
            continue
        seen.add(("person", registry_id))
        found.append(Candidate(f"p{len([c for c in found if c.kind == 'person']) + 1}", "person",
                               item.get("id"), registry_id, item.get("canonical_name") or item.get("text") or "",
                               item.get("count") or 0))
    return found


def response_schema(batch: list[Candidate]) -> dict:
    """JSON Schema forcing exactly one string-or-null answer per candidate key."""
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "entity_descriptions",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {candidate.key: {"type": ["string", "null"]} for candidate in batch},
                "required": [candidate.key for candidate in batch],
                "additionalProperties": False,
            },
        },
    }


def build_prompt(batch: list[Candidate], chapter_title: str, chapter_text: str, title: str = "") -> str:
    """The exact prompt sent to the model; the chapter is capped at ``MAX_CHAPTER_CHARS``."""
    organizations = [c for c in batch if c.kind == "organization"]
    persons = [c for c in batch if c.kind == "person"]
    lines = []
    if organizations:
        lines.append("ORGANIZACJE:\n" + "\n".join(f"[{c.key}] {c.name}" for c in organizations))
    if persons:
        lines.append("OSOBY:\n" + "\n".join(f"[{c.key}] {c.name}" for c in persons))
    keys = ", ".join(c.key for c in batch)
    return (
        "Poniżej jest rozdział dokumentu oraz lista organizacji i osób, które w nim występują.\n"
        "Napisz po polsku krótki opis (1-2 zdania) każdej pozycji: czym jest, czym się zajmuje, w jakim "
        "kraju działa (organizacja) albo kim jest i jaką pełni rolę (osoba) — ale TYLKO jeśli wynika to "
        "z podanego rozdziału. Niczego nie dodawaj z własnej wiedzy. Tekst pochodzi czasem z transkrypcji "
        "mowy, więc może zawierać przejęzyczenia.\n"
        f"Odpowiedz wyłącznie obiektem JSON z kluczami {keys}: wartością jest opis albo null, gdy rozdział "
        "nie wystarcza do opisu danej pozycji.\n\n"
        + "\n\n".join(lines)
        + f"\n\nTYTUŁ DOKUMENTU: {title}\nTYTUŁ ROZDZIAŁU: {chapter_title}\n\nROZDZIAŁ:\n{chapter_text[:MAX_CHAPTER_CHARS]}"
    )


def parse_answer(raw: str | None, batch: list[Candidate]) -> dict[str, str | None] | None:
    """``{key: description | None}`` for the requested keys, or None when the answer is not usable JSON.

    Keys the model invented are ignored; a missing key counts as "no description"; ``null``, an empty string,
    ``BRAK`` and non-strings all mean the chapter was not enough. Descriptions are trimmed and capped.
    """
    text = (raw or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(text[start:end + 1])
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    answers: dict[str, str | None] = {}
    for candidate in batch:
        value = data.get(candidate.key)
        description = value.strip() if isinstance(value, str) else ""
        if (not description or description.upper().startswith(NO_DESCRIPTION)
                or _echoes_name(description, candidate.name)):
            answers[candidate.key] = None
        else:
            answers[candidate.key] = description[:MAX_DESCRIPTION_CHARS]
    return answers


def _echoes_name(description: str, name: str) -> bool:
    """True for a "description" that only repeats the name or is a single word (a small model's way to say nothing)."""
    plain = re.sub(r"[\W_]+", " ", description.casefold()).strip()
    return len(plain.split()) < 2 or plain == re.sub(r"[\W_]+", " ", name.casefold()).strip()


def supports_structured_output(model: str) -> bool:
    """Whether a JSON-schema ``response_format`` may be sent to ``model`` (checked against what is known)."""
    from library.ai import SHERLOCK_MODELS

    if model in SHERLOCK_MODELS:
        return True
    if model.startswith("openrouter/"):
        from library.api.openrouter.openrouter_catalog import get_model_info

        info = get_model_info(model.removeprefix("openrouter/"))
        return bool(info and info.supports_structured_outputs)
    return False


def max_tokens_for(batch_size: int, model: str) -> int:
    """Answer budget for ``batch_size`` entities, capped by the model's own output limit when the registry knows it."""
    budget = TOKENS_OVERHEAD + TOKENS_PER_ENTITY * batch_size
    try:
        from library.llm_model_registry import model_details

        details = model_details(model)
    except Exception:
        details = None
    limit = (details or {}).get("max_output_tokens")
    return min(budget, limit) if isinstance(limit, int) and limit > 0 else budget


def _call_model(prompt: str, batch: list[Candidate], model: str):
    from library.ai import ai_ask

    return ai_ask(
        prompt, model=model, temperature=0.0, max_token_count=max_tokens_for(len(batch), model),
        response_format=response_schema(batch) if supports_structured_output(model) else None,
        operation=OPERATION,
    )


def describe_batch(batch: list[Candidate], chapter_title: str, chapter_text: str, title: str, model: str) -> dict:
    """One model call for ``batch``; an unusable answer splits the batch in halves and retries each half.

    Returns ``{"answers": {key: description | None}, "errors": {key: error_code}, "calls": [usage, ...]}``.
    """
    prompt = build_prompt(batch, chapter_title, chapter_text, title)
    try:
        response = _call_model(prompt, batch, model)
    except Exception as exc:
        logger.error("Entity descriptions failed with model %s: %s", model, type(exc).__name__)
        return {"answers": {}, "errors": {c.key: type(exc).__name__ for c in batch}, "calls": []}
    call = usage_summary(response)
    answers = parse_answer(getattr(response, "response_text", None), batch)
    if answers is not None:
        return {"answers": answers, "errors": {}, "calls": [call]}
    if len(batch) == 1:
        return {"answers": {}, "errors": {batch[0].key: "UnparseableAnswer"}, "calls": [call]}
    middle = len(batch) // 2
    first = describe_batch(batch[:middle], chapter_title, chapter_text, title, model)
    second = describe_batch(batch[middle:], chapter_title, chapter_text, title, model)
    return {"answers": {**first["answers"], **second["answers"]}, "errors": {**first["errors"], **second["errors"]},
            "calls": [call, *first["calls"], *second["calls"]]}


def describe_candidates(candidates: list[Candidate], chapter_title: str, chapter_text: str, title: str = "",
                        model: str | None = None) -> dict:
    """Proposals for every candidate, ``MAX_ENTITIES_PER_CALL`` per model call.

    Each proposal: the candidate fields plus ``status`` (``ok`` / ``insufficient_context`` / ``error``),
    ``description`` and ``error_code``. ``usage`` sums tokens and cost of all calls (``None`` when unknown).
    """
    from library.article_tagging import _tagging_model

    model = model or _tagging_model()
    proposals: list[dict] = []
    calls: list[dict] = []
    for start in range(0, len(candidates), MAX_ENTITIES_PER_CALL):
        batch = candidates[start:start + MAX_ENTITIES_PER_CALL]
        result = describe_batch(batch, chapter_title, chapter_text, title, model)
        calls.extend(result["calls"])
        for candidate in batch:
            description = result["answers"].get(candidate.key)
            error_code = result["errors"].get(candidate.key)
            status = "error" if error_code else ("ok" if description else "insufficient_context")
            proposals.append({
                "key": candidate.key, "kind": candidate.kind, "entity_id": candidate.entity_id,
                "registry_id": candidate.registry_id, "name": candidate.name, "mentions": candidate.mentions,
                "status": status, "description": description, "error_code": error_code,
            })
    return {"model": model, "proposals": proposals, "usage": _sum_usage(calls), "model_calls": len(calls)}


def _sum_usage(calls: list[dict]) -> dict:
    tokens = [call.get("tokens") for call in calls]
    costs = [call.get("cost") for call in calls]
    currencies = {call.get("currency") for call in calls if call.get("cost") is not None}
    total_cost = None
    if calls and all(cost is not None for cost in costs) and len(currencies) == 1:
        total_cost = str(sum((Decimal(cost) for cost in costs), Decimal(0)))
    return {
        "tokens": sum(tokens) if calls and all(t is not None for t in tokens) else None,
        "cost": total_cost, "currency": currencies.pop() if total_cost is not None else None,
    }
