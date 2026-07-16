"""Service for creating chunk analysis runs on existing documents.

Full pipeline:
  text extraction → speech filler removal → chunk splitting → LLM analysis
  → topic grouping → optional synthesis → DB persistence

Designed to be called from Flask endpoints (via REST API) and CLI scripts
(imports/youtube_batch_analyze.py, imports/youtube_add.py --analyze). File
exports (HTML/JSON/MD) live in library/analysis_exports.py; this service
handles only DB-backed pipeline execution.
"""

import json
import logging
import re
from typing import Callable

from library.db.models import (
    DocumentAnalysisRun, DocumentChunk, DocumentTopicSection, WebDocument,
)

logger = logging.getLogger(__name__)

CHUNK_CHARS = 5_000
DEFAULT_ANALYSIS_MODEL = "Bielik-11B-v3.0-Instruct"
ANALYSIS_MODELS = [DEFAULT_ANALYSIS_MODEL, f"arklabs/{DEFAULT_ANALYSIS_MODEL}"]
# mode: transcript (YouTube STT — speakers, fillers, verbatim rewrite)
#       article    (clean markdown/text — header-based split, classify+summarize only)
ANALYSIS_MODES = ("transcript", "article")
SYNTHESIS_MAX_TOKENS = 2_000
SYNTHESIS_MAX_INPUT_CHARS = 20_000
_SECTION_HEADER_RE = re.compile(r'^### (REKLAMA|TEMAT|SZUM): ?(.+)$', re.MULTILINE)

# Run statuses that mean review never finished — once a newer run of the same
# document+scope exists, such a run is an abandoned attempt (double click,
# retry after an error) and gets marked "superseded".
UNFINISHED_RUN_STATUSES = ("created", "in_review")

# Chunk statuses that still represent pending review work — flipped to
# "skipped" when their run is superseded, so they stop counting as chunks
# missing an Obsidian note. Approved/split chunks and note paths stay intact.
OPEN_CHUNK_STATUSES = ("pending", "needs_reanalysis", "split_requested")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _load_segments(text_raw: str | None) -> list[dict]:
    """Parse YouTube transcript JSON from text_raw — returns [] when not valid JSON."""
    if not text_raw or not text_raw.strip().startswith("["):
        return []
    try:
        segs = json.loads(text_raw.strip())
        if isinstance(segs, list) and segs and "start" in segs[0]:
            return segs
    except (ValueError, KeyError, IndexError):
        pass
    return []


def _map_chunks_to_segments(
    chunk_texts: list[str], segments: list[dict]
) -> list[tuple[int | None, int | None]]:
    """Map each chunk to proportional range of segment indices (by character count)."""
    total = sum(len(c) for c in chunk_texts)
    if not total or not segments:
        return [(None, None)] * len(chunk_texts)
    n = len(segments)
    result = []
    cum = 0
    for chunk in chunk_texts:
        start = round(n * cum / total)
        cum += len(chunk)
        end = round(n * cum / total)
        result.append((min(start, n), min(end, n)))
    return result


def _sentence_tail(text: str, max_chars: int = 300) -> str:
    """Last up to max_chars of text, preferring a sentence boundary start."""
    if len(text) <= max_chars:
        return text
    seg = text[-max_chars:]
    for sep in ('. ', '.\n', '? ', '! '):
        idx = seg.find(sep)
        if idx != -1:
            return seg[idx + len(sep):]
    return seg


def _sentence_head(text: str, max_chars: int = 300) -> str:
    """First up to max_chars of text, preferring a sentence boundary end."""
    if len(text) <= max_chars:
        return text
    seg = text[:max_chars]
    for sep in ('. ', '.\n', '? ', '! '):
        idx = seg.rfind(sep)
        if idx != -1:
            return seg[:idx + 1]
    return seg


def _extract_text(doc: WebDocument, prefer_md: bool = False) -> tuple[str, str]:
    """Return (text, field_name) from best available field.

    Priority: text → text_md → text_raw (JSON transcript → plain text).
    With prefer_md=True (article mode) text_md wins over text, so the
    markdown-header splitter sees the document structure.
    Returns ("", "") when no usable text found.
    """
    fields = ("text_md", "text") if prefer_md else ("text", "text_md")
    for field in fields:
        val = getattr(doc, field, None)
        if val and len(val) > 100:
            return val, field
    raw = getattr(doc, "text_raw", None)
    if raw and len(raw) > 100:
        segs = _load_segments(raw)
        if segs:
            return "\n".join(s["text"] for s in segs), "text_raw (JSON→plain)"
        return raw, "text_raw"
    return "", ""


