"""Flask blueprint: chunk review API.

The interactive review UI lives in the React frontend (`/chunks/:id` in
web_interface_react) — the legacy standalone HTML page previously served at
GET /chunk_review was removed 2026-07-08 (Etap 6): it predated modes/sections/
embeddings/notes and only ever supported the YouTube/transcript case.

Endpoints:
  GET  /analysis_runs?doc_id=<id>            — list runs for a document
  GET  /document/<doc_id>/chapters           — table of contents (H1/H2 headers, or TEMAT chunk topics as fallback)
  GET  /document/<doc_id>/chapter/<position> — one chapter's text (reader view)
  POST /document/<doc_id>/analyze_chunks     — create a new analysis run
  GET  /analysis_run/<run_id>/chunks         — run data (chunks + segments;
                                               lite/section_id/offset/limit for books)
  POST /analysis_run/<run_id>/extract_speakers
  PATCH /analysis_run/<run_id>               — run workflow status
  PATCH /topic_section/<section_id>          — edit section title
  PATCH /chunk/<chunk_id>                    — update status / type / topic / split_at_seg
  POST /chunk/<chunk_id>/execute_split
  POST /chunk/<chunk_id>/reanalyze
"""

import json
import logging
import threading
import uuid
from datetime import datetime

from flask import Blueprint, jsonify, request, abort
from sqlalchemy import func, select, update as sa_update

from library.db.engine import get_scoped_session
from library.db.models import (
    DocumentAnalysisRun, DocumentChunk, DocumentRemovedLine, DocumentTopicSection,
    WebDocument, WebsiteEmbedding,
)

logger = logging.getLogger(__name__)

bp = Blueprint("chunk_review", __name__)

# In-memory job registry for async analysis runs.
# Keyed by job_id (short UUID). Lives as long as the server process.
_analysis_jobs: dict[str, dict] = {}

# In-memory job registry for async embedding-generation runs (separate from
# _analysis_jobs — different job shape, polled via /embedding_job/<job_id>).
_embedding_jobs: dict[str, dict] = {}

ALLOWED_STATUSES = {"pending", "approved", "needs_reanalysis", "split_requested", "split", "skipped"}
ALLOWED_TYPES = {"TEMAT", "REKLAMA", "SZUM"}
ALLOWED_RUN_STATUSES = {"created", "in_review", "reviewed"}


def _removed_lines_diff(old_text: str, new_text: str) -> list[str]:
    """Return non-empty lines (stripped) present in old_text but absent from new_text.

    Whole-line set difference, order preserved from old_text. A line still
    present elsewhere in new_text is not reported even if one of its
    occurrences was removed — good enough for cleaner-rule mining.
    """
    new_lines = {ln.strip() for ln in new_text.split("\n")}
    seen: set[str] = set()
    removed: list[str] = []
    for ln in old_text.split("\n"):
        stripped = ln.strip()
        if stripped and stripped not in new_lines and stripped not in seen:
            seen.add(stripped)
            removed.append(stripped)
    return removed


def _log_removed_lines(session, *, document_id: int, run_id: int | None,
                       chunk_id: int | None, lines: list[str], source: str) -> int:
    """Queue DocumentRemovedLine rows on the session (no commit). Returns row count.

    Removed lines feed cleaner-rule mining (article_cleaner.py / site_rules.json):
    aggregate what the automatic cleanup missed and humans had to remove.
    """
    count = 0
    for line in lines:
        if not line or not line.strip():
            continue
        session.add(DocumentRemovedLine(
            document_id=document_id, run_id=run_id, chunk_id=chunk_id,
            source=source, line_text=line.strip(),
        ))
        count += 1
    return count


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


TEXT_PREVIEW_CHARS = 200


