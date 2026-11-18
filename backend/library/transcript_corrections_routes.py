"""Service-key writes and document-by-document previews of STT corrections."""

import datetime
from collections import Counter

from flask import Blueprint, abort, g, jsonify, request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from library.db.engine import get_scoped_session
from library.db.models import Document, TranscriptCorrection, TranscriptCorrectionApplication
from library.transcript_corrections import (
    TranscriptCorrectionValidationError, _bump_hit_counts, bust_cache, correct_text_detailed,
    country_slugs_from_tags, load_active_rules, normalize_author, replace_phrase, validate_one_off, validate_rule,
)

bp = Blueprint("transcript_corrections", __name__)
_MATCH_FIELDS = ("pattern", "replacement", "scope", "author", "country_slug")


def _require_service() -> None:
    if getattr(getattr(g, "auth", None), "kind", None) != "service":
        abort(403, "Zapis reguł wymaga klucza service")


def _require_writer() -> None:
    # Reviewers fix a transcript slip from the web UI (/ner/:id) with their own household key.
    if getattr(getattr(g, "auth", None), "kind", None) not in ("service", "user"):
        abort(403, "Zapis reguł wymaga klucza service lub user")


def _body() -> dict:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, "Wymagany obiekt JSON")
    if "note" in data and data["note"] is not None and not isinstance(data["note"], str):
        abort(400, "note musi być tekstem")
    if "active" in data and type(data["active"]) is not bool:
        abort(400, "active musi być wartością logiczną")
    return data


def _serialize(rule) -> dict:
    return {
        column.name: (value.isoformat() if isinstance(value, datetime.datetime) else value)
        for column in TranscriptCorrection.__table__.columns
        for value in [getattr(rule, column.name)]
    }


def _values(data, rule=None):
    values = {key: data.get(key, getattr(rule, key, None)) for key in _MATCH_FIELDS}
    if rule is None and "scope" not in data:
        values["scope"] = "global"
    validate_rule(**values)
    values["pattern"] = values["pattern"].strip()
    values["author"] = normalize_author(values["author"])
    if isinstance(values["country_slug"], str):
        values["country_slug"] = values["country_slug"].strip().casefold()
    return values


def _commit(session):
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        abort(409, "Regula o takim wzorcu i zakresie juz istnieje")
    except Exception:
        session.rollback()
        raise


@bp.get("/transcript_corrections")
def list_rules():
    query = select(TranscriptCorrection).order_by(TranscriptCorrection.id)
    if "active" in request.args:
        if request.args["active"] not in ("0", "1"):
            abort(400, "active musi być 0 lub 1")
        query = query.where(TranscriptCorrection.active.is_(request.args["active"] == "1"))
    if "scope" in request.args:
        scopes = [scope.strip() for scope in request.args["scope"].split(",") if scope.strip()]
        query = query.where(TranscriptCorrection.scope == scopes[0] if len(scopes) == 1
                            else TranscriptCorrection.scope.in_(scopes))
    if "author" in request.args:
        query = query.where(TranscriptCorrection.author == normalize_author(request.args["author"]))
    if "country_slug" in request.args:
        query = query.where(TranscriptCorrection.country_slug == request.args["country_slug"].strip().casefold())
    session = get_scoped_session()
    # Optional pagination (the dictionary page); without limit every rule is returned as before.
    if "limit" in request.args or "offset" in request.args:
        try:
            limit = int(request.args.get("limit", 50))
            offset = int(request.args.get("offset", 0))
        except ValueError:
            abort(400, "limit i offset muszą być liczbami całkowitymi")
        if not 1 <= limit <= 200 or offset < 0:
            abort(400, "limit musi być 1–200, a offset nieujemny")
        total = session.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
        rules = session.scalars(query.limit(limit).offset(offset)).all()
        return jsonify({"status": "success", "total": total, "limit": limit, "offset": offset,
                        "rules": [_serialize(rule) for rule in rules]})
    rules = session.scalars(query).all()
    return jsonify({"status": "success", "total": len(rules), "rules": [_serialize(rule) for rule in rules]})


@bp.post("/transcript_corrections")
def add_rule():
    _require_writer()
    data = _body()
    try:
        values = _values(data)
    except TranscriptCorrectionValidationError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    rule = TranscriptCorrection(
        **values, note=data.get("note"), active=data.get("active", True), hit_count=0,
        created_by=str(getattr(g.auth, "key_name", None) or getattr(g.auth, "user_id", None) or "service")[:100],
    )
    session = get_scoped_session()
    session.add(rule)
    _commit(session)
    bust_cache()
    return jsonify({"status": "success", "rule": _serialize(rule)}), 201


