"""API reguł czyszczenia; zapis dostępny wyłącznie dla kluczy service."""

import datetime

from flask import Blueprint, abort, g, jsonify, request
from sqlalchemy import select

from library.cleanup_rules import CleanupRuleValidationError, bust_cache, validate_rule
from library.db.engine import get_scoped_session
from library.db.models import CleanupRule, DocumentRemovedLine
from library.publisher_domain import normalize_publisher_domain

bp = Blueprint("cleanup_rules", __name__)
_MATCH_FIELDS = ("scope", "domain", "match_type", "pattern")


def _require_service() -> None:
    if getattr(getattr(g, "auth", None), "kind", None) != "service":
        abort(403, "Zapis reguł wymaga klucza service")


def _body() -> dict:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, "Wymagany obiekt JSON")
    if "note" in data and data["note"] is not None and not isinstance(data["note"], str):
        abort(400, "note musi być tekstem")
    return data


def _serialize(rule) -> dict:
    return {
        column.name: (value.isoformat() if isinstance(value, datetime.datetime) else value)
        for column in CleanupRule.__table__.columns
        for value in [getattr(rule, column.name)]
    }


@bp.get("/cleanup_rules")
def list_rules():
    query = select(CleanupRule).order_by(CleanupRule.id)
    if "active" in request.args:
        active = request.args["active"]
        if active not in ("0", "1"):
            abort(400, "active musi być 0 lub 1")
        query = query.where(CleanupRule.active.is_(active == "1"))
    if "scope" in request.args:
        query = query.where(CleanupRule.scope == request.args["scope"])
    if "domain" in request.args:
        query = query.where(CleanupRule.domain == normalize_publisher_domain(request.args["domain"]))
    rules = get_scoped_session().scalars(query).all()
    return jsonify({"status": "success", "rules": [_serialize(rule) for rule in rules]})


@bp.post("/cleanup_rules")
def add_rule():
    _require_service()
    data = _body()
    values = {key: data.get(key) for key in _MATCH_FIELDS}
    try:
        validate_rule(**values)
    except CleanupRuleValidationError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    source_id = data.get("source_removed_line_id")
    if source_id is not None and (type(source_id) is not int or source_id <= 0):
        abort(400, "source_removed_line_id musi być dodatnią liczbą całkowitą")
    session = get_scoped_session()
    source = session.get(DocumentRemovedLine, source_id) if source_id is not None else None
    values["domain"] = normalize_publisher_domain(values["domain"])
    rule = CleanupRule(
        **values, note=data.get("note"), active=True, hit_count=0,
        source_removed_line_id=source.id if source is not None else None,
        created_by=str(getattr(g.auth, "key_name", None) or getattr(g.auth, "user_id", None) or "service")[:100],
    )
    try:
        session.add(rule)
        session.flush()
        if source is not None:
            source.review_status = "rule_added"
            source.rule_reference = f"cleanup_rules:{rule.id}"
            source.reviewed_at = datetime.datetime.now()
        session.commit()
    except Exception:
        session.rollback()
        raise
    bust_cache()
    return jsonify({"status": "success", "rule": _serialize(rule)}), 201


@bp.patch("/cleanup_rules/<int:rule_id>")
def patch_rule(rule_id: int):
    _require_service()
    data = _body()
    if "active" in data and type(data["active"]) is not bool:
        abort(400, "active musi być wartością logiczną")
    session = get_scoped_session()
    rule = session.get(CleanupRule, rule_id)
    if rule is None:
        abort(404, "Nie znaleziono reguły")
    if any(key in data for key in _MATCH_FIELDS):
        try:
            validate_rule(**{key: data.get(key, getattr(rule, key)) for key in _MATCH_FIELDS})
        except CleanupRuleValidationError as exc:
            return jsonify({"status": "error", "message": str(exc)}), 400
    try:
        for key in (*_MATCH_FIELDS, "active", "note"):
            if key in data:
                setattr(rule, key, normalize_publisher_domain(data[key]) if key == "domain" else data[key])
        session.commit()
    except Exception:
        session.rollback()
        raise
    bust_cache()
    return jsonify({"status": "success", "rule": _serialize(rule)})


@bp.delete("/cleanup_rules/<int:rule_id>")
def delete_rule(rule_id: int):
    _require_service()
    session = get_scoped_session()
    rule = session.get(CleanupRule, rule_id)
    if rule is None:
        abort(404, "Nie znaleziono reguły")
    try:
        session.delete(rule)
        session.commit()
    except Exception:
        session.rollback()
        raise
    bust_cache()
    return jsonify({"status": "success"})
