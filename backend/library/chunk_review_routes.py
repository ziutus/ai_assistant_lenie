"""Flask blueprint: chunk review API + interactive HTML page.

Endpoints:
  GET  /analysis_runs?doc_id=<id>            — list runs for a document
  POST /document/<doc_id>/analyze_chunks     — create a new analysis run
  GET  /analysis_run/<run_id>/chunks         — full run data (chunks + segments)
  POST /analysis_run/<run_id>/extract_speakers
  PATCH /chunk/<chunk_id>                    — update status / type / topic / split_at_seg
  POST /chunk/<chunk_id>/execute_split
  POST /chunk/<chunk_id>/reanalyze
  GET  /chunk_review                         — interactive HTML review page
"""

import json
import logging
import threading
import uuid
from datetime import datetime

from flask import Blueprint, jsonify, request, abort
from sqlalchemy import select, update as sa_update

from library.db.engine import get_scoped_session
from library.db.models import (
    DocumentAnalysisRun, DocumentChunk, DocumentTopicSection, WebDocument,
)

logger = logging.getLogger(__name__)

bp = Blueprint("chunk_review", __name__)

# In-memory job registry for async analysis runs.
# Keyed by job_id (short UUID). Lives as long as the server process.
_analysis_jobs: dict[str, dict] = {}

ALLOWED_STATUSES = {"pending", "approved", "needs_reanalysis", "split_requested", "split"}
ALLOWED_TYPES = {"TEMAT", "REKLAMA"}


def _parse_segments(text_raw: str | None) -> list[dict]:
    if not text_raw or not text_raw.strip().startswith("["):
        return []
    try:
        segs = json.loads(text_raw.strip())
        if isinstance(segs, list) and segs and "start" in segs[0]:
            return segs
    except (ValueError, KeyError, IndexError):
        pass
    return []


def _chunk_to_dict(c: DocumentChunk) -> dict:
    return {
        "id": c.id,
        "position": c.position,
        "type": c.type,
        "topic": c.topic,
        "corrected_text": c.corrected_text,
        "summary": c.summary,
        "seg_start": c.seg_start,
        "seg_end": c.seg_end,
        "rewrite_ratio": c.rewrite_ratio,
        "status": c.status,
        "split_at_seg": c.split_at_seg,
        "split_first_type": c.split_first_type,
        "split_second_type": c.split_second_type,
    }


# ---------------------------------------------------------------------------
# API: GET /analysis_runs
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# API: POST /document/<doc_id>/analyze_chunks
# ---------------------------------------------------------------------------

@bp.route("/document/<int:doc_id>/analyze_chunks", methods=["POST"])
def analyze_document_chunks(doc_id: int):
    """Start an async chunk analysis run for an existing document.

    Body (JSON, all optional):
        model        — LLM model name (default: Bielik-11B-v3.0-Instruct)
        chunk_size   — max chars per chunk (default: 5000)
        no_synthesis — skip final synthesis step (default: false)

    Returns immediately with {job_id}. Poll GET /analysis_job/<job_id> for status.
    """
    data = request.get_json(silent=True) or {}
    model = data.get("model", "Bielik-11B-v3.0-Instruct")
    chunk_size = int(data.get("chunk_size", 5000))
    no_synthesis = bool(data.get("no_synthesis", False))

    job_id = uuid.uuid4().hex[:8]
    _analysis_jobs[job_id] = {
        "status": "running",
        "doc_id": doc_id,
        "model": model,
        "run_id": None,
        "chunk_count": None,
        "ad_count": None,
        "topic_section_count": None,
        "error": None,
        "progress": "Startowanie...",
    }

    def _run_analysis() -> None:
        from library.db.engine import get_session
        from library.document_analysis_service import DocumentAnalysisService

        session = get_session()
        try:
            def _progress(msg: str) -> None:
                _analysis_jobs[job_id]["progress"] = msg

            service = DocumentAnalysisService(session)
            run = service.create_run(
                doc_id=doc_id,
                model=model,
                chunk_size=chunk_size,
                no_synthesis=no_synthesis,
                progress_fn=_progress,
            )
            ad_count = sum(1 for c in run.chunks if c.type == "REKLAMA")
            _analysis_jobs[job_id].update({
                "status": "done",
                "run_id": run.id,
                "chunk_count": len(run.chunks),
                "ad_count": ad_count,
                "topic_section_count": len(run.topic_sections),
                "progress": f"Gotowe: {len(run.chunks)} chunków, {len(run.topic_sections)} sekcji",
            })
        except ValueError as exc:
            _analysis_jobs[job_id].update({"status": "failed", "error": str(exc)})
        except Exception as exc:
            logger.exception("background analysis failed for doc %d", doc_id)
            _analysis_jobs[job_id].update({"status": "failed", "error": str(exc)})
        finally:
            session.close()

    t = threading.Thread(target=_run_analysis, daemon=True, name=f"analysis-{job_id}")
    t.start()

    return jsonify({"status": "started", "job_id": job_id, "doc_id": doc_id})


@bp.route("/analysis_job/<job_id>", methods=["GET"])
def get_analysis_job(job_id: str):
    """Poll status of an async analysis job started by POST /document/<id>/analyze_chunks."""
    job = _analysis_jobs.get(job_id)
    if job is None:
        return jsonify({"status": "error", "message": "Job not found"}), 404
    return jsonify({"status": "success", "job": job})

@bp.route("/analysis_runs", methods=["GET"])
def list_runs():
    doc_id = request.args.get("doc_id", type=int)
    if not doc_id:
        return jsonify({"status": "error", "message": "doc_id required"}), 400

    session = get_scoped_session()
    runs = session.scalars(
        select(DocumentAnalysisRun)
        .where(DocumentAnalysisRun.document_id == doc_id)
        .order_by(DocumentAnalysisRun.created_at.desc())
    ).all()

    return jsonify({
        "status": "success",
        "doc_id": doc_id,
        "runs": [
            {
                "id": r.id,
                "model": r.model,
                "chunk_size": r.chunk_size,
                "created_at": r.created_at.isoformat(),
                "chunk_count": len(r.chunks),
            }
            for r in runs
        ],
    })


# ---------------------------------------------------------------------------
# API: GET /analysis_run/<run_id>/chunks
# ---------------------------------------------------------------------------