def _slice_chapter(text: str, scope_chapter: int) -> tuple[str, str]:
    """Cut out one chapter (1-based position from detect_chapters) of the text.

    Returns (chapter_text, chapter_title). Raises ValueError when the text has
    no detectable chapters or the position is out of range.
    """
    from library.text_functions import detect_chapters

    chapters = detect_chapters(text)
    if not chapters:
        raise ValueError("Document has no detectable chapters (H1/H2 headers)")
    match = next((c for c in chapters if c["position"] == scope_chapter), None)
    if match is None:
        raise ValueError(f"scope_chapter {scope_chapter} out of range (1..{len(chapters)})")
    return text[match["char_start"]:match["char_end"]].strip(), match["title"]


def _chapter_chunks_from_text(text: str, chapter_titles: list[str], chunk_size: int) -> list[str] | None:
    """Split a YouTube transcript at its chapter boundaries, when they're still present.

    youtube_processing.py inserts each chapter's title as a standalone line at
    the start of its block (blocks separated by a blank line) when the video
    has a chapter_list — see text_transcript.py:_append_with_chapters. This
    reuses those already-correct boundaries instead of the blind
    split_text_into_sentence_chunks() char-count cut, so each chunk lines up
    with a real video chapter (subject to chunk_size: an overlong chapter is
    still sub-split at sentence boundaries).

    Only reliable for single-speaker transcripts — assign_speakers() rebuilds
    the text by >>-marker turns and destroys this block structure, so the
    caller must not call this after labeling multi-speaker turns.

    Returns None (caller falls back to split_text_into_sentence_chunks) when
    less than a strict majority of the known chapter titles are found as
    exact block-leading lines — the transcript may have been reshaped upstream.
    """
    from library.text_functions import split_text_into_sentence_chunks

    if not chapter_titles:
        return None
    title_set = set(chapter_titles)
    blocks = text.split("\n\n")
    found = sum(1 for b in blocks if b.split("\n", 1)[0].strip() in title_set)
    if found < (len(chapter_titles) + 1) // 2:  # require a strict majority
        return None

    def cap(piece: str) -> list[str]:
        return [piece] if len(piece) <= chunk_size else split_text_into_sentence_chunks(piece, chunk_size)

    chunks: list[str] = []
    current = ""
    for block in blocks:
        starts_chapter = block.split("\n", 1)[0].strip() in title_set
        if starts_chapter and current:
            chunks.extend(cap(current))
            current = block
        else:
            current = f"{current}\n\n{block}" if current else block
    if current:
        chunks.extend(cap(current))
    return chunks


def _merge_topics(sections: list[dict], model: str, mode: str = "transcript") -> list[dict]:
    """Ask LLM to group adjacent chunks into logical topic sections.

    Returns list of {title, type, chunks: [1-based indices]}.
    Returns [] if LLM call fails — caller falls back to one section per chunk.
    """
    from library.chunk_llm_analysis import call_model

    chunk_list = "\n".join(
        f"{i + 1}. [{s['type']}] {s['topic']}"
        for i, s in enumerate(sections)
    )
    source_desc = "transkrypcji podcastu" if mode == "transcript" else "dokumentu"
    prompt = (
        f"Poniżej lista {len(sections)} fragmentów {source_desc} z ich tematami.\n"
        "Pogrupuj SĄSIADUJĄCE fragmenty w logiczne sekcje tematyczne (zwykle 5-10 sekcji).\n"
        "Fragmenty reklamowe (REKLAMA) i szum techniczny (SZUM) możesz pominąć lub zgrupować\n"
        "razem pod jedną sekcją odpowiednio REKLAMA lub SZUM.\n\n"
        "Zwróć TYLKO tablicę JSON bez żadnego dodatkowego tekstu, w formacie:\n"
        '[{"title": "Tytuł sekcji tematycznej", "type": "TEMAT", "chunks": [1, 2]}]\n'
        'Gdzie "chunks" to numery fragmentów (numeracja od 1), "type" to "TEMAT", "REKLAMA" lub "SZUM".\n\n'
        f"Fragmenty:\n{chunk_list}"
    )
    try:
        response_text, _ = call_model(prompt, model, max_tokens=600)
        match = re.search(r'\[.*\]', response_text, re.DOTALL)
        if match:
            groups = json.loads(match.group())
            # Unwrap if LLM wrapped result in an extra array: [[{...}]] → [{...}]
            if groups and isinstance(groups[0], list):
                logger.warning("merge_topics: got nested list, unwrapping")
                groups = groups[0]
            # Discard any non-dict elements to avoid AttributeError on .get()
            groups = [g for g in groups if isinstance(g, dict)]
            logger.info("merge_topics: %d sections", len(groups))
            return groups
    except Exception:
        logger.exception("merge_topics LLM call failed")
    return []


