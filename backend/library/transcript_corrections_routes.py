"""Service-key writes and document-by-document previews of STT corrections."""

import datetime
from collections import Counter

from flask import Blueprint, abort, g, jsonify, request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from library.db.engine import get_scoped_session
from library.db.models import Document, TranscriptCorrection
from library.transcript_corrections import (
    TranscriptCorrectionValidationError, _bump_hit_counts, bust_cache, correct_text,
    load_active_rules, normalize_author, validate_rule,
)

bp = Blueprint("transcript_corrections", __name__)
_MATCH_FIELDS = ("pattern", "replacement", "scope", "author")


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
        query = query.where(TranscriptCorrection.scope == request.args["scope"])
    if "author" in request.args:
        query = query.where(TranscriptCorrection.author == normalize_author(request.args["author"]))
    rules = get_scoped_session().scalars(query).all()
    return jsonify({"status": "success", "rules": [_serialize(rule) for rule in rules]})


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
    session = get_scoped_session()
    doc = session.get(Document, document_id)
    if doc is None:
        abort(404, "Nie znaleziono dokumentu")
    rules = load_active_rules(session=session)
    hits = Counter()
    fields = {}
    for field in ("text", "text_md"):
        before = getattr(doc, field)
        if not before:
            continue
        after, field_hits = correct_text(before, doc.byline, rules)
        hits.update(dict(field_hits))
        fields[field] = {"hits": [{"rule_id": rule_id, "count": count} for rule_id, count in field_hits],
                         "changed": before != after, "snippet": _snippet(before, after) if before != after else None}
        if not dry_run and before != after:
            setattr(doc, field, after)
    if not dry_run:
        _commit(session)
        _bump_hit_counts(list(hits.items()))
    return jsonify({"status": "success", "document_id": document_id, "dry_run": dry_run, "fields": fields,
                    "hits": [{"rule_id": rule_id, "count": count} for rule_id, count in sorted(hits.items())]})
