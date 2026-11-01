"""REST catalog of feed review reasons; writes require a service key."""

import datetime
from dataclasses import asdict

from flask import Blueprint, abort, g, jsonify, request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from library import feed_review_reason_store as store
from library.db.engine import get_scoped_session
from library.db.models import FeedItem, FeedReviewDecision, FeedReviewReason

bp = Blueprint("feed_review_reasons", __name__)
_PATCHABLE = ("label", "sort_order", "active", "selectable")


def _require_service():
    if getattr(getattr(g, "auth", None), "kind", None) != "service":
        abort(403, "Zapis powodów pominięcia wymaga klucza service")


def _body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, "Wymagany obiekt JSON")
    return data


def _error(message, status):
    return jsonify(status="error", message=message), status


def _serialize(row):
    return {
        column.name: value.isoformat() if isinstance(value, datetime.datetime) else value
        for column in FeedReviewReason.__table__.columns
        for value in [getattr(row, column.name)]
    }


def _usage(session, code):
    """Rows that still point at the reason; the review history counts too, because undoing a decision restores it."""
    items = session.scalar(select(func.count()).select_from(FeedItem).where(FeedItem.review_reason == code)) or 0
    history = (
        session.scalar(
            select(func.count()).select_from(FeedReviewDecision).where(FeedReviewDecision.previous_review_reason == code)
        )
        or 0
    )
    return items + history


@bp.get("/feed_review_reasons")
def list_reasons():
    if request.args.get("selectable") == "1":
        return jsonify(status="success", reasons=[asdict(row) for row in store.selectable_reasons()])
    session = get_scoped_session()
    counts = dict(
        session.execute(
            select(FeedItem.review_reason, func.count()).group_by(FeedItem.review_reason),
        ).all()
    )
    rows = session.scalars(
        select(FeedReviewReason).order_by(
            FeedReviewReason.sort_order,
            FeedReviewReason.code,
        )
    ).all()
    return jsonify(
        status="success", reasons=[{**_serialize(row), "usage_count": counts.get(row.code, 0)} for row in rows]
    )


@bp.post("/feed_review_reasons")
def add_reason():
    _require_service()
    data = _body()
    if set(data) - {"code", "label", "sort_order"}:
        return _error("Dozwolone pola: code, label, sort_order", 400)
    values, problem = store.check_reason(
        code=data.get("code"),
        label=data.get("label"),
        sort_order=data.get("sort_order", 100),
    )
    if problem:
        return _error(problem, 400)
    session = get_scoped_session()
    if session.get(FeedReviewReason, values["code"]) is not None:
        return _error("Powód o tym kodzie już istnieje", 409)
    row = FeedReviewReason(**values, system=False)
    try:
        session.add(row)
        session.commit()
    except IntegrityError:
        session.rollback()
        return _error("Powód o tym kodzie już istnieje", 409)
    except Exception:
        session.rollback()
        raise
    store.bust_cache()
    return jsonify(status="success", reason=_serialize(row)), 201


@bp.patch("/feed_review_reasons/<code>")
def patch_reason(code):
    _require_service()
    data = _body()
    session = get_scoped_session()
    row = session.get(FeedReviewReason, code)
    if row is None:
        abort(404, "Nie znaleziono powodu")
    allowed = {"label", "sort_order"} if row.system else set(_PATCHABLE)
    if set(data) - allowed:
        return _error(
            "Niedozwolone pola; kod jest niezmienny, a powód systemowy pozwala zmienić tylko etykietę i kolejność", 400
        )
    merged = {key: getattr(row, key) for key in _PATCHABLE}
    merged.update(data)
    values, problem = store.check_reason(code=code, **merged)
    if problem:
        return _error(problem, 400)
    try:
        for key in _PATCHABLE:
            setattr(row, key, values[key])
        row.updated_at = datetime.datetime.now(datetime.timezone.utc)
        session.commit()
    except Exception:
        session.rollback()
        raise
    store.bust_cache()
    return jsonify(status="success", reason=_serialize(row))


@bp.delete("/feed_review_reasons/<code>")
def delete_reason(code):
    _require_service()
    session = get_scoped_session()
    row = session.get(FeedReviewReason, code)
    if row is None:
        abort(404, "Nie znaleziono powodu")
    if row.system:
        return _error(
            "Nie można usunąć powodu systemowego; dezaktywacja jest dostępna tylko dla powodów użytkownika", 409
        )
    if _usage(session, code):
        return _error("Powód jest używany; dezaktywuj go zamiast usuwać", 409)
    try:
        session.delete(row)
        session.commit()
    except IntegrityError:
        session.rollback()
        return _error("Powód jest używany; dezaktywuj go zamiast usuwać", 409)
    except Exception:
        session.rollback()
        raise
    store.bust_cache()
    return jsonify(status="success", deleted_code=code)
