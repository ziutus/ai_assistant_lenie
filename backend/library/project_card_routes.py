"""Flask blueprint: project cards (hands-on project library filterable by child age).

Endpoints (x-api-key required via the global before_request):
  GET   /project_cards                — paginated list (limit/offset/total); filters: age,
                                        stretch, max_difficulty, max_time, group, q,
                                        review_status, needs_adult
  GET   /project_cards/<id>           — full card
  PATCH /project_cards/<id>           — edit fields / mark reviewed
  POST  /project_cards/import         — bulk upsert {cards: [...], series?}

See ``library/project_cards.py`` for the age-filter semantics and import rules.
"""

import logging

from flask import Blueprint, jsonify, request

from library.db.engine import get_scoped_session
from library.db.models import ProjectCard
from library.project_cards import (
    DEFAULT_SERIES,
    REVIEW_STATUSES,
    ProjectCardError,
    card_to_dict,
    group_counts,
    list_cards,
    update_card,
    upsert_cards,
)

logger = logging.getLogger(__name__)

bp = Blueprint("project_cards", __name__)

MAX_IMPORT_CARDS = 500


def _error(message: str, status: int = 400):
    return jsonify({"status": "error", "message": message}), status


def _int_arg(name: str, low: int, high: int) -> int | None:
    raw = request.args.get(name)
    if raw in (None, ""):
        return None
    try:
        value = int(raw)
    except ValueError:
        raise ProjectCardError(f"{name} must be an integer") from None
    if not low <= value <= high:
        raise ProjectCardError(f"{name} must be between {low} and {high}")
    return value


def _bool_arg(name: str) -> bool | None:
    raw = request.args.get(name)
    if raw in (None, ""):
        return None
    if raw.lower() in {"1", "true", "yes"}:
        return True
    if raw.lower() in {"0", "false", "no"}:
        return False
    raise ProjectCardError(f"{name} must be true or false")


@bp.route("/project_cards", methods=["GET"])
def get_project_cards():
    session = get_scoped_session()
    try:
        age = _int_arg("age", 0, 18)
        stretch = _int_arg("stretch", 0, 5) or 0
        max_difficulty = _int_arg("max_difficulty", 1, 3)
        max_time = _int_arg("max_time", 1, 1440)
        needs_adult = _bool_arg("needs_adult")
        limit = _int_arg("limit", 1, 200) or 50
        offset = _int_arg("offset", 0, 100000) or 0
        review_status = request.args.get("review_status") or None
        if review_status and review_status not in REVIEW_STATUSES:
            raise ProjectCardError(f"review_status must be one of {', '.join(REVIEW_STATUSES)}")
    except ProjectCardError as exc:
        return _error(str(exc))
    cards, total = list_cards(
        session,
        age=age,
        stretch=stretch,
        max_difficulty=max_difficulty,
        max_time=max_time,
        group=request.args.get("group") or None,
        query=request.args.get("q") or None,
        review_status=review_status,
        needs_adult=needs_adult,
        limit=limit,
        offset=offset,
    )
    return jsonify({
        "status": "success",
        "total": total,
        "limit": limit,
        "offset": offset,
        "cards": [card_to_dict(card, age=age, stretch=stretch) for card in cards],
        "groups": group_counts(session),
        "review_statuses": list(REVIEW_STATUSES),
    })


@bp.route("/project_cards/<int:card_id>", methods=["GET"])
def get_project_card(card_id: int):
    card = get_scoped_session().get(ProjectCard, card_id)
    if card is None:
        return _error("Project card not found", 404)
    return jsonify({"status": "success", "card": card_to_dict(card, detail=True)})


@bp.route("/project_cards/<int:card_id>", methods=["PATCH"])
def patch_project_card(card_id: int):
    session = get_scoped_session()
    card = session.get(ProjectCard, card_id)
    if card is None:
        return _error("Project card not found", 404)
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not data:
        return _error("JSON object with fields to update is required")
    try:
        update_card(session, card, data)
    except ProjectCardError as exc:
        session.rollback()
        return _error(str(exc))
    return jsonify({"status": "success", "card": card_to_dict(card, detail=True)})


@bp.route("/project_cards/import", methods=["POST"])
def import_project_cards():
    data = request.get_json(silent=True)
    cards = data.get("cards") if isinstance(data, dict) else None
    if not isinstance(cards, list) or not cards:
        return _error("cards must be a non-empty list")
    if len(cards) > MAX_IMPORT_CARDS:
        return _error(f"at most {MAX_IMPORT_CARDS} cards per request")
    series = (data.get("series") or DEFAULT_SERIES).strip()
    session = get_scoped_session()
    try:
        result = upsert_cards(session, cards, series=series)
    except ProjectCardError as exc:
        session.rollback()
        return _error(str(exc))
    return jsonify({"status": "success", **result.as_dict()})
