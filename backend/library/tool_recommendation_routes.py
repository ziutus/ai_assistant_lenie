"""API for the lightweight, provenance-preserving tool recommendation radar."""

import datetime
import logging
from urllib.parse import urlparse

from flask import Blueprint, abort, g, jsonify, request
from sqlalchemy import Text, func, or_, select
from sqlalchemy.orm import joinedload, selectinload

from library import github_repo_stats, tool_links
from library.db.engine import get_scoped_session
from library import feed_mentions, tool_note_parser, tool_radar_feed, tool_relations_service
from library.db.models import Document, Tool, ToolRecommendation, ToolRecommendationEvidence, ToolRelation
from library.obsidian_vault import read_note
from library.tool_recommendation_importer import fetch_markdown, parse_markdown_recommendations

bp = Blueprint("tool_recommendations", __name__)
logger = logging.getLogger(__name__)

STATUSES = {"watchlist", "compare", "testing", "test_future", "adopted", "phasing_out", "rejected", "archived"}
MAX_TAGS = 20
MAX_TAG_LENGTH = 40


def normalize_tags(raw) -> list[str]:
    """Lowercase, trim, collapse inner spaces to ``-`` and de-duplicate, keeping the given order."""
    if raw is None:
        return []
    if not isinstance(raw, list):
        abort(400, "tags must be a list of strings")
    tags: list[str] = []
    for value in raw:
        if not isinstance(value, str):
            abort(400, "tags must be a list of strings")
        tag = "-".join(value.strip().lower().split())
        if not tag:
            continue
        if len(tag) > MAX_TAG_LENGTH:
            abort(400, f"a tag is at most {MAX_TAG_LENGTH} characters")
        if tag not in tags:
            tags.append(tag)
    if len(tags) > MAX_TAGS:
        abort(400, f"at most {MAX_TAGS} tags per entry")
    return tags


def _catalog_tags(item: ToolRecommendation) -> list[str]:
    """Tags for the catalog tool: the category first, then the radar tags, without repeats."""
    merged = [item.category] if item.category else []
    merged.extend(tag for tag in (item.tags or []) if tag not in merged)
    return merged


def _existing_tool(session, name: str, homepage_url: str | None = None) -> Tool | None:
    clauses = [func.lower(Tool.name) == name.strip().lower()]
    if homepage_url:
        clauses.append(Tool.homepage_url == homepage_url)
    return session.execute(select(Tool).where(or_(*clauses)).limit(1)).scalars().first()


def _ensure_tool(session, item: ToolRecommendation) -> tuple[Tool, bool]:
    existing = _existing_tool(session, item.name, item.homepage_url)
    if existing is not None:
        item.tool_id = existing.id
        return existing, False
    tool = Tool(
        name=item.name,
        homepage_url=item.homepage_url,
        github_url=item.homepage_url if github_repo_stats.parse_repo_url(item.homepage_url) else None,
        links=tool_links.merge_links([], item.links),
        category_tags=_catalog_tags(item),
        personal_notes=item.personal_note,
        obsidian_note_path=item.obsidian_note_path,
        source_document_id=item.source_document_id,
        source_candidate_id=item.source_candidate_id,
        status="accepted",
    )
    _fill_from_vault_note(tool)
    if not tool.purpose:
        tool.purpose = item.description
    session.add(tool)
    session.flush()
    item.tool_id = tool.id
    return tool, True


def _fill_from_vault_note(tool: Tool) -> None:
    """Best effort: read the tool's Obsidian note (if any) into its still-empty fields; never blocks adoption."""
    if not tool.obsidian_note_path:
        return
    try:
        text = read_note(tool.obsidian_note_path)
        if text:
            tool_note_parser.apply_note_to_tool(tool, tool_note_parser.parse_tool_note(text))
    except Exception:  # vault unmounted, bad path, unreadable file
        logger.warning("could not read the Obsidian note of tool %s", tool.name, exc_info=True)


def _catalog_label(url: str) -> str:
    parsed = urlparse(url)
    path = [part for part in parsed.path.split("/") if part]
    if parsed.netloc.lower() in {"github.com", "www.github.com"} and len(path) >= 2:
        return f"{path[0]}/{path[1]}"
    return parsed.netloc or url


