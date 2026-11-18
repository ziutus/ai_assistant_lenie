"""REST for the countries / macro-regions a person is tied to (see library/person_territories.py).

Reads accept any valid key; writes need a ``user`` or ``service`` key (the same rule as the other person editors).
"""

import datetime
import logging

from flask import Blueprint, abort, g, jsonify, request

from library import person_territories
from library.db.engine import get_scoped_session
from library.db.models import Person
from library.geopolitical_region_gazetteer import known_geopolitical_regions

bp = Blueprint("person_territories", __name__)
logger = logging.getLogger(__name__)


def _writer() -> None:
    if getattr(g, "auth", None) is None or g.auth.kind not in {"user", "service"}:
        abort(403, "user or service API key required")


def _on_date():
    value = request.args.get("on")
    if not value:
        return None
    try:
        return datetime.date.fromisoformat(value)
    except ValueError:
        abort(400, "on must be an ISO date (YYYY-MM-DD)")


@bp.get("/persons/<int:person_id>/territories")
def list_person_territories(person_id: int):
    """Ties of one person, candidates from their documents, and the lists the editor offers."""
    session = get_scoped_session()
    if session.get(Person, person_id) is None:
        abort(404, "Person not found")
    return jsonify({
        "status": "success",
        "territories": person_territories.list_territories(session, person_id),
        "suggestions": person_territories.territory_suggestions(session, person_id),
        "relations": person_territories.RELATIONS,
        "regions": known_geopolitical_regions(),
    })


@bp.post("/persons/<int:person_id>/territories")
def add_person_territory(person_id: int):
    """Body ``{"kind": "country"|"region", "slug": "jemen", "relation": "holds_office_in", "note"?, "valid_from"?,
    "valid_to"?}``; 201 when created, 200 when the (kind, slug, relation) tie already existed (note/dates refreshed)."""
    _writer()
    session = get_scoped_session()
    if session.get(Person, person_id) is None:
        abort(404, "Person not found")
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, "JSON object required")
    try:
        tie, created = person_territories.add_territory(
            session, person_id, data.get("kind"), data.get("slug"), data.get("relation"),
            note=data.get("note"), valid_from=data.get("valid_from"), valid_to=data.get("valid_to"))
        session.commit()
    except person_territories.TerritoryError as exc:
        session.rollback()
        # a fixed text per error code, never the exception's own message
        return jsonify({"status": "error", "message": person_territories.ERROR_MESSAGES.get(exc.code, "invalid tie")}), 400
    except Exception:
        session.rollback()
        logger.exception("person territory add failed for %s", person_id)
        return jsonify({"status": "error", "message": "DB error"}), 500
    return jsonify({"status": "success", "territory": tie}), 201 if created else 200


@bp.delete("/persons/<int:person_id>/territories/<int:row_id>")
def delete_person_territory(person_id: int, row_id: int):
    _writer()
    session = get_scoped_session()
    try:
        removed = person_territories.remove_territory(session, person_id, row_id)
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("person territory delete failed for %s/%s", person_id, row_id)
        return jsonify({"status": "error", "message": "DB error"}), 500
    if not removed:
        return jsonify({"status": "error", "message": "Territory tie not found"}), 404
    return jsonify({"status": "success"})


@bp.get("/territories/<kind>/<slug>/persons")
def persons_of_territory(kind: str, slug: str):
    """People tied to one country (``/territories/country/jemen/persons``) or macro-region
    (``/territories/region/bliski-wschod/persons``); ``?on=YYYY-MM-DD`` keeps ties valid on that day."""
    name = person_territories.territory_name(kind, slug)
    if name is None:
        abort(404, "Unknown territory")
    session = get_scoped_session()
    return jsonify({
        "status": "success", "kind": kind, "slug": slug, "name_pl": name,
        "persons": person_territories.persons_for_territories(session, {(kind, slug)}, on=_on_date()),
    })


@bp.get("/document/<int:document_id>/territory_persons")
def document_territory_persons(document_id: int):
    """The countries / regions a document is tagged with and the people tied to them — the candidate list for
    picking between namesakes and for repairing mangled names of this document."""
    session = get_scoped_session()
    result = person_territories.persons_for_document(session, document_id, on=_on_date())
    if result is None:
        abort(404, "Document not found")
    return jsonify({"status": "success", "document_id": document_id, **result})
