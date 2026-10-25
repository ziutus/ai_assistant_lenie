"""Place registry API: browse places across documents, set Wikipedia link/aliases. Auth: server.before_request."""

import logging

from flask import Blueprint, jsonify, request

from library import place_registry as registry
from library.db.engine import get_scoped_session

bp = Blueprint("places", __name__)
logger = logging.getLogger(__name__)


@bp.errorhandler(ValueError)
def invalid_request(exc):
    get_scoped_session().rollback()
    return jsonify(status="error", message=str(exc)), 400


@bp.get("/places")
def places_list():
    limit = int(request.args.get("limit", "50"))
    offset = int(request.args.get("offset", "0"))
    if not 1 <= limit <= 100 or offset < 0:
        raise ValueError("limit must be between 1 and 100; offset must be non-negative")
    items, total = registry.list_places(
        get_scoped_session(), query=request.args.get("q", ""),
        only_with_wikipedia=request.args.get("with_wikipedia") in {"1", "true"}, limit=limit, offset=offset,
    )
    return jsonify(status="success", places=items, total=total)


@bp.get("/places/detail")
def places_detail():
    name = (request.args.get("name") or "").strip()
    if not name:
        raise ValueError("name is required")
    return jsonify(status="success", **registry.place_detail(get_scoped_session(), name))


@bp.put("/places/profile")
def places_profile_save():
    """Body: {"name": str, "wikipedia_url"?: str|null, "aliases"?: [str], "note"?: str|null}; absent keys are kept."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get("name"), str):
        raise ValueError("Pole name jest wymagane.")
    fields = {k for k in ("wikipedia_url", "aliases", "note") if k in data}
    if "aliases" in fields and not (isinstance(data["aliases"], list) and all(isinstance(a, str) for a in data["aliases"])):
        raise ValueError("Pole aliases musi być listą nazw.")
    session = get_scoped_session()
    try:
        profile = registry.upsert_profile(
            session, data["name"], wikipedia_url=data.get("wikipedia_url"), aliases=data.get("aliases"),
            note=data.get("note"), set_fields=fields,
        )
        session.commit()
    except ValueError:
        raise
    except Exception:
        session.rollback()
        logger.exception("place profile save failed for %r", data.get("name"))
        return jsonify(status="error", message="Nie udało się zapisać profilu miejsca."), 500
    return jsonify(status="success", profile=registry.profile_to_dict(profile))
