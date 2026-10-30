"""Catalog suggestions and feed-only new-topic proposals with a household model choice."""

import hashlib
import json
import re
from datetime import datetime, timezone

from sqlalchemy import select
from unidecode import unidecode

from library.ai import ai_ask
from library import app_settings
from library.llm_model_registry import is_selectable
from library.entity_description_batch import supports_structured_output
from library.config_loader import load_config
from library.db.models import (
    ContentGroup,
    ContentGroupSuggestion,
    ContentGroupSuggestionRun,
    Document,
    DocumentGroupMembership,
    FeedItem,
    FeedItemGroupMembership,
    Job,
    PromptTemplate,
)
from library.content_group_service import render_catalog_tree, topic_ancestors
from library.job_queue import enqueue
from library import prompt_templates

PROMPT_VERSION = "content-groups-v1"
FEED_PROMPT_VERSION = "content-groups-v2"
MAX_INPUT_CHARS = 6000
MAX_COMMENT_CHARS = 1000  # the reader's own note about a feed item; kept whole, the item text is cut to make room
MAX_SUGGESTIONS = 5
TASK = "content_group_suggestion"
SETTING_KEY = "content_group_suggestion_model"
FEED_DEFAULT_MODEL = "openrouter/mistralai/mistral-small-3.2-24b-instruct"


def default_model(session) -> str:
    saved = app_settings.get_setting(session, SETTING_KEY)
    if isinstance(saved, str) and is_selectable(saved, TASK):
        return saved
    return FEED_DEFAULT_MODEL if is_selectable(FEED_DEFAULT_MODEL, TASK) else suggestion_model()


def _config(name: str, fallback: str | None = None):
    try:
        return load_config().get(name) or fallback
    except Exception:
        return fallback


def suggestion_model() -> str:
    return _config("CONTENT_GROUP_SUGGESTION_MODEL") or _config("TAGGING_MODEL") or "Bielik-11B-v3.0-Instruct"


def active_topic_catalog(session) -> list[dict]:
    # parent_id and description only when set: a catalog without them keeps the exact JSON (and prompt hash) it always had
    return [
        {
            "id": group.id, "name": group.name,
            **({"parent_id": group.parent_id} if group.parent_id is not None else {}),
            **({"description": group.description} if group.description else {}),
        }
        for group in session.scalars(
            select(ContentGroup).where(ContentGroup.kind == "topic", ContentGroup.archived_at.is_(None)).order_by(ContentGroup.name)
        ).all()
    ]


def drop_ancestor_suggestions(candidate_group_ids, existing_group_ids, catalog: list[dict]) -> set[int]:
    """Candidates that must not be suggested because a more specific topic already covers the material.

    A candidate is dropped when it is an ancestor of another candidate of the same answer or of a topic the target
    already has ("Informatyka" never gets proposed next to "Web development").
    """
    candidates = list(candidate_group_ids)
    specific = set(candidates) | set(existing_group_ids)
    return {
        group_id for group_id in candidates
        if any(group_id in topic_ancestors(catalog, other) for other in specific if other != group_id)
    }


def _existing_group_ids(session, target_type: str, target_id: int) -> list[int]:
    membership, key = (FeedItemGroupMembership, "feed_item_id") if target_type == "feed_item" else (DocumentGroupMembership, "document_id")
    return list(session.scalars(
        select(membership.group_id)
        .join(ContentGroup, ContentGroup.id == membership.group_id)
        .where(getattr(membership, key) == target_id, ContentGroup.archived_at.is_(None))
    ).all())


def target_text(target) -> str:
    if isinstance(target, FeedItem):
        raw = target.raw_payload or {}
        safe_raw = {key: value for key, value in raw.items() if key in {"title", "summary", "description", "content", "author"}}
        text = f"TYTUŁ: {target.title or ''}\n\nSUMMARY: {target.summary or ''}\n\nPAYLOAD:\n{json.dumps(safe_raw, ensure_ascii=False, default=str)}"
        note = (getattr(target, "review_note", None) or "").strip()[:MAX_COMMENT_CHARS]
        if not note:
            return text[:MAX_INPUT_CHARS]
        block = f"\n\nKOMENTARZ UŻYTKOWNIKA (co go zainteresowało i co dalej): {note}"
        return text[:MAX_INPUT_CHARS - len(block)] + block
    synthesis = getattr(target, "text_md", None) or getattr(target, "text", None) or ""
    return f"TYTUŁ: {target.title or ''}\n\nSUMMARY: {target.summary or ''}\n\nTREŚĆ:\n{synthesis}"[:MAX_INPUT_CHARS]


