"""Flask blueprint: the registry of concepts and the decisions about ``conceptName`` mentions.

Endpoints (x-api-key required via the global before_request; writes are blocked for read_only keys there):
  GET    /concepts?q=&limit=&offset=          — registry concepts with aliases and the documents that mention them
  POST   /concepts                            — {name, description?, aliases?}: a name already owned answers the existing one
  GET    /concepts/<id>                       — one concept with all its documents
  PATCH  /concepts/<id>                       — {name?, description?, aliases?: [new names to add]}
  DELETE /concepts/<id>                       — removes the concept, its aliases and links (mentions in documents stay)
  DELETE /concepts/<id>/aliases/<alias_id>
  GET    /concepts/unlinked?q=&limit=&offset= — concept mentions with no confirmed link, with suggestions
  GET    /concepts/candidates?name=           — concepts a name may mean (alias first, then similar)
  POST   /concepts/mentions/link              — {name, concept_id, document_ids?}
  POST   /concepts/mentions/reject            — {name, concept_id}: do not suggest this concept for this name
  POST   /concepts/mentions/unlink            — {name, concept_id, document_id?}
  POST   /concepts/from_mention               — {name, description?}: create + link
"""

import logging

from flask import Blueprint, g, jsonify, request

from library.concept_service import (
    ConceptError,
    concept_to_dict,
    create_concept,
    create_concept_from_mention,
    delete_concept,
    find_concepts_by_name,
    get_concept,
    link_mentions,
    list_concepts,
    reject_suggestion,
    remove_alias,
    unlink_mentions,
    unlinked_mentions,
    update_concept,
)
from library.db.engine import get_scoped_session

logger = logging.getLogger(__name__)

bp = Blueprint("concepts", __name__)


@bp.errorhandler(Exception)
def _unexpected_error(exc):
    from werkzeug.exceptions import HTTPException

    if isinstance(exc, HTTPException):
        return exc
    logger.exception("concepts request failed")
    return jsonify(
        {"status": "error", "message": f"Błąd serwera ({type(exc).__name__}); szczegóły w logu backendu"}
    ), 500


def _user_id() -> int | None:
    return getattr(getattr(g, "auth", None), "user_id", None)


def _error(exc: ConceptError):
    return jsonify({"status": "error", "message": exc.message}), exc.status


def _int_arg(name: str, default: int, maximum: int) -> int:
    try:
        return max(0, min(int(request.args.get(name, default)), maximum))
    except (TypeError, ValueError):
        return default


@bp.route("/concepts", methods=["GET"])
def get_concepts():
    session = get_scoped_session()
    items, total = list_concepts(
        session,
        q=request.args.get("q") or None,
        limit=_int_arg("limit", 50, 200) or 50,
        offset=_int_arg("offset", 0, 1_000_000),
    )
    return jsonify({"status": "success", "total": total, "concepts": items})


@bp.route("/concepts", methods=["POST"])
def post_concept():
    data = request.get_json(silent=True) or {}
    session = get_scoped_session()
    try:
        concept, created = create_concept(
            session,
            name=data.get("name"),
            description=data.get("description"),
            aliases=data.get("aliases") or [],
            user_id=_user_id(),
        )
        session.commit()
        return jsonify({"status": "success", "created": created, "concept": get_concept(session, concept.id)}), (
            201 if created else 200
        )
    except ConceptError as exc:
        session.rollback()
        return _error(exc)


@bp.route("/concepts/unlinked", methods=["GET"])
def get_unlinked():
    session = get_scoped_session()
    items, total = unlinked_mentions(
        session,
        q=request.args.get("q") or None,
        limit=_int_arg("limit", 50, 200) or 50,
        offset=_int_arg("offset", 0, 1_000_000),
    )
    return jsonify({"status": "success", "total": total, "mentions": items})


@bp.route("/concepts/candidates", methods=["GET"])
def get_candidates():
    name = (request.args.get("name") or "").strip()
    if not name:
        return jsonify({"status": "error", "message": "name is required"}), 400
    return jsonify({"status": "success", "candidates": find_concepts_by_name(get_scoped_session(), name)})


@bp.route("/concepts/<int:concept_id>", methods=["GET"])
def get_one(concept_id: int):
    try:
        return jsonify({"status": "success", "concept": get_concept(get_scoped_session(), concept_id)})
    except ConceptError as exc:
        return _error(exc)


@bp.route("/concepts/<int:concept_id>", methods=["PATCH"])
def patch_concept(concept_id: int):
    data = request.get_json(silent=True) or {}
    session = get_scoped_session()
    try:
        update_concept(
            session,
            concept_id,
            name=data.get("name"),
            description=data["description"] if "description" in data else ...,
            aliases=data.get("aliases"),
        )
        session.commit()
        return jsonify({"status": "success", "concept": get_concept(session, concept_id)})
    except ConceptError as exc:
        session.rollback()
        return _error(exc)


@bp.route("/concepts/<int:concept_id>", methods=["DELETE"])
def delete_one(concept_id: int):
    session = get_scoped_session()
    try:
        delete_concept(session, concept_id)
        session.commit()
        return jsonify({"status": "success"})
    except ConceptError as exc:
        session.rollback()
        return _error(exc)


@bp.route("/concepts/<int:concept_id>/aliases/<int:alias_id>", methods=["DELETE"])
def delete_alias(concept_id: int, alias_id: int):
    session = get_scoped_session()
    try:
        remove_alias(session, concept_id, alias_id)
        session.commit()
        return jsonify({"status": "success", "concept": get_concept(session, concept_id)})
    except ConceptError as exc:
        session.rollback()
        return _error(exc)


def _mention_action(action):
    data = request.get_json(silent=True) or {}
    name, concept_id = data.get("name"), data.get("concept_id")
    if not isinstance(name, str) or not name.strip() or not isinstance(concept_id, int):
        return jsonify({"status": "error", "message": "name and concept_id are required"}), 400
    session = get_scoped_session()
    try:
        changed = action(session, name, concept_id, data)
        session.commit()
        return jsonify({"status": "success", "changed": changed})
    except ConceptError as exc:
        session.rollback()
        return _error(exc)


@bp.route("/concepts/mentions/link", methods=["POST"])
def post_link():
    return _mention_action(
        lambda s, name, cid, d: link_mentions(s, name, cid, document_ids=d.get("document_ids"), user_id=_user_id())
    )


@bp.route("/concepts/mentions/reject", methods=["POST"])
def post_reject():
    return _mention_action(lambda s, name, cid, d: reject_suggestion(s, name, cid, user_id=_user_id()))


@bp.route("/concepts/mentions/unlink", methods=["POST"])
def post_unlink():
    return _mention_action(lambda s, name, cid, d: unlink_mentions(s, name, cid, document_id=d.get("document_id")))


@bp.route("/concepts/from_mention", methods=["POST"])
def post_from_mention():
    data = request.get_json(silent=True) or {}
    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        return jsonify({"status": "error", "message": "name is required"}), 400
    session = get_scoped_session()
    try:
        concept, created, linked = create_concept_from_mention(
            session, name, description=data.get("description"), user_id=_user_id()
        )
        session.commit()
        return (
            jsonify(
                {"status": "success", "created": created, "linked": linked, "concept": concept_to_dict(concept)}
            ),
            201 if created else 200,
        )
    except ConceptError as exc:
        session.rollback()
        return _error(exc)
