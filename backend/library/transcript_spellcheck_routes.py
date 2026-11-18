"""REST for speech-to-text spellcheck proposals (read-only: nothing is stored or changed)."""

import logging

from flask import Blueprint, abort, jsonify, request

from library import app_settings, llm_model_registry
from library import transcript_spellcheck as spellcheck
from library.db.engine import get_scoped_session
from library.db.models import Document

logger = logging.getLogger(__name__)

bp = Blueprint("transcript_spellcheck", __name__)


@bp.route("/transcript_spellcheck/model", methods=["GET", "PUT"])
def transcript_spellcheck_model():
    session = get_scoped_session()
    if request.method == "PUT":
        body = request.get_json(silent=True)
        if not isinstance(body, dict) or "model" not in body:
            abort(400, "model is required")
        model = body["model"]
        if model is not None and (
            not isinstance(model, str) or not llm_model_registry.is_selectable(model, spellcheck.TASK)
        ):
            abort(400, "unknown model")
        app_settings.set_setting(session, spellcheck.SETTING_KEY, model)
    return jsonify({"default_model": spellcheck.default_model(session),
                    "saved": isinstance(app_settings.get_setting(session, spellcheck.SETTING_KEY), str),
                    "models": llm_model_registry.selectable_models(spellcheck.TASK)})


@bp.route("/document/<int:doc_id>/transcript_spellcheck", methods=["POST"])
def document_transcript_spellcheck(doc_id: int):
    """Words of a video transcript the dictionary does not know, with a model's proposed spelling.

    Body ``{"model"?, "dry_run"?}``. ``dry_run`` lists the suspects without calling a model. Apply an approved
    proposal with ``POST /transcript_corrections/apply`` (``pattern`` + ``replacement``, one document).
    """
    session = get_scoped_session()
    doc = session.get(Document, doc_id)
    if doc is None:
        abort(404)
    if doc.document_type not in ("youtube", "movie") or not (doc.text or "").strip():
        return jsonify(status="error", message="Wymagana jest transkrypcja filmu."), 400
    body = request.get_json(silent=True)
    if body is None:
        body = {}
    if not isinstance(body, dict):
        return jsonify(status="error", message="Wymagany jest obiekt JSON."), 400
    if "dry_run" in body and type(body["dry_run"]) is not bool:
        return jsonify(status="error", message="dry_run musi być wartością logiczną."), 400
    model = body.get("model") or spellcheck.default_model(session)
    if not body.get("dry_run") and (
        not isinstance(model, str) or not llm_model_registry.is_selectable(model, spellcheck.TASK)
    ):
        return jsonify(status="error", message="Nieznany model."), 400

    try:
        found = spellcheck.find_suspects(doc.text)
    except spellcheck.SpellcheckUnavailable:
        logger.exception("Spellcheck dictionary missing")
        return jsonify(status="error", error_code="dictionary_unavailable",
                       message="Słownik morfologiczny jest niedostępny."), 503
    if body.get("dry_run"):
        return jsonify(status="ok", dry_run=True, default_model=model, **found)
    if not found["suspects"]:
        return jsonify(status="ok", proposals=[], rejected={}, model=model, model_calls=0, usage=None,
                       skipped=found["skipped"], suspects=0)
    try:
        result = spellcheck.propose(found["suspects"], model=model, document_id=doc_id)
    except Exception:
        logger.exception("Transcript spellcheck failed for %s", doc_id)
        return jsonify(status="error", error_code="model_call_failed",
                       message="Wywołanie modelu nie powiodło się."), 502
    return jsonify(status="ok", suspects=len(found["suspects"]), skipped=found["skipped"], **result)
