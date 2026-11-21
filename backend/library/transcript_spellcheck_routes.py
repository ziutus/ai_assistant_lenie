"""REST for speech-to-text spellcheck proposals.

The proposal endpoints are read-only (nothing is stored or changed in the transcript); the reviewer's decisions are
the only thing written, to ``transcript_spellcheck_memory``, by an explicit call.
"""

import logging

from flask import Blueprint, abort, jsonify, request

from library import app_settings, llm_model_registry
from library import transcript_spellcheck as spellcheck
from library import transcript_spellcheck_memory as memory
from library.db.engine import get_scoped_session
from library.db.models import Document
from library.transcript_corrections_routes import _require_writer

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


def _transcript(session, doc_id: int):
    """The document, or ``(None, error response)`` when it is not a video transcript."""
    doc = session.get(Document, doc_id)
    if doc is None:
        abort(404)
    if doc.document_type not in ("youtube", "movie") or not (doc.text or "").strip():
        return None, (jsonify(status="error", message="Wymagana jest transkrypcja filmu."), 400)
    return doc, None


def _body():
    body = request.get_json(silent=True)
    if body is None:
        return {}, None
    if not isinstance(body, dict):
        return None, (jsonify(status="error", message="Wymagany jest obiekt JSON."), 400)
    return body, None


def _pick_model(session, body, *, needed: bool):
    model = body.get("model") or spellcheck.default_model(session)
    if needed and (not isinstance(model, str) or not llm_model_registry.is_selectable(model, spellcheck.TASK)):
        return None, (jsonify(status="error", message="Nieznany model."), 400)
    return model, None


@bp.route("/document/<int:doc_id>/transcript_spellcheck", methods=["POST"])
def document_transcript_spellcheck(doc_id: int):
    """Words of a video transcript the dictionary does not know, with a model's proposed spelling.

    Body ``{"model"?, "dry_run"?}``. The transcript is read chapter by chapter; chapters typed advertisement,
    noise or sources are skipped (``skipped_chapters``). Words the reviewer approved before for this channel come
    back as proposals ``source: "memory"`` without a model call, words rejected before are listed in
    ``known_rejected`` (``memory_id`` restores one) and only the rest is sent to the model. ``dry_run`` lists the
    suspects (each with a ``status`` ``new`` / ``memory`` / ``rejected``) without calling a model. Apply an approved
    proposal with ``POST /transcript_corrections/apply`` (``pattern`` + ``replacement``, one document) and report the
    decisions with ``POST /document/<id>/transcript_spellcheck/decisions``.
    """
    session = get_scoped_session()
    doc, error = _transcript(session, doc_id)
    if error:
        return error
    body, error = _body()
    if error:
        return error
    if "dry_run" in body and type(body["dry_run"]) is not bool:
        return jsonify(status="error", message="dry_run musi być wartością logiczną."), 400
    dry_run = bool(body.get("dry_run"))
    model, error = _pick_model(session, body, needed=not dry_run)
    if error:
        return error
    try:
        result = spellcheck.analyse_document(session, doc, model=model, dry_run=dry_run)
    except spellcheck.SpellcheckUnavailable:
        logger.exception("Spellcheck dictionary missing")
        return jsonify(status="error", error_code="dictionary_unavailable",
                       message="Słownik morfologiczny jest niedostępny."), 503
    except Exception:
        logger.exception("Transcript spellcheck failed for %s", doc_id)
        return jsonify(status="error", error_code="model_call_failed",
                       message="Wywołanie modelu nie powiodło się."), 502
    if dry_run:
        return jsonify(status="ok", dry_run=True, default_model=model, **result)
    return jsonify(status="ok", **result)


def _clean_items(body):
    items = body.get("items")
    if not isinstance(items, list) or not 1 <= len(items) <= spellcheck.MAX_REANALYSIS_ITEMS:
        return None
    cleaned = []
    for item in items:
        if not isinstance(item, dict):
            return None
        original, replacement, chapter = item.get("original"), item.get("replacement"), item.get("chapter")
        if not isinstance(original, str) or not original.strip() or len(original) > memory.MAX_WORD_LENGTH:
            return None
        if replacement is not None and (not isinstance(replacement, str) or len(replacement) > 500):
            return None
        if chapter is not None and (type(chapter) is not int or chapter < 0):
            return None
        cleaned.append({"original": original.strip(), "replacement": replacement, "chapter": chapter})
    return cleaned


