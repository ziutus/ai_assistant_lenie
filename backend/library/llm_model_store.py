"""Database-backed allowlist of language models (ADR-030): cached read + write validation.

The ``llm_models`` table is the allowlist of models a reviewer may pick for a task and the routing
table ``ai_ask()`` consults for model ids it has no built-in rule for. ``SEED_MODELS`` is only the
fallback used while the database is unreachable (and the content of the first migration); it never
overrides a row, so retiring a model is one ``PATCH /llm_models/<id>`` — no code change, no deploy.

Same safety model as ``ner_gazetteer_store``: a short TTL cache (REST writes bust it) and the rule that
an LLM call never fails because of this lookup — any database error, including the ``SystemExit`` that
``config_loader.require()`` raises when config is missing, yields the seed.
"""

import datetime
import logging
import re
import threading
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Providers a model of the allowlist can belong to (what ``ai_ask`` can dispatch for an arbitrary model id).
PROVIDERS = ("cloudferro", "openai", "google-vertexai", "openrouter")
STATUSES = ("active", "deprecated", "retired")
OPENROUTER_PREFIX = "openrouter/"
SOURCE_DATABASE = "database"
SOURCE_SEED = "seed"
TTL_SECONDS = 60
MAX_MODEL_ID_LENGTH = 100
MAX_LABEL_LENGTH = 120
MAX_NOTE_LENGTH = 1000


class ModelValidationError(ValueError):
    """A model row does not meet the allowlist rules."""


@dataclass(frozen=True)
class ModelEntry:
    model_id: str
    label: str
    provider: str
    external: bool = False
    verified: bool = False
    status: str = "active"
    retires_on: datetime.date | None = None
    note: str | None = None


# Same content as the seed of migration f2c8a4d6b190 (a unit test keeps the two in step).
# ``verified`` False = id/price/quality not yet checked by a human.
SEED_MODELS: tuple[ModelEntry, ...] = (
    ModelEntry("Bielik-11B-v3.0-Instruct", "Bielik 11B v3.0 (CloudFerro)", "cloudferro", verified=True),
    ModelEntry("Bielik-11B-v2.3-Instruct", "Bielik 11B v2.3 (CloudFerro)", "cloudferro", verified=True),
    ModelEntry("gpt-4o-mini", "GPT-4o mini (OpenAI)", "openai", verified=True),
    ModelEntry("gemini-3.1-flash-lite", "Gemini 3.1 Flash Lite (Google Vertex)", "google-vertexai", verified=True),
    ModelEntry("gemini-3.5-flash-lite", "Gemini 3.5 Flash Lite (Google Vertex)", "google-vertexai", verified=True),
    ModelEntry("openrouter/openai/gpt-4o-mini", "GPT-4o mini (OpenRouter)", "openrouter", external=True),
    ModelEntry(
        "openrouter/google/gemini-2.5-flash-lite", "Gemini 2.5 Flash Lite (OpenRouter)", "openrouter", external=True,
        status="deprecated", retires_on=datetime.date(2026, 10, 20),
        note="Google wycofał ten model 2026-10-20; OpenRouter nadal go listuje. Ustaw status retired, gdy przestanie działać.",
    ),
    ModelEntry(
        "openrouter/mistralai/mistral-small-3.2-24b-instruct", "Mistral Small 3.2 24B (OpenRouter)", "openrouter",
        external=True,
    ),
    ModelEntry("openrouter/google/gemma-3-27b-it", "Gemma 3 27B (OpenRouter)", "openrouter", external=True),
    ModelEntry("openrouter/meta-llama/llama-3.1-8b-instruct", "Llama 3.1 8B (OpenRouter)", "openrouter", external=True),
    ModelEntry("openrouter/qwen/qwen-2.5-7b-instruct", "Qwen 2.5 7B (OpenRouter)", "openrouter", external=True),
)


