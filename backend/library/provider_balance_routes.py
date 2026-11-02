"""``/provider_balances``: remaining balance of the paid providers in one list (see ``provider_balance.py``)."""

from flask import Blueprint, abort, g, jsonify, request

from library import app_settings, provider_balance
from library.db.engine import get_scoped_session

bp = Blueprint("provider_balances", __name__)


def _writer() -> None:
    if getattr(g, "auth", None) is None or g.auth.kind not in {"user", "service"}:
        abort(403, "user or service API key required")


def _known(provider: str) -> None:
    if provider not in provider_balance.ESTIMATED_PROVIDERS:
        abort(404, f"{provider} has no hand-entered balance (known: {', '.join(provider_balance.ESTIMATED_PROVIDERS)})")


@bp.get("/provider_balances")
def get_provider_balances():
    """``{"balances": [...]}``: OpenRouter from its API (``source: api``) and CloudFerro estimated from the last
    balance the owner entered minus priced usage since (``source: estimated``). ``low`` means fewer than ``warn_days``
    days of runway at the recent consumption."""
    return jsonify({"balances": provider_balance.all_balances(get_scoped_session())})


@bp.put("/provider_balances/<provider>")
def put_provider_balance(provider: str):
    """Set the last known balance of a provider that has no billing API: ``{amount, as_of?, fixed_monthly?,
    warn_days?, pln_per_eur?}`` (``as_of`` defaults to today)."""
    _writer()
    _known(provider)
    try:
        config = provider_balance.validate_config(request.get_json(silent=True) or {})
    except ValueError as exc:
        abort(400, str(exc))
    session = get_scoped_session()
    app_settings.set_setting(session, provider_balance.setting_key(provider), config)
    return jsonify({"balance": provider_balance.estimated_balance(session, provider)})


@bp.delete("/provider_balances/<provider>")
def delete_provider_balance(provider: str):
    _writer()
    _known(provider)
    session = get_scoped_session()
    app_settings.set_setting(session, provider_balance.setting_key(provider), None)
    return jsonify({"balance": provider_balance.estimated_balance(session, provider)})