@bp.patch("/transcript_corrections/<int:rule_id>")
def patch_rule(rule_id):
    _require_service()
    data = _body()
    session = get_scoped_session()
    rule = session.get(TranscriptCorrection, rule_id)
    if rule is None:
        abort(404, "Nie znaleziono reguły")
    if any(key in data for key in _MATCH_FIELDS):
        try:
            values = _values(data, rule)
        except TranscriptCorrectionValidationError as exc:
            return jsonify({"status": "error", "message": str(exc)}), 400
        for key, value in values.items():
            setattr(rule, key, value)
    for key in ("active", "note"):
        if key in data:
            setattr(rule, key, data[key])
    _commit(session)
    bust_cache()
    return jsonify({"status": "success", "rule": _serialize(rule)})


@bp.delete("/transcript_corrections/<int:rule_id>")
def delete_rule(rule_id):
    _require_service()
    session = get_scoped_session()
    rule = session.get(TranscriptCorrection, rule_id)
    if rule is None:
        abort(404, "Nie znaleziono reguły")
    session.delete(rule)
    _commit(session)
    bust_cache()
    return jsonify({"status": "success"})


def _snippet(before, after):
    index = next((i for i, (a, b) in enumerate(zip(before, after)) if a != b), min(len(before), len(after)))
    start = max(0, index - 60)
    return {"before": before[start:index + 100], "after": after[start:index + 100]}


def _parse_rule_ids(data):
    """The optional ``rule_ids`` list of ``apply`` (only these rules may change the text), or ``None``."""
    if "rule_ids" not in data:
        return None
    rule_ids = data["rule_ids"]
    if "pattern" in data:
        abort(400, "rule_ids nie łączy się z pattern (zamiana jednorazowa nie używa reguł)")
    if (not isinstance(rule_ids, list) or not rule_ids or len(rule_ids) > 500
            or any(type(item) is not int or item <= 0 for item in rule_ids)):
        abort(400, "rule_ids musi być niepustą listą dodatnich liczb całkowitych (maks. 500)")
    return set(rule_ids)


def _group_changes(changes, rules):
    """Real changes (``(rule_id, original, replacement, chapter)`` per match) grouped by rule for the review UI."""
    by_rule = {rule.id: rule for rule in rules}
    groups = {}
    for rule_id, original, replacement, chapter in changes:
        rule = by_rule.get(rule_id)
        group = groups.setdefault(rule_id, {
            "rule_id": rule_id, "scope": getattr(rule, "scope", None), "country_slug": getattr(rule, "country_slug", None),
            "pattern": getattr(rule, "pattern", original), "replacement": getattr(rule, "replacement", replacement),
            "occurrences": 0, "chapters": set(), "wordings": {},
        })
        group["occurrences"] += 1
        group["chapters"].add(chapter)
        wording = group["wordings"].setdefault((original, replacement), 0)
        group["wordings"][(original, replacement)] = wording + 1
    result = []
    for group in groups.values():
        group["chapters"] = sorted(group["chapters"])
        group["wordings"] = [{"original": original, "replacement": replacement, "occurrences": count}
                             for (original, replacement), count in sorted(group["wordings"].items(),
                                                                          key=lambda item: (-item[1], item[0][0]))]
        result.append(group)
    return sorted(result, key=lambda group: (group["chapters"][0], group["rule_id"]))


def _record_applications(session, document_id, changes) -> None:
    """Audit what really changed: one row per (rule, original wording, replacement, chapter)."""
    for (rule_id, original, replacement, chapter), count in Counter(changes).items():
        session.add(TranscriptCorrectionApplication(
            document_id=document_id, rule_id=rule_id or None, original_text=original,
            replacement_text=replacement, chapter_position=chapter, occurrences=count,
        ))