def _resolve_source_document(session, source_url: str, requested_id: int | None) -> Document | None:
    """Use an explicit document as an override, otherwise resolve the catalog URL.

    A saved LinkDocument often carries its discovery source (for example a
    newsletter), so resolving the URL here preserves the whole recommendation
    path without making a user copy an internal numeric ID.
    """
    if requested_id is not None:
        document = session.get(Document, requested_id)
        if document is None:
            abort(404, "source document not found")
        return document
    return session.execute(
        select(Document)
        .where(or_(Document.url == source_url, Document.canonical_url == source_url))
        .order_by(Document.ingested_at.desc(), Document.id.desc())
        .limit(1)
    ).scalars().first()


def _repository_urls(item: ToolRecommendation) -> list[str]:
    """Every URL of the entry that may be a repository: the homepage first, then its further links."""
    return github_repo_stats.repository_urls(item.homepage_url, item.links)


def _reader():
    if getattr(g, "auth", None) is None or g.auth.kind not in {"user", "service"}:
        abort(403, "user or service API key required")


def _user():
    # Single-owner project: a service key (scripts, skills) may write to the radar like a user key.
    if getattr(g, "auth", None) is None or g.auth.kind not in {"user", "service"}:
        abort(403, "user or service API key required")


def _dict(item: ToolRecommendation, github: dict | None = None, relations: list | None = None,
          feed_mention: dict | None = None) -> dict:
    document = item.source_document
    relations = relations or []
    return {
        "github": github,
        "feed_mentions": feed_mention or {"count": 0, "samples": []},
        "relations": relations,
        "stack_matches": sorted({r["other_name"] for r in relations if r["in_my_stack"]}),
        "id": item.id,
        "tool_id": item.tool_id,
        "name": item.name,
        "homepage_url": item.homepage_url,
        "links": list(item.links or []),
        "description": item.description,
        "category": item.category,
        "tags": list(item.tags or []),
        "status": item.status,
        "personal_note": item.personal_note,
        "obsidian_note_path": item.obsidian_note_path,
        "source_url": item.source_url,
        "source_context": item.source_context,
        "source_document_id": item.source_document_id,
        "source_candidate_id": item.source_candidate_id,
        "origin": "ai_detected" if item.source_candidate_id is not None else "curated",
        "source_document": None if document is None else {
            "id": document.id,
            "title": document.title,
            "url": document.url,
            "discovery_source": document.discovery_source.name if document.discovery_source else None,
        },
        "evidences": [{
            "id": evidence.id,
            "relation_type": evidence.relation_type,
            "catalog_url": evidence.catalog_url,
            "catalog_label": evidence.catalog_label,
            "context": evidence.context,
            "recommender_document": None if evidence.recommender_document is None else {
                "id": evidence.recommender_document.id,
                "title": evidence.recommender_document.title,
                "url": evidence.recommender_document.url,
                "discovery_source": evidence.recommender_document.discovery_source.name if evidence.recommender_document.discovery_source else None,
            },
        } for evidence in getattr(item, "evidences", [])],
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


@bp.get("/tool_recommendations")
def get_tool_recommendations():
    _reader()
    status = request.args.get("status", "watchlist")
    if status not in STATUSES and status != "all":
        abort(400, "unsupported status")
    category = request.args.get("category")
    tags = normalize_tags(request.args.getlist("tag"))  # repeated ?tag= narrows: an entry needs all of them
    text = (request.args.get("q") or "").strip()
    origin = request.args.get("origin", "all")
    if origin not in {"all", "ai_detected", "curated"}:
        abort(400, "unsupported origin")
    entry_id = request.args.get("id", type=int)
    session = get_scoped_session()
    query = select(ToolRecommendation).options(
        joinedload(ToolRecommendation.source_document).joinedload(Document.discovery_source),
        selectinload(ToolRecommendation.evidences)
        .joinedload(ToolRecommendationEvidence.recommender_document)
        .joinedload(Document.discovery_source),
    ).order_by(ToolRecommendation.created_at.desc())
    if entry_id is not None:  # one entry of any stage, for a shareable link to a single tool
        query = query.where(ToolRecommendation.id == entry_id)
    if status != "all":
        query = query.where(ToolRecommendation.status == status)
    if category:
        query = query.where(ToolRecommendation.category == category)
    for tag in tags:
        query = query.where(ToolRecommendation.tags.contains([tag]))
    if text:
        like = f"%{text}%"
        query = query.where(or_(
            ToolRecommendation.name.ilike(like), ToolRecommendation.description.ilike(like),
            ToolRecommendation.category.ilike(like), func.cast(ToolRecommendation.tags, Text).ilike(like),
        ))
    if origin == "ai_detected":
        query = query.where(ToolRecommendation.source_candidate_id.is_not(None))
    if origin == "curated":
        query = query.where(ToolRecommendation.source_candidate_id.is_(None))
    items = session.execute(query).scalars().all()
    categories = session.execute(
        select(ToolRecommendation.category)
        .where(ToolRecommendation.category.is_not(None))
        .distinct()
        .order_by(ToolRecommendation.category)
    ).scalars().all()
    tag_counts: dict[str, int] = {}
    for tag_list in session.execute(select(ToolRecommendation.tags)).scalars().all():
        for tag in tag_list or []:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
    github = github_repo_stats.combined_stats_for_entries(session, {item.id: _repository_urls(item) for item in items})
    relations = tool_relations_service.relations_for(session, [item.id for item in items])
    mentions = feed_mentions.mentions_for(session, {item.id: item.name for item in items})
    return jsonify({
        "tool_recommendations": [
            _dict(item, github.get(item.id), relations.get(item.id), mentions.get(item.id)) for item in items
        ],
        "categories": categories,
        "all_tags": [{"tag": tag, "count": count} for tag, count in sorted(tag_counts.items())],
        "filters": {"status": status, "category": category, "origin": origin, "tags": tags, "q": text},
    })


def _category_key(value: str | None) -> str:
    """Fold spellings such as ``DecisionModels`` and ``decision-models`` into one key."""
    return "".join(char for char in (value or "").lower() if char.isalnum())


@bp.get("/tool_recommendations/<int:recommendation_id>/peers")
def get_recommendation_peers(recommendation_id):
    """Alternatives for one radar entry: other radar entries and saved tools of the same category.

    Catalogs spell categories differently (``DecisionModels`` vs ``decision-models``), so
    the match ignores case and punctuation. Saved tools (Spis narzędzi) are what the user
    already uses, so the review card can set a candidate next to its incumbent.
    """
    _reader()
    session = get_scoped_session()
    item = session.get(ToolRecommendation, recommendation_id)
    if item is None:
        abort(404, "tool recommendation not found")
    key = _category_key(item.category)
    if not key:
        return jsonify({"category": item.category, "radar": [], "tools": []})
    radar = [
        other for other in session.execute(
            select(ToolRecommendation).where(
                ToolRecommendation.id != item.id, ToolRecommendation.category.is_not(None),
            ).order_by(ToolRecommendation.name)
        ).scalars().all()
        if _category_key(other.category) == key
    ]
    tools = [
        tool for tool in session.execute(select(Tool).order_by(Tool.name)).scalars().all()
        if any(_category_key(str(tag)) == key for tag in (tool.category_tags or []))
    ]
    github = github_repo_stats.combined_stats_for_entries(session, {other.id: _repository_urls(other) for other in radar})
    linked_tool_ids = {entry.tool_id for entry in [item, *radar] if entry.tool_id is not None}
    radar_urls = {other.homepage_url for other in radar if other.homepage_url}
    return jsonify({
        "category": item.category,
        "radar": [{
            "id": other.id, "name": other.name, "status": other.status, "category": other.category,
            "description": other.description, "homepage_url": other.homepage_url,
            "personal_note": other.personal_note, "github": github.get(other.id),
        } for other in radar],
        # A tool adopted from the radar exists in both lists; show it once, as the radar entry.
        "tools": [{
            "id": tool.id, "name": tool.name, "homepage_url": tool.homepage_url, "status": tool.status,
            "personal_notes": tool.personal_notes, "pricing": tool.pricing, "license": tool.license,
        } for tool in tools if tool.id not in linked_tool_ids and tool.homepage_url not in radar_urls],
    })


@bp.get("/tool_recommendations/github_rate")
def get_github_rate():
    """GitHub quota left for this server (``limit``, ``remaining``, ``reset``, ``authenticated``); ``rate: null`` when unreachable."""
    _reader()
    return jsonify({"rate": github_repo_stats.fetch_rate_limit()})


@bp.post("/tool_recommendations/github_stats/refresh")
def refresh_github_stats():
    """Pull fresh GitHub numbers for the radar entries of one status (or all), a bounded batch per call.

    Never-fetched repositories go first, then the ones older than a day. GitHub allows
    60 unauthenticated requests per hour, so ``pending`` tells the caller to come back.
    ``{"id": N, "force": true}`` refreshes that one entry's repository whatever its age; ``force`` is
    accepted only together with ``id`` (a bulk forced run would re-fetch the same repositories again).
    """
    _user()
    body = request.get_json(silent=True) or {}
    force = body.get("force", False)
    if not isinstance(force, bool):
        abort(400, "force must be a boolean")
    if body.get("id") is not None:
        session = get_scoped_session()
        try:
            item = session.get(ToolRecommendation, int(body["id"]))
        except (TypeError, ValueError):
            abort(400, "id must be an integer")
        if item is None:
            abort(404, "tool recommendation not found")
        urls = _repository_urls(item)
        repositories = [ref for ref in map(github_repo_stats.parse_repository_url, urls) if ref is not None]
        if not repositories:
            abort(400, "this entry has no GitHub or GitLab repository")
        summary = github_repo_stats.refresh_stale(session, urls, limit=len(repositories), force=force)
        session.commit()
        return jsonify(summary)
    if force:
        abort(400, "force needs an id")
    status = body.get("status", "watchlist")
    if status not in STATUSES and status != "all":
        abort(400, "unsupported status")
    try:
        limit = int(body.get("limit", github_repo_stats.default_refresh_limit()))
    except (TypeError, ValueError):
        abort(400, "limit must be an integer")
    if not 1 <= limit <= github_repo_stats.max_refresh_limit():
        abort(400, f"limit must be between 1 and {github_repo_stats.max_refresh_limit()}")
    session = get_scoped_session()
    query = select(ToolRecommendation.homepage_url, ToolRecommendation.links)
    if status != "all":
        query = query.where(ToolRecommendation.status == status)
    urls = github_repo_stats.repository_urls(*(
        value for homepage_url, links in session.execute(query).all() for value in (homepage_url, links)
    ))
    summary = github_repo_stats.refresh_stale(session, urls, limit=limit)
    session.commit()
    return jsonify(summary)


@bp.post("/tool_recommendations")
def create_tool_recommendation():
    _user()
    body = request.get_json(silent=True) or {}
    name = str(body.get("name") or "").strip()
    if not name:
        abort(400, "name is required")
    status = body.get("status") or "watchlist"
    if status not in STATUSES:
        abort(400, "unsupported status")
    session = get_scoped_session()
    existing_tool = _existing_tool(session, name, body.get("homepage_url"))
    if existing_tool is not None:
        return jsonify({"existing_tool": {"id": existing_tool.id, "name": existing_tool.name}}), 200
    existing_item = session.execute(
        select(ToolRecommendation).where(func.lower(ToolRecommendation.name) == name.lower()).limit(1)
    ).scalars().first()
    if existing_item is not None:
        return jsonify({"existing_tool_recommendation": {"id": existing_item.id, "name": existing_item.name}}), 200
    item = ToolRecommendation(
        name=name[:255], homepage_url=body.get("homepage_url"), description=body.get("description"),
        links=tool_links.clean_links(body["links"]) if "links" in body else [],
        category=body.get("category"), tags=normalize_tags(body.get("tags")), status=status,
        personal_note=body.get("personal_note"),
        obsidian_note_path=(str(body.get("obsidian_note_path") or "").strip() or None),
        source_url=body.get("source_url"), source_context=body.get("source_context"),
        source_document_id=body.get("source_document_id"), source_candidate_id=body.get("source_candidate_id"),
    )
    session.add(item)
    session.flush()
    tool_relations_service.detect_relations(session, item)
    session.commit()
    return jsonify({"tool_recommendation": _dict(item)}), 201


@bp.post("/feed_items/<int:item_id>/to_radar")
def feed_item_to_radar(item_id):
    """Turn a feed candidate into a watchlist radar entry and take it out of the review queue.

    Body (all optional): ``name`` (default: the title up to the first dash), ``homepage_url``
    (default: the item's URL, ``""`` = none) and ``category``.
    """
    _user()
    body = request.get_json(silent=True) or {}
    session = get_scoped_session()
    try:
        outcome = tool_radar_feed.send_to_radar(
            session, item_id, g.auth.user_id, name=body.get("name"), homepage_url=body.get("homepage_url"),
            category=body.get("category"),
        )
    except ValueError as exc:
        abort(404 if str(exc) == "feed item not found" else 400, str(exc))
    except RuntimeError as exc:
        abort(409, str(exc))
    return jsonify(outcome), 201 if outcome["created"] else 200


@bp.post("/tool_recommendations/relations/detect")
def detect_tool_relations():
    """Propose ``works_with`` relations from each entry's source text (``{id}`` for one, else all of ``status``)."""
    _user()
    body = request.get_json(silent=True) or {}
    session = get_scoped_session()
    query = select(ToolRecommendation)
    if body.get("id") is not None:
        query = query.where(ToolRecommendation.id == body["id"])
    else:
        status = body.get("status", "watchlist")
        if status not in STATUSES and status != "all":
            abort(400, "unsupported status")
        if status != "all":
            query = query.where(ToolRecommendation.status == status)
    items = session.execute(query).scalars().all()
    proposed = []
    for item in items:
        outcome = tool_relations_service.detect_relations(session, item)
        if outcome["created"]:
            proposed.append({"id": item.id, "name": item.name, "related": outcome["created"]})
    session.commit()
    return jsonify({"checked": len(items), "proposed": proposed})


@bp.patch("/tool_relations/<int:relation_id>")
def update_tool_relation(relation_id):
    _user()
    body = request.get_json(silent=True) or {}
    status = body.get("status")
    if status not in tool_relations_service.STATUSES:
        abort(400, "unsupported status")
    relation = body.get("relation")
    if relation is not None and relation not in tool_relations_service.RELATIONS:
        abort(400, "unsupported relation")
    session = get_scoped_session()
    edge = session.get(ToolRelation, relation_id)
    if edge is None:
        abort(404, "tool relation not found")
    edge.status = status
    if relation is not None:
        edge.relation = relation
    session.commit()
    return jsonify({"id": edge.id, "status": edge.status, "relation": edge.relation})


@bp.post("/tool_recommendations/import_markdown")
def import_markdown_recommendations():
    """Import a curated GitHub Markdown list into the watchlist, preserving its categories."""
    _user()
    body = request.get_json(silent=True) or {}
    source_url = str(body.get("source_url") or "").strip()
    if not source_url:
        abort(400, "source_url is required")
    source_document_id = body.get("source_document_id")
    if source_document_id is not None:
        try:
            source_document_id = int(source_document_id)
        except (TypeError, ValueError):
            abort(400, "source_document_id must be an integer")
    try:
        markdown = fetch_markdown(source_url)
    except ValueError as exc:
        abort(400, str(exc))
    except Exception:
        abort(502, "could not fetch GitHub Markdown")
    parsed = parse_markdown_recommendations(markdown)
    session = get_scoped_session()
    source_document = _resolve_source_document(session, source_url, source_document_id)
    created = skipped = evidence_created = evidence_upgraded = tools_skipped = 0
    linked_existing = 0
    skipped_items = []
    for entry in parsed:
        if _existing_tool(session, entry["name"], entry["homepage_url"]) is not None:
            tools_skipped += 1
            skipped_items.append({"name": entry["name"], "reason": "already_in_tools"})
            continue
        item = session.execute(
            select(ToolRecommendation).where(
                or_(
                    ToolRecommendation.homepage_url == entry["homepage_url"],
                    func.lower(ToolRecommendation.name) == entry["name"].lower(),
                ),
            ).limit(1)
        ).scalar_one_or_none()
        if item is not None:
            skipped += 1
            if source_document is not None and item.source_document_id is None:
                item.source_document_id = source_document.id
                linked_existing += 1
            skipped_items.append({"name": entry["name"], "existing_id": item.id, "reason": "already_in_radar"})
        else:
            item = ToolRecommendation(
                name=entry["name"], homepage_url=entry["homepage_url"], description=entry["description"],
                category=entry["category"], source_url=source_url, source_context="Katalog GitHub",
                source_document_id=source_document.id if source_document is not None else None, status="watchlist",
            )
            session.add(item)
            session.flush()
            created += 1

        evidence = session.execute(select(ToolRecommendationEvidence).where(
            ToolRecommendationEvidence.tool_recommendation_id == item.id,
            ToolRecommendationEvidence.catalog_url == source_url,
            ToolRecommendationEvidence.recommender_document_id == (source_document.id if source_document else None),
        ).limit(1)).scalar_one_or_none()
        if evidence is None and source_document is not None:
            # Imports made before graph provenance had a catalog edge without
            # an upstream document. Upgrade that edge in place during a
            # re-import so the UI shows one coherent path, not a duplicate.
            evidence = session.execute(select(ToolRecommendationEvidence).where(
                ToolRecommendationEvidence.tool_recommendation_id == item.id,
                ToolRecommendationEvidence.catalog_url == source_url,
                ToolRecommendationEvidence.recommender_document_id.is_(None),
            ).limit(1)).scalar_one_or_none()
            if evidence is not None:
                evidence.recommender_document_id = source_document.id
                evidence.catalog_label = _catalog_label(source_url)
                evidence.context = entry["category"]
                evidence_upgraded += 1
        if evidence is None:
            session.add(ToolRecommendationEvidence(
                tool_recommendation_id=item.id, relation_type="listed_in", catalog_url=source_url,
                catalog_label=_catalog_label(source_url), context=entry["category"],
                recommender_document_id=source_document.id if source_document else None,
            ))
            evidence_created += 1
    session.commit()
    return jsonify({
        "created": created,
        "skipped": skipped,
        "skipped_items": skipped_items,
        "linked_existing": linked_existing,
        "evidence_created": evidence_created,
        "evidence_upgraded": evidence_upgraded,
        "tools_skipped": tools_skipped,
        "resolved_source_document": None if source_document is None else {
            "id": source_document.id,
            "title": source_document.title,
            "discovery_source": source_document.discovery_source.name if source_document.discovery_source else None,
        },
        "parsed": len(parsed),
    }), 201


@bp.patch("/tool_recommendations/<int:recommendation_id>")
def update_tool_recommendation(recommendation_id):
    """Edit the descriptive fields of one radar entry (absent key = unchanged, empty string clears)."""
    _user()
    body = request.get_json(silent=True) or {}
    session = get_scoped_session()
    item = session.get(ToolRecommendation, recommendation_id)
    if item is None:
        abort(404, "tool recommendation not found")
    if "tags" in body:
        item.tags = normalize_tags(body["tags"])
    if "links" in body:
        item.links = tool_links.clean_links(body["links"])
    for field in ("homepage_url", "description", "category", "personal_note", "obsidian_note_path"):
        if field in body:
            value = body[field]
            if value is not None and not isinstance(value, str):
                abort(400, f"{field} must be a string")
            setattr(item, field, (value or "").strip() or None)
    item.updated_at = datetime.datetime.now(datetime.timezone.utc)
    session.commit()
    return jsonify({"tool_recommendation": _dict(item)})


@bp.get("/tool_recommendations/tag_model")
def get_tag_model():
    """Models that may propose tags, the one in effect (``default_model``) and whether it was chosen (``saved``)."""
    _reader()
    from library import app_settings, tool_tag_suggester
    from library.llm_model_registry import selectable_models

    session = get_scoped_session()
    saved = app_settings.get_setting(session, tool_tag_suggester.SETTING_KEY)
    return jsonify({
        "default_model": tool_tag_suggester.default_model(session),
        "saved": isinstance(saved, str),
        "models": selectable_models(tool_tag_suggester.TASK),
    })


@bp.put("/tool_recommendations/tag_model")
def put_tag_model():
    """Set the default tag model (``{"model": id}``); ``{"model": null}`` goes back to the built-in default."""
    _user()
    from library import app_settings, tool_tag_suggester
    from library.llm_model_registry import is_selectable

    body = request.get_json(silent=True) or {}
    if "model" not in body:
        abort(400, "model is required")
    model = body["model"]
    if model is not None and (not isinstance(model, str) or not is_selectable(model, tool_tag_suggester.TASK)):
        abort(400, "unknown model")
    session = get_scoped_session()
    app_settings.set_setting(session, tool_tag_suggester.SETTING_KEY, model)
    return jsonify({"default_model": tool_tag_suggester.default_model(session), "saved": model is not None})


@bp.post("/tool_recommendations/<int:recommendation_id>/suggest_tags")
def suggest_tags(recommendation_id):
    """Ask a model for tags of one entry (``{"model"?}``, default = the saved choice). Nothing is stored.

    The UI shows the proposals and saves the accepted ones through ``PATCH /tool_recommendations/<id>``.
    """
    _user()
    from library import tool_tag_suggester
    from library.llm_model_registry import is_selectable

    body = request.get_json(silent=True) or {}
    session = get_scoped_session()
    item = session.get(ToolRecommendation, recommendation_id)
    if item is None:
        abort(404, "tool recommendation not found")
    model = body.get("model")
    if model is not None and (not isinstance(model, str) or not is_selectable(model, tool_tag_suggester.TASK)):
        abort(400, "unknown model")
    model = model or tool_tag_suggester.default_model(session)
    if not model:
        abort(503, "no model available")
    github = github_repo_stats.combined_stats_for_entries(session, {item.id: _repository_urls(item)}).get(item.id)
    return jsonify(tool_tag_suggester.suggest_tags(item, _tag_vocabulary(session), model, github))


def _tag_vocabulary(session) -> list[str]:
    """Every tag in use on the radar, most used first."""
    counts: dict[str, int] = {}
    for tag_list in session.execute(select(ToolRecommendation.tags)).scalars().all():
        for tag in tag_list or []:
            counts[tag] = counts.get(tag, 0) + 1
    return [tag for tag, _ in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))]


