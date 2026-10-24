"""Server-side allowlist of language models a reviewer may pick for a task.

Only models that ``library.ai.ai_ask`` can dispatch are listed; the endpoint rejects any other id, so a
client can never route a document to an arbitrary provider. OpenRouter models are listed only while the
``OPENROUTER_ENABLED`` flag is on, because they send the document text to an external intermediary.
The content_group_suggestion task sends public feed titles/summaries to that provider;
document topic suggestions retain their existing Bielik model.

Limits and prices are not hard-coded: an OpenRouter model takes them from the live public catalog
(``library.api.openrouter.openrouter_catalog``), every other model from its active ``llm_pricing`` row.
Whatever cannot be resolved is reported as ``None`` — never as a guessed number.
"""

import logging

logger = logging.getLogger(__name__)

# (id, label, provider, external, verified) — ``verified`` False = id/price/quality not yet checked by a human.
_ORGANIZATION_DESCRIPTION_MODELS: tuple[tuple[str, str, str, bool, bool], ...] = (
    ("Bielik-11B-v3.0-Instruct", "Bielik 11B v3.0 (CloudFerro)", "cloudferro", False, True),
    ("Bielik-11B-v2.3-Instruct", "Bielik 11B v2.3 (CloudFerro)", "cloudferro", False, True),
    ("gpt-4o-mini", "GPT-4o mini (OpenAI)", "openai", False, True),
    ("gemini-2.0-flash-lite-001", "Gemini 2.0 Flash Lite (Google)", "google-vertexai", False, True),
    ("openrouter/openai/gpt-4o-mini", "GPT-4o mini (OpenRouter)", "openrouter", True, False),
    ("openrouter/google/gemini-2.5-flash-lite", "Gemini 2.5 Flash Lite (OpenRouter)", "openrouter", True, False),
    ("openrouter/meta-llama/llama-3.1-8b-instruct", "Llama 3.1 8B (OpenRouter)", "openrouter", True, False),
    ("openrouter/qwen/qwen-2.5-7b-instruct", "Qwen 2.5 7B (OpenRouter)", "openrouter", True, False),
)

# Tasks that share the list above. ``tool_tags`` sends only public tool metadata (name, URL, description).
# Content-group suggestions send public feed titles/summaries to an external provider
# when an OpenRouter model is selected; document classification stays on Bielik.
_TASKS = {"organization_description", "tool_tags", "content_group_suggestion"}

_OPENROUTER_PREFIX = "openrouter/"
PRICE_SOURCE_OPENROUTER = "openrouter_api"
PRICE_SOURCE_DATABASE = "llm_pricing"


def _openrouter_enabled() -> bool:
    from library.api.openrouter.openrouter_completion import is_enabled

    try:
        return is_enabled()
    except Exception:  # config unavailable -> treat the external provider as off
        return False


def _base_models(task: str) -> list[dict]:
    """The allowlist as ``{id, label, provider, external, verified}`` dicts — no network, no database."""
    if task not in _TASKS:
        return []
    show_openrouter = _openrouter_enabled()
    return [{"id": model_id, "label": label, "provider": provider, "external": external, "verified": verified}
            for model_id, label, provider, external, verified in _ORGANIZATION_DESCRIPTION_MODELS
            if provider != "openrouter" or show_openrouter]


def _money(value) -> str | None:
    """Decimal price as a plain string (JSON-safe, never float); None when unknown."""
    return format(value.normalize(), "f") if value is not None else None


def _empty_details() -> dict:
    return {"context_length": None, "max_output_tokens": None, "input_price_per_million": None,
            "output_price_per_million": None, "currency": None, "price_source": None,
            "supports_structured_outputs": None, "listed_by_provider": None}


def _openrouter_details(model_id: str) -> dict:
    from library.api.openrouter import openrouter_catalog

    catalog = openrouter_catalog.get_catalog()
    details = _empty_details()
    if not catalog:  # catalog unreachable: say nothing rather than claim the model is gone
        return details
    info = catalog.get(model_id.removeprefix(_OPENROUTER_PREFIX))
    details["listed_by_provider"] = info is not None
    if info is None:
        return details
    priced = info.input_price_per_million is not None and info.output_price_per_million is not None
    details.update(
        context_length=info.context_length, max_output_tokens=info.max_completion_tokens,
        input_price_per_million=_money(info.input_price_per_million),
        output_price_per_million=_money(info.output_price_per_million),
        currency=info.currency if priced else None,
        price_source=PRICE_SOURCE_OPENROUTER if priced else None,
        supports_structured_outputs=info.supports_structured_outputs)
    return details


def _database_prices(models: list[dict]) -> dict[tuple[str, str], tuple]:
    """``{(provider, model): (input, output, currency)}`` from the active ``llm_pricing`` rows; {} on any failure."""
    from sqlalchemy import select

    from library.db.engine import get_session
    from library.db.models import LlmPricing

    session = None
    try:
        session = get_session()
        rows = session.execute(select(LlmPricing).where(
            LlmPricing.effective_to.is_(None), LlmPricing.pricing_mode == "per_token",
            LlmPricing.model.in_([item["id"] for item in models]))).scalars().all()
        return {(row.provider, row.model): (row.input_price_per_million, row.output_price_per_million, row.currency)
                for row in rows}
    except (SystemExit, Exception):  # no database config / unreachable -> prices stay unknown
        logger.warning("llm_pricing lookup for the model registry failed")
        return {}
    finally:
        if session is not None:
            session.close()


def selectable_models(task: str = "organization_description") -> list[dict]:
    """Models offered for ``task`` with their limits and prices (``None`` where unknown).

    Each item: ``id, label, provider, external, verified`` plus ``context_length, max_output_tokens,
    input_price_per_million, output_price_per_million, currency`` (prices per 1M tokens, as strings),
    ``price_source`` (``openrouter_api`` / ``llm_pricing`` / None), ``supports_structured_outputs`` (True = a
    JSON-schema ``response_format`` is honoured: Bielik on CloudFerro, OpenRouter models whose catalog entry
    lists it; False = not sent; None = OpenRouter catalog unreachable) and
    ``listed_by_provider`` (False = an OpenRouter id the live catalog no longer knows).
    """
    from library.ai import _RESPONSE_FORMAT_PROVIDERS

    models = _base_models(task)
    database_models = [item for item in models if item["provider"] != "openrouter"]
    stored = _database_prices(database_models) if database_models else {}
    for item in models:
        if item["provider"] == "openrouter":
            item.update(_openrouter_details(item["id"]))
            continue
        item.update(_empty_details())
        # Direct providers: a JSON-schema response_format is accepted exactly where ai_ask() forwards it.
        item["supports_structured_outputs"] = item["provider"] in _RESPONSE_FORMAT_PROVIDERS
        row = stored.get((item["provider"], item["id"]))
        if row is not None and row[0] is not None and row[1] is not None:
            item.update(input_price_per_million=_money(row[0]), output_price_per_million=_money(row[1]),
                        currency=row[2], price_source=PRICE_SOURCE_DATABASE)
    return models


def is_selectable(model: str, task: str = "organization_description") -> bool:
    """Allowlist check only — deliberately no catalog or database access, it runs on every request."""
    return any(item["id"] == model for item in _base_models(task))


def model_details(model: str, task: str = "organization_description") -> dict | None:
    """The ``selectable_models`` entry for one model (limits and prices included), or None when not allowed."""
    return next((item for item in selectable_models(task) if item["id"] == model), None)