@bp.route("/analysis_run/<int:run_id>/chunks", methods=["GET"])
def get_run_chunks(run_id: int):
    session = get_scoped_session()
    run = session.get(DocumentAnalysisRun, run_id)
    if run is None:
        abort(404, f"Run {run_id} not found")

    doc = session.get(WebDocument, run.document_id)
    segments = _parse_segments(doc.text_raw if doc else None)

    topic_sections = session.scalars(
        select(DocumentTopicSection)
        .where(DocumentTopicSection.run_id == run_id)
        .order_by(DocumentTopicSection.position)
    ).all()

    return jsonify({
        "status": "success",
        "run": {
            "id": run.id,
            "model": run.model,
            "chunk_size": run.chunk_size,
            "synthesis": run.synthesis,
            "speakers": run.speakers or [],
            "created_at": run.created_at.isoformat(),
        },
        "document": {
            "id": doc.id if doc else None,
            "title": doc.title if doc else "",
            "original_id": doc.original_id if doc else "",
        },
        "segments": segments,
        "chunks": [_chunk_to_dict(c) for c in run.chunks],
        "topic_sections": [
            {
                "id": ts.id,
                "position": ts.position,
                "type": ts.type,
                "title": ts.title,
                "summary": ts.summary,
                "chunk_positions": ts.chunk_positions,
            }
            for ts in topic_sections
        ],
    })


# ---------------------------------------------------------------------------
# API: POST /analysis_run/<run_id>/extract_speakers
# ---------------------------------------------------------------------------

@bp.route("/analysis_run/<int:run_id>/extract_speakers", methods=["POST"])
def extract_speakers(run_id: int):
    """Extract speaker names from the first few chunks using LLM.

    Uses the intro text (first 3 chunks' original_text) where participants
    typically introduce themselves. Saves result to run.speakers.
    """
    session = get_scoped_session()
    run = session.get(DocumentAnalysisRun, run_id)
    if run is None:
        abort(404, f"Run {run_id} not found")

    intro_chunks = session.scalars(
        select(DocumentChunk)
        .where(DocumentChunk.run_id == run_id)
        .order_by(DocumentChunk.position)
        .limit(3)
    ).all()

    intro_text = "\n\n".join(
        c.corrected_text or c.original_text or ""
        for c in intro_chunks
    ).strip()

    if not intro_text:
        return jsonify({"status": "error", "message": "No text in first chunks"}), 400

    try:
        from library.chunk_llm_analysis import extract_speaker_info
        speakers = extract_speaker_info(intro_text, run.model)
    except Exception:
        logger.exception("extract_speaker_info failed for run %d", run_id)
        return jsonify({"status": "error", "message": "LLM call failed"}), 500

    run.speakers = speakers
    try:
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("DB save failed for run %d speakers", run_id)
        return jsonify({"status": "error", "message": "DB save failed"}), 500

    return jsonify({"status": "success", "speakers": speakers})


# ---------------------------------------------------------------------------
# API: PATCH /chunk/<chunk_id>
# ---------------------------------------------------------------------------

@bp.route("/chunk/<int:chunk_id>", methods=["PATCH", "OPTIONS"])
def update_chunk(chunk_id: int):
    if request.method == "OPTIONS":
        return jsonify({"status": "ok"}), 200

    session = get_scoped_session()
    chunk = session.get(DocumentChunk, chunk_id)
    if chunk is None:
        abort(404, f"Chunk {chunk_id} not found")

    data = request.get_json() or {}
    changed = False

    if "status" in data:
        if data["status"] not in ALLOWED_STATUSES:
            return jsonify({"status": "error", "message": f"Invalid status: {data['status']}"}), 400
        chunk.status = data["status"]
        changed = True

    if "type" in data:
        if data["type"] not in ALLOWED_TYPES:
            return jsonify({"status": "error", "message": f"Invalid type: {data['type']}"}), 400
        chunk.type = data["type"]
        changed = True

    if "topic" in data:
        chunk.topic = data["topic"] or None
        changed = True

    if "split_at_seg" in data:
        chunk.split_at_seg = data["split_at_seg"]
        changed = True

    if "split_first_type" in data:
        val = data["split_first_type"]
        if val and val not in ALLOWED_TYPES:
            return jsonify({"status": "error", "message": f"Invalid split_first_type: {val}"}), 400
        chunk.split_first_type = val or None
        changed = True

    if "split_second_type" in data:
        val = data["split_second_type"]
        if val and val not in ALLOWED_TYPES:
            return jsonify({"status": "error", "message": f"Invalid split_second_type: {val}"}), 400
        chunk.split_second_type = val or None
        changed = True

    if changed:
        chunk.updated_at = datetime.utcnow()
        try:
            session.commit()
        except Exception:
            session.rollback()
            logger.exception("Failed to update chunk %d", chunk_id)
            return jsonify({"status": "error", "message": "DB error"}), 500

    return jsonify({"status": "success", "chunk": _chunk_to_dict(chunk)})


# ---------------------------------------------------------------------------
# API: POST /chunk/<chunk_id>/execute_split
# ---------------------------------------------------------------------------