def _synthesize(sections: list[dict], title: str, model: str, mode: str = "transcript") -> str:
    """Generate overall synthesis from all TEMAT chunk summaries.

    Returns "" if no summaries available or LLM call fails.
    """
    from library.chunk_llm_analysis import call_model

    content = [s for s in sections if s["type"] == "TEMAT" and s["summary"]]
    if not content:
        return ""

    summaries = "\n\n".join(
        f"**{s.get('topic', '')}**: {s['summary']}" for s in content
    )
    if len(summaries) > SYNTHESIS_MAX_INPUT_CHARS:
        logger.warning("synthesis input too long (%d chars), skipping", len(summaries))
        return ""

    source_desc = "podcastu YouTube" if mode == "transcript" else "dokumentu"
    prompt = (
        f'Poniżej są streszczenia kolejnych sekcji merytorycznych {source_desc} pt.: „{title}".\n\n'
        "Na ich podstawie przygotuj:\n"
        "1. GŁÓWNE WNIOSKI: 5-7 najważniejszych wniosków (lista punktowana).\n"
        "2. SYNTEZA: Spójne streszczenie całości (6-8 zdań).\n\n"
        "Odpowiedz wyłącznie po polsku.\n\n"
        f"--- STRESZCZENIA SEKCJI ---\n{summaries}\n--- KONIEC ---"
    )
    try:
        response_text, _ = call_model(prompt, model, SYNTHESIS_MAX_TOKENS)
        return response_text.strip()
    except Exception:
        logger.exception("synthesis LLM call failed")
        return ""


def _apply_tags(doc: WebDocument, text: str) -> None:
    """Thematic + country tagging — same pipeline as article_browser.py's [w]/[k] actions.

    Merges newly detected tags into doc.tags rather than overwriting: repeat
    analysis runs (e.g. one run per book chapter) should accumulate tags
    across runs, not clobber ones set by a previous run or by article_browser.py.
    """
    from library.article_tagging import COUNTRY_TAG_TRIGGERS, extract_countries_hybrid, tag_article_with_llm

    article_tags = tag_article_with_llm(text, doc.title or "")
    country_tags = (
        extract_countries_hybrid(text, doc.title or "")
        if article_tags and COUNTRY_TAG_TRIGGERS.intersection(article_tags)
        else []
    )
    new_tags = article_tags + country_tags
    if not new_tags:
        return
    existing = [t.strip() for t in (doc.tags or "").split(",") if t.strip()]
    existing_set = set(existing)
    doc.tags = ",".join(existing + [t for t in new_tags if t not in existing_set])


def stale_duplicate_runs(runs: list) -> list:
    """Given all runs of ONE document+scope group, return the abandoned duplicates.

    A run is a stale duplicate when a newer run of the same scope exists and
    it never reached "reviewed" — the case behind document 9245: a first
    /analyze_chunks call abandoned mid-workflow (status=created) plus a second
    one actually used for notes. Legal multi-run setups (a split_only run over
    a whole book + article runs per chapter) live in different scope groups
    and never meet here. The newest run of the group is never returned, even
    when itself unfinished — it is the current one.
    """
    if len(runs) < 2:
        return []
    ordered = sorted(runs, key=lambda r: (r.created_at, r.id))
    return [r for r in ordered[:-1] if r.status in UNFINISHED_RUN_STATUSES]