@bp.post("/tool_recommendations/<int:recommendation_id>/suggest_profile")
def suggest_profile(recommendation_id):
    """Ask a model ONCE for a description, a category and tags of one entry (``{"model"?}``). Nothing is stored.

    The model is the one chosen for tag suggestions. The prompt carries the entry's public facts, the categories
    and tags already in use (so existing ones are reused and a broad one such as ``AI`` is narrowed) and asks the
    model to use what it knows about the tool. The UI saves what the user accepts through
    ``PATCH /tool_recommendations/<id>``.
    """
    _user()
    from library import tool_profile_suggester, tool_tag_suggester
    from library.llm_model_registry import is_selectable

    body = request.get_json(silent=True) or {}
    session = get_scoped_session()
    item = session.get(ToolRecommendation, recommendation_id)
    if item is None:
        abort(404, "tool recommendation not found")
    model = body.get("model")
    if model is not None and (not isinstance(model, str) or not is_selectable(model, tool_tag_suggester.TASK)):
        abort(400, "unknown model")
    model = model or tool_tag_suggester.default_model(session)
    if not model:
        abort(503, "no model available")
    rows = session.execute(
        select(ToolRecommendation.category, func.count())
        .where(ToolRecommendation.category.is_not(None))
        .group_by(ToolRecommendation.category)
        .order_by(func.count().desc(), ToolRecommendation.category)
    ).all()
    categories = [(label, count) for label, count in rows if label]
    github = github_repo_stats.combined_stats_for_entries(session, {item.id: _repository_urls(item)}).get(item.id)
    return jsonify(tool_profile_suggester.suggest_profile(item, github, categories, _tag_vocabulary(session), model))