@bp.get("/document/<int:document_id>/transcript_corrections")
def document_corrections(document_id):
    """What the stored dictionaries did to this document, and what they would still change."""
    from library.country_gazetteer import slug_to_name

    session = get_scoped_session()
    doc = session.get(Document, document_id)
    if doc is None:
        abort(404, "Nie znaleziono dokumentu")
    countries = country_slugs_from_tags(doc.tags)
    rows = session.execute(
        select(TranscriptCorrectionApplication, TranscriptCorrection.scope, TranscriptCorrection.country_slug)
        .outerjoin(TranscriptCorrection, TranscriptCorrection.id == TranscriptCorrectionApplication.rule_id)
        .where(TranscriptCorrectionApplication.document_id == document_id)
        .order_by(TranscriptCorrectionApplication.chapter_position, TranscriptCorrectionApplication.id)
    ).all()
    merged = {}
    for application, scope, country_slug in rows:
        key = (application.rule_id, application.original_text, application.replacement_text,
               application.chapter_position)
        entry = merged.setdefault(key, {
            "rule_id": application.rule_id, "scope": scope, "country_slug": country_slug,
            "original_text": application.original_text, "replacement_text": application.replacement_text,
            "chapter_position": application.chapter_position, "occurrences": 0, "applied_at": None,
        })
        entry["occurrences"] += application.occurrences
        entry["applied_at"] = application.applied_at.isoformat() if application.applied_at else None
    rules = load_active_rules(session=session)
    by_country = Counter()
    for rule in rules:
        if rule.scope != "region" or (rule.country_slug or "") not in countries:
            continue
        if rule.author and normalize_author(rule.author) != normalize_author(doc.byline):
            continue
        by_country[rule.country_slug] += 1
    pending = len(correct_text_detailed(doc.text or "", doc.byline, rules, countries)[2])
    return jsonify({
        "status": "success", "document_id": document_id, "author": doc.byline,
        "applications": list(merged.values()),
        "dictionaries": [
            {"country_slug": slug, "country_name": slug_to_name(slug.removeprefix("kraj-")), "rules": count}
            for slug, count in sorted(by_country.items())
        ],
        "pending_changes": pending,
    })


@bp.post("/transcript_corrections/apply")
def apply_rules():
    _require_writer()
    data = _body()
    document_id = data.get("document_id")
    dry_run = data.get("dry_run", True)
    if type(document_id) is not int or document_id <= 0:
        abort(400, "document_id musi być dodatnią liczbą całkowitą")
    if type(dry_run) is not bool:
        abort(400, "dry_run musi być wartością logiczną")
    rule_ids = _parse_rule_ids(data)
    session = get_scoped_session()
    doc = session.get(Document, document_id)
    if doc is None:
        abort(404, "Nie znaleziono dokumentu")
    # `pattern` + `replacement` = a one-document replacement: no stored rule, no statistics, one word allowed.
    one_off = "pattern" in data
    if one_off:
        try:
            validate_one_off(pattern=data.get("pattern"), replacement=data.get("replacement"))
        except TranscriptCorrectionValidationError as exc:
            abort(400, str(exc))
        rules = []
    else:
        rules = load_active_rules(session=session)
        if rule_ids is not None:  # the reviewer ticked only some of the pending changes
            rules = [rule for rule in rules if rule.id in rule_ids]
    # A region rule fires only for the countries the document is tagged with (kraj-<slug>).
    countries = country_slugs_from_tags(doc.tags)
    hits = Counter()
    fields = {}
    changes = []
    for field in ("text", "text_md"):
        before = getattr(doc, field)
        if not before:
            continue
        if one_off:
            after, count = replace_phrase(before, data["pattern"].strip(), data["replacement"])
            field_hits = [(0, count)] if count else []
        else:
            after, field_hits, field_changes = correct_text_detailed(before, doc.byline, rules, countries)
            if field == "text":  # text_md repeats the same words; count them once
                changes = field_changes
        hits.update(dict(field_hits))
        fields[field] = {"hits": [{"rule_id": rule_id, "count": count} for rule_id, count in field_hits],
                         "changed": before != after, "snippet": _snippet(before, after) if before != after else None}
        if not dry_run and before != after:
            setattr(doc, field, after)
    if not dry_run:
        if not one_off:
            _record_applications(session, document_id, changes)
        _commit(session)
        if not one_off:
            _bump_hit_counts(list(hits.items()))
    return jsonify({"status": "success", "document_id": document_id, "dry_run": dry_run, "fields": fields,
                    "countries": sorted(countries),
                    "hits": [{"rule_id": rule_id, "count": count} for rule_id, count in sorted(hits.items())],
                    "changes": _group_changes(changes, rules)})
