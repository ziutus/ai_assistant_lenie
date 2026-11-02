"""Remaining balance of the paid providers Lenie uses, in one shape (``GET /provider_balances``).

Two sources, told apart by ``source``:

* ``api`` - the provider reports it itself (OpenRouter, ``api/openrouter/openrouter_key.py``).
* ``estimated`` - the provider has no usable billing API (CloudFerro: the wallet is visible only in the customer
  panel and in a "balance is low" e-mail). The owner types the last known balance and its date; the estimate is that
  balance minus what ``llm_usage_logs`` priced for the provider since then. Nothing outside Lenie's own LLM and
  embedding calls is counted, so a wallet that also pays for VMs or storage needs ``fixed_monthly`` (billing units per
  month) to stay honest, and the owner corrects the base after a top-up or a provider e-mail.

The warning is "days of runway" (``warn_days``), not a fixed amount: the same balance is plenty at one consumption and
dangerous at another.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from sqlalchemy import func, select

from library import app_settings
from library.db.models import LlmUsageLog

SETTING_PREFIX = "provider_balance:"
DEFAULT_WARN_DAYS = 14
DEFAULT_PLN_PER_EUR = 4.25  # a billing unit is worth 1 EUR; PLN-priced calls are converted with this rate
BURN_WINDOW_DAYS = 30

# provider id in the API -> display data and the ``llm_usage_logs.provider`` it is estimated from
ESTIMATED_PROVIDERS = {
    "cloudferro": {"name": "CloudFerro", "unit": "BU", "usage_provider": "cloudferro"},
}


def setting_key(provider: str) -> str:
    return f"{SETTING_PREFIX}{provider}"


def _number(value, low: float, high: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    if not low <= value <= high:
        raise ValueError(f"{name} must be between {low:g} and {high:g}")
    return float(value)


def validate_config(body: dict, today: datetime.date | None = None) -> dict:
    """The stored configuration from a PUT body; ``ValueError`` (with a message for the caller) on bad input."""
    if "amount" not in body:
        raise ValueError("amount is required")
    as_of = body.get("as_of") or (today or datetime.date.today()).isoformat()
    try:
        datetime.date.fromisoformat(as_of)
    except (TypeError, ValueError):
        raise ValueError("as_of must be an ISO date (YYYY-MM-DD)") from None
    warn_days = body.get("warn_days", DEFAULT_WARN_DAYS)
    if isinstance(warn_days, bool) or not isinstance(warn_days, int) or not 1 <= warn_days <= 365:
        raise ValueError("warn_days must be an integer from 1 to 365")
    return {
        "amount": _number(body["amount"], 0, 10_000_000, "amount"),
        "as_of": as_of,
        "fixed_monthly": _number(body.get("fixed_monthly", 0), 0, 10_000_000, "fixed_monthly"),
        "warn_days": warn_days,
        "pln_per_eur": _number(body.get("pln_per_eur", DEFAULT_PLN_PER_EUR), 1, 20, "pln_per_eur"),
    }


def to_eur(rows, pln_per_eur: float) -> tuple[Decimal, int]:
    """Sum ``(currency, amount)`` rows in EUR. Returns ``(eur, skipped)``: rows without an amount or in a currency
    that cannot be converted are skipped, never guessed."""
    total, skipped = Decimal(0), 0
    for currency, amount in rows:
        if amount is None:
            skipped += 1
        elif currency == "EUR":
            total += Decimal(amount)
        elif currency == "PLN":
            total += Decimal(amount) / Decimal(str(pln_per_eur))
        else:
            skipped += 1
    return total, skipped


def estimate(config: dict, spent_eur: float, window_eur: float, window_days: int = BURN_WINDOW_DAYS) -> dict:
    """Pure estimate. ``spent_eur`` = priced usage since ``as_of``; ``window_eur`` = priced usage in the last
    ``window_days`` (the consumption the runway is projected from)."""
    remaining = config["amount"] - spent_eur
    daily = window_eur / window_days + config["fixed_monthly"] / 30
    exhausted = remaining <= 0
    days_left = 0.0 if exhausted else (remaining / daily if daily > 0 else None)
    low = (not exhausted) and days_left is not None and days_left < config["warn_days"]
    return {
        "remaining": round(remaining, 2),
        "spent_since": round(spent_eur, 4),
        "daily_burn": round(daily, 4),
        "days_left": None if days_left is None else round(days_left, 1),
        "low": low,
        "exhausted": exhausted,
    }


def _usage_rows(session, usage_provider: str, since: datetime.datetime):
    return session.execute(
        select(LlmUsageLog.cost_currency, func.sum(LlmUsageLog.cost_amount))
        .where(LlmUsageLog.provider == usage_provider, LlmUsageLog.called_at >= since)
        .group_by(LlmUsageLog.cost_currency)
    ).all()


def estimated_balance(session, provider: str, now: datetime.datetime | None = None) -> dict:
    info = ESTIMATED_PROVIDERS[provider]
    entry = {"provider": provider, "name": info["name"], "source": "estimated", "unit": info["unit"]}
    config = app_settings.get_setting(session, setting_key(provider))
    if not isinstance(config, dict) or "amount" not in config or "as_of" not in config:
        return {**entry, "status": "not_configured"}
    now = now or datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)  # called_at is naive UTC
    since = datetime.datetime.combine(datetime.date.fromisoformat(config["as_of"]), datetime.time.min)
    window_start = now - datetime.timedelta(days=BURN_WINDOW_DAYS)
    rate = config.get("pln_per_eur", DEFAULT_PLN_PER_EUR)
    spent, skipped = to_eur(_usage_rows(session, info["usage_provider"], since), rate)
    window, skipped_window = to_eur(_usage_rows(session, info["usage_provider"], window_start), rate)
    config = {"fixed_monthly": 0, "warn_days": DEFAULT_WARN_DAYS, **config}
    return {
        **entry, "status": "ok", **estimate(config, float(spent), float(window)),
        "base_amount": config["amount"], "as_of": config["as_of"],
        "fixed_monthly": config["fixed_monthly"], "warn_days": config["warn_days"],
        "unpriced_rows": max(skipped, skipped_window),
    }


def openrouter_balance() -> dict:
    from library.api.openrouter.openrouter_key import fetch_key_status

    data = fetch_key_status()
    entry = {"provider": "openrouter", "name": "OpenRouter", "source": "api", "unit": "USD", "status": data["status"]}
    if data["status"] != "ok":
        return entry
    has_limit = bool(data.get("has_limit"))
    return {**entry, "remaining": data.get("remaining_usd") if has_limit else None, "limit": data.get("limit_usd"),
            "spent_since": data.get("usage_usd"), "days_left": None,
            "low": bool(data.get("low")), "exhausted": bool(data.get("exhausted")),
            "has_limit": has_limit}


def all_balances(session) -> list[dict]:
    return [openrouter_balance(), *(estimated_balance(session, provider) for provider in ESTIMATED_PROVIDERS)]
