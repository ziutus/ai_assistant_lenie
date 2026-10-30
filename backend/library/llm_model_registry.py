"""Server-side allowlist of language models a reviewer may pick for a task.

The list lives in the ``llm_models`` table (ADR-032, ``library.llm_model_store``): adding or retiring a model is
a REST call, not a deploy. Only models that ``library.ai.ai_ask`` can dispatch are listed; the endpoint rejects
any other id, so a client can never route a document to an arbitrary provider. A ``retired`` model is hidden
from every picker; a ``deprecated`` one is still offered, with its ``status`` and ``retires_on``. OpenRouter
models are listed only while the ``OPENROUTER_ENABLED`` flag is on, because they send the document text to an
external intermediary. The content_group_suggestion task sends public feed titles/summaries to that provider;
document topic suggestions retain their existing Bielik model.

Limits and prices are not hard-coded: an OpenRouter model takes them from the live public catalog
(``library.api.openrouter.openrouter_catalog``), every other model from its active ``llm_pricing`` row.
Whatever cannot be resolved is reported as ``None`` — never as a guessed number.
"""

import logging

from library import llm_model_store

logger = logging.getLogger(__name__)

# Tasks that share the model list. ``tool_tags`` sends only public tool metadata (name, URL, description).
# Content-group suggestions send public feed titles/summaries to an external provider
# when an OpenRouter model is selected; document classification stays on Bielik.
_TASKS = {"organization_description", "tool_tags", "content_group_suggestion", "transcript_chapters"}

# Tasks whose answer must be structured JSON: models that cannot honour a JSON-schema ``response_format`` are not
# offered (and, where it is known without a network call, not accepted) for them.
_STRUCTURED_OUTPUT_TASKS = {"content_group_suggestion"}

_OPENROUTER_PREFIX = "openrouter/"
PRICE_SOURCE_OPENROUTER = "openrouter_api"
PRICE_SOURCE_DATABASE = "llm_pricing"


def _openrouter_enabled() -> bool:
    from library.api.openrouter.openrouter_completion import is_enabled

    try:
        return is_enabled()
    except Exception:  # config unavailable -> treat the external provider as off
        return False


def _provider_problem(provider: str) -> str | None:
    """Why models of ``provider`` cannot be called right now (missing credentials), or None.

    Only Google Vertex AI has a local check today; every other provider is assumed to be reachable.
    """
    if provider != "google-vertexai":
        return None
    from library.api.google import google_vertexai

    try:
        return google_vertexai.configuration_problem()
    except Exception:  # a failed check must not hide the model
        return None


def _base_models(task: str) -> list[dict]:
    """The offered models as ``{id, label, provider, external, verified, status, retires_on, available,
    unavailable_reason}`` dicts.

    No network; the database is read through the cached ``llm_model_store`` (the code seed while it is unreachable).
    A model whose provider has no credentials is still listed — greyed out in the pickers, with the reason — but is
    not ``is_selectable``.
    """
    if task not in _TASKS:
        return []
    from library.ai import _RESPONSE_FORMAT_PROVIDERS

    show_openrouter = _openrouter_enabled()
    needs_json = task in _STRUCTURED_OUTPUT_TASKS
    problems: dict[str, str | None] = {}
    models = []
    for m in llm_model_store.get_models():
        if m.status == "retired" or (m.provider == "openrouter" and not show_openrouter):
            continue
        if needs_json and m.provider not in _RESPONSE_FORMAT_PROVIDERS:
            continue
        if m.provider not in problems:
            problems[m.provider] = _provider_problem(m.provider)
        problem = problems[m.provider]
        models.append({"id": m.model_id, "label": m.label, "provider": m.provider, "external": m.external,
                       "verified": m.verified, "status": m.status,
                       "retires_on": m.retires_on.isoformat() if m.retires_on else None,
                       "available": problem is None, "unavailable_reason": problem})
    return models


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
    if task in _STRUCTURED_OUTPUT_TASKS:
        # False = the live OpenRouter catalog says the model has no structured outputs; None (catalog unreachable) stays.
        models = [item for item in models if item["supports_structured_outputs"] is not False]
    return models


def is_selectable(model: str, task: str = "organization_description") -> bool:
    """Allowlist check — no catalog lookup and no query of its own (the store is cached), it runs on every request.

    A listed model whose provider has no credentials is NOT selectable: the endpoints reject it and a saved household
    choice falls back to the task default until the credential is configured.
    """
    return any(item["id"] == model and item["available"] for item in _base_models(task))


def model_details(model: str, task: str = "organization_description") -> dict | None:
    """The ``selectable_models`` entry for one model (limits and prices included), or None when not allowed."""
    return next((item for item in selectable_models(task) if item["id"] == model), None)
