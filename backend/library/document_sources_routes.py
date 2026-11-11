"""Flask blueprint: reviewing one information source of a document.

  PATCH /document/<id>/information_sources/<link_id>
        {name?, source_type?, role?, review_status?: approved|needs_review|rejected}
        rename / retype / approve / reject the link; answers the updated entry.
        A rejected link is hidden from GET /document/<id>/information_sources (``?include_rejected=1`` lists it).

Listing and the plain approve live in ``server.py`` (``GET /document/<id>/information_sources``,
``POST .../<link_id>/approve``); the rules are in ``library/document_source_review.py``.
"""

import logging

from flask import Blueprint, jsonify, request

from library.db.engine import get_scoped_session
from library.document_source_review import update_document_source_link
from library.geopolitics_service import GeopoliticsError

logger = logging.getLogger(__name__)

bp = Blueprint("document_sources", __name__)


@bp.route("/document/<int:doc_id>/information_sources/<int:link_id>", methods=["PATCH"])
def document_information_source_update(doc_id: int, link_id: int):
    session = get_scoped_session()
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"status": "error", "message": "Wymagany obiekt JSON"}), 400
    try:
        entry = update_document_source_link(session, doc_id, link_id, data)
        session.commit()
    except GeopoliticsError as exc:
        session.rollback()
        return jsonify({"status": "error", "message": exc.message}), exc.status
    except Exception:
        session.rollback()
        logger.exception("information source link %s of document %s update failed", link_id, doc_id)
        return jsonify({"status": "error", "message": "Błąd zapisu źródła"}), 500
    return jsonify({"status": "success", "entry": entry}), 200