def input_hash(text: str, catalog: list[dict], target_type: str = "document", prompt_label: str | None = None) -> str:
    version = prompt_label or (FEED_PROMPT_VERSION if target_type == "feed_item" else PROMPT_VERSION)
    payload = json.dumps({"text": text, "prompt_version": version, "catalog": catalog}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def response_schema(catalog: list[dict], allow_new_topics: bool = False) -> dict:
    result = {
        "type": "json_schema",
        "json_schema": {
            "name": "content_group_suggestions",
            "strict": True,
            "schema": {
                "type": "object",
                "required": ["suggestions", "no_match"],
                "properties": {
                    "suggestions": {"type": "array", "items": {"type": "object", "properties": {
                        "group_id": {"type": "integer", "enum": [item["id"] for item in catalog]},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        "reason": {"type": "string", "maxLength": 300},
                    }, "required": ["group_id", "confidence", "reason"], "additionalProperties": False}},
                    "no_match": {"type": "boolean"},
                },
                "additionalProperties": False,
            },
        },
    }
    if allow_new_topics:
        schema = result["json_schema"]["schema"]
        if not catalog:
            schema["properties"]["suggestions"]["maxItems"] = 0
            del schema["properties"]["suggestions"]["items"]["properties"]["group_id"]["enum"]
        schema["required"].append("new_topics")
        schema["properties"]["new_topics"] = {
            "type": "array", "maxItems": 3, "items": {
                "type": "object", "additionalProperties": False,
                "required": ["name", "confidence", "reason"],
                "properties": {
                    "name": {"type": "string", "maxLength": 60},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "reason": {"type": "string", "maxLength": 200},
                },
            },
        }
    return result


MAX_NEW_TOPICS = 3
MAX_DROPPED_NEW_TOPICS = 10


def triage_new_topics(proposals, catalog: list[dict]) -> tuple[list[dict], list[dict]]:
    """Split the model's new-topic proposals into the kept ones and the dropped ones with the reason for each.

    A dropped proposal carries ``dropped_because``: ``invalid`` (no usable name), ``bad_confidence``, ``low_confidence``
    (below ``CONTENT_GROUP_SUGGESTION_MIN_CONFIDENCE``), ``duplicate_of_catalog`` (an existing topic has that name),
    ``duplicate_in_answer`` or ``over_limit`` (more than three kept).
    """
    in_catalog = {unidecode(" ".join(item["name"].split())).casefold() for item in catalog}
    threshold = float(_config("CONTENT_GROUP_SUGGESTION_MIN_CONFIDENCE", "0.60"))
    kept, dropped, kept_folded = [], [], set()
    for item in proposals if isinstance(proposals, list) else []:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            continue
        name = " ".join(item["name"].split())[:60].strip()
        folded = unidecode(name).casefold()
        entry = {"name": name, "reason": str(item.get("reason", ""))[:200]}
        try:
            confidence = float(item.get("confidence"))
        except (TypeError, ValueError):
            dropped.append({**entry, "confidence": None, "dropped_because": "bad_confidence"})
            continue
        entry["confidence"] = confidence
        if not name:
            dropped.append({**entry, "dropped_because": "invalid"})
        elif folded in in_catalog:
            dropped.append({**entry, "dropped_because": "duplicate_of_catalog"})
        elif folded in kept_folded:
            dropped.append({**entry, "dropped_because": "duplicate_in_answer"})
        elif not threshold <= confidence <= 1:
            dropped.append({**entry, "dropped_because": "low_confidence"})
        elif len(kept) >= MAX_NEW_TOPICS:
            dropped.append({**entry, "dropped_because": "over_limit"})
        else:
            kept_folded.add(folded)
            kept.append(entry)
    return kept, dropped[:MAX_DROPPED_NEW_TOPICS]


def sanitize_new_topics(proposals, catalog: list[dict]) -> list[dict]:
    return triage_new_topics(proposals, catalog)[0]


def _parse_result(raw: str | None) -> dict:
    value = (raw or "").strip()
    value = re.sub(r"^```(?:json)?\s*|\s*```$", "", value, flags=re.I | re.S)
    try:
        result = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {"suggestions": [], "no_match": True}
    return result if isinstance(result, dict) else {"suggestions": [], "no_match": True}


def resolve_template(session, target_type: str, template_id: int | None = None) -> "prompt_templates.ResolvedTemplate":
    """The template a new run will use: the explicitly chosen version, else the active one for the target type."""
    if template_id is None:
        return prompt_templates.get_active(session, prompt_templates.TASK_CONTENT_GROUPS, target_type)
    row = session.get(PromptTemplate, template_id)
    if row is None or row.task != prompt_templates.TASK_CONTENT_GROUPS or row.variant != target_type:
        raise ValueError("unknown prompt template")
    return prompt_templates.get_by_id(session, template_id, prompt_templates.TASK_CONTENT_GROUPS, target_type)


def request_suggestions(session, target_type: str, target_id: int, *, user_id: int | None = None, force: bool = False, model: str | None = None, template_id: int | None = None) -> tuple[Job | None, ContentGroupSuggestionRun]:
    if target_type not in {"feed_item", "document"}:
        raise ValueError("invalid suggestion target")
    if target_type == "feed_item":
        if model is not None and (not isinstance(model, str) or not is_selectable(model, TASK)):
            raise ValueError("unknown model")
        model = model if model is not None else default_model(session)
    else:
        model = suggestion_model()
    target = session.get(FeedItem if target_type == "feed_item" else Document, target_id)
    if target is None:
        raise LookupError("target not found")
    catalog = active_topic_catalog(session)
    text = target_text(target)
    target_column = ContentGroupSuggestionRun.feed_item_id if target_type == "feed_item" else ContentGroupSuggestionRun.document_id
    active = session.scalar(select(ContentGroupSuggestionRun).where(target_column == target_id, ContentGroupSuggestionRun.status.in_(["queued", "running"])).order_by(ContentGroupSuggestionRun.id.desc()))
    if active is not None:
        return (session.get(Job, active.job_id) if active.job_id else None), active
    template = resolve_template(session, target_type, template_id)
    digest = input_hash(text, catalog, target_type, template.label)
    if not force:
        completed = session.scalar(select(ContentGroupSuggestionRun).where(target_column == target_id, ContentGroupSuggestionRun.input_hash == digest, ContentGroupSuggestionRun.model == model, ContentGroupSuggestionRun.status == "completed").order_by(ContentGroupSuggestionRun.id.desc()))
        if completed is not None:
            return None, completed
    run = ContentGroupSuggestionRun(
        feed_item_id=target_id if target_type == "feed_item" else None,
        document_id=target_id if target_type == "document" else None,
        status="queued", model=model, prompt_version=template.label, prompt_template_id=template.id,
        input_hash=digest, catalog_snapshot=catalog,
    )
    session.add(run)
    session.flush()
    if not catalog and target_type == "document":
        run.status = "completed"
        run.completed_at = datetime.now(timezone.utc)
        session.commit()
        return None, run
    job = enqueue(session, "content_group_suggest", {f"{target_type}_id": target_id, "run_id": run.id, "input_hash": digest}, idempotency_key=f"content_group_suggest:{target_type}:{target_id}:{digest}:{run.id}", user_id=user_id)
    run.job_id = job.id
    session.commit()
    return job, run


def _auto_apply_suggestion(session, document_id: int, group_id: int, suggestion: "ContentGroupSuggestion") -> None:
    """Auto-accept a high-confidence document suggestion (no human in the loop).

    Only ever called for document targets (never feed items, which stay a
    curated manual-review workflow). ``decided_by_user_id`` is deliberately
    left ``None`` -- that is the marker distinguishing a Bielik auto-decision
    from a human's ``decide_suggestion(action="accept")`` call, so the UI can
    show "why did this get classified here" for either case.
    """
    group = session.scalar(
        select(ContentGroup).where(ContentGroup.id == group_id, ContentGroup.kind == "topic", ContentGroup.archived_at.is_(None))
    )
    if group is None:
        return
    existing = session.scalar(
        select(DocumentGroupMembership).where(
            DocumentGroupMembership.document_id == document_id, DocumentGroupMembership.group_id == group_id
        )
    )
    if existing is not None:
        return
    session.add(DocumentGroupMembership(document_id=document_id, group_id=group_id, source="llm_suggestion", source_suggestion_id=suggestion.id))
    suggestion.status = "accepted"
    suggestion.membership_created = True
    suggestion.decided_at = datetime.now(timezone.utc)


def build_request(target_type: str, target, model: str, catalog: list[dict], template: "prompt_templates.ResolvedTemplate") -> dict:
    """Everything sent to the model for one target: the single place both the job and the UI preview use.

    ``system_sent`` is False when the provider path would drop the system message; ``response_format`` is the
    JSON-schema argument (None for a model that gets the schema inside the prompt text instead).
    """
    allow_new_topics = target_type == "feed_item"
    schema = response_schema(catalog, allow_new_topics=allow_new_topics)
    structured = target_type == "document" or supports_structured_output(model)
    variables = {
        "catalog": json.dumps(catalog, ensure_ascii=False),
        "material": target_text(target),
        "schema": "" if structured else json.dumps(schema["json_schema"]["schema"], ensure_ascii=False),
        "catalog_tree": render_catalog_tree(catalog),
    }
    system = prompt_templates.render(template.system, **variables) or None
    return {
        "prompt": prompt_templates.render(template.user, **variables),
        "system_prompt": system,
        "system_sent": bool(system) and (structured or model.startswith("openrouter/")),
        "response_format": schema if structured else None,
        "structured": structured,
    }


def _record_usage(run: ContentGroupSuggestionRun, usage) -> None:
    """Copy tokens, latency and cost of the call onto the run so models and prompts can be compared per run."""
    if usage is None:
        return
    cost = getattr(usage, "cost", None)
    run.prompt_tokens = getattr(usage, "prompt_tokens", None)
    run.completion_tokens = getattr(usage, "completion_tokens", None)
    run.latency_ms = getattr(usage, "latency_ms", None)
    if cost is not None:
        run.cost_amount = getattr(cost, "total_cost", None)
        run.cost_currency = getattr(cost, "currency", None)
        status = getattr(cost, "status", None)
        run.cost_status = getattr(status, "value", status)


def execute_suggestion_job(session, job: Job) -> dict:
    parameters = job.parameters or {}
    target_type = "feed_item" if "feed_item_id" in parameters else "document"
    target_id = parameters.get(f"{target_type}_id")
    target = session.get(FeedItem if target_type == "feed_item" else Document, target_id)
    run = session.get(ContentGroupSuggestionRun, parameters.get("run_id"))
    if target is None or run is None:
        raise ValueError("suggestion target or run not found")
    earlier_error = run.error  # left by a failed attempt of this same job; cleared once an attempt succeeds
    run.status = "running"
    session.flush()
    allow_new_topics = target_type == "feed_item"
    template = prompt_templates.get_by_id(session, run.prompt_template_id, prompt_templates.TASK_CONTENT_GROUPS, target_type)
    try:
        built = build_request(target_type, target, run.model, run.catalog_snapshot, template)
        response = ai_ask(built["prompt"], model=run.model, temperature=0, operation="content_group_suggestion", document_id=target.id if target_type == "document" else None, response_format=built["response_format"], system_prompt=built["system_prompt"] if built["system_sent"] else None)
        _record_usage(run, getattr(response, "usage", None))
        raw = getattr(response, "response_text", "")
        run.raw_result = _parse_result(raw)
        if allow_new_topics:
            kept, dropped = triage_new_topics(run.raw_result.get("new_topics"), active_topic_catalog(session) if run.raw_result.get("new_topics") else [])
            # the dropped proposals stay on the run (with the reason): the kept list alone hides what the model said
            run.raw_result = {**run.raw_result, "new_topics": kept, **({"dropped_new_topics": dropped} if dropped else {})}
        if earlier_error and isinstance(run.raw_result, dict):
            # a retry that succeeded must not look like a clean run: keep what the failed attempt said (a 429, a timeout)
            run.raw_result = {**run.raw_result, "retried_after": earlier_error[:500], "attempts": job.attempt}
        run.error = None
        allowed = {item["id"] for item in run.catalog_snapshot}
        threshold = float(_config("CONTENT_GROUP_SUGGESTION_MIN_CONFIDENCE", "0.60"))
        auto_apply_threshold = float(_config("CONTENT_GROUP_AUTO_APPLY_MIN_CONFIDENCE", "0.75"))
        seen = set()
        valid = []
        for item in ([] if isinstance(run.raw_result, dict) and run.raw_result.get("no_match") else (run.raw_result.get("suggestions", []) if isinstance(run.raw_result, dict) else [])):
            try:
                group_id, confidence = int(item["group_id"]), float(item["confidence"])
            except (KeyError, TypeError, ValueError):
                continue
            if group_id not in allowed or group_id in seen or confidence < threshold or not 0 <= confidence <= 1:
                continue
            seen.add(group_id)
            valid.append((group_id, confidence, item))
        # A general topic is not proposed when a more specific one fits (or the target already has it).
        dropped = drop_ancestor_suggestions([entry[0] for entry in valid], _existing_group_ids(session, target_type, target.id) if valid else [], run.catalog_snapshot)
        kept = [entry for entry in valid if entry[0] not in dropped][:MAX_SUGGESTIONS]
        for group_id, confidence, item in kept:
            suggestion = ContentGroupSuggestion(run_id=run.id, group_id=group_id, confidence=confidence, reason=str(item.get("reason", ""))[:300])
            session.add(suggestion)
            if target_type == "document" and confidence >= auto_apply_threshold:
                session.flush()
                _auto_apply_suggestion(session, target.id, group_id, suggestion)
        run.status = "completed"
        run.completed_at = datetime.now(timezone.utc)
        session.commit()
        return {"run_id": run.id, "suggestions": len(kept)}
    except Exception as exc:
        run.status, run.error, run.completed_at = "error", str(exc)[:2000], datetime.now(timezone.utc)
        session.commit()
        raise


def decide_suggestion(session, suggestion_id: int, action: str, user_id: int | None):
    suggestion = session.get(ContentGroupSuggestion, suggestion_id)
    if suggestion is None:
        raise LookupError("suggestion not found")
    run = session.get(ContentGroupSuggestionRun, suggestion.run_id)
    target_model = FeedItem if run.feed_item_id is not None else Document
    target_id = run.feed_item_id or run.document_id
    target = session.execute(select(target_model).where(target_model.id == target_id).with_for_update()).scalar_one()
    if action == "accept":
        if suggestion.status != "pending":
            raise RuntimeError("suggestion is not pending")
        group = session.scalar(select(ContentGroup).where(ContentGroup.id == suggestion.group_id, ContentGroup.kind == "topic", ContentGroup.archived_at.is_(None)))
        if group is None:
            raise RuntimeError("suggested group is no longer an active topic")
        membership_model = FeedItemGroupMembership if run.feed_item_id is not None else DocumentGroupMembership
        key = "feed_item_id" if run.feed_item_id is not None else "document_id"
        membership = session.scalar(select(membership_model).where(getattr(membership_model, key) == target_id, membership_model.group_id == group.id))
        if membership is None:
            membership = membership_model(**{key: target_id, "group_id": group.id, "source": "llm_suggestion", "source_suggestion_id": suggestion.id})
            session.add(membership)
            suggestion.membership_created = True
        suggestion.status = "accepted"
    elif action == "dismiss":
        if suggestion.status != "pending":
            raise RuntimeError("suggestion is not pending")
        suggestion.status = "dismissed"
    elif action == "revert":
        if suggestion.status != "accepted":
            raise RuntimeError("suggestion is not accepted")
        membership_model = FeedItemGroupMembership if run.feed_item_id is not None else DocumentGroupMembership
        key = "feed_item_id" if run.feed_item_id is not None else "document_id"
        membership = session.scalar(select(membership_model).where(getattr(membership_model, key) == target_id, membership_model.group_id == suggestion.group_id))
        removed = bool(membership and membership.source_suggestion_id == suggestion.id)
        if removed:
            session.delete(membership)
        suggestion.status = "reverted"
        suggestion.membership_created = removed
    else:
        raise ValueError("invalid suggestion action")
    suggestion.decided_by_user_id, suggestion.decided_at = user_id, datetime.now(timezone.utc)
    session.commit()
    return suggestion, target
