"""Auditable REST hand-off for human-operated LLM clients."""

import datetime as dt
from flask import Blueprint, abort, g, jsonify, request
from sqlalchemy import select
from library.db.engine import get_scoped_session
from library.db.models import FeedItem, FeedItemLlmAnalysis, Document, DocumentLlmAnalysis

bp = Blueprint("llm_analysis", __name__)


def _user():
    if getattr(g, "auth", None) is None or g.auth.kind != "user":
        abort(403, "user API key required")
    return g.auth.user_id


def _candidate(a):
    return {
        "id": a.id,
        "feed_item_id": a.feed_item_id,
        "status": a.status,
        "claimed_by": a.claimed_by,
        "prompt_payload": a.prompt_payload,
        "result": a.result,
        "recommendation": a.recommendation,
        "error": a.error,
    }


def _document(a):
    return {
        "id": a.id,
        "document_id": a.document_id,
        "status": a.status,
        "claimed_by": a.claimed_by,
        "input_payload": a.input_payload,
        "result": a.result,
        "next_status": a.next_status,
        "error": a.error,
    }


@bp.post("/feed_items/<int:item_id>/llm_analysis")
def request_candidate_analysis(item_id):
    user_id = _user()
    session = get_scoped_session()
    item = session.get(FeedItem, item_id)
    if item is None:
        abort(404)
    if item.status not in {"new", "error"}:
        abort(409, "feed item is not eligible for analysis")
    payload = {"url": item.url, "title": item.title, "summary": item.summary, "raw_payload": item.raw_payload}
    analysis = FeedItemLlmAnalysis(feed_item_id=item.id, requested_by_user_id=user_id, prompt_payload=payload)
    item.status = "llm_analysis_requested"
    session.add(analysis)
    session.commit()
    return jsonify(_candidate(analysis)), 201


@bp.get("/feed_item_llm_analyses")
def candidate_queue():
    _user()
    session = get_scoped_session()
    return jsonify(
        {
            "analyses": [
                _candidate(a)
                for a in session.scalars(
                    select(FeedItemLlmAnalysis)
                    .where(FeedItemLlmAnalysis.status.in_(["requested", "claimed"]))
                    .order_by(FeedItemLlmAnalysis.created_at)
                ).all()
            ]
        }
    )


@bp.patch("/feed_item_llm_analyses/<int:analysis_id>")
def update_candidate_analysis(analysis_id):
    _user()
    session = get_scoped_session()
    a = session.get(FeedItemLlmAnalysis, analysis_id)
    if a is None:
        abort(404)
    body = request.get_json(silent=True) or {}
    action = body.get("action")
    if action == "claim":
        if a.status != "requested":
            abort(409, "analysis already claimed or completed")
        a.status, a.claimed_by, a.claimed_at = (
            "claimed",
            (body.get("claimed_by") or "llm-client")[:255],
            dt.datetime.now(dt.timezone.utc),
        )
    elif action in {"complete", "error"}:
        if a.status not in {"requested", "claimed"}:
            abort(409, "analysis is not active")
        a.status, a.result, a.recommendation, a.error, a.completed_at = (
            ("completed" if action == "complete" else "error"),
            body.get("result"),
            body.get("recommendation"),
            body.get("error"),
            dt.datetime.now(dt.timezone.utc),
        )
    else:
        abort(400, "action must be claim, complete or error")
    session.commit()
    return jsonify(_candidate(a))


@bp.get("/document_llm_analyses")
def document_queue():
    _user()
    session = get_scoped_session()
    query = select(Document).where(Document.processing_status == "NEED_LLM_ANALYSIS").order_by(Document.id)
    return jsonify(
        {
            "documents": [
                {
                    "id": d.id,
                    "url": d.url,
                    "title": d.title,
                    "summary": d.summary,
                    "processing_status": d.processing_status,
                }
                for d in session.scalars(query).all()
            ]
        }
    )


@bp.get("/document/<int:document_id>/llm_analyses")
def document_history(document_id):
    _user()
    session = get_scoped_session()
    return jsonify(
        {
            "analyses": [
                _document(a)
                for a in session.scalars(
                    select(DocumentLlmAnalysis)
                    .where(DocumentLlmAnalysis.document_id == document_id)
                    .order_by(DocumentLlmAnalysis.created_at.desc())
                ).all()
            ]
        }
    )


@bp.post("/document/<int:document_id>/llm_analysis")
def request_document_analysis(document_id):
    user_id = _user()
    session = get_scoped_session()
    doc = session.get(Document, document_id)
    if doc is None:
        abort(404)
    if doc.processing_status != "NEED_LLM_ANALYSIS":
        abort(409, "document does not require LLM analysis")
    a = DocumentLlmAnalysis(
        document_id=document_id,
        requested_by_user_id=user_id,
        input_payload={"url": doc.url, "title": doc.title, "summary": doc.summary, "text": doc.text},
    )
    session.add(a)
    session.commit()
    return jsonify(_document(a)), 201


@bp.patch("/document_llm_analyses/<int:analysis_id>")
def update_document_analysis(analysis_id):
    _user()
    session = get_scoped_session()
    a = session.get(DocumentLlmAnalysis, analysis_id)
    if a is None:
        abort(404)
    body = request.get_json(silent=True) or {}
    action = body.get("action")
    if action == "claim":
        if a.status != "requested":
            abort(409)
        a.status, a.claimed_by = "claimed", (body.get("claimed_by") or "llm-client")[:255]
    elif action == "complete":
        if a.status not in {"requested", "claimed"} or body.get("next_status") not in {
            "URL_ADDED",
            "READY_FOR_EMBEDDING",
            "NEED_MANUAL_REVIEW",
            "ERROR",
        }:
            abort(409, "invalid analysis decision")
        a.status, a.result, a.next_status, a.completed_at = (
            "completed",
            body.get("result"),
            body["next_status"],
            dt.datetime.now(dt.timezone.utc),
        )
    elif action == "error":
        a.status, a.error, a.completed_at = "error", body.get("error"), dt.datetime.now(dt.timezone.utc)
    else:
        abort(400)
    session.commit()
    return jsonify(_document(a))


@bp.patch("/document/<int:document_id>/processing_status")
def set_document_status(document_id):
    _user()
    session = get_scoped_session()
    doc = session.get(Document, document_id)
    if doc is None:
        abort(404)
    body = request.get_json(silent=True) or {}
    status = body.get("status")
    if doc.processing_status != "NEED_LLM_ANALYSIS" or status not in {
        "URL_ADDED",
        "READY_FOR_EMBEDDING",
        "NEED_MANUAL_REVIEW",
        "ERROR",
    }:
        abort(409, "invalid document status decision")
    doc.set_processing_status(status)
    session.commit()
    return jsonify({"id": doc.id, "processing_status": doc.processing_status})