def _chunk_to_dict(c: DocumentChunk, has_embeddings: bool | None = None, lite: bool = False) -> dict:
    """Serialize a chunk. lite=True drops the full texts (book-sized runs are
    lazy-loaded per section) and ships a short preview + length instead."""
    text = c.corrected_text or c.original_text or ""
    return {
        "id": c.id,
        "position": c.position,
        "type": c.type,
        "topic": c.topic,
        "original_text": None if lite else c.original_text,
        "corrected_text": None if lite else c.corrected_text,
        "text_length": len(text),
        "text_preview": text[:TEXT_PREVIEW_CHARS] if lite else None,
        "summary": c.summary,
        "seg_start": c.seg_start,
        "seg_end": c.seg_end,
        "rewrite_ratio": c.rewrite_ratio,
        "status": c.status,
        "split_at_seg": c.split_at_seg,
        "split_first_type": c.split_first_type,
        "split_second_type": c.split_second_type,
        "obsidian_note_paths": c.obsidian_note_paths or [],
        "has_embeddings": bool(has_embeddings) if has_embeddings is not None else None,
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
        mode         — "transcript" (default) or "article"
        split_only   — split into chunks without any LLM analysis (default: false)
        scope_chapter — 1-based chapter position (see GET /document/<id>/chapters);
                       analyze only that chapter (article mode only)

    Returns immediately with {job_id}. Poll GET /analysis_job/<job_id> for status.
    """
    from library.document_analysis_service import ANALYSIS_MODES

    data = request.get_json(silent=True) or {}
    model = data.get("model", "Bielik-11B-v3.0-Instruct")
    chunk_size = int(data.get("chunk_size", 5000))
    no_synthesis = bool(data.get("no_synthesis", False))
    mode = data.get("mode", "transcript")
    split_only = bool(data.get("split_only", False))
    scope_chapter = data.get("scope_chapter")
    if mode not in ANALYSIS_MODES:
        return jsonify({"status": "error", "message": f"Invalid mode: {mode}"}), 400
    if scope_chapter is not None:
        try:
            scope_chapter = int(scope_chapter)
        except (TypeError, ValueError):
            return jsonify({"status": "error", "message": "scope_chapter must be an integer"}), 400
        if mode != "article":
            return jsonify({"status": "error", "message": "scope_chapter requires article mode"}), 400

    job_id = uuid.uuid4().hex[:8]
    _analysis_jobs[job_id] = {
        "status": "running",
        "doc_id": doc_id,
        "model": model,
        "mode": mode,
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
                mode=mode,
                split_only=split_only,
                scope_chapter=scope_chapter,
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


@bp.route("/document/<int:doc_id>/split_preview", methods=["GET"])
def split_preview(doc_id: int):
    """Preview how a document would split into chunks — no LLM calls, no DB writes.

    Query params: mode (article|transcript, default article), chunk_size (default 5000),
    scope_chapter (1-based chapter position — article mode only).
    Transcript sizes are approximate (speaker labeling happens only in a real run).
    """
    from library.document_analysis_service import ANALYSIS_MODES, _extract_text
    from library.text_functions import detect_chapters, split_markdown_into_chunks, split_text_into_sentence_chunks

    mode = request.args.get("mode", "article")
    chunk_size = request.args.get("chunk_size", 5000, type=int)
    scope_chapter = request.args.get("scope_chapter", type=int)
    if mode not in ANALYSIS_MODES:
        return jsonify({"status": "error", "message": f"Invalid mode: {mode}"}), 400
    if not 500 <= chunk_size <= 50000:
        return jsonify({"status": "error", "message": f"chunk_size out of range: {chunk_size}"}), 400
    if scope_chapter is not None and mode != "article":
        return jsonify({"status": "error", "message": "scope_chapter requires article mode"}), 400

    session = get_scoped_session()
    doc = session.get(WebDocument, doc_id)
    if doc is None:
        abort(404, f"Document {doc_id} not found")

    text, field = _extract_text(doc, prefer_md=(mode == "article"))
    if not text:
        return jsonify({"status": "error", "message": "Document has no usable text"}), 400

    scope_title = None
    if mode == "article":
        if scope_chapter is not None:
            chapters = detect_chapters(text)
            if not chapters:
                return jsonify({
                    "status": "error",
                    "message": "Document has no detectable chapters (H1/H2 headers)",
                }), 400
            match = next((c for c in chapters if c["position"] == scope_chapter), None)
            if match is None:
                return jsonify({
                    "status": "error",
                    "message": f"scope_chapter {scope_chapter} out of range (1..{len(chapters)})",
                }), 400
            text = text[match["char_start"]:match["char_end"]].strip()
            scope_title = match["title"]
        parts = split_markdown_into_chunks(text, chunk_size)
    else:
        from library.chunk_llm_analysis import remove_speech_fillers
        parts = split_text_into_sentence_chunks(remove_speech_fillers(text), chunk_size)

    return jsonify({
        "status": "success",
        "mode": mode,
        "chunk_size": chunk_size,
        "source_field": field,
        "scope_chapter": scope_chapter,
        "scope_title": scope_title,
        "text_length": len(text),
        "chunk_count": len(parts),
        "chunk_sizes": [len(p) for p in parts],
    })


def _latest_run_for_document(session, doc_id: int) -> DocumentAnalysisRun | None:
    return session.scalars(
        select(DocumentAnalysisRun)
        .where(DocumentAnalysisRun.document_id == doc_id)
        .order_by(DocumentAnalysisRun.created_at.desc())
    ).first()


def _chunk_based_chapters(run: DocumentAnalysisRun) -> list[dict]:
    """Fallback table of contents built from TEMAT chunk topics.

    Used when the document's text has no markdown H1/H2 headers — the case
    for YouTube/movie transcripts, which are split into topic chunks
    (transcript-mode analysis) instead of markdown-structured text.
    REKLAMA/SZUM chunks are excluded, same as the note-writing workflow.
    """
    temat_chunks = [c for c in sorted(run.chunks, key=lambda c: c.position) if c.type == "TEMAT"]
    return [
        {
            "position": i,
            "level": 1,
            "title": chunk.topic or f"Fragment {i}",
            "chunk_id": chunk.id,
            "length": len(chunk.corrected_text or chunk.original_text or ""),
        }
        for i, chunk in enumerate(temat_chunks, start=1)
    ]


@bp.route("/document/<int:doc_id>/chapters", methods=["GET"])
def document_chapters(doc_id: int):
    """Detect the document's table of contents.

    Prefers markdown H1/H2 headers (text_md, article-mode analysis). When
    none are found, falls back to TEMAT chunk topics from the latest
    analysis run — the only structure transcript-mode documents (YouTube/
    movie) have. Chapter positions can be passed as scope_chapter to
    POST /analyze_chunks or GET /split_preview to analyze a single chapter
    (markdown chapters only — chunk-based chapters aren't a valid scope there).
    """
    from library.document_analysis_service import _extract_text
    from library.text_functions import detect_chapters

    session = get_scoped_session()
    doc = session.get(WebDocument, doc_id)
    if doc is None:
        abort(404, f"Document {doc_id} not found")

    text, field = _extract_text(doc, prefer_md=True)
    chapters = detect_chapters(text) if text else []
    source = "markdown" if chapters else "none"

    run = _latest_run_for_document(session, doc_id)
    if not chapters and run:
        chapters = _chunk_based_chapters(run)
        if chapters:
            source = "chunks"

    if not text and source == "none":
        return jsonify({"status": "error", "message": "Document has no usable text"}), 400

    from library.country_gazetteer import slug_to_name

    tags = [t.strip() for t in (doc.tags or "").split(",") if t.strip()]
    country_slugs = [t[len("kraj-"):] for t in tags if t.startswith("kraj-")]
    countries = [{"slug": slug, "name_pl": slug_to_name(slug) or slug} for slug in country_slugs]
    thematic_tags = [t for t in tags if not t.startswith("kraj-")]

    return jsonify({
        "status": "success",
        "doc_id": doc_id,
        "document_type": doc.document_type,
        "title": doc.title,
        "url": doc.url,
        "source_field": field,
        "text_length": len(text),
        "chapters": chapters,
        "chapter_source": source,
        "countries": countries,
        "thematic_tags": thematic_tags,
        "synthesis": run.synthesis if run else None,
    })


def _resolve_chapter_text(session, doc, position: int) -> tuple[tuple[str, str, int] | None, str | None]:
    """Resolve one reader chapter to ((text, title, chapter_total), None).

    Positions are 1-based and match GET /document/<id>/chapters — markdown
    H1/H2 chapters when the text has them, otherwise the TEMAT-chunk fallback
    (see _chunk_based_chapters). On a bad position or a chapterless document
    returns (None, user-facing error message) — a plain value, not an
    exception, so no exception detail can leak into the HTTP response.
    """
    from library.document_analysis_service import _extract_text
    from library.text_functions import detect_chapters

    text, _field = _extract_text(doc, prefer_md=True)
    md_chapters = detect_chapters(text) if text else []

    if md_chapters:
        chapter_total = len(md_chapters)
        match = next((c for c in md_chapters if c["position"] == position), None)
        if match is None:
            return None, f"position {position} out of range (1..{chapter_total})"
        return (text[match["char_start"]:match["char_end"]].strip(), match["title"], chapter_total), None

    run = _latest_run_for_document(session, doc.id)
    chunk_chapters = _chunk_based_chapters(run) if run else []
    if not chunk_chapters:
        return None, "Document has no detectable chapters (no H1/H2 headers, no chunk analysis run)"

    chapter_total = len(chunk_chapters)
    match = next((c for c in chunk_chapters if c["position"] == position), None)
    if match is None:
        return None, f"scope_chapter {position} out of range (1..{chapter_total})"

    chunk = next(c for c in run.chunks if c.id == match["chunk_id"])
    return (chunk.corrected_text or chunk.original_text or "", match["title"], chapter_total), None


@bp.route("/document/<int:doc_id>/chapter/<int:position>", methods=["GET"])
def document_chapter(doc_id: int, position: int):
    """Return one chapter's text for the reader view (/read/:id).

    Positions are 1-based and match GET /document/<id>/chapters — either
    markdown-header chapters or, as a fallback, TEMAT-chunk chapters (see
    _chunk_based_chapters).
    """
    session = get_scoped_session()
    doc = session.get(WebDocument, doc_id)
    if doc is None:
        abort(404, f"Document {doc_id} not found")

    resolved, error = _resolve_chapter_text(session, doc, position)
    if resolved is None:
        return jsonify({"status": "error", "message": error}), 400
    chapter_text, title, chapter_total = resolved

    # footnotes extracted out of the text (library/references.py) — the reader
    # renders them as a "Przypisy" section at the end of the chapter
    from library.db.models import DocumentReference

    references = [
        {"marker": r.marker, "text": r.ref_text, "url": r.url}
        for r in session.query(DocumentReference)
        .filter(
            DocumentReference.document_id == doc_id,
            DocumentReference.chapter_position == position,
        )
        .order_by(DocumentReference.id)
        .all()
    ]

    return jsonify({
        "status": "success",
        "doc_id": doc_id,
        "position": position,
        "title": title,
        "text": chapter_text,
        "chapter_total": chapter_total,
        "references": references,
        "prev": position - 1 if position > 1 else None,
        "next": position + 1 if position < chapter_total else None,
    })


@bp.route("/document/<int:doc_id>/chapter/<int:position>/entities", methods=["GET"])
def document_chapter_entities(doc_id: int, position: int):
    """NER entities + country tags scoped to one chapter of the document.

    The expensive document-level verification (geocoder, Wikidata, LLM) is
    reused as-is — this endpoint only attributes the already-verified entities
    to the chapter by matching their surface variants in the chapter's text
    (entity_service.filter_entities_to_text), and intersects the document's
    kraj-* tags with countries the gazetteer finds in the chapter. The reader
    sidebar uses it so a long video's map/persons/places reflect the chapter
    being read instead of the whole material.
    """
    from library.country_gazetteer import detect_countries
    from library.entity_service import filter_entities_to_text, get_document_entities

    session = get_scoped_session()
    doc = session.get(WebDocument, doc_id)
    if doc is None:
        abort(404, f"Document {doc_id} not found")

    resolved, error = _resolve_chapter_text(session, doc, position)
    if resolved is None:
        return jsonify({"status": "error", "message": error}), 400
    chapter_text, title, chapter_total = resolved

    entities = filter_entities_to_text(get_document_entities(session, doc_id), chapter_text)

    doc_tags = [t.strip() for t in (doc.tags or "").split(",") if t.strip()]
    doc_country_slugs = {t[len("kraj-"):] for t in doc_tags if t.startswith("kraj-")}
    countries = [
        {"slug": c.slug, "name_pl": c.name_pl}
        for c in detect_countries(chapter_text)
        if c.slug in doc_country_slugs
    ]

    return jsonify({
        "status": "success",
        "doc_id": doc_id,
        "position": position,
        "title": title,
        "chapter_total": chapter_total,
        "entities": entities,
        "countries": countries,
    })


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
                "mode": r.mode,
                "status": r.status,
                "scope": r.scope,
                "created_at": r.created_at.isoformat(),
                "chunk_count": len(r.chunks),
                "temat_count": sum(1 for c in r.chunks if c.type == "TEMAT"),
                "approved_count": sum(
                    1 for c in r.chunks if c.type == "TEMAT" and c.status == "approved"
                ),
            }
            for r in runs
        ],
    })


# ---------------------------------------------------------------------------
# API: GET /analysis_run/<run_id>/chunks
# ---------------------------------------------------------------------------

@bp.route("/analysis_run/<int:run_id>/chunks", methods=["GET"])
def get_run_chunks(run_id: int):
    """Run data with chunks and topic sections.

    Query params (all optional — omit all for the classic full response):
        lite=1       — chunk dicts without full texts (text_preview/text_length
                       instead); segments are skipped too. For book-sized runs.
        section_id   — only chunks of that topic section (by chunk_positions).
        offset/limit — slice of the (possibly section-filtered) chunk list.
    """
    lite = request.args.get("lite", type=int) == 1
    section_id = request.args.get("section_id", type=int)
    offset = request.args.get("offset", 0, type=int)
    limit = request.args.get("limit", type=int)

    session = get_scoped_session()
    run = session.get(DocumentAnalysisRun, run_id)
    if run is None:
        abort(404, f"Run {run_id} not found")

    doc = session.get(WebDocument, run.document_id)
    segments = [] if lite else _parse_segments(doc.text_raw if doc else None)

    topic_sections = session.scalars(
        select(DocumentTopicSection)
        .where(DocumentTopicSection.run_id == run_id)
        .order_by(DocumentTopicSection.position)
    ).all()

    all_chunks = run.chunks  # ordered by position (relationship order_by)
    chunk_ids = [c.id for c in all_chunks]
    embedded_chunk_ids: set[int] = set()
    if chunk_ids:
        embedded_chunk_ids = set(session.scalars(
            select(WebsiteEmbedding.chunk_id)
            .where(WebsiteEmbedding.chunk_id.in_(chunk_ids))
            .distinct()
        ).all())

    from library.country_gazetteer import slug_to_name

    doc_tags = [t.strip() for t in ((doc.tags if doc else None) or "").split(",") if t.strip()]
    country_slugs = [t[len("kraj-"):] for t in doc_tags if t.startswith("kraj-")]
    doc_countries = [{"slug": slug, "name_pl": slug_to_name(slug) or slug} for slug in country_slugs]
    doc_thematic_tags = [t for t in doc_tags if not t.startswith("kraj-")]

    chunks = all_chunks
    if section_id is not None:
        section = next((ts for ts in topic_sections if ts.id == section_id), None)
        if section is None:
            return jsonify({"status": "error",
                            "message": f"Topic section {section_id} not found in run {run_id}"}), 404
        wanted = set(section.chunk_positions or [])
        chunks = [c for c in chunks if c.position in wanted]
    chunk_total = len(chunks)
    if offset:
        chunks = chunks[offset:]
    if limit is not None:
        chunks = chunks[:limit]

    def _section_stats(ts: DocumentTopicSection) -> dict:
        members = [c for c in all_chunks if c.position in set(ts.chunk_positions or [])]
        temat = [c for c in members if c.type == "TEMAT"]
        return {
            "chunk_count": len(members),
            "temat_count": len(temat),
            "approved_count": sum(1 for c in temat if c.status == "approved"),
            "notes_count": sum(1 for c in members if c.obsidian_note_paths),
        }

    return jsonify({
        "status": "success",
        "run": {
            "id": run.id,
            "model": run.model,
            "chunk_size": run.chunk_size,
            "mode": run.mode,
            "status": run.status,
            "scope": run.scope,
            "synthesis": run.synthesis,
            "speakers": run.speakers or [],
            "created_at": run.created_at.isoformat(),
        },
        "document": {
            "id": doc.id if doc else None,
            "title": doc.title if doc else "",
            "original_id": doc.original_id if doc else "",
            "document_type": doc.document_type if doc else "",
            "countries": doc_countries,
            "thematic_tags": doc_thematic_tags,
        },
        "segments": segments,
        "lite": lite,
        "offset": offset,
        "chunk_total": chunk_total,
        "chunks": [_chunk_to_dict(c, has_embeddings=c.id in embedded_chunk_ids, lite=lite) for c in chunks],
        "topic_sections": [
            {
                "id": ts.id,
                "position": ts.position,
                "type": ts.type,
                "title": ts.title,
                "summary": ts.summary,
                "chunk_positions": ts.chunk_positions,
                **_section_stats(ts),
            }
            for ts in topic_sections
        ],
    })


# ---------------------------------------------------------------------------
# API: PATCH /topic_section/<section_id>
# ---------------------------------------------------------------------------

@bp.route("/topic_section/<int:section_id>", methods=["PATCH", "OPTIONS"])
def update_topic_section(section_id: int):
    """Update a topic section. Body (JSON): {"title": "..."}."""
    if request.method == "OPTIONS":
        return jsonify({"status": "ok"}), 200

    session = get_scoped_session()
    section = session.get(DocumentTopicSection, section_id)
    if section is None:
        abort(404, f"Topic section {section_id} not found")

    data = request.get_json() or {}
    if "title" in data:
        title = data["title"]
        if not isinstance(title, str) or not title.strip():
            return jsonify({"status": "error", "message": "title must be a non-empty string"}), 400
        section.title = title.strip()[:500]
        section.updated_at = datetime.utcnow()
        try:
            session.commit()
        except Exception:
            session.rollback()
            logger.exception("Failed to update topic section %d", section_id)
            return jsonify({"status": "error", "message": "DB error"}), 500

    return jsonify({
        "status": "success",
        "topic_section": {
            "id": section.id,
            "position": section.position,
            "type": section.type,
            "title": section.title,
            "summary": section.summary,
            "chunk_positions": section.chunk_positions,
        },
    })


# ---------------------------------------------------------------------------
# API: PATCH /analysis_run/<run_id>
# ---------------------------------------------------------------------------

@bp.route("/analysis_run/<int:run_id>", methods=["PATCH", "OPTIONS"])
def update_run(run_id: int):
    """Update run workflow fields. Body (JSON): {"status": "created"|"in_review"|"reviewed"}."""
    if request.method == "OPTIONS":
        return jsonify({"status": "ok"}), 200

    session = get_scoped_session()
    run = session.get(DocumentAnalysisRun, run_id)
    if run is None:
        abort(404, f"Run {run_id} not found")

    data = request.get_json() or {}
    if "status" in data:
        if data["status"] not in ALLOWED_RUN_STATUSES:
            return jsonify({"status": "error", "message": f"Invalid run status: {data['status']}"}), 400
        run.status = data["status"]
        try:
            session.commit()
        except Exception:
            session.rollback()
            logger.exception("Failed to update run %d", run_id)
            return jsonify({"status": "error", "message": "DB error"}), 500

    return jsonify({
        "status": "success",
        "run": {"id": run.id, "mode": run.mode, "status": run.status, "scope": run.scope},
    })


# ---------------------------------------------------------------------------
# API: DELETE /analysis_run/<run_id>
# ---------------------------------------------------------------------------

@bp.route("/analysis_run/<int:run_id>", methods=["DELETE"])
def delete_run(run_id: int):
    """Delete an analysis run with all its chunks and topic sections.

    Document-level obsidian_note_paths stay intact; only the chunk-level
    note links stored on this run's chunks are lost.
    """
    session = get_scoped_session()
    run = session.get(DocumentAnalysisRun, run_id)
    if run is None:
        abort(404, f"Run {run_id} not found")

    chunk_count = len(run.chunks)
    try:
        session.delete(run)  # ORM cascade removes chunks and topic_sections
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("Failed to delete run %d", run_id)
        return jsonify({"status": "error", "message": "DB error"}), 500

    logger.info("Deleted analysis run %d (%d chunks)", run_id, chunk_count)
    return jsonify({"status": "success", "deleted_run_id": run_id, "chunk_count": chunk_count})


# ---------------------------------------------------------------------------
# API: POST /analysis_run/<run_id>/apply_cleanup
# ---------------------------------------------------------------------------

@bp.route("/analysis_run/<int:run_id>/apply_cleanup", methods=["POST"])
def apply_run_cleanup(run_id: int):
    """Overwrite the document's source text with the run's TEMAT chunks only.

    Article-mode runs are a full partition of the source text, so joining the
    TEMAT chunks (which already carry manual line removals) yields the cleaned
    document: REKLAMA/SZUM chunks and removed lines disappear from the source.
    After this, a fresh analysis run ("zaproponuj nowy podział") starts clean.

    Transcript runs are rejected: their chunk texts were transformed before
    splitting (speaker labels, filler removal), so the join is not the source.
    """
    session = get_scoped_session()
    run = session.get(DocumentAnalysisRun, run_id)
    if run is None:
        abort(404, f"Run {run_id} not found")
    if run.mode != "article":
        return jsonify({"status": "error",
                        "message": "apply_cleanup works only for article-mode runs"}), 400

    chunks = session.scalars(
        select(DocumentChunk)
        .where(DocumentChunk.run_id == run_id)
        .order_by(DocumentChunk.position)
    ).all()
    temat = [c for c in chunks if c.type == "TEMAT"]
    cleaned = "\n\n".join(c.original_text for c in temat).strip()
    if not cleaned:
        return jsonify({"status": "error", "message": "Run has no TEMAT chunks"}), 400

    doc = session.get(WebDocument, run.document_id)
    if doc is None:
        abort(404, f"Document {run.document_id} not found")

    # Write back to the same field an article-mode analysis would read
    from library.document_analysis_service import _extract_text
    _, field = _extract_text(doc, prefer_md=True)
    if field not in ("text", "text_md"):
        return jsonify({"status": "error",
                        "message": f"Cannot apply cleanup to source field: {field or 'none'}"}), 400

    length_before = len(getattr(doc, field) or "")
    setattr(doc, field, cleaned)

    # Log dropped SZUM/REKLAMA chunks as cleaner-training data. Deduped by
    # chunk_id so a repeated apply_cleanup does not double-log.
    dropped = [c for c in chunks if c.type != "TEMAT"]
    if dropped:
        already_logged = set(session.scalars(
            select(DocumentRemovedLine.chunk_id)
            .where(DocumentRemovedLine.run_id == run_id,
                   DocumentRemovedLine.source == "szum_chunk")
        ).all())
        for c in dropped:
            if c.id not in already_logged:
                _log_removed_lines(
                    session, document_id=run.document_id, run_id=run_id,
                    chunk_id=c.id, lines=[c.original_text], source="szum_chunk",
                )

    try:
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("apply_cleanup DB save failed for run %d", run_id)
        return jsonify({"status": "error", "message": "DB save failed"}), 500

    logger.info("apply_cleanup run %d: %s %d -> %d chars (%d TEMAT / %d chunks)",
                run_id, field, length_before, len(cleaned), len(temat), len(chunks))
    return jsonify({
        "status": "success",
        "field": field,
        "length_before": length_before,
        "length_after": len(cleaned),
        "temat_chunks": len(temat),
        "dropped_chunks": len(chunks) - len(temat),
    })


# ---------------------------------------------------------------------------
# API: POST /analysis_run/<run_id>/generate_embeddings
# ---------------------------------------------------------------------------

@bp.route("/analysis_run/<int:run_id>/generate_embeddings", methods=["POST"])
def generate_embeddings(run_id: int):
    """Start an async job generating embeddings from this run's approved TEMAT chunks.

    Returns immediately with {job_id}. Poll GET /embedding_job/<job_id> for status.
    """
    session = get_scoped_session()
    run = session.get(DocumentAnalysisRun, run_id)
    if run is None:
        abort(404, f"Run {run_id} not found")

    job_id = uuid.uuid4().hex[:8]
    _embedding_jobs[job_id] = {
        "status": "running",
        "run_id": run_id,
        "result": None,
        "error": None,
        "progress": "Startowanie...",
    }

    def _run_embeddings() -> None:
        from library.db.engine import get_session
        from library.document_analysis_service import generate_embeddings_from_run

        job_session = get_session()
        try:
            def _progress(msg: str) -> None:
                _embedding_jobs[job_id]["progress"] = msg

            result = generate_embeddings_from_run(job_session, run_id, progress_fn=_progress)
            _embedding_jobs[job_id].update({
                "status": "done",
                "result": result,
                "progress": f"Gotowe: {result['embeddings_created']} embeddingów "
                            f"z {result['chunks_considered']} chunków",
            })
        except ValueError as exc:
            _embedding_jobs[job_id].update({"status": "failed", "error": str(exc)})
        except Exception as exc:
            logger.exception("background embedding generation failed for run %d", run_id)
            _embedding_jobs[job_id].update({"status": "failed", "error": str(exc)})
        finally:
            job_session.close()

    t = threading.Thread(target=_run_embeddings, daemon=True, name=f"embeddings-{job_id}")
    t.start()

    return jsonify({"status": "started", "job_id": job_id, "run_id": run_id})


@bp.route("/embedding_job/<job_id>", methods=["GET"])
def get_embedding_job(job_id: str):
    """Poll status of an async embedding job started by POST /analysis_run/<id>/generate_embeddings."""
    job = _embedding_jobs.get(job_id)
    if job is None:
        return jsonify({"status": "error", "message": "Job not found"}), 404
    return jsonify({"status": "success", "job": job})


# ---------------------------------------------------------------------------
# API: POST /analysis_run/<run_id>/extract_speakers
# ---------------------------------------------------------------------------

@bp.route("/analysis_run/<int:run_id>/extract_speakers", methods=["POST"])
def extract_speakers(run_id: int):
    """Extract speaker names from a few chunks using LLM.

    By default uses the intro text (first 3 chunks' original_text, ordered by
    position) where participants typically introduce themselves. Pass
    chunk_ids (JSON body) to use specific chunk(s) instead — e.g. a single
    chunk the reviewer has manually split out to contain just the
    self-introductions, so detection doesn't need the surrounding chunks.
    Saves result to run.speakers.
    """
    session = get_scoped_session()
    run = session.get(DocumentAnalysisRun, run_id)
    if run is None:
        abort(404, f"Run {run_id} not found")

    data = request.get_json(silent=True) or {}
    chunk_ids = data.get("chunk_ids")

    if chunk_ids:
        if not isinstance(chunk_ids, list) or not all(isinstance(i, int) for i in chunk_ids):
            return jsonify({"status": "error", "message": "chunk_ids must be a list of integers"}), 400
        intro_chunks = session.scalars(
            select(DocumentChunk)
            .where(DocumentChunk.run_id == run_id, DocumentChunk.id.in_(chunk_ids))
            .order_by(DocumentChunk.position)
        ).all()
        if len(intro_chunks) != len(set(chunk_ids)):
            return jsonify({"status": "error", "message": "One or more chunk_ids not found in this run"}), 400
    else:
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
        return jsonify({"status": "error", "message": "No text in selected chunks"}), 400

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

    manually_removed: list[str] = []
    if "original_text" in data:
        # Manual cleanup: UI line-removal mode sends the whole edited text
        val = data["original_text"]
        if not isinstance(val, str) or not val.strip():
            return jsonify({"status": "error", "message": "original_text must be a non-empty string"}), 400
        manually_removed = _removed_lines_diff(chunk.original_text, val)
        chunk.original_text = val
        changed = True

    doc_lines_removed = 0
    removed_lines = data.get("remove_lines_from_document") or []
    if removed_lines:
        # Propagate cleanup to the source document: drop ALL whole-line exact
        # matches (junk lines like player controls repeat per embedded video)
        targets = {ln.strip() for ln in removed_lines if isinstance(ln, str) and ln.strip()}
        if targets:
            doc = session.get(WebDocument, chunk.document_id)
            if doc is not None:
                for field in ("text", "text_md"):
                    value = getattr(doc, field, None)
                    if not value:
                        continue
                    kept = [ln for ln in value.split("\n") if ln.strip() not in targets]
                    doc_lines_removed += value.count("\n") + 1 - len(kept)
                    setattr(doc, field, "\n".join(kept))
                changed = True
            # Lines propagated to the document but not caught by the chunk-text
            # diff (e.g. still present elsewhere in the chunk) — log those too
            already = set(manually_removed)
            manually_removed += [t for t in sorted(targets) if t not in already]

    if manually_removed:
        _log_removed_lines(
            session, document_id=chunk.document_id, run_id=chunk.run_id,
            chunk_id=chunk.id, lines=manually_removed, source="manual",
        )

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

    return jsonify({
        "status": "success",
        "chunk": _chunk_to_dict(chunk),
        "document_lines_removed": doc_lines_removed,
    })


# ---------------------------------------------------------------------------
# API: POST /chunk/<chunk_id>/execute_split
# ---------------------------------------------------------------------------

@bp.route("/chunk/<int:chunk_id>/execute_split", methods=["POST"])
def execute_split(chunk_id: int):
    """Split a chunk into two.

    Body (JSON) — exactly one split point:
        split_at_seg      — absolute transcript segment index (transcript chunks)
        split_at_line     — line index in original_text; the line starts part B
                            (article chunks without segments)
        split_first_type  — type for part before split: TEMAT | REKLAMA | SZUM
        split_second_type — type for part after split:  TEMAT | REKLAMA | SZUM

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
    split_at_line = data.get("split_at_line")
    first_type = data.get("split_first_type", chunk.split_first_type)
    second_type = data.get("split_second_type", chunk.split_second_type)

    if first_type not in ALLOWED_TYPES:
        return jsonify({"status": "error", "message": f"Invalid split_first_type: {first_type}"}), 400
    if second_type not in ALLOWED_TYPES:
        return jsonify({"status": "error", "message": f"Invalid split_second_type: {second_type}"}), 400

    if split_at_line is not None:
        # Line-based split (article chunks — no transcript segments)
        lines = (chunk.original_text or "").split("\n")
        try:
            split_at_line = int(split_at_line)
        except (TypeError, ValueError):
            return jsonify({"status": "error", "message": "split_at_line must be an integer"}), 400
        if not 0 < split_at_line < len(lines):
            return jsonify({"status": "error",
                            "message": f"split_at_line {split_at_line} out of range (1..{len(lines) - 1})"}), 400
        text_a = "\n".join(lines[:split_at_line]).strip()
        text_b = "\n".join(lines[split_at_line:]).strip()
        if not text_a or not text_b:
            return jsonify({"status": "error", "message": "Both parts must contain text"}), 400
        seg_a = (None, None)
        seg_b = (None, None)
        # Fresh TEMAT parts need new topic/summary; junk is auto-approved
        status_a = "needs_reanalysis" if first_type == "TEMAT" else "approved"
        status_b = "needs_reanalysis" if second_type == "TEMAT" else "approved"
    else:
        if split_at is None:
            return jsonify({"status": "error", "message": "split_at_seg or split_at_line required"}), 400

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

        text_a = _text_from_segs(seg_start, split_at)
        text_b = _text_from_segs(split_at, seg_end)
        seg_a = (seg_start, split_at)
        seg_b = (split_at, seg_end)
        status_a = "approved" if first_type in ("REKLAMA", "SZUM") else "pending"
        status_b = "needs_reanalysis" if second_type == "TEMAT" else "approved"

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

        chunk_a = DocumentChunk(
            run_id=run_id, document_id=doc_id, position=orig_pos,
            type=first_type, topic=None,
            original_text=text_a or "(brak tekstu)",
            corrected_text=None, summary=None,
            seg_start=seg_a[0], seg_end=seg_a[1],
            rewrite_ratio=None, status=status_a,
        )

        chunk_b = DocumentChunk(
            run_id=run_id, document_id=doc_id, position=orig_pos + 1,
            type=second_type, topic=None,
            original_text=text_b or "(brak tekstu)",
            corrected_text=None, summary=None,
            seg_start=seg_b[0], seg_end=seg_b[1],
            rewrite_ratio=None, status=status_b,
        )

        session.add(chunk_a)
        session.add(chunk_b)
        session.commit()

        split_point = f"line {split_at_line}" if split_at_line is not None else f"seg {split_at}"
        logger.info("Split chunk %d at %s → chunks at pos %d and %d",
                    chunk_id, split_point, orig_pos, orig_pos + 1)

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
# API: POST /chunk/<chunk_id>/merge_with_next
# ---------------------------------------------------------------------------

@bp.route("/chunk/<int:chunk_id>/merge_with_next", methods=["POST"])
def merge_with_next(chunk_id: int):
    """Merge a chunk with the following one (inverse of execute_split).

    Concatenates texts, unions obsidian_note_paths, keeps the TEMAT type when
    either side is TEMAT, and marks the merged chunk needs_reanalysis so the
    topic/summary get refreshed. Positions after the removed chunk shift by -1.
    """
    session = get_scoped_session()
    chunk = session.get(DocumentChunk, chunk_id)
    if chunk is None:
        abort(404, f"Chunk {chunk_id} not found")

    next_chunk = session.scalar(
        select(DocumentChunk).where(
            DocumentChunk.run_id == chunk.run_id,
            DocumentChunk.position == chunk.position + 1,
        )
    )
    if next_chunk is None:
        return jsonify({"status": "error", "message": "Chunk has no successor to merge with"}), 400

    try:
        chunk.original_text = f"{chunk.original_text}\n\n{next_chunk.original_text}".strip()
        if chunk.corrected_text and next_chunk.corrected_text:
            chunk.corrected_text = f"{chunk.corrected_text}\n\n{next_chunk.corrected_text}".strip()
        else:
            chunk.corrected_text = None
        chunk.seg_end = next_chunk.seg_end
        if next_chunk.type == "TEMAT":
            chunk.type = "TEMAT"
        chunk.topic = None
        chunk.summary = None
        chunk.rewrite_ratio = None
        chunk.status = "needs_reanalysis"
        merged_paths = list(chunk.obsidian_note_paths or [])
        for p in next_chunk.obsidian_note_paths or []:
            if p not in merged_paths:
                merged_paths.append(p)
        chunk.obsidian_note_paths = merged_paths
        chunk.updated_at = datetime.utcnow()

        removed_pos = next_chunk.position
        session.delete(next_chunk)
        session.flush()

        # Shift following positions down via temp range (unique constraint on run_id+position)
        session.execute(
            sa_update(DocumentChunk)
            .where(DocumentChunk.run_id == chunk.run_id, DocumentChunk.position > removed_pos)
            .values(position=DocumentChunk.position + 10000)
        )
        session.execute(
            sa_update(DocumentChunk)
            .where(DocumentChunk.run_id == chunk.run_id, DocumentChunk.position > 10000)
            .values(position=DocumentChunk.position - 10001)
        )
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("Failed to merge chunk %d with next", chunk_id)
        return jsonify({"status": "error", "message": "DB error during merge"}), 500

    logger.info("Merged chunk %d with its successor (pos %d)", chunk_id, removed_pos)
    return jsonify({"status": "success", "chunk": _chunk_to_dict(chunk)})


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
        if run.mode == "article":
            # Article runs have no rewrite step — always re-run classify+summarize
            text_to_analyze = chunk.original_text or ""
            if not text_to_analyze.strip():
                return jsonify({"status": "error", "message": "Chunk has no original_text to analyze"}), 400
            total = session.scalar(
                select(func.count()).select_from(DocumentChunk)
                .where(DocumentChunk.run_id == chunk.run_id)
            ) or 1
            from library.chunk_llm_analysis import analyze_article_chunk
            result = analyze_article_chunk(text_to_analyze, model,
                                           position=chunk.position, total=total)
        elif mode == "semantic" and chunk.corrected_text and chunk.corrected_text.strip():
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