@bp.route("/chunk/<int:chunk_id>/execute_split", methods=["POST"])
def execute_split(chunk_id: int):
    """Split a chunk into two at the given segment index.

    Body (JSON):
        split_at_seg      — absolute segment index (required)
        split_first_type  — type for part before split: TEMAT | REKLAMA
        split_second_type — type for part after split:  TEMAT | REKLAMA

    Effect:
        - Deletes the original chunk
        - Inserts chunk A (before split) at original position
        - Inserts chunk B (after split) at original position + 1
        - Shifts all following chunks' positions by +1
    """
    session = get_scoped_session()
    chunk = session.get(DocumentChunk, chunk_id)
    if chunk is None:
        abort(404, f"Chunk {chunk_id} not found")

    data = request.get_json() or {}

    # Allow split data from body OR from what's already stored on the chunk
    split_at = data.get("split_at_seg", chunk.split_at_seg)
    first_type = data.get("split_first_type", chunk.split_first_type)
    second_type = data.get("split_second_type", chunk.split_second_type)

    if split_at is None:
        return jsonify({"status": "error", "message": "split_at_seg required"}), 400
    if first_type not in ALLOWED_TYPES:
        return jsonify({"status": "error", "message": f"Invalid split_first_type: {first_type}"}), 400
    if second_type not in ALLOWED_TYPES:
        return jsonify({"status": "error", "message": f"Invalid split_second_type: {second_type}"}), 400

    seg_start = chunk.seg_start or 0
    seg_end = chunk.seg_end

    if not (seg_start <= split_at < (seg_end or split_at + 1)):
        return jsonify({"status": "error",
                        "message": f"split_at_seg {split_at} out of range [{seg_start}, {seg_end})"}), 400

    # Reconstruct text from raw transcript segments
    doc = session.get(WebDocument, chunk.document_id)
    segments = _parse_segments(doc.text_raw if doc else None)

    def _text_from_segs(start: int, end: int | None) -> str:
        parts = []
        for seg in (segments[start:end] if segments else []):
            t = (seg.get("text") or "").strip()
            if t.startswith(">>"):
                t = t[2:].strip()
            if t:
                parts.append(t)
        return " ".join(parts)

    orig_pos = chunk.position
    run_id = chunk.run_id
    doc_id = chunk.document_id

    try:
        # Shift positions after orig_pos to a temp range to avoid unique constraint violation,
        # then back shifted by +1 (making room for chunk B).
        session.execute(
            sa_update(DocumentChunk)
            .where(DocumentChunk.run_id == run_id, DocumentChunk.position > orig_pos)
            .values(position=DocumentChunk.position + 10000)
        )
        session.execute(
            sa_update(DocumentChunk)
            .where(DocumentChunk.run_id == run_id, DocumentChunk.position > 10000)
            .values(position=DocumentChunk.position - 9999)
        )

        # Remove original chunk (its position is now free)
        session.delete(chunk)
        session.flush()

        # Chunk A — content before the split point
        text_a = _text_from_segs(seg_start, split_at)
        status_a = "approved" if first_type == "REKLAMA" else "pending"
        chunk_a = DocumentChunk(
            run_id=run_id, document_id=doc_id, position=orig_pos,
            type=first_type, topic=None,
            original_text=text_a or "(brak tekstu)",
            corrected_text=None, summary=None,
            seg_start=seg_start, seg_end=split_at,
            rewrite_ratio=None, status=status_a,
        )

        # Chunk B — content after the split point
        text_b = _text_from_segs(split_at, seg_end)
        status_b = "needs_reanalysis" if second_type == "TEMAT" else "approved"
        chunk_b = DocumentChunk(
            run_id=run_id, document_id=doc_id, position=orig_pos + 1,
            type=second_type, topic=None,
            original_text=text_b or "(brak tekstu)",
            corrected_text=None, summary=None,
            seg_start=split_at, seg_end=seg_end,
            rewrite_ratio=None, status=status_b,
        )

        session.add(chunk_a)
        session.add(chunk_b)
        session.commit()

        logger.info("Split chunk %d at seg %d → chunks at pos %d and %d",
                    chunk_id, split_at, orig_pos, orig_pos + 1)

        return jsonify({
            "status": "success",
            "chunk_a": _chunk_to_dict(chunk_a),
            "chunk_b": _chunk_to_dict(chunk_b),
        })

    except Exception:
        session.rollback()
        logger.exception("Failed to execute split on chunk %d", chunk_id)
        return jsonify({"status": "error", "message": "DB error during split"}), 500


# ---------------------------------------------------------------------------
# API: POST /chunk/<chunk_id>/reanalyze
# ---------------------------------------------------------------------------

@bp.route("/chunk/<int:chunk_id>/reanalyze", methods=["POST"])
def reanalyze_chunk(chunk_id: int):
    """Re-run LLM analysis on a single chunk.

    Body (JSON): {"mode": "full"|"semantic"}
      full     — rewrite from original_text + summarize (default)
      semantic — classify + summarize from existing corrected_text (no rewrite)

    Updates: corrected_text, summary, type, topic, rewrite_ratio, status → pending.
    """
    mode = (request.get_json(silent=True) or {}).get("mode", "full")

    session = get_scoped_session()
    chunk = session.get(DocumentChunk, chunk_id)
    if chunk is None:
        abort(404, f"Chunk {chunk_id} not found")

    run = session.get(DocumentAnalysisRun, chunk.run_id)
    if run is None:
        abort(404, f"Run {chunk.run_id} not found")

    model = run.model

    speakers = run.speakers or []

    try:
        if mode == "semantic" and chunk.corrected_text and chunk.corrected_text.strip():
            from library.chunk_llm_analysis import analyze_chunk_semantic
            result = analyze_chunk_semantic(chunk.corrected_text, model, speakers=speakers)
        else:
            text_to_analyze = chunk.original_text or ""
            if not text_to_analyze.strip():
                return jsonify({"status": "error", "message": "Chunk has no original_text to analyze"}), 400
            all_chunks = session.scalars(
                select(DocumentChunk)
                .where(DocumentChunk.run_id == chunk.run_id)
                .order_by(DocumentChunk.position)
            ).all()
            from library.chunk_llm_analysis import analyze_chunk
            result = analyze_chunk(text_to_analyze, model, position=chunk.position,
                                   total=len(all_chunks), speakers=speakers)
    except Exception:
        logger.exception("LLM call failed for chunk %d (mode=%s)", chunk_id, mode)
        return jsonify({"status": "error", "message": "LLM call failed"}), 500

    chunk.type = result["type"]
    chunk.topic = result["topic"] or None
    chunk.corrected_text = result["corrected_text"] or None
    chunk.summary = result["summary"] or None
    chunk.rewrite_ratio = result["rewrite_ratio"]
    chunk.status = "pending"
    chunk.updated_at = datetime.utcnow()

    try:
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("DB save failed for reanalyzed chunk %d", chunk_id)
        return jsonify({"status": "error", "message": "DB save failed"}), 500

    return jsonify({"status": "success", "chunk": _chunk_to_dict(chunk)})


# ---------------------------------------------------------------------------
# HTML review page
# ---------------------------------------------------------------------------

