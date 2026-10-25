"""REST API for the UI-editable prompt templates and the model/prompt comparison report."""

import datetime as dt
import json
from collections import defaultdict
from decimal import Decimal

from flask import Blueprint, abort, g, jsonify, request
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from library import prompt_templates
from library.content_group_suggestion_service import active_topic_catalog, target_text
from library.db.engine import get_scoped_session
from library.db.models import ContentGroupSuggestionRun, FeedItem

bp = Blueprint("prompt_templates", __name__)

MAX_COMPARISON_RUNS = 5000


def _principal():
    """Single-owner project: a household user key or a service key may read and edit templates."""
    if getattr(g, "auth", None) is None or g.auth.kind not in {"user", "service"}:
        abort(403, "user or service API key required")
    return g.auth.user_id if g.auth.kind == "user" else None


def _task_variant(source) -> tuple[str, str]:
    task = source.get("task") or prompt_templates.TASK_CONTENT_GROUPS
    variant = source.get("variant")
    if variant not in prompt_templates.VARIANTS.get(task, ()):
        abort(400, "unknown task or variant")
    return task, variant


@bp.get("/prompt_templates")
def list_prompt_templates():
    _principal()
    task = request.args.get("task") or prompt_templates.TASK_CONTENT_GROUPS
    if task not in prompt_templates.VARIANTS:
        abort(400, "unknown task")
    session = get_scoped_session()
    rows = prompt_templates.list_versions(session, task, request.args.get("variant"))
    builtin = {variant: prompt_templates.builtin(task, variant) for variant in prompt_templates.VARIANTS[task]}
    return jsonify({
        "task": task,
        "variants": list(prompt_templates.VARIANTS[task]),
        "variables": prompt_templates.VARIABLES.get(task, {}),
        "templates": [prompt_templates.to_dict(row) for row in rows],
        "builtin": {variant: {"system_template": item.system, "user_template": item.user} for variant, item in builtin.items()},
    })


@bp.post("/prompt_templates")
def create_prompt_template():
    user_id = _principal()
    body = request.get_json(silent=True) or {}
    task, variant = _task_variant(body)
    try:
        row = prompt_templates.create_version(
            get_scoped_session(), task, variant, body.get("system_template") or None, body.get("user_template"),
            note=body.get("note"), user_id=user_id, activate=body.get("activate", True) is not False)
    except prompt_templates.TemplateInvalid as exc:
        abort(400, str(exc))
    return jsonify({"template": prompt_templates.to_dict(row)}), 201


@bp.post("/prompt_templates/<int:template_id>/activate")
def activate_prompt_template(template_id):
    _principal()
    try:
        row = prompt_templates.activate(get_scoped_session(), template_id)
    except LookupError:
        abort(404)
    return jsonify({"template": prompt_templates.to_dict(row)})


@bp.post("/prompt_templates/preview")
def preview_prompt_template():
    """Render a draft against a real feed item (or sample text) without calling any model or saving anything."""
    _principal()
    body = request.get_json(silent=True) or {}
    task, variant = _task_variant(body)
    system_template, user_template = body.get("system_template") or None, body.get("user_template")
    try:
        prompt_templates.validate(task, variant, system_template, user_template)
    except prompt_templates.TemplateInvalid as exc:
        abort(400, str(exc))
    session = get_scoped_session()
    item = session.get(FeedItem, body["feed_item_id"]) if isinstance(body.get("feed_item_id"), int) else None
    variables = {
        "catalog": json.dumps(active_topic_catalog(session), ensure_ascii=False),
        "material": target_text(item) if item is not None else "TYTUŁ: Przykładowy tytuł\n\nSUMMARY: Przykładowe streszczenie.",
        "schema": "" if body.get("structured", True) else '{"type": "object", "...": "schemat odpowiedzi"}',
    }
    return jsonify({
        "system": prompt_templates.render(system_template, **variables),
        "user": prompt_templates.render(user_template, **variables),
        "feed_item_id": item.id if item is not None else None,
    })


def _decimal(value) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _money(value: Decimal | None) -> str | None:
    return None if value is None else format(value.normalize(), "f")


def build_comparison(runs: list[ContentGroupSuggestionRun]) -> list[dict]:
    """One row per (model, prompt version): size of the sample, tokens, cost and how many suggestions the reviewer accepted."""
    groups: dict[tuple, list[ContentGroupSuggestionRun]] = defaultdict(list)
    for run in runs:
        groups[(run.model, run.prompt_version, run.prompt_template_id)].append(run)
    rows = []
    for (model, version, template_id), items in groups.items():
        costs: dict[str, Decimal] = defaultdict(Decimal)
        costed = defaultdict(int)
        for run in items:
            if run.cost_amount is not None and run.cost_currency:
                costs[run.cost_currency] += _decimal(run.cost_amount)
                costed[run.cost_currency] += 1
        statuses = [s.status for run in items for s in run.suggestions]
        accepted, dismissed = statuses.count("accepted"), statuses.count("dismissed")
        decided = accepted + dismissed

        def average(attribute):
            values = [getattr(run, attribute) for run in items if getattr(run, attribute) is not None]
            return round(sum(values) / len(values), 1) if values else None

        per_currency = {currency: {
            "total": _money(total), "per_run": _money(total / costed[currency]), "runs_with_cost": costed[currency],
            "per_accepted": _money(total / accepted) if accepted else None,
        } for currency, total in costs.items()}
        rows.append({
            "model": model, "prompt_version": version, "prompt_template_id": template_id, "runs": len(items),
            "avg_prompt_tokens": average("prompt_tokens"), "avg_completion_tokens": average("completion_tokens"),
            "avg_latency_ms": average("latency_ms"), "cost": per_currency,
            "suggestions": len(statuses), "accepted": accepted, "dismissed": dismissed,
            "pending": len(statuses) - decided - statuses.count("reverted"), "reverted": statuses.count("reverted"),
            "accept_rate": round(accepted / decided, 3) if decided else None,
            "no_match_runs": sum(1 for run in items if isinstance(run.raw_result, dict) and run.raw_result.get("no_match")),
            "last_run_at": max((run.created_at for run in items if run.created_at), default=None),
        })
    for row in rows:
        row["last_run_at"] = row["last_run_at"].isoformat() if row["last_run_at"] else None
    return sorted(rows, key=lambda row: (row["prompt_version"], row["model"]))


@bp.get("/prompt_templates/comparison")
def prompt_template_comparison():
    """Completed runs grouped by model and prompt version; ``days`` limits the window (default 90, 0 = all)."""
    _principal()
    _, variant = _task_variant({"variant": request.args.get("variant", "feed_item")})
    days = request.args.get("days", default=90, type=int)
    target = ContentGroupSuggestionRun.feed_item_id if variant == "feed_item" else ContentGroupSuggestionRun.document_id
    query = (select(ContentGroupSuggestionRun)
             .where(ContentGroupSuggestionRun.status == "completed", target.is_not(None))
             .options(selectinload(ContentGroupSuggestionRun.suggestions))
             .order_by(ContentGroupSuggestionRun.id.desc()).limit(MAX_COMPARISON_RUNS))
    if days and days > 0:
        query = query.where(ContentGroupSuggestionRun.created_at >= dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days))
    runs = get_scoped_session().scalars(query).all()
    return jsonify({"variant": variant, "days": days, "rows": build_comparison(list(runs)), "runs_considered": len(runs)})
