"""Registry identifiers; standard server authentication and CORS apply."""

import logging

from flask import Blueprint, request

from library import organization_identifiers as service
from library.db.engine import get_scoped_session
from library.db.models import Organization, OrganizationIdentifier
from library.organization_identifier_sync import check_and_store

organization_identifiers_bp = Blueprint("organization_identifiers", __name__)
logger = logging.getLogger(__name__)


@organization_identifiers_bp.route("/organizations/<int:organization_id>/identifiers/sync", methods=["POST", "OPTIONS"])
def sync_identifiers(organization_id):
    """Registry check that also stores the safe KRS / REGON (GET /company_registry/check stays read-only)."""
    if request.method == "OPTIONS":
        return {"status": "OK"}
    session = get_scoped_session()
    if session.get(Organization, organization_id) is None:
        return {"message": "Nie znaleziono organizacji."}, 404
    try:
        result = check_and_store(session, organization_id)
        session.commit()
        return result
    except ValueError:
        session.rollback()
        return {"message": "Organizacja potrzebuje dokładnie jednego polskiego numeru NIP lub KRS."}, 400
    except Exception:
        logger.exception("Registry check with identifier saving failed")
        session.rollback()
        return {"message": "Nie udało się sprawdzić rejestrów i zapisać numerów."}, 500


@organization_identifiers_bp.route("/organizations/<int:organization_id>/identifiers", methods=["GET", "POST", "OPTIONS"])
@organization_identifiers_bp.route("/organizations/<int:organization_id>/identifiers/<int:row_id>", methods=["DELETE", "OPTIONS"])
def identifiers(organization_id, row_id=None):
    if request.method == "OPTIONS":
        return {"status": "OK"}
    session = get_scoped_session()
    if session.get(Organization, organization_id) is None:
        return {"message": "Nie znaleziono organizacji."}, 404
    if request.method == "GET":
        return {"identifiers": service.list_identifiers(session, organization_id)}
    try:
        if request.method == "DELETE":
            row = session.get(OrganizationIdentifier, row_id)
            if row is None or row.organization_id != organization_id:
                return {"message": "Nie znaleziono numeru organizacji."}, 404
            session.delete(row)
            session.commit()
            return {"status": "success"}
        row, created = service.add_identifier(session, organization_id, request.get_json(silent=True))
        session.commit()
        return {"identifier": row}, 201 if created else 200
    except service.IdentifierConflict:
        session.rollback()
        owner = service.find_owner(session, request.get_json(silent=True))
        return {"message": "Ten numer jest już przypisany do innej organizacji.",
                "conflict_organization": owner and {"id": owner.id, "canonical_name": owner.canonical_name}}, 409
    except service.IdentifierError as exc:
        session.rollback()
        return {"message": service.ERRORS.get(exc.code, "Nieprawidłowe dane numeru.")}, 400
    except Exception:
        logger.exception("Organization identifier change failed")
        session.rollback()
        return {"message": "Nie udało się zapisać zmiany w bazie."}, 500