_HTML = r"""<!DOCTYPE html>
<html lang="pl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Przegląd chunków — Lenie AI</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:Arial,sans-serif;background:#f5f5f5;color:#222;font-size:14px}
#header{background:#1e293b;color:#fff;padding:14px 20px;display:flex;align-items:center;gap:16px;flex-wrap:wrap}
#header h1{font-size:1.05em;font-weight:bold;flex:1}
#header select,#header input{background:#334155;color:#fff;border:1px solid #475569;border-radius:4px;padding:5px 9px;font-size:0.88em}
#progress-bar{background:#0f172a;padding:8px 20px;display:flex;align-items:center;gap:12px;font-size:0.82em;color:#94a3b8}
#progress-fill{height:8px;border-radius:4px;background:#22c55e;transition:width .3s}
#progress-track{flex:1;background:#334155;border-radius:4px;height:8px}
#chunks{padding:16px 20px;display:flex;flex-direction:column;gap:14px}
.chunk{background:#fff;border-radius:6px;box-shadow:0 1px 3px rgba(0,0,0,.12);overflow:hidden}
.chunk-header{display:flex;align-items:center;gap:8px;padding:8px 14px;background:#f8fafc;border-bottom:1px solid #e2e8f0;flex-wrap:wrap}
.pos{font-size:0.8em;color:#64748b;font-weight:bold;min-width:28px}
.badge{display:inline-block;padding:2px 8px;border-radius:3px;font-size:0.78em;font-weight:bold;cursor:pointer;user-select:none;transition:opacity .15s}
.badge:hover{opacity:.8}
.badge.TEMAT{background:#dbeafe;color:#1d4ed8}
.badge.REKLAMA{background:#fef3c7;color:#92400e}
.badge.pending{background:#e2e8f0;color:#475569}
.badge.approved{background:#dcfce7;color:#15803d}
.badge.needs_reanalysis{background:#fee2e2;color:#b91c1c}
.badge.split_requested{background:#fef9c3;color:#713f12}
.badge.split{background:#f1f5f9;color:#94a3b8}
.topic-input{flex:1;border:none;border-bottom:1px dashed #cbd5e1;background:transparent;font-size:0.88em;padding:2px 4px;color:#334155;min-width:120px}
.topic-input:focus{outline:none;border-bottom-color:#3b82f6}
.btn-save{margin-left:auto;padding:3px 12px;border-radius:3px;border:none;background:#3b82f6;color:#fff;font-size:0.8em;cursor:pointer;font-weight:bold}
.btn-save:hover{background:#2563eb}
.btn-save:disabled{background:#94a3b8;cursor:default}
.chunk-body{min-height:60px}
.tc{padding:10px 14px;font-size:0.84em;line-height:1.6;overflow-wrap:anywhere}
.summary-box{padding:8px 14px 10px;background:#f8fafc;border-top:1px solid #e2e8f0;
  font-size:0.84em;line-height:1.6;color:#334155}
.summary-box em{color:#94a3b8}
.summary-label{font-size:0.76em;font-weight:bold;color:#64748b;text-transform:uppercase;
  letter-spacing:.03em;margin-bottom:4px}
/* segment row */
.seg{margin:0 0 8px;position:relative;padding-right:28px}
.seg:hover .split-btn{opacity:1}
.split-btn{position:absolute;right:2px;top:0;background:none;border:1px solid #e2e8f0;border-radius:3px;
  font-size:0.82em;cursor:pointer;padding:1px 4px;color:#94a3b8;opacity:0;transition:opacity .15s}
.split-btn:hover{background:#fef3c7;border-color:#fbbf24;color:#92400e}
.seg.split-mark{background:#fff7ed;border-left:3px solid #f97316;padding-left:6px;border-radius:2px}
.ts{color:#c00;text-decoration:none;font-weight:bold;font-size:0.8em;white-space:nowrap}
.ts:hover{text-decoration:underline}
.spname{font-size:0.76em;font-weight:bold;padding:1px 5px;border-radius:3px;margin-right:4px}
.sp1{background:#dbeafe;color:#1d4ed8}
.sp2{background:#dcfce7;color:#15803d}
.sc-arrow{color:#aaa;font-size:0.9em}
.summary-text{color:#334155}
em{color:#94a3b8}
#loading{text-align:center;padding:60px;color:#64748b;font-size:1.1em}
#error-msg{background:#fee2e2;color:#b91c1c;padding:12px 20px;border-radius:4px;margin:20px}
.saved-flash{color:#15803d;font-size:0.78em;margin-left:6px;opacity:0;transition:opacity .3s}
.btn-reanalyze{padding:3px 11px;border-radius:3px;border:none;background:#7c3aed;color:#fff;
  font-size:0.8em;cursor:pointer;font-weight:bold}
.btn-reanalyze:hover{background:#6d28d9}
.btn-reanalyze:disabled{background:#94a3b8;cursor:default}
.analyzing-spinner{display:inline-block;width:12px;height:12px;border:2px solid #fff;
  border-top-color:transparent;border-radius:50%;animation:spin .7s linear infinite;margin-right:4px;vertical-align:middle}
@keyframes spin{to{transform:rotate(360deg)}}
#btn-ads{padding:3px 11px;border-radius:3px;border:none;color:#fff;font-size:0.8em;cursor:pointer;font-weight:bold}
#btn-ads.hide-mode{background:#475569}
#btn-ads.show-mode{background:#b91c1c}
#btn-analyze-all{padding:3px 11px;border-radius:3px;border:none;background:#0369a1;color:#fff;
  font-size:0.8em;cursor:pointer;font-weight:bold}
#btn-analyze-all:hover{background:#0284c7}
#btn-analyze-all:disabled{background:#94a3b8;cursor:default}
.btn-view-chunk{padding:2px 8px;border-radius:3px;border:1px solid #94a3b8;background:#f1f5f9;
  color:#475569;font-size:0.75em;cursor:pointer}
.btn-view-chunk:hover{background:#e2e8f0}
#speakers-bar{background:#1e3a5f;color:#bfdbfe;padding:6px 20px;font-size:0.82em;display:none;
  align-items:center;gap:12px;flex-wrap:wrap}
#speakers-bar strong{color:#fff}
#btn-extract-speakers{padding:3px 10px;border-radius:3px;border:none;background:#1d4ed8;color:#fff;
  font-size:0.8em;cursor:pointer;font-weight:bold;margin-left:auto}
#btn-extract-speakers:disabled{background:#94a3b8;cursor:default}
.btn-reanalyze-sem{padding:3px 9px;border-radius:3px;border:none;background:#059669;color:#fff;
  font-size:0.8em;cursor:pointer;font-weight:bold;margin-left:4px}
.btn-reanalyze-sem:hover{background:#047857}
.btn-reanalyze-sem:disabled{background:#94a3b8;cursor:default}
.tc-corrected{white-space:pre-wrap;font-size:0.85em;line-height:1.6;color:#1e293b}
/* new-run panel */
#new-run-panel{display:none;background:#0f172a;padding:10px 20px;border-top:1px solid #334155;
  font-size:0.84em;color:#cbd5e1;flex-wrap:wrap;gap:10px;align-items:center}
#new-run-panel label{display:flex;align-items:center;gap:6px}
#new-run-panel select,#new-run-panel input[type=number]{
  background:#334155;color:#fff;border:1px solid #475569;border-radius:4px;padding:4px 8px;font-size:0.85em}
#btn-new-run{padding:3px 11px;border-radius:3px;border:none;background:#0369a1;color:#fff;
  font-size:0.8em;cursor:pointer;font-weight:bold}
#btn-new-run:hover{background:#0284c7}
#btn-new-run:disabled{background:#94a3b8;cursor:default}
#btn-toggle-new-run{padding:3px 9px;border-radius:3px;border:1px solid #475569;background:#1e293b;
  color:#94a3b8;font-size:0.8em;cursor:pointer}
#btn-toggle-new-run:hover{background:#334155;color:#fff}
#new-run-status{color:#fbbf24;font-size:0.82em}
/* split panel */
.split-panel{margin-top:10px;padding:10px 12px;background:#fff7ed;border:1px solid #fed7aa;
  border-radius:5px;font-size:0.84em}
.split-panel strong{color:#92400e}
.split-panel .sp-row{display:flex;align-items:center;gap:10px;margin-top:8px;flex-wrap:wrap}
.split-panel select{padding:3px 6px;border-radius:3px;border:1px solid #d1d5db;font-size:0.85em}
.split-panel .btn-confirm{padding:4px 12px;background:#f97316;color:#fff;border:none;border-radius:3px;
  cursor:pointer;font-weight:bold;font-size:0.82em}
.split-panel .btn-confirm:hover{background:#ea580c}
.split-panel .btn-cancel{padding:4px 10px;background:#e2e8f0;color:#475569;border:none;
  border-radius:3px;cursor:pointer;font-size:0.82em}
.split-panel .btn-cancel:hover{background:#cbd5e1}
.split-panel .split-hint{color:#92400e;font-size:0.8em;margin-top:4px}
</style>
</head>
<body>
<div id="header">
  <h1 id="doc-title">Lenie AI — przegląd chunków</h1>
  <label>Run:
    <select id="run-select" onchange="loadRun(this.value)"></select>
  </label>
  <button id="btn-toggle-new-run" onclick="toggleNewRunPanel()" title="Nowa analiza">+ Nowa</button>
  <label>API key:
    <input type="password" id="api-key-input" placeholder="x-api-key" oninput="saveKey(this.value)">
  </label>
</div>
<div id="new-run-panel">
  <label>Model:
    <select id="new-run-model">
      <option value="Bielik-11B-v3.0-Instruct">Bielik-11B v3.0 (Sherlock)</option>
      <option value="arklabs/Bielik-11B-v3.0-Instruct">Bielik-11B v3.0 (ArkLabs)</option>
    </select>
  </label>
  <label>Chunk:
    <input type="number" id="new-run-chunk-size" value="5000" min="1000" max="20000" step="500" style="width:80px">
    znaków
  </label>
  <label><input type="checkbox" id="new-run-no-synthesis"> Pomiń syntezę</label>
  <button id="btn-new-run" onclick="createNewRun()">▶ Utwórz analizę</button>
  <span id="new-run-status"></span>
</div>
<div id="progress-bar">
  <span id="progress-text">Ładowanie...</span>
  <div id="progress-track"><div id="progress-fill" style="width:0%"></div></div>
  <button id="btn-analyze-all" onclick="reanalyzeAll()" style="display:none">Analizuj wszystkie</button>
  <button id="btn-ads" class="hide-mode" onclick="toggleAds()">Ukryj reklamy</button>
</div>
<div id="speakers-bar">
  <strong>Rozmówcy:</strong>
  <span id="speakers-list"></span>
  <button id="btn-extract-speakers" onclick="extractSpeakers()">Wykryj rozmówców</button>
</div>
<div id="chunks"><div id="loading">Ładowanie danych...</div></div>

<script>
const params = new URLSearchParams(location.search);
let DOC_ID = parseInt(params.get("doc_id") || "0");
let RUN_ID = parseInt(params.get("run_id") || "0");
let API_KEY = params.get("api_key") || localStorage.getItem("lenie_api_key") || "";
let _data = null;
let _hideAds = false;
const _splitState = {};  // chunkId → {segIdx, ts, firstType, secondType}

document.getElementById("api-key-input").value = API_KEY;

function saveKey(v) {
  API_KEY = v;
  localStorage.setItem("lenie_api_key", v);
}

function headers() {
  return {"Content-Type": "application/json", "x-api-key": API_KEY};
}

async function apiFetch(path, opts = {}) {
  const r = await fetch(path, {...opts, headers: {...headers(), ...(opts.headers || {})}});
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

function secs2ts(s) {
  s = Math.floor(s);
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  return h ? `${String(h).padStart(2,"0")}:${String(m).padStart(2,"0")}:${String(sec).padStart(2,"0")}`
           : `${String(m).padStart(2,"0")}:${String(sec).padStart(2,"0")}`;
}

function ytUrl(videoId, secs) {
  return videoId ? `https://www.youtube.com/watch?v=${videoId}&t=${Math.floor(secs)}` : "#";
}

// Renders transcript segments. absOffset = chunk.seg_start (absolute index in full segments array).
// Each paragraph gets a scissors button storing the absolute segment index where it starts.
function renderSegments(segs, videoId, chunkId, absOffset) {
  if (!segs || !segs.length) return "<em>brak segmentów</em>";
  const MAX = 8;
  const groups = [];
  let cur = [], curStart = null, curSc = false, curRawIdx = 0;
  let rawIdx = 0;

  function flush() {
    if (cur.length) {
      groups.push({start: curStart, text: cur.join(" "), sc: curSc, rawIdx: curRawIdx});
      cur = []; curStart = null; curSc = false;
    }
  }

  for (const seg of segs) {
    const raw = (seg.text || "").trim();
    if (!raw) { rawIdx++; continue; }
    const isSc = raw.startsWith(">>");
    const text = isSc ? raw.slice(2).trim() : raw;
    if (isSc && cur.length) flush();
    if (curStart === null) { curStart = seg.start; curSc = isSc; curRawIdx = rawIdx; }
    cur.push(text);
    rawIdx++;
    if (text.match(/[.?!…]$/) || cur.length >= MAX) flush();
  }
  flush();

  const markedAbsIdx = _splitState[chunkId] ? _splitState[chunkId].segIdx : null;

  return groups.map(g => {
    const absIdx = absOffset + g.rawIdx;
    const ts = secs2ts(g.start);
    const url = ytUrl(videoId, g.start);
    const tsLink = `<a href="${url}" target="_blank" class="ts">[${ts}]</a>`;
    const prefix = g.sc ? `<span class="sc-arrow">▶</span> ` : "";
    const escaped = g.text.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
    const isMarked = markedAbsIdx === absIdx;
    const markClass = isMarked ? " split-mark" : "";
    const splitBtn = chunkId != null
      ? `<button class="split-btn" onclick="markSplit(${chunkId},${absIdx},'${ts}')" title="Podziel tutaj">✂</button>`
      : "";
    return `<p class="seg${markClass}" id="seg-${chunkId}-${absIdx}">${prefix}${tsLink}<br>${escaped}${splitBtn}</p>`;
  }).join("\n");
}

// --- split workflow ---

function markSplit(chunkId, absSegIdx, ts) {
  _splitState[chunkId] = {
    segIdx: absSegIdx,
    ts,
    firstType: "REKLAMA",
    secondType: "TEMAT",
  };
  rerenderChunkTranscript(chunkId);
}

function cancelSplit(chunkId) {
  delete _splitState[chunkId];
  rerenderChunkTranscript(chunkId);
}

async function confirmSplit(chunkId) {
  const st = _splitState[chunkId];
  if (!st) return;
  const ft = document.getElementById(`split-first-type-${chunkId}`)?.value || st.firstType;
  const st2 = document.getElementById(`split-second-type-${chunkId}`)?.value || st.secondType;
  const btn = document.querySelector(`#chunk-${chunkId} .btn-confirm`);
  if (btn) { btn.disabled = true; btn.textContent = "Dzielę..."; }
  try {
    const res = await apiFetch(`/chunk/${chunkId}/execute_split`, {
      method: "POST",
      body: JSON.stringify({
        split_at_seg: st.segIdx,
        split_first_type: ft,
        split_second_type: st2,
      }),
    });
    if (res.status === "success") {
      delete _splitState[chunkId];
      await loadRun(RUN_ID);  // reload all chunks to reflect new positions
    }
  } catch (e) {
    alert(`Błąd podziału: ${e.message}`);
    if (btn) { btn.disabled = false; btn.textContent = "Wykonaj podział"; }
  }
}

function renderSplitPanel(chunkId) {
  const st = _splitState[chunkId];
  const chunk = _data.chunks.find(c => c.id === chunkId);
  if (!st && !(chunk && chunk.split_at_seg != null)) return "";

  if (!st) return "";

  return `<div class="split-panel">
    <strong>✂ Punkt podziału: [${st.ts}]</strong>
    <div class="sp-row">
      <label>Część 1 (przed):
        <select id="split-first-type-${chunkId}">
          <option value="REKLAMA" ${st.firstType==="REKLAMA"?"selected":""}>REKLAMA</option>
          <option value="TEMAT" ${st.firstType==="TEMAT"?"selected":""}>TEMAT</option>
        </select>
      </label>
      <label>Część 2 (po):
        <select id="split-second-type-${chunkId}">
          <option value="TEMAT" ${st.secondType==="TEMAT"?"selected":""}>TEMAT</option>
          <option value="REKLAMA" ${st.secondType==="REKLAMA"?"selected":""}>REKLAMA</option>
        </select>
      </label>
      <button class="btn-confirm" onclick="confirmSplit(${chunkId})">Wykonaj podział</button>
      <button class="btn-cancel" onclick="cancelSplit(${chunkId})">Anuluj</button>
    </div>
    <div class="split-hint">Kliknij ✂ przy innym akapicie aby zmienić punkt podziału.</div>
  </div>`;
}


function rerenderChunkTranscript(chunkId) {
  const chunk = _data.chunks.find(c => c.id === chunkId);
  if (!chunk) return;
  const segs = _data.segments || [];
  const videoId = _data.document.original_id || "";
  const chunkSegs = segs.slice(chunk.seg_start ?? 0, chunk.seg_end ?? segs.length);
  const tcEl = document.querySelector(`#chunk-${chunkId} .tc`);
  if (tcEl) {
    tcEl.innerHTML = renderSegments(chunkSegs, videoId, chunkId, chunk.seg_start ?? 0)
                   + renderSplitPanel(chunkId);
  }
}

// --- status / type / topic ---

function updateProgress() {
  if (!_data) return;
  const temat = _data.chunks.filter(c => c.type !== "REKLAMA");
  const reklama = _data.chunks.filter(c => c.type === "REKLAMA");
  const approved = temat.filter(c => c.status === "approved").length;
  const pct = temat.length ? Math.round(approved / temat.length * 100) : 0;
  const adsPart = reklama.length
    ? ` • ${reklama.length} reklam${_hideAds ? " (ukryte)" : ""}`
    : "";
  document.getElementById("progress-text").textContent =
    `TEMAT: ${approved}/${temat.length} zatwierdzonych (${pct}%)${adsPart}`;
  document.getElementById("progress-fill").style.width = pct + "%";
  updateAdsButton();
  updateAnalyzeAllButton();
}

function cycleStatus(chunkId) {
  const order = ["pending", "approved", "needs_reanalysis"];
  const chunk = _data.chunks.find(c => c.id === chunkId);
  if (!chunk) return;
  const idx = order.indexOf(chunk.status);
  const next = order[(idx + 1) % order.length];
  saveChunk(chunkId, {status: next});
}

function toggleType(chunkId) {
  const chunk = _data.chunks.find(c => c.id === chunkId);
  if (!chunk) return;
  saveChunk(chunkId, {type: chunk.type === "TEMAT" ? "REKLAMA" : "TEMAT"});
}

function saveTopic(chunkId) {
  const input = document.getElementById(`topic-${chunkId}`);
  saveChunk(chunkId, {topic: input.value});
}

async function saveChunk(chunkId, updates) {
  const btn = document.getElementById(`save-${chunkId}`);
  if (btn) btn.disabled = true;
  try {
    const res = await apiFetch(`/chunk/${chunkId}`, {
      method: "PATCH",
      body: JSON.stringify(updates),
    });
    if (res.status === "success") {
      const chunk = _data.chunks.find(c => c.id === chunkId);
      if (chunk) Object.assign(chunk, res.chunk);
      refreshChunkHeader(chunkId);
      updateProgress();
      const flash = document.getElementById(`flash-${chunkId}`);
      if (flash) { flash.style.opacity = "1"; setTimeout(() => flash.style.opacity = "0", 1500); }
    }
  } catch (e) {
    alert(`Błąd zapisu chunka ${chunkId}: ${e.message}`);
  } finally {
    if (btn) btn.disabled = false;
  }
}

function refreshChunkHeader(chunkId) {
  const chunk = _data.chunks.find(c => c.id === chunkId);
  if (!chunk) return;
  const typeBadge = document.getElementById(`type-${chunkId}`);
  if (typeBadge) {
    typeBadge.textContent = chunk.type;
    typeBadge.className = `badge ${chunk.type}`;
  }
  const stBadge = document.getElementById(`status-${chunkId}`);
  if (stBadge) {
    stBadge.textContent = chunk.status;
    stBadge.className = `badge ${chunk.status}`;
  }
}

function renderChunk(chunk, segs, videoId) {
  const chunkSegs = segs.slice(chunk.seg_start ?? 0, chunk.seg_end ?? segs.length);
  const transcript = renderSegments(chunkSegs, videoId, chunk.id, chunk.seg_start ?? 0);
  const splitPanel = renderSplitPanel(chunk.id);

  // Default: show corrected text when available, fall back to raw transcript
  const hasCorrected = !!chunk.corrected_text;
  const rawStyle    = hasCorrected ? 'display:none'  : 'display:block';
  const corStyle    = hasCorrected ? 'display:block' : 'display:none';
  const viewBtnLabel = hasCorrected ? "Surowy" : "Poprawiony";

  const summaryContent = chunk.summary
    ? chunk.summary.replace(/\n/g,"<br>")
    : `<em>${chunk.type === "REKLAMA" ? "brak streszczenia (reklama)" : "brak streszczenia"}</em>`;

  return `
<div class="chunk" id="chunk-${chunk.id}">
  <div class="chunk-header">
    <span class="pos">#${chunk.position}</span>
    <span class="badge ${chunk.type}" id="type-${chunk.id}"
          onclick="toggleType(${chunk.id})" title="Kliknij aby zmienić typ">${chunk.type}</span>
    <span class="badge ${chunk.status}" id="status-${chunk.id}"
          onclick="cycleStatus(${chunk.id})" title="Kliknij aby zmienić status">${chunk.status}</span>
    <input class="topic-input" id="topic-${chunk.id}" value="${(chunk.topic||"").replace(/"/g,"&quot;")}"
           placeholder="temat" title="Edytuj temat">
    <button class="btn-save" id="save-${chunk.id}"
            onclick="saveTopic(${chunk.id})">Zapisz</button>
    <span class="saved-flash" id="flash-${chunk.id}">✓ zapisano</span>
    <button class="btn-reanalyze" id="reanalyze-${chunk.id}"
            onclick="reanalyzeChunk(${chunk.id},'full')">▶ Pełna</button>
    ${hasCorrected
      ? `<button class="btn-reanalyze-sem" id="reanalyze-sem-${chunk.id}"
               onclick="reanalyzeChunk(${chunk.id},'semantic')">▶ Sem.</button>`
      : ""}
    ${hasCorrected
      ? `<button class="btn-view-chunk" id="btn-view-${chunk.id}"
               onclick="toggleChunkView(${chunk.id})">${viewBtnLabel}</button>`
      : ""}
  </div>
  <div class="chunk-body">
    <div class="tc">
      <div class="tc-raw" style="${rawStyle}">${transcript}${splitPanel}</div>
      <div class="tc-corrected" style="${corStyle}">${(chunk.corrected_text||"").replace(/\n/g,"<br>")}</div>
    </div>
    <div class="summary-box">
      <div class="summary-label">Streszczenie</div>
      ${summaryContent}
    </div>
  </div>
</div>`;
}

async function reanalyzeChunk(chunkId, mode) {
  mode = mode || "full";
  const btnFull = document.getElementById(`reanalyze-${chunkId}`);
  const btnSem  = document.getElementById(`reanalyze-sem-${chunkId}`);
  const activeBtn = mode === "semantic" ? (btnSem || btnFull) : btnFull;
  if (btnFull) { btnFull.disabled = true; }
  if (btnSem)  { btnSem.disabled  = true; }
  if (activeBtn) activeBtn.innerHTML = '<span class="analyzing-spinner"></span>...';
  try {
    const res = await apiFetch(`/chunk/${chunkId}/reanalyze`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({mode}),
    });
    if (res.status === "success") {
      const chunk = _data.chunks.find(c => c.id === chunkId);
      if (chunk) Object.assign(chunk, res.chunk);
      const el = document.getElementById(`chunk-${chunkId}`);
      if (el && _data) {
        const segs = _data.segments || [];
        const videoId = _data.document.original_id || "";
        el.outerHTML = renderChunk(res.chunk, segs, videoId);
      }
      updateProgress();
    }
  } catch (e) {
    alert(`Błąd analizy chunka ${chunkId}: ${e.message}`);
    if (btnFull) { btnFull.disabled = false; btnFull.innerHTML = "▶ Pełna"; }
    if (btnSem)  { btnSem.disabled  = false; btnSem.innerHTML  = "▶ Sem."; }
  }
}

function renderSpeakers(speakers) {
  const bar = document.getElementById("speakers-bar");
  const list = document.getElementById("speakers-list");
  if (!bar || !list) return;
  if (speakers && speakers.length > 0) {
    list.innerHTML = speakers.map(sp =>
      `<span><b>${sp.name}</b>${sp.role ? ` (${sp.role})` : ""}</span>`
    ).join(" &nbsp;|&nbsp; ");
    bar.style.display = "flex";
  } else {
    list.innerHTML = "";
    bar.style.display = "flex";  // show bar with just the button
  }
}

async function extractSpeakers() {
  const btn = document.getElementById("btn-extract-speakers");
  btn.disabled = true;
  btn.textContent = "Wykrywam...";
  try {
    const res = await apiFetch(`/analysis_run/${RUN_ID}/extract_speakers`, {method: "POST"});
    if (res.status === "success") {
      if (_data) _data.run.speakers = res.speakers;
      renderSpeakers(res.speakers);
      btn.textContent = res.speakers.length
        ? `Wykryj ponownie (${res.speakers.length})`
        : "Nie wykryto — spróbuj ponownie";
    }
  } catch (e) {
    alert(`Błąd wykrywania rozmówców: ${e.message}`);
    btn.textContent = "Wykryj rozmówców";
  }
  btn.disabled = false;
}

function updateAdsButton() {
  const btn = document.getElementById("btn-ads");
  if (!btn || !_data) return;
  const count = _data.chunks.filter(c => c.type === "REKLAMA").length;
  if (_hideAds) {
    btn.textContent = `Pokaż reklamy (${count})`;
    btn.className = "show-mode";
  } else {
    btn.textContent = `Ukryj reklamy (${count})`;
    btn.className = "hide-mode";
  }
}

function updateAnalyzeAllButton() {
  const btn = document.getElementById("btn-analyze-all");
  if (!btn || !_data) return;
  const count = _data.chunks.filter(c => c.status === "needs_reanalysis").length;
  if (count > 0) {
    btn.textContent = `Analizuj wszystkie (${count})`;
    btn.style.display = "";
    btn.disabled = false;
  } else {
    btn.style.display = "none";
  }
}

function applyChunkFilter() {
  if (!_data) return;
  document.querySelectorAll(".chunk").forEach(el => {
    const chunkId = parseInt(el.id.replace("chunk-", ""));
    const chunk = _data.chunks.find(c => c.id === chunkId);
    if (chunk) el.style.display = (_hideAds && chunk.type === "REKLAMA") ? "none" : "";
  });
}

async function reanalyzeAll() {
  const btn = document.getElementById("btn-analyze-all");
  const pending = _data.chunks.filter(c => c.status === "needs_reanalysis");
  if (!pending.length) return;
  btn.disabled = true;
  for (let i = 0; i < pending.length; i++) {
    btn.textContent = `Analizuję ${i + 1}/${pending.length}...`;
    const mode = pending[i].corrected_text ? "semantic" : "full";
    await reanalyzeChunk(pending[i].id, mode);
  }
  updateProgress();
}

function toggleChunkView(chunkId) {
  const raw = document.querySelector(`#chunk-${chunkId} .tc-raw`);
  const cor = document.querySelector(`#chunk-${chunkId} .tc-corrected`);
  const btn = document.getElementById(`btn-view-${chunkId}`);
  if (!raw || !cor || !btn) return;
  const showingCorrected = cor.style.display !== "none";
  raw.style.display = showingCorrected ? "block" : "none";
  cor.style.display = showingCorrected ? "none" : "block";
  btn.textContent = showingCorrected ? "Poprawiony" : "Surowy";
}

function toggleAds() {
  _hideAds = !_hideAds;
  localStorage.setItem(`lenie_hide_ads_${RUN_ID}`, _hideAds ? "1" : "0");
  applyChunkFilter();
  updateProgress();
}

function renderAll() {
  if (!_data) return;
  const videoId = _data.document.original_id || "";
  const segs = _data.segments || [];
  document.getElementById("doc-title").textContent = _data.document.title || "Lenie AI";
  document.getElementById("chunks").innerHTML =
    _data.chunks.map(c => renderChunk(c, segs, videoId)).join("\n");
  renderSpeakers(_data.run.speakers || []);
  const extractBtn = document.getElementById("btn-extract-speakers");
  if (extractBtn) extractBtn.textContent = (_data.run.speakers || []).length
    ? `Wykryj ponownie (${_data.run.speakers.length})`
    : "Wykryj rozmówców";
  updateProgress();
  applyChunkFilter();
}

async function loadRun(runId) {
  RUN_ID = parseInt(runId);
  _hideAds = localStorage.getItem(`lenie_hide_ads_${RUN_ID}`) === "1";
  document.getElementById("chunks").innerHTML = '<div id="loading">Ładowanie...</div>';
  try {
    _data = await apiFetch(`/analysis_run/${RUN_ID}/chunks`);
    renderAll();
  } catch (e) {
    document.getElementById("chunks").innerHTML =
      `<div id="error-msg">Błąd: ${e.message}. Sprawdź API key i uruchomiony backend.</div>`;
  }
}

async function loadRuns() {
  if (!DOC_ID) {
    document.getElementById("chunks").innerHTML =
      '<div id="error-msg">Podaj <code>?doc_id=&lt;id&gt;</code> w URL.</div>';
    return;
  }
  try {
    const res = await apiFetch(`/analysis_runs?doc_id=${DOC_ID}`);
    const sel = document.getElementById("run-select");
    sel.innerHTML = res.runs.map(r =>
      `<option value="${r.id}" ${r.id === RUN_ID ? "selected" : ""}>` +
      `Run #${r.id} — ${r.model} — ${r.created_at.slice(0,16).replace("T"," ")}</option>`
    ).join("");
    if (!RUN_ID && res.runs.length) RUN_ID = res.runs[0].id;
    if (RUN_ID) await loadRun(RUN_ID);
  } catch (e) {
    document.getElementById("chunks").innerHTML =
      `<div id="error-msg">Błąd ładowania runów: ${e.message}.<br>Sprawdź czy backend działa i API key jest poprawny.</div>`;
  }
}

function toggleNewRunPanel() {
  const panel = document.getElementById("new-run-panel");
  panel.style.display = panel.style.display === "flex" ? "none" : "flex";
}

async function createNewRun() {
  if (!DOC_ID) { alert("Brak doc_id w URL — odśwież stronę z ?doc_id=<id>"); return; }
  const model = document.getElementById("new-run-model").value;
  const chunkSize = parseInt(document.getElementById("new-run-chunk-size").value) || 5000;
  const noSynthesis = document.getElementById("new-run-no-synthesis").checked;
  const btn = document.getElementById("btn-new-run");
  const statusEl = document.getElementById("new-run-status");

  btn.disabled = true;
  btn.textContent = "Analizuję...";
  statusEl.textContent = "⏳ Startowanie...";

  let jobId = null;
  try {
    const res = await apiFetch(`/document/${DOC_ID}/analyze_chunks`, {
      method: "POST",
      body: JSON.stringify({model, chunk_size: chunkSize, no_synthesis: noSynthesis}),
    });
    if (res.status !== "started") throw new Error(res.message || "Nieznany błąd");
    jobId = res.job_id;
  } catch (e) {
    statusEl.textContent = `✗ Błąd: ${e.message}`;
    btn.textContent = "▶ Utwórz analizę";
    btn.disabled = false;
    return;
  }

  // Poll until done or failed
  const poll = setInterval(async () => {
    try {
      const res = await apiFetch(`/analysis_job/${jobId}`);
      const job = res.job;
      statusEl.textContent = `⏳ ${job.progress || job.status}`;

      if (job.status === "done") {
        clearInterval(poll);
        statusEl.textContent =
          `✓ Gotowe: run #${job.run_id}, ${job.chunk_count} chunków (${job.ad_count} reklam), ${job.topic_section_count} sekcji`;
        btn.textContent = "▶ Utwórz analizę";
        btn.disabled = false;
        await loadRuns();
      } else if (job.status === "failed") {
        clearInterval(poll);
        statusEl.textContent = `✗ Błąd: ${job.error || "nieznany"}`;
        btn.textContent = "▶ Utwórz analizę";
        btn.disabled = false;
      }
    } catch (e) {
      // transient network error — keep polling
      statusEl.textContent = `⏳ Sprawdzam... (${e.message})`;
    }
  }, 5000);  // poll every 5 seconds
}

loadRuns();
</script>
</body>
</html>"""


@bp.route("/chunk_review", methods=["GET"])
def chunk_review_page():
    from flask import Response
    return Response(_HTML, mimetype="text/html")
