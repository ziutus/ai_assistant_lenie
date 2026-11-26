"""Related companies; standard application authentication and CORS apply."""

import logging

from flask import Blueprint, jsonify, request

from library.db.engine import get_scoped_session
from library.db.models import Organization, OrganizationRelation
from library.organization_relations import related_companies

organization_relations_bp = Blueprint("organization_relations", __name__)
logger = logging.getLogger(__name__)


@organization_relations_bp.route("/organizations/<int:organization_id>/related_companies", methods=["GET", "OPTIONS"])
@organization_relations_bp.route("/organizations/<int:organization_id>/relations/<int:relation_id>",
                                  methods=["PATCH", "OPTIONS"])
def relations(organization_id, relation_id=None):
    if request.method == "OPTIONS":
        return {"status": "OK"}
    session = get_scoped_session()
    try:
        if session.get(Organization, organization_id) is None:
            return {"message": "Nie znaleziono organizacji."}, 404
        data = related_companies(session, organization_id)
        if request.method == "GET":
            return jsonify(data)
        row = session.get(OrganizationRelation, relation_id)
        allowed = {r["id"] for r in data["shareholders"] + data["holdings"]}
        if row is None or relation_id not in allowed:
            return {"message": "Nie znaleziono powiązania organizacji."}, 404
        body = request.get_json(silent=True)
        if not isinstance(body, dict) or set(body) != {"related_organization_id"}:
            return {"message": "Podaj organizację do powiązania."}, 400
        target = body["related_organization_id"]
        if target is not None:
            if type(target) is not int or target <= 0:
                return {"message": "Nieprawidłowy identyfikator organizacji."}, 400
            if target == row.organization_id:
                return {"message": "Nie można powiązać organizacji z nią samą."}, 400
            if session.get(Organization, target) is None:
                return {"message": "Nie znaleziono organizacji."}, 404
        row.related_organization_id, row.link_rejected = target, target is None
        session.commit()
        return jsonify(related_companies(session, organization_id))
    except Exception:
        session.rollback()
        logger.exception("Related company operation failed")
        return {"message": "Nie udało się odczytać lub zapisać powiązań firm."}, 500