@bp.route("/document/<int:doc_id>/transcript_spellcheck/reanalyze", methods=["POST"])
def document_transcript_spellcheck_reanalyze(doc_id: int):
    """Ask the model again about open proposals, with a longer stretch of the transcript around each word.

    Body ``{"items": [{"original", "replacement"?, "chapter"?}], "context_chars"?: 100-2500 (default 400),
    "model"?}``. The answer has one entry per item in ``results``: the new validated ``replacement`` (null when the
    earlier proposal stays, ``rejected`` says why), the longer ``context`` used and a short ``reason`` of what the
    speaker meant. Nothing is stored.
    """
    session = get_scoped_session()
    doc, error = _transcript(session, doc_id)
    if error:
        return error
    body, error = _body()
    if error:
        return error
    items = _clean_items(body)
    if items is None:
        return jsonify(status="error", message=f"items musi być listą od 1 do {spellcheck.MAX_REANALYSIS_ITEMS} "
                       "wpisów z polem original."), 400
    context_chars = body.get("context_chars", spellcheck.REANALYSIS_CONTEXT_STEPS[0])
    if type(context_chars) is not int or not 100 <= context_chars <= spellcheck.MAX_REANALYSIS_CONTEXT:
        return jsonify(status="error",
                       message=f"context_chars musi być liczbą od 100 do {spellcheck.MAX_REANALYSIS_CONTEXT}."), 400
    model, error = _pick_model(session, body, needed=True)
    if error:
        return error
    try:
        result = spellcheck.reanalyze(items, doc.text, model=model, chapter_types=doc.chapter_types,
                                      context_chars=context_chars, document_id=doc_id)
    except spellcheck.SpellcheckUnavailable:
        logger.exception("Spellcheck dictionary missing")
        return jsonify(status="error", error_code="dictionary_unavailable",
                       message="Słownik morfologiczny jest niedostępny."), 503
    except Exception:
        logger.exception("Transcript spellcheck reanalysis failed for %s", doc_id)
        return jsonify(status="error", error_code="model_call_failed",
                       message="Wywołanie modelu nie powiodło się."), 502
    return jsonify(status="ok", **result)


@bp.route("/document/<int:doc_id>/transcript_spellcheck/decisions", methods=["POST"])
def document_transcript_spellcheck_decisions(doc_id: int):
    """Remember what the reviewer decided in the panel, so later runs spend no model call on the same words.

    Body ``{"decisions": [{"original", "decision": "accepted"|"rejected", "replacement"?}]}`` (1-200 entries;
    ``replacement`` is the spelling the reviewer finally approved and is required for ``accepted``). Stored per
    channel (the document's byline). A pair approved in two documents becomes trusted and is pre-ticked next time.
    """
    _require_writer()
    session = get_scoped_session()
    doc = session.get(Document, doc_id)
    if doc is None:
        abort(404)
    body, error = _body()
    if error:
        return error
    try:
        counts = memory.record_decisions(session, document_id=doc_id, author=doc.byline,
                                         decisions=body.get("decisions"))
        session.commit()
    except memory.MemoryValidationError as exc:
        session.rollback()
        return jsonify(status="error", message=str(exc)), 400
    except Exception:
        session.rollback()
        logger.exception("Saving spellcheck decisions failed for %s", doc_id)
        return jsonify(status="error", message="Nie udało się zapisać decyzji."), 500
    return jsonify(status="success", **counts)


@bp.route("/transcript_spellcheck/memory/<int:memory_id>", methods=["DELETE"])
def transcript_spellcheck_memory_forget(memory_id: int):
    """Forget one remembered decision (e.g. "restore" a word the reviewer rejected by mistake)."""
    _require_writer()
    session = get_scoped_session()
    try:
        found = memory.forget(session, memory_id)
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("Forgetting spellcheck memory %s failed", memory_id)
        return jsonify(status="error", message="Nie udało się usunąć wpisu."), 500
    if not found:
        abort(404)
    return jsonify(status="success", id=memory_id)
