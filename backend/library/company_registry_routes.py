"""Company registry lookup and explicit import; standard user/service authentication applies."""

import logging

from flask import Blueprint, jsonify, request
from sqlalchemy.exc import IntegrityError

from library import company_registry_import as service
from library import organization_identifiers as identifiers
from library.company_registry_service import check_company
from library.db.engine import get_scoped_session
from library.organization_registry import AliasConflictError

company_registry_bp = Blueprint("company_registry", __name__)
logger = logging.getLogger(__name__)


def error(code, status, conflict=None):
    payload = {"message": service.ERRORS[code]}
    if conflict:
        payload["conflict_organization"] = conflict
    return jsonify(payload), status


@company_registry_bp.get("/company_registry/check")
def company_registry_check():
    try:
        result = check_company(nip=request.args.get("nip"), krs=request.args.get("krs"),
                               organization_id=request.args.get("organization_id"))
        if request.args.get("match") == "1":
            result["lenie_match"] = service.match_company(get_scoped_session(), result)
        return jsonify(result)
    except LookupError:
        return error("missing", 404)
    except ValueError:
        return error("input", 400)
    except Exception:
        logger.exception("Company registry lookup failed")
        return error("failed", 500)


@company_registry_bp.route("/company_registry/organizations", methods=["POST", "OPTIONS"])
def company_registry_organizations():
    if request.method == "OPTIONS":
        return {"status": "OK"}
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or sum(data.get(key) is not None for key in ("nip", "krs")) != 1:
        return error("input", 400)
    session = get_scoped_session()
    try:
        result = check_company(nip=data.get("nip"), krs=data.get("krs"))
        response = service.store_company(session, result, data)
        session.commit()
        return jsonify(response), 201 if response["created"] else 200
    except service.ImportError as exc:
        session.rollback()
        return error(exc.code, exc.status, exc.conflict)
    except identifiers.IdentifierConflict:
        session.rollback()
        match = service.match_company(session, result)
        owner = next((o for o in match["owners"] if o["id"] != data.get("organization_id")), None)
        return error("owner", 409, {k: owner[k] for k in ("id", "canonical_name")} if owner else None)
    except (AliasConflictError, IntegrityError):
        session.rollback()
        owner = service.name_owner(session, data.get("canonical_name") or "")
        if owner:
            return error("name_taken", 409, service.brief(owner))
        logger.exception("Company registry import constraint failed")
        return error("failed", 409)
    except ValueError:
        session.rollback()
        return error("input", 400)
    except Exception:
        logger.exception("Company registry import failed")
        session.rollback()
        return error("failed", 500)
