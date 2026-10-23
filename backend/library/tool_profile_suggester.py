"""LLM-proposed description, category and tags for a tool radar entry in ONE request. The model only proposes; nothing is
stored here.

Many radar descriptions are one line copied from an awesome list ("JupyterLab computational environment.") and
some categories are too broad ("AI"). The model is asked to use what it already knows about the tool, together
with the public facts the radar has (name, links, GitHub description and topics) and the categories already in
use, so it prefers an existing category and narrows a broad one only when a more specific one fits. It may also
say it does not know the tool; then the description stays empty rather than invented. Tags are asked for in the
same request (the context - name, links, GitHub facts, categories and tags in use - is sent and paid for once
instead of once per field).

The model is the same household choice as for tag suggestions (``tool_tag_suggester``), so an OpenRouter model
such as ``openrouter/google/gemini-2.5-flash-lite`` is picked once in the UI and billed through OpenRouter.
"""

import json
import logging
import re

from library import tool_tag_suggester
from library.entity_description_batch import supports_structured_output
from library.event_description import usage_summary

logger = logging.getLogger(__name__)

OPERATION = "tool_profile_suggestion"
MAX_TOKENS = 600
MAX_TAG_VOCABULARY = 60
MAX_CATEGORIES = 60
MAX_DESCRIPTION_CHARS = 1500
MAX_PROPOSED_DESCRIPTION = 600
MAX_CATEGORY_LENGTH = 60
CONFIDENCE = ("known", "partial", "unknown")


def response_schema() -> dict:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "tool_profile",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "description": {"type": "string"},
                    "category": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "confidence": {"type": "string", "enum": list(CONFIDENCE)},
                },
                "required": ["description", "category", "tags", "confidence"],
                "additionalProperties": False,
            },
        },
    }


def build_prompt(name: str, homepage_url: str | None, links: list[dict], description: str | None, category: str | None,
                 tags: list[str], github: dict | None, categories: list[tuple[str, int]],
                 tag_vocabulary: list[str] | None = None) -> str:
    github = github or {}
    about = ""
    if github.get("description") or github.get("topics"):
        about = (f"GitHub description: {(github.get('description') or '-')[:MAX_DESCRIPTION_CHARS]}\n"
                 f"GitHub topics: {', '.join(github.get('topics') or []) or '-'}\n")
    other_links = ", ".join(link["url"] for link in links if link.get("url")) or "-"
    known = ", ".join(f"{label} ({count})" for label, count in categories[:MAX_CATEGORIES]) or "(none yet)"
    known_tags = ", ".join((tag_vocabulary or [])[:MAX_TAG_VOCABULARY]) or "(none yet)"
    return (
        "You help keep a personal radar of software tools. For the tool below, write a short description, choose "
        "its category and propose tags. Use what you already know about this tool as well as the facts given; the facts can be thin "
        "or wrong, and the current description is often a one-line copy from a list.\n\n"
        f"Tool: {name}\n"
        f"Homepage: {homepage_url or '-'}\n"
        f"Other links: {other_links}\n"
        f"Current category: {category or '-'}\n"
        f"Current description: {(description or '-')[:MAX_DESCRIPTION_CHARS]}\n"
        f"{about}"
        f"Tags already on this tool: {', '.join(tags) or '(none)'}\n"
        f"Tags already used elsewhere on the radar: {known_tags}\n"
        f"Categories already used on the radar (with the number of tools): {known}\n\n"
        "Answer with four fields:\n"
        f"- description: one or two plain sentences IN POLISH (at most {MAX_PROPOSED_DESCRIPTION} characters) saying what "
        "the tool is and what it is used for, concrete and without marketing words;\n"
        "- category: one short English label in CamelCase like the existing ones (MediaManagement, FileSharing, "
        "KnowledgeBase). Reuse an existing category when it fits the tool precisely. A very broad existing category "
        "(for example AI or Tools) should be narrowed: choose a more specific existing one, or propose a new one "
        "only when no existing category fits. If the current category is already right, repeat it exactly;\n"
        f"- tags: up to {tool_tag_suggester.MAX_SUGGESTIONS} NEW lowercase English tags, one to three words joined by '-' "
        "(docker, kubernetes, sbom, container-images, cli), naming technologies it works with, the kind of task and its "
        "main domain. Reuse a tag from the already-used list when it fits exactly, never repeat the tool's own name or "
        "tags it already has; fewer tags is better than guessing;\n"
        "- confidence: known = you know this tool well; partial = you recognise it but not the details; "
        "unknown = you do not recognise it.\n"
        "If confidence is unknown, return an empty description, the current category and no tags. Never invent features.\n"
        'Answer with JSON only: {"description": "...", "category": "...", "tags": ["..."], "confidence": "known"}'
    )