def supersede_unfinished_runs(session, doc_id: int, scope: str | None) -> list[DocumentAnalysisRun]:
    """Mark unfinished runs of the same document+scope as superseded.

    Called by create_run() just before a new run of that scope is persisted:
    an earlier run that never reached "reviewed" is an abandoned attempt once
    a newer run of the same scope exists — left as "created", its pending
    chunks would stay visible forever in the "missing Obsidian notes" filter.
    Chunks still awaiting review are flipped to "skipped"; approved/split
    chunks and recorded note paths stay untouched. Nothing is deleted — the
    run and its chunks remain browsable in /chunks/:id.
    """
    from sqlalchemy import select, update

    siblings = session.scalars(
        select(DocumentAnalysisRun).where(DocumentAnalysisRun.document_id == doc_id)
    ).all()
    stale = [r for r in siblings if r.scope == scope and r.status in UNFINISHED_RUN_STATUSES]
    for run in stale:
        run.status = "superseded"
        session.execute(
            update(DocumentChunk)
            .where(
                DocumentChunk.run_id == run.id,
                DocumentChunk.status.in_(OPEN_CHUNK_STATUSES),
            )
            .values(status="skipped")
        )
    return stale


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class DocumentAnalysisService:
    """Full pipeline: load doc → split → LLM analysis → topic grouping → DB save."""

    def __init__(self, session):
        self.session = session

    def create_run(
        self,
        doc_id: int,
        model: str,
        chunk_size: int = CHUNK_CHARS,
        no_synthesis: bool = False,
        progress_fn: Callable[[str], None] | None = None,
        speakers: list[dict] | None = None,
        mode: str = "transcript",
        split_only: bool = False,
        preclean: bool = False,
        scope_chapter: int | None = None,
    ) -> DocumentAnalysisRun:
        """Create a new analysis run for an existing document and persist to DB.

        Args:
            doc_id:       ID of document in web_documents.
            model:        LLM model name (Bielik via Sherlock or "arklabs/<model>").
            chunk_size:   Max characters per chunk (default 5 000 ≈ 1 500 tokens).
            no_synthesis: Skip the final synthesis step.
            progress_fn:  Optional callback for progress messages (used by batch scripts).
            speakers:     Optional speaker list [{"name", "role", "description"}] —
                          when given, skips LLM speaker extraction (transcript mode only).
            mode:         "transcript" (STT: speakers, fillers, verbatim rewrite) or
                          "article" (clean text: header-based split, classify+summarize).
            split_only:   Split into chunks WITHOUT any LLM calls — chunks land as
                          TEMAT/pending with no topic/summary, so the user can first
                          clean lines, merge or re-split, then analyze on demand.
            preclean:     Article-only pre-pass: LLM marks exact REKLAMA/SZUM line
                          ranges before final chunking. The resulting lossless proposal
                          is saved in this same run without semantic chunk analysis.
            scope_chapter: 1-based chapter position (as returned by detect_chapters /
                          GET /document/<id>/chapters) — analyze only that chapter;
                          run.scope is set to the chapter title. Article mode only.

        Returns:
            Persisted DocumentAnalysisRun with .chunks and .topic_sections populated.

        Raises:
            ValueError:   Document not found, no text content, or invalid mode.
            RuntimeError: LLM call failed or DB commit failed.
        """
        from library.chunk_llm_analysis import (
            analyze_article_chunk, analyze_chunk, assign_speakers,
            extract_speaker_info, propose_article_cleanup, remove_speech_fillers,
        )
        from library.text_functions import split_markdown_into_chunks, split_text_into_sentence_chunks

        if mode not in ANALYSIS_MODES:
            raise ValueError(f"Invalid mode: {mode!r} (expected one of {ANALYSIS_MODES})")
        is_transcript = mode == "transcript"
        if scope_chapter is not None and is_transcript:
            raise ValueError("scope_chapter requires article mode")
        if preclean and is_transcript:
            raise ValueError("preclean requires article mode")
        proposal_only = split_only or preclean

        def log(msg: str) -> None:
            logger.info(msg)
            if progress_fn:
                progress_fn(msg)

        session = self.session

        # 1. Load document
        doc = WebDocument.get_by_id(session, doc_id)
        if doc is None:
            raise ValueError(f"Document {doc_id} not found")

        # 2. Extract text (article mode prefers text_md — headers drive the split)
        text, text_field = _extract_text(doc, prefer_md=not is_transcript)
        if not text:
            raise ValueError(f"Document {doc_id} has no usable text (checked: text, text_md, text_raw)")

        log(f"doc={doc_id} mode={mode} field={text_field} len={len(text):,}")

        scope: str | None = None
        author_bio = None
        author_bio_position = None
        if is_transcript:
            # 3. Detect format (multi-speaker = has >> speaker markers)
            speaker_changes = len(re.findall(r'>>', text))
            is_multi_speaker = speaker_changes > 0
            log(f"format={'multi-speaker' if is_multi_speaker else 'monologue'} ({speaker_changes} >>)")

            # 4. Extract speakers from intro text (only for multi-speaker conversations),
            #    unless the caller already provided them
            if speakers is None:
                speakers = []
                if is_multi_speaker and not split_only:
                    intro_text = text[800:2400].strip()
                    try:
                        speakers = extract_speaker_info(intro_text, model)
                        log(f"speakers={[sp['name'] for sp in speakers]}")
                    except Exception:
                        logger.exception("speaker extraction failed, continuing without speakers")

            # 5. Label speaker turns from >> markers (must happen before splitting,
            #    so the rewrite prompt sees the [Name]: labels it is asked to preserve)
            if is_multi_speaker and len(speakers) >= 2:
                text = assign_speakers(text, speakers[0]["name"], speakers[1]["name"])
                log(f"labeled speaker turns: [{speakers[0]['name']}] / [{speakers[1]['name']}]")

            # 6. Remove speech fillers before splitting (cheaper than asking LLM)
            text = remove_speech_fillers(text)

            # 7. Split into chunks — chapter-aware when the video has a YouTube
            #    chapter_list and speaker labeling didn't restructure the text
            #    (see _chapter_chunks_from_text); otherwise blind sentence-chunk split.
            chunk_texts = None
            if not is_multi_speaker and getattr(doc, "chapter_list", None):
                from library.text_transcript import chapters_text_to_list

                chapter_titles = [c["title"] for c in chapters_text_to_list(doc.chapter_list)]
                chunk_texts = _chapter_chunks_from_text(text, chapter_titles, chunk_size)
                if chunk_texts:
                    log(f"chapter-aware split: {len(chapter_titles)} video chapters detected")
            if chunk_texts is None:
                chunk_texts = split_text_into_sentence_chunks(text, chunk_size)

            # 8. Map chunks to transcript segments (for timestamp links)
            segments = _load_segments(getattr(doc, "text_raw", None) or "")
        else:
            # Article mode: text is already clean — no speakers, no fillers,
            # split at markdown headers, no transcript segments to map.
            speakers = speakers or []
            if scope_chapter is not None:
                text, scope_title = _slice_chapter(text, scope_chapter)
                scope = scope_title[:200]
                log(f'scope: chapter {scope_chapter} "{scope}" ({len(text):,} chars)')
            from library.author_biography import extract_trailing_author_biography

            article_body, author_bio = extract_trailing_author_biography(text, getattr(doc, "author", None))
            preclean_meta: list[tuple[str, str | None]] = []
            if preclean:
                log("preclean: detecting ads and noisy line ranges before final split...")
                proposed = propose_article_cleanup(article_body, model)
                chunk_texts = []
                for piece in proposed:
                    piece_chunks = (
                        split_markdown_into_chunks(piece["text"], chunk_size)
                        if piece["type"] == "TEMAT" else [piece["text"]]
                    )
                    chunk_texts.extend(piece_chunks)
                    preclean_meta.extend([(piece["type"], piece["topic"])] * len(piece_chunks))
                log(f"preclean: {sum(1 for t, _ in preclean_meta if t != 'TEMAT')} excluded ranges proposed")
            else:
                chunk_texts = split_markdown_into_chunks(article_body, chunk_size)
            if author_bio:
                chunk_texts.append(author_bio)
                author_bio_position = len(chunk_texts) - 1
                if preclean:
                    preclean_meta.append(("SZUM", "Notka biograficzna autora"))
                log(f"author biography isolated ({len(author_bio):,} chars)")
            segments = []
        log(f"split={len(chunk_texts)} chunks, max {chunk_size:,} chars")

        seg_map = (
            _map_chunks_to_segments(chunk_texts, segments)
            if segments else [(None, None)] * len(chunk_texts)
        )

        # 9. Analyze each chunk via LLM (with boundary context from adjacent chunks).
        #    split_only: no LLM at all — chunks await manual cleanup + on-demand analysis.
        sections: list[dict] = []
        total = len(chunk_texts)
        if proposal_only:
            log(f"proposal: {total} chunks without semantic LLM analysis")
            sections = [
                {
                    "type": preclean_meta[i][0] if preclean else ("SZUM" if i == author_bio_position else "TEMAT"),
                    "topic": preclean_meta[i][1] if preclean else ("Notka biograficzna autora" if i == author_bio_position else None),
                    "original": chunk_text,
                    "text": None,
                    "ratio": None,
                    "summary": None,
                }
                for i, chunk_text in enumerate(chunk_texts)
            ]
            chunk_texts_iter: list[str] = []
        else:
            chunk_texts_iter = chunk_texts
        for i, chunk_text in enumerate(chunk_texts_iter):
            log(f"chunk {i + 1}/{total} ({len(chunk_text):,} chars)...")
            try:
                if i == author_bio_position:
                    result = {
                        "type": "SZUM",
                        "topic": "Notka biograficzna autora",
                        "corrected_text": None,
                        "summary": None,
                        "rewrite_ratio": None,
                    }
                elif is_transcript:
                    result = analyze_chunk(
                        chunk_text, model,
                        position=i + 1, total=total,
                        speakers=speakers or None,
                        prev_context=_sentence_tail(chunk_texts[i - 1]) if i > 0 else "",
                        next_context=_sentence_head(chunk_texts[i + 1]) if i < total - 1 else "",
                    )
                else:
                    result = analyze_article_chunk(chunk_text, model, position=i + 1, total=total)
            except Exception as exc:
                raise RuntimeError(f"LLM call failed for chunk {i + 1}/{total}: {exc}") from exc

            sections.append({
                "type": result["type"],
                "topic": result["topic"],
                "original": chunk_text,
                "text": result["corrected_text"],
                "ratio": result["rewrite_ratio"],
                "summary": result["summary"],
            })

        # 10. Group chunks into logical topic sections (skip LLM grouping for split_only)
        topic_groups = [] if proposal_only else _merge_topics(sections, model, mode=mode)
        if topic_groups:
            topic_sections_data = []
            for group in topic_groups:
                indices = [i - 1 for i in group.get("chunks", [])]
                valid = [i for i in indices if 0 <= i < len(sections)]
                if not valid:
                    continue
                merged_summary = " ".join(
                    sections[i]["summary"] for i in valid if sections[i]["summary"]
                )
                topic_sections_data.append({
                    "title": group.get("title", ""),
                    "type": group.get("type", "TEMAT"),
                    "chunk_indices": [i + 1 for i in valid],
                    "summary": merged_summary.strip(),
                })
        elif proposal_only:
            # No LLM ran — sections would carry no information yet
            topic_sections_data = []
        else:
            # Fallback: each chunk is its own section
            topic_sections_data = [
                {
                    "title": s["topic"] or "",
                    "type": s["type"],
                    "chunk_indices": [i + 1],
                    "summary": s["summary"] or "",
                }
                for i, s in enumerate(sections)
            ]
        log(f"topic_sections={len(topic_sections_data)}")

        # 11. Optional synthesis
        synthesis = ""
        if not no_synthesis and not proposal_only:
            log("generating synthesis...")
            synthesis = _synthesize(sections, doc.title or f"Dokument {doc_id}", model, mode=mode)

        # 11b. Thematic + country tagging (same as article_browser.py's [w]/[k]
        #      actions) — uses the synthesis as input when available (concise,
        #      already LLM-summarized), else falls back to concatenated topic
        #      summaries. Skipped for split_only: no LLM output exists yet.
        if not proposal_only:
            tagging_text = synthesis or "\n\n".join(
                ts["summary"] for ts in topic_sections_data if ts["summary"]
            )
            if tagging_text:
                log("tagging document...")
                _apply_tags(doc, tagging_text)

            # 11b2. Article author fallback (LLM) — article_metadata.extract_article_author()
            #       (deterministic, WP.pl only) already ran at import time; this is a
            #       fallback for everything else. Never overwrites an existing doc.author
            #       (deterministic or manually entered). Whole-document runs only — a
            #       single chapter excerpt is not a reliable place to look for a byline.
            if not is_transcript and scope is None and not (getattr(doc, "author", None) or "").strip():
                try:
                    from library.chunk_llm_analysis import extract_author_info, head_tail_excerpt

                    author_name = extract_author_info(head_tail_excerpt(text), model)
                    if author_name:
                        doc.author = author_name
                        log(f"author detected: {author_name}")
                except Exception:
                    logger.exception("author extraction failed, continuing without author")

            # 11f. Article quality ("staranność") scoring — deterministic
            #      penalties + one LLM rubric call (library/article_quality.py).
            #      Whole-document article runs only: a transcript or a single
            #      chapter is not a fair sample of the article's care.
            if not is_transcript and scope is None:
                try:
                    from library.article_quality import compute_quality

                    doc.quality = compute_quality(doc, sections, model=model)
                    log(f"quality: {doc.quality['score']}/100 "
                        f"(penalties: {doc.quality['penalties'] or '-'})")
                except Exception:
                    logger.exception("quality scoring failed, continuing without quality")

        # 11c. NER entities (persons/places) on the full document text — offline
        #      (no LLM), stored in document_entities with replace semantics, so
        #      chapter-scoped runs skip it (a single chapter's entities must not
        #      clobber the whole document's). See docs/ner-integration-plan.md.
        if scope is None:
            try:
                from library.entity_service import refresh_document_entities
                from library.ner_client import NERServiceUnavailable

                entity_rows = refresh_document_entities(session, doc_id, text)
                log(f"entities={len(entity_rows)}")
            except NERServiceUnavailable:
                log("WARNING: NER service unavailable — entities not refreshed for this run")
            except Exception:
                logger.exception("entity extraction failed, continuing without entities")

            # 11d. Place verification (stage 3): geocoder confirms the places
            #      exist (cached), LLM confirms relevance -> miejsce-* tags.
            if not proposal_only:
                try:
                    from library.place_verification import verify_document_places

                    summary = verify_document_places(session, doc, text)
                    log(f"places: {len(summary['resolved'])} resolved, tags: {summary['tagged'] or '-'}")
                except Exception:
                    logger.exception("place verification failed, continuing without place tags")

                # 11e. Person resolution (stage 4): alias/Wikidata+LLM/fuzzy ->
                #      document_persons links (low confidence => manual_review).
                try:
                    from library.person_registry import resolve_document_persons

                    p_summary = resolve_document_persons(session, doc, text)
                    log(f"persons: linked={len(p_summary['linked'])} skipped={len(p_summary['skipped'])}")
                except Exception:
                    logger.exception("person resolution failed, continuing without person links")

                if author_bio:
                    try:
                        from library.author_biography import process_author_biography

                        bio_summary = process_author_biography(session, doc, author_bio, model)
                        log(f"author biography: {bio_summary['status']}")
                    except Exception:
                        logger.exception("author biography processing failed, continuing")

                try:
                    from library.information_provenance import refresh_document_information_sources

                    provenance = refresh_document_information_sources(session, doc, text, model)
                    log(f"information sources: {len(provenance['sources'])}")
                except Exception:
                    logger.exception("information-source extraction failed, continuing")

        # 12. Persist to DB. An unfinished earlier run of the same scope is an
        #     abandoned attempt once this one lands — supersede it so its
        #     pending chunks stop counting as missing Obsidian notes (same
        #     transaction as the new run, so a failed commit changes nothing).
        for stale_run in supersede_unfinished_runs(session, doc_id, scope):
            log(f"superseded unfinished run_id={stale_run.id} (same scope, never reviewed)")

        run = DocumentAnalysisRun(
            document_id=doc_id,
            model=model,
            chunk_size=chunk_size,
            synthesis=synthesis or None,
            speakers=speakers,
            mode=mode,
            status="created",
            scope=scope,
        )
        session.add(run)
        session.flush()  # get run.id before adding children

        for i, s in enumerate(sections):
            seg_start, seg_end = seg_map[i]
            session.add(DocumentChunk(
                run_id=run.id,
                document_id=doc_id,
                position=i + 1,
                type=s["type"],
                topic=s["topic"] or None,
                original_text=s["original"],
                corrected_text=s["text"] or None,
                summary=s["summary"] or None,
                seg_start=seg_start,
                seg_end=seg_end,
                rewrite_ratio=s["ratio"],
                status="pending",
            ))

        for i, ts in enumerate(topic_sections_data):
            session.add(DocumentTopicSection(
                run_id=run.id,
                document_id=doc_id,
                position=i + 1,
                type=ts["type"],
                title=ts["title"] or None,
                summary=ts["summary"] or None,
                chunk_positions=ts["chunk_indices"],
            ))

        try:
            session.commit()
        except Exception as exc:
            session.rollback()
            raise RuntimeError(f"DB commit failed: {exc}") from exc

        log(f"saved run_id={run.id} chunks={len(sections)} topic_sections={len(topic_sections_data)}")
        return run


