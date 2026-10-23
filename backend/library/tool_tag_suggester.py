"""LLM-proposed tags for a tool radar entry. The model only proposes; nothing is stored here.

The household picks the model in the UI; the choice is kept in ``app_settings`` (``tool_tags_model``). With no
choice the first allowlisted model that is not Bielik applies, because Bielik handled English technical
vocabulary poorly for this task.
"""

import json
import logging
import re

from library import app_settings
from library.entity_description_batch import supports_structured_output
from library.event_description import usage_summary

logger = logging.getLogger(__name__)

TASK = "tool_tags"
SETTING_KEY = "tool_tags_model"
OPERATION = "tool_tag_suggestion"
MAX_SUGGESTIONS = 8
MAX_TOKENS = 300
MAX_VOCABULARY = 60
MAX_DESCRIPTION_CHARS = 1500

# Preferred when nothing was chosen and it is on the allowlist; otherwise the first non-Bielik model.
FALLBACK_MODEL = "gpt-4o-mini"


def default_model(session) -> str | None:
    """The saved choice when it is still allowed, else ``gpt-4o-mini``, else the first non-Bielik model."""
    from library.llm_model_registry import is_selectable, selectable_models

    saved = app_settings.get_setting(session, SETTING_KEY)
    if isinstance(saved, str) and is_selectable(saved, TASK):
        return saved
    ids = [item["id"] for item in selectable_models(TASK)]
    if FALLBACK_MODEL in ids:
        return FALLBACK_MODEL
    return next((model_id for model_id in ids if "bielik" not in model_id.lower()), ids[0] if ids else None)


def response_schema() -> dict:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "tool_tags",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {"tags": {"type": "array", "items": {"type": "string"}}},
                "required": ["tags"],
                "additionalProperties": False,
            },
        },
    }


def build_prompt(name: str, homepage_url: str | None, description: str | None, category: str | None,
                 current_tags: list[str], vocabulary: list[str]) -> str:
    known = ", ".join(vocabulary[:MAX_VOCABULARY]) or "(none yet)"
    return (
        "You label software tools for a personal tool radar so they can be found by what they work with and what "
        "they are for.\n\n"
        f"Tool: {name}\n"
        f"Homepage: {homepage_url or '-'}\n"
        f"Category: {category or '-'}\n"
        f"Description: {(description or '-')[:MAX_DESCRIPTION_CHARS]}\n"
        f"Tags already on this tool: {', '.join(current_tags) or '(none)'}\n"
        f"Tags already used elsewhere on the radar: {known}\n\n"
        f"Propose up to {MAX_SUGGESTIONS} NEW tags. Rules:\n"
        "- lowercase English, one to three words joined by '-', for example docker, kubernetes, sbom, "
        "container-images, supply-chain, cli;\n"
        "- name technologies it works with, the kind of task it does and its main domain, not marketing words;\n"
        "- reuse a tag from the already-used list when it fits exactly, instead of inventing a synonym;\n"
        "- never repeat the tool's own name or tags it already has;\n"
        "- if you are not sure what the tool is, return fewer tags rather than guessing.\n"
        'Answer with JSON only: {"tags": ["..."]}'
    )


def parse_answer(raw: str | None) -> list[str] | None:
    """The tag list from a model answer (fences and surrounding prose tolerated); None when unusable."""
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
    tags = data.get("tags") if isinstance(data, dict) else None
    if not isinstance(tags, list):
        return None
    return [value for value in tags if isinstance(value, str)]


def clean_suggestions(tags: list[str], current_tags: list[str], name: str) -> list[str]:
    """Normalise like the stored tags, drop repeats, existing tags and the tool's own name; cap the count."""
    from library.tool_recommendation_routes import MAX_TAG_LENGTH

    own = "-".join(name.lower().split())
    cleaned: list[str] = []
    for value in tags:
        tag = re.sub(r"[^a-z0-9+#.\-]", "", "-".join(value.strip().lower().split()))
        tag = re.sub(r"-{2,}", "-", tag).strip("-")
        if not tag or len(tag) > MAX_TAG_LENGTH or tag == own or tag in current_tags or tag in cleaned:
            continue
        cleaned.append(tag)
    return cleaned[:MAX_SUGGESTIONS]


def suggest_tags(item, vocabulary: list[str], model: str) -> dict:
    """Ask ``model`` for tags of the radar entry ``item``.

    Returns ``{"status": "ok"|"error", "tags": [...], "model", "tokens", "cost", "currency"}``; an unusable
    answer is ``error`` with ``error_code`` so the UI can say so instead of showing an empty list as a result.
    """
    from library.ai import ai_ask

    current = list(item.tags or [])
    prompt = build_prompt(item.name, item.homepage_url, item.description, item.category, current, vocabulary)
    try:
        response = ai_ask(
            prompt, model=model, temperature=0.0, max_token_count=MAX_TOKENS,
            response_format=response_schema() if supports_structured_output(model) else None,
            operation=OPERATION,
        )
    except Exception as exc:
        logger.error("Tool tag suggestion failed with model %s: %s", model, type(exc).__name__)
        return {"status": "error", "error_code": type(exc).__name__, "tags": [], "model": model,
                "tokens": None, "cost": None, "currency": None}
    parsed = parse_answer(getattr(response, "response_text", None))
    usage = usage_summary(response)
    if parsed is None:
        return {"status": "error", "error_code": "unparseable_answer", "tags": [], "model": model, **usage}
    return {"status": "ok", "tags": clean_suggestions(parsed, current, item.name), "model": model, **usage}
