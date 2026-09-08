"""Flask blueprint: typed links between two library documents.

Endpoints (x-api-key required via the global before_request):
  GET    /document/<doc_id>/links          — every link touching the document,
                                              resolved from its perspective
  POST   /document/<doc_id>/links           — create a link {to_document_id,
                                              relation, note?, direction?}
  POST   /document/<doc_id>/links/detect    — propose `references` links for
                                              other documents whose URL this
                                              document's text mentions
  PATCH  /document_links/<link_id>          — {status: confirmed|rejected}
  DELETE /document_links/<link_id>          — remove a link

See ``library/document_links_service.py`` for the relation vocabulary.
"""

import logging

from flask import Blueprint, g, jsonify, request

from library.db.engine import get_scoped_session
from library.db.models import Document, DocumentLink
from library.document_links_service import (
    RELATIONS,
    DocumentLinkError,
    create_link,
    delete_link,
    detect_url_mention_links,
    link_to_dict,
    list_document_links,
    set_link_status,
)

logger = logging.getLogger(__name__)

bp = Blueprint("document_links", __name__)


def _current_user_id() -> int | None:
    return getattr(getattr(g, "auth", None), "user_id", None)


@bp.route("/document/<int:doc_id>/links", methods=["GET"])
def get_document_links(doc_id: int):
    session = get_scoped_session()
    if session.get(Document, doc_id) is None:
        return jsonify({"status": "error", "message": "Document not found"}), 404
    include_rejected = request.args.get("include_rejected") in {"1", "true", "yes"}
    return jsonify({
        "status": "success",
        "relations": [
            {"value": key, "forward_label": forward, "backward_label": backward}
            for key, (forward, backward) in RELATIONS.items()
        ],
        "links": list_document_links(session, doc_id, include_rejected=include_rejected),
    })


@bp.route("/document/<int:doc_id>/links", methods=["POST"])
def add_document_link(doc_id: int):
    session = get_scoped_session()
    if session.get(Document, doc_id) is None:
        return jsonify({"status": "error", "message": "Document not found"}), 404
    data = request.get_json(silent=True) or {}
    other_id = data.get("to_document_id") or data.get("other_document_id")
    if not isinstance(other_id, int):
        return jsonify({"status": "error", "message": "to_document_id must be an integer"}), 400
    # direction="incoming" means the OTHER document is the subject of the relation.
    if data.get("direction") == "incoming":
        from_id, to_id = other_id, doc_id
    else:
        from_id, to_id = doc_id, other_id
    try:
        link = create_link(
            session,
            from_document_id=from_id,
            to_document_id=to_id,
            relation=data.get("relation"),
            note=data.get("note"),
            status=data.get("status") or "confirmed",
            created_by_user_id=_current_user_id(),
        )
    except DocumentLinkError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    session.refresh(link)
    return jsonify({"status": "success", "link": link_to_dict(link, perspective_document_id=doc_id)}), 201


@bp.route("/document/<int:doc_id>/links/detect", methods=["POST"])
def detect_document_links(doc_id: int):
    session = get_scoped_session()
    try:
        created = detect_url_mention_links(session, doc_id)
    except DocumentLinkError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 404
    for link in created:
        session.refresh(link)
    return jsonify({
        "status": "success",
        "created_count": len(created),
        "links": [link_to_dict(link, perspective_document_id=doc_id) for link in created],
    })


@bp.route("/document_links/<int:link_id>", methods=["PATCH"])
def patch_document_link(link_id: int):
    session = get_scoped_session()
    link = session.get(DocumentLink, link_id)
    if link is None:
        return jsonify({"status": "error", "message": "Link not found"}), 404
    data = request.get_json(silent=True) or {}
    try:
        set_link_status(session, link, data.get("status"))
    except DocumentLinkError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    session.refresh(link)
    return jsonify({"status": "success", "link": link_to_dict(link)})


@bp.route("/document_links/<int:link_id>", methods=["DELETE"])
def remove_document_link(link_id: int):
    session = get_scoped_session()
    link = session.get(DocumentLink, link_id)
    if link is None:
        return jsonify({"status": "error", "message": "Link not found"}), 404
    delete_link(session, link)
    return jsonify({"status": "success"})