@bp.post("/tool_recommendations/<int:recommendation_id>/status")
def update_status(recommendation_id):
    _user()
    body = request.get_json(silent=True) or {}
    status = body.get("status")
    if status not in STATUSES:
        abort(400, "unsupported status")
    session = get_scoped_session()
    item = session.get(ToolRecommendation, recommendation_id)
    if item is None:
        abort(404, "tool recommendation not found")
    item.status = status
    item.personal_note = body.get("personal_note", item.personal_note)
    item.updated_at = datetime.datetime.now(datetime.timezone.utc)
    tool = created = None
    if status == "adopted":
        tool, created = _ensure_tool(session, item)
    session.commit()
    return jsonify({"tool_recommendation": _dict(item), "tool": None if tool is None else {"id": tool.id, "name": tool.name}, "tool_created": created})


@bp.post("/tool_recommendations/bulk_status")
def bulk_update_status():
    """Move a deliberate selection of radar entries to one lifecycle stage."""
    _user()
    body = request.get_json(silent=True) or {}
    status = body.get("status")
    raw_ids = body.get("ids")
    if status not in STATUSES:
        abort(400, "unsupported status")
    if not isinstance(raw_ids, list) or not raw_ids or len(raw_ids) > 1000:
        abort(400, "ids must contain between 1 and 1000 recommendation IDs")
    try:
        ids = sorted({int(item) for item in raw_ids})
    except (TypeError, ValueError):
        abort(400, "ids must be integers")
    session = get_scoped_session()
    items = session.execute(select(ToolRecommendation).where(ToolRecommendation.id.in_(ids))).scalars().all()
    now = datetime.datetime.now(datetime.timezone.utc)
    tools_created = []
    for item in items:
        item.status = status
        item.updated_at = now
        if status == "adopted":
            tool, created = _ensure_tool(session, item)
            if created:
                tools_created.append(tool.id)
    session.commit()
    return jsonify({"updated": len(items), "status": status, "tools_created": tools_created})