def parse_answer(raw: str | None) -> dict | None:
    """The three fields of a model answer (fences and surrounding prose tolerated); None when unusable."""
    if not raw:
        return None
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("description"), str) or not isinstance(data.get("category"), str):
        return None
    confidence = data.get("confidence")
    tags = data.get("tags")
    return {
        "description": data["description"],
        "category": data["category"],
        "tags": [value for value in tags if isinstance(value, str)] if isinstance(tags, list) else [],
        "confidence": confidence if confidence in CONFIDENCE else "partial",
    }


def category_key(value: str | None) -> str:
    """Fold spellings such as ``DecisionModels`` and ``decision-models`` into one key (same rule as the peers view)."""
    return "".join(char for char in (value or "").lower() if char.isalnum())


def normalise_category(value: str) -> str:
    """``data science`` / ``data-science`` -> ``DataScience``; other characters are dropped, long values cut."""
    words = [word for word in re.split(r"[^A-Za-z0-9]+", value.strip()) if word]
    return "".join(word[:1].upper() + word[1:] for word in words)[:MAX_CATEGORY_LENGTH]


def clean_profile(parsed: dict, current_category: str | None, categories: list[tuple[str, int]],
                  current_tags: list[str] | None = None, name: str = "") -> dict:
    """Shape a parsed answer for the UI: an existing spelling of the category when there is one, a flag for a new one."""
    confidence = parsed["confidence"]
    description = "" if confidence == "unknown" else re.sub(r"\s+", " ", parsed["description"]).strip()[:MAX_PROPOSED_DESCRIPTION]
    proposed = normalise_category(parsed["category"])
    existing = {category_key(label): label for label, _count in categories}
    category = existing.get(category_key(proposed), proposed)
    return {
        "description": description,
        "category": category or None,
        "category_is_new": bool(category) and category_key(category) not in existing,
        "category_changed": bool(category) and category_key(category) != category_key(current_category),
        "tags": [] if confidence == "unknown" else tool_tag_suggester.clean_suggestions(parsed["tags"], current_tags or [], name),
        "confidence": confidence,
    }


def suggest_profile(item, github: dict | None, categories: list[tuple[str, int]], tag_vocabulary: list[str],
                    model: str) -> dict:
    """Ask ``model`` once for a description, category and tags of the radar entry ``item``.

    Returns ``{"status": "ok"|"error", ..., "model", "tokens", "cost", "currency"}``; an unusable answer is ``error``
    with ``error_code`` so the UI can say so instead of showing an empty proposal as a result.
    """
    from library.ai import ai_ask

    prompt = build_prompt(
        item.name, item.homepage_url, list(item.links or []), item.description, item.category, list(item.tags or []),
        github, categories, tag_vocabulary,
    )
    try:
        response = ai_ask(
            prompt, model=model, temperature=0.0, max_token_count=MAX_TOKENS,
            response_format=response_schema() if supports_structured_output(model) else None,
            operation=OPERATION,
        )
    except Exception as exc:
        logger.error("Tool profile suggestion failed with model %s: %s", model, type(exc).__name__)
        return {"status": "error", "error_code": type(exc).__name__, "model": model,
                "tokens": None, "cost": None, "currency": None}
    parsed = parse_answer(getattr(response, "response_text", None))
    usage = usage_summary(response)
    if parsed is None:
        return {"status": "error", "error_code": "unparseable_answer", "model": model, **usage}
    return {"status": "ok", **clean_profile(parsed, item.category, categories, list(item.tags or []), item.name),
            "model": model, **usage}
