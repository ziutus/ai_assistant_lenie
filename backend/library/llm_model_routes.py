"""REST for the database-backed model allowlist (ADR-030); writes need a service key.

A retired model disappears from every picker (``PATCH {"status": "retired"}``), a new one is offered
after ``POST``; both take effect within the store's cache TTL, without a deploy.
"""

import datetime

from flask import Blueprint, abort, g, jsonify, request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from library import llm_model_store
from library.db.engine import get_scoped_session
from library.db.models import LlmModel, LlmPricing
from library.llm_model_store import ModelValidationError, invalidate_cache, validate_model

bp = Blueprint("llm_models", __name__)

_PATCHABLE = ("label", "external", "verified", "status", "retires_on", "note")


def _require_service() -> None:
    if getattr(getattr(g, "auth", None), "kind", None) != "service":
        abort(403, "Zapis listy modeli wymaga klucza service")


def _body() -> dict:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, "Wymagany obiekt JSON")
    return data


def _serialize(model) -> dict:
    return {
        column.name: (value.isoformat() if isinstance(value, (datetime.datetime, datetime.date)) else value)
        for column in LlmModel.__table__.columns
        for value in [getattr(model, column.name)]
    }


def _pricing_warning(session, provider: str, model_id: str) -> str | None:
    """OpenRouter models are priced from its live catalog; every other provider needs an ``llm_pricing`` row."""
    if provider == "openrouter":
        return None
    priced = session.scalars(select(LlmPricing.id).where(
        LlmPricing.provider == provider, LlmPricing.model == model_id, LlmPricing.effective_to.is_(None),
    )).first()
    if priced is None:
        return f"Brak aktywnej ceny w llm_pricing dla {provider}/{model_id}: koszt wywołań będzie nieznany"
    return None


def _error(message: str, status: int):
    return jsonify({"status": "error", "message": message}), status


@bp.get("/llm_models")
def list_models():
    query = select(LlmModel).order_by(LlmModel.id)
    if "status" in request.args:
        if request.args["status"] not in llm_model_store.STATUSES:
            abort(400, f"status musi być jednym z: {', '.join(llm_model_store.STATUSES)}")
        query = query.where(LlmModel.status == request.args["status"])
    models = get_scoped_session().scalars(query).all()
    return jsonify({"status": "success", "models": [_serialize(model) for model in models]})


@bp.post("/llm_models")
def add_model():
    _require_service()
    data = _body()
    try:
        values = validate_model(
            model_id=data.get("model_id"), label=data.get("label"), provider=data.get("provider"),
            external=data.get("external"), verified=data.get("verified", False),
            status=data.get("status", "active"), retires_on=data.get("retires_on"), note=data.get("note"),
        )
    except ModelValidationError as exc:
        return _error(str(exc), 400)
    session = get_scoped_session()
    if session.scalars(select(LlmModel.id).where(LlmModel.model_id == values["model_id"])).first() is not None:
        return _error("Model o tym identyfikatorze już istnieje", 409)
    model = LlmModel(**values)
    try:
        session.add(model)
        session.commit()
    except IntegrityError:
        session.rollback()
        return _error("Model o tym identyfikatorze już istnieje", 409)
    except Exception:
        session.rollback()
        raise
    invalidate_cache()
    warning = _pricing_warning(session, values["provider"], values["model_id"])
    return jsonify({"status": "success", "model": _serialize(model), "warnings": [warning] if warning else []}), 201


@bp.patch("/llm_models/<int:model_pk>")
def patch_model(model_pk: int):
    _require_service()
    data = _body()
    session = get_scoped_session()
    model = session.get(LlmModel, model_pk)
    if model is None:
        abort(404, "Nie znaleziono modelu")
    for key in ("model_id", "provider"):
        if key in data and data[key] != getattr(model, key):
            return _error(f"{key} jest niezmienny: usuń model i dodaj go ponownie", 400)
    merged = {key: getattr(model, key) for key in ("model_id", "provider", *_PATCHABLE)}
    merged.update({key: data[key] for key in _PATCHABLE if key in data})
    try:
        values = validate_model(**merged)
    except ModelValidationError as exc:
        return _error(str(exc), 400)
    try:
        for key in _PATCHABLE:
            setattr(model, key, values[key])
        model.updated_at = datetime.datetime.now()
        session.commit()
    except Exception:
        session.rollback()
        raise
    invalidate_cache()
    return jsonify({"status": "success", "model": _serialize(model)})


@bp.delete("/llm_models/<int:model_pk>")
def delete_model(model_pk: int):
    _require_service()
    session = get_scoped_session()
    model = session.get(LlmModel, model_pk)
    if model is None:
        abort(404, "Nie znaleziono modelu")
    try:
        session.delete(model)
        session.commit()
    except Exception:
        session.rollback()
        raise
    invalidate_cache()
    return jsonify({"status": "success", "deleted_model_id": model_pk})
