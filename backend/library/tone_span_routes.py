"""REST for the on-demand tone passages of a document (``library/tone_spans.py``).

Nothing here is called by a pipeline: a reviewer asks for one chapter (or an article without chapters) at a time.
"""

import logging

from flask import Blueprint, abort, jsonify, request

from library.db.engine import get_scoped_session
from library.db.models import Document, DocumentToneSpan

logger = logging.getLogger(__name__)

bp = Blueprint("tone_spans", __name__)

_CORE_TONE_ERRORS = {
    "no_outliers": "Brak fragmentów odstających tonem do wyłączenia - najpierw wykryj fragmenty.",
    "no_tone": "Ten rozdział nie ma jeszcze oceny tonu - najpierw oceń ton rozdziału.",
    "text_too_short": "Po wyłączeniu fragmentów odstających zostaje za mało tekstu do oceny.",
    "failed": "Model odpowiedział w sposób, którego nie da się odczytać. Spróbuj innego modelu.",
}


def _model_from_request(session):
    """``(model, None)`` from the body (checked against the allowlist) or the household default; else ``(None, response)``."""
    from library import chapter_analysis_model as cam
    from library.llm_model_registry import is_selectable

    data = request.get_json(silent=True) or {}
    model = data.get("model")
    if model is not None and not isinstance(model, str):
        return None, (jsonify({"status": "error", "message": "model must be a string"}), 400)
    if model and not is_selectable(model, cam.TASK):
        return None, (jsonify({"status": "error", "message": "Model is not available"}), 400)
    return model or cam.default_model(session), None


@bp.route("/document/<int:doc_id>/tone_spans", methods=["GET"])
def list_tone_spans(doc_id: int):
    """Stored passages, rejected ones included (the reader hides them); optional ``?chapter_position=N``."""
    from library.tone_spans import span_to_dict

    session = get_scoped_session()
    if session.get(Document, doc_id) is None:
        abort(404, f"Document {doc_id} not found")
    query = session.query(DocumentToneSpan).filter(DocumentToneSpan.document_id == doc_id)
    chapter = request.args.get("chapter_position", type=int)
    if chapter is not None:
        query = query.filter(DocumentToneSpan.chapter_position == chapter)
    rows = query.order_by(DocumentToneSpan.chapter_position.asc().nullsfirst(), DocumentToneSpan.id.asc()).all()
    return jsonify({"status": "success", "doc_id": doc_id, "spans": [span_to_dict(row) for row in rows]})


@bp.route("/document/<int:doc_id>/chapter/<int:position>/detect_tone_spans", methods=["POST"])
def detect_chapter_tone_spans(doc_id: int, position: int):
    """Ask a model for the passages of ONE chapter that stand out from its tone or carry its substance.

    Body: optional ``{"model"}`` (the ``chapter_analysis`` allowlist, else the household default) and
    ``{"whole_document": true}``, which reads every chapter instead (the reader shows a short article with several
    ``##`` headings as one chapter). An article without ``##`` headings is one whole-document unit whatever
    ``position`` says. Replaces the earlier ``proposed`` passages of the scope; ``confirmed`` / ``rejected`` ones
    stay. Answers every stored passage of the scope.
    """
    from library.chapter_fragments import resolve_chapter_scope
    from library.tone_spans import refresh_document_tone_spans, span_to_dict

    session = get_scoped_session()
    model, error = _model_from_request(session)
    if error:
        return error
    doc = session.get(Document, doc_id)
    if doc is None:
        abort(404, f"Document {doc_id} not found")
    whole_document = (request.get_json(silent=True) or {}).get("whole_document") is True
    scope = None if whole_document else resolve_chapter_scope(doc, position)

    try:
        result = refresh_document_tone_spans(session, doc, model, chapter_position=scope)
        session.flush()
        spans = [span_to_dict(row) for row in result["all"]]
        session.commit()
    except ValueError:
        session.rollback()
        logger.info("tone spans refused for document %s chapter %s", doc_id, position, exc_info=True)
        return jsonify({"status": "error", "message": "Chapter not found or document has no usable text"}), 400
    except Exception:
        session.rollback()
        logger.exception("tone span detection failed for document %s chapter %s", doc_id, position)
        return jsonify({"status": "error", "message": "Tone span detection failed"}), 500

    report = (result.get("chapters") or [{}])[0]
    return jsonify({
        "status": "success",
        "doc_id": doc_id,
        "chapter_position": position,
        "model": model,
        "spans": spans,
        "kept_previous": False,
        "report": {key: value for key, value in report.items() if key not in ("chapter_title", "usage_log_ids")},
    })


@bp.route("/tone_spans/<int:span_id>", methods=["PATCH"])
def review_tone_span(span_id: int):
    """The reviewer's decision on one passage: ``{"status": "confirmed" | "rejected" | "proposed"}``."""
    from library.tone_spans import STATUSES, span_to_dict

    data = request.get_json(silent=True) or {}
    status = data.get("status")
    if status not in STATUSES:
        return jsonify({"status": "error", "message": f"status must be one of {list(STATUSES)}"}), 400
    session = get_scoped_session()
    row = session.get(DocumentToneSpan, span_id)
    if row is None:
        abort(404, f"Tone span {span_id} not found")
    row.status = status
    session.commit()
    return jsonify({"status": "success", "span": span_to_dict(row)})


@bp.route("/document/<int:doc_id>/chapter/<int:position>/core_tone", methods=["POST"])
def recompute_chapter_core_tone(doc_id: int, position: int):
    """Classify the chapter's tone again WITHOUT its outlier passages (``core_tone`` of the stored tone).

    Body: optional ``{"model"}``. 409 with a reason when there is nothing to recompute (no outliers, no stored tone,
    too little text left); 502 when the model's answer was unusable.
    """
    from library.chapter_fragments import resolve_chapter_scope
    from library.tone_spans import recompute_core_tone

    session = get_scoped_session()
    model, error = _model_from_request(session)
    if error:
        return error
    doc = session.get(Document, doc_id)
    if doc is None:
        abort(404, f"Document {doc_id} not found")
    scope = resolve_chapter_scope(doc, position)

    try:
        result = recompute_core_tone(session, doc, model, chapter_position=scope)
        session.commit()
    except ValueError as exc:
        session.rollback()
        reason = str(exc)
        # Only a key of the constant table ever reaches the response, never the exception's own text.
        for known_code, known_message in _CORE_TONE_ERRORS.items():
            if reason == known_code:
                return jsonify({"status": "error", "code": known_code, "message": known_message}), (
                    502 if known_code == "failed" else 409
                )
        logger.info("core tone refused for document %s chapter %s", doc_id, position, exc_info=True)
        return jsonify({"status": "error", "message": "Chapter not found or document has no usable text"}), 400
    except Exception:
        session.rollback()
        logger.exception("core tone failed for document %s chapter %s", doc_id, position)
        return jsonify({"status": "error", "message": "Core tone recomputation failed"}), 500

    report = result["report"]
    return jsonify({
        "status": "success",
        "doc_id": doc_id,
        "chapter_position": position,
        "model": model,
        "core_tone": result["core_tone"],
        "report": {key: value for key, value in report.items() if key != "usage_log_ids"},
    })