@dataclass
class _Cache:
    models: tuple[ModelEntry, ...] = SEED_MODELS
    source: str = SOURCE_SEED
    expires_at: float = 0.0


_cache = _Cache()
_lock = threading.RLock()


def _fetch_rows() -> list[ModelEntry]:
    """Read every row through a short own session; patched in unit tests."""
    from sqlalchemy import select

    from library.db.engine import get_session
    from library.db.models import LlmModel

    session = get_session()
    try:
        return [
            ModelEntry(r.model_id, r.label, r.provider, r.external, r.verified, r.status, r.retires_on, r.note)
            for r in session.scalars(select(LlmModel).order_by(LlmModel.id))
        ]
    finally:
        session.close()


def _refresh_locked() -> None:
    try:
        _cache.models = tuple(_fetch_rows())
        _cache.source = SOURCE_DATABASE
    except (SystemExit, Exception):
        logger.warning("LLM models: cannot load the database allowlist; using the code seed", exc_info=True)
        _cache.models = SEED_MODELS
        _cache.source = SOURCE_SEED
    _cache.expires_at = time.monotonic() + TTL_SECONDS


def get_models() -> tuple[ModelEntry, ...]:
    """Every model row (retired ones included) — the seed while the database is unavailable. Never raises."""
    with _lock:
        if time.monotonic() >= _cache.expires_at:
            _refresh_locked()
        return _cache.models


def source() -> str:
    """``database`` or ``seed``: where ``get_models()`` currently reads from."""
    with _lock:
        if time.monotonic() >= _cache.expires_at:
            _refresh_locked()
        return _cache.source


def invalidate_cache() -> None:
    with _lock:
        _cache.expires_at = 0.0


def provider_of(model_id: str) -> str | None:
    """Provider of a non-retired allowlisted model (how ``ai_ask`` routes an id it has no built-in rule for)."""
    return next((m.provider for m in get_models() if m.model_id == model_id and m.status != "retired"), None)


def _text(value, name: str, max_length: int, *, required: bool = True) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > max_length:
        raise ModelValidationError(f"{name} musi mieć od 1 do {max_length} znaków")
    return value.strip()


def _date(value) -> datetime.date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime.date):
        return value
    try:
        return datetime.date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ModelValidationError("retires_on musi być datą RRRR-MM-DD") from exc


def validate_model(*, model_id, label, provider, external=None, verified=False, status="active", retires_on=None,
                   note=None) -> dict:
    """Return the normalized row fields or raise ModelValidationError."""
    model_id = _text(model_id, "model_id", MAX_MODEL_ID_LENGTH)
    if re.search(r"\s", model_id):
        raise ModelValidationError("model_id nie może zawierać białych znaków")
    if provider not in PROVIDERS:
        raise ModelValidationError(f"provider musi być jednym z: {', '.join(PROVIDERS)}")
    if provider == "openrouter":
        if not model_id.startswith(OPENROUTER_PREFIX) or "/" not in model_id[len(OPENROUTER_PREFIX):]:
            raise ModelValidationError("model OpenRouter musi mieć postać openrouter/<dostawca>/<model>")
    elif model_id.startswith(OPENROUTER_PREFIX):
        raise ModelValidationError("prefiks openrouter/ jest zarezerwowany dla providera openrouter")
    label = _text(label, "label", MAX_LABEL_LENGTH)
    if status not in STATUSES:
        raise ModelValidationError(f"status musi być jednym z: {', '.join(STATUSES)}")
    if external is None:
        external = provider == "openrouter"  # an intermediary that receives the text
    if not isinstance(external, bool) or not isinstance(verified, bool):
        raise ModelValidationError("external i verified muszą być wartościami logicznymi")
    note = _text(note or None, "note", MAX_NOTE_LENGTH, required=False)
    return {"model_id": model_id, "label": label, "provider": provider, "external": external, "verified": verified,
            "status": status, "retires_on": _date(retires_on), "note": note}
