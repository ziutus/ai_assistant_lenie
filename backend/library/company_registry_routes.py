"""Read-only public registry lookup; authentication is handled by server middleware."""

from flask import Blueprint, request

from library.company_registry_service import check_company

company_registry_bp = Blueprint("company_registry", __name__)


@company_registry_bp.get("/company_registry/check")
def company_registry_check():
    try:
        return check_company(nip=request.args.get("nip"), krs=request.args.get("krs"))
    except ValueError as exc:
        return {"message": str(exc)}, 400