def generate_embeddings_from_run(
    session, run_id: int, progress_fn: Callable[[str], None] | None = None,
) -> dict:
    """Generate embeddings from a run's approved TEMAT chunks.

    For each chunk with type == "TEMAT" and status == "approved": takes
    corrected_text (transcript mode) or original_text (article mode), splits it
    into embedding-sized pieces (md_split_for_emb, same splitter used by
    webdocument_md_decode.py), strips markdown syntax, and stores one
    WebsiteEmbedding row per piece with chunk_id set. REKLAMA/SZUM chunks and
    non-approved TEMAT chunks are skipped.

    Re-running deletes this run's previously chunk-linked embeddings first, so
    it is safe to call again after a chunk is re-approved or edited.
    """
    from sqlalchemy import delete, select

    from library.config_loader import load_config
    from library.db.models import WebsiteEmbedding
    from library.lenie_markdown import md_remove_markdown, md_split_for_emb
    from library.models.stalker_document_status import StalkerDocumentStatus
    from library.stalker_web_documents_db_postgresql import WebsitesDBPostgreSQL
    import library.embedding as embedding

    def log(msg: str) -> None:
        logger.info("[embeddings run=%d] %s", run_id, msg)
        if progress_fn:
            progress_fn(msg)

    run = session.get(DocumentAnalysisRun, run_id)
    if run is None:
        raise ValueError(f"Run {run_id} not found")

    doc = session.get(WebDocument, run.document_id)
    if doc is None:
        raise ValueError(f"Document {run.document_id} not found")

    model = load_config().require("EMBEDDING_MODEL")
    websites = WebsitesDBPostgreSQL(session)

    all_chunks = session.scalars(
        select(DocumentChunk).where(DocumentChunk.run_id == run_id)
    ).all()
    eligible = [c for c in all_chunks if c.type == "TEMAT" and c.status == "approved"]

    chunk_ids = [c.id for c in all_chunks]
    if chunk_ids:
        session.execute(delete(WebsiteEmbedding).where(WebsiteEmbedding.chunk_id.in_(chunk_ids)))
        session.commit()

    if not doc.language:
        doc.language = "pl"

    created = 0
    skipped_empty = 0
    for i, chunk in enumerate(eligible, 1):
        log(f"chunk {i}/{len(eligible)} (position {chunk.position})...")
        text = (chunk.corrected_text or chunk.original_text or "").strip()
        if not text:
            skipped_empty += 1
            continue
        for part in md_split_for_emb(text):
            cleaned = md_remove_markdown(part).strip()
            if not cleaned:
                continue
            result = embedding.get_embedding(model=model, text=cleaned)
            if result.status != "success" or not result.embedding:
                logger.warning(
                    "Embedding generation failed for chunk %d (run %d): %s",
                    chunk.id, run_id, result.status,
                )
                continue
            websites.embedding_add(
                website_id=doc.id,
                embedding=result.embedding,
                language=doc.language,
                text=cleaned,
                text_original=cleaned,
                model=model,
                chunk_id=chunk.id,
            )
            created += 1

    if created:
        doc.document_state = StalkerDocumentStatus.EMBEDDING_EXIST.name

    session.commit()
    log(f"done: {created} embeddings created from {len(eligible)} chunks")

    return {
        "run_id": run_id,
        "document_id": doc.id,
        "model": model,
        "chunks_considered": len(eligible),
        "chunks_skipped_empty": skipped_empty,
        "embeddings_created": created,
    }
