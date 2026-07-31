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
    DocumentAnalysisRun, DocumentChunk, DocumentTopicSection, Document,
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
# Chunk LLM calls are independent (see create_run's _analyze_one) and safe to
# run concurrently. Also caps book/article runs (hundreds of chunks) from
# firing them all at once — actual concurrency is min(this, chunk_count), so
# a typical video (10-25 chunks) runs nearly all of them in one wave while a
# book never exceeds this many in flight.
#
# Live-tested on a 19-chunk video (2026-07-30, doc 9356/9353 investigation):
# 1 worker -> 338.7s stage time, 17.8s avg/call, 0 errors
# 4 workers -> 100.7s, 19.8s avg/call, 0 errors
# 19 workers -> 33.7s, 31.7s avg/call (+78% vs baseline), 0 errors — no hard
#   rate limit hit, but per-call latency degrades noticeably (soft ceiling,
#   likely queuing/GPU contention on CloudFerro's side). Settled below that
#   tested-safe point rather than extrapolating further untested.
CHUNK_ANALYSIS_MAX_WORKERS = 16
_SECTION_HEADER_RE = re.compile(r'^### (REKLAMA|TEMAT|ZRODLA|SZUM): ?(.+)$', re.MULTILINE)

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


def _flatten_segment_words(segments: list[dict]) -> tuple[list[str], list[int]]:
    """Raw segment text as a flat word stream, plus a parallel array mapping
    each word back to the segment index it came from."""
    words: list[str] = []
    word_seg: list[int] = []
    for idx, seg in enumerate(segments):
        t = (seg.get("text") or "").strip()
        if t.startswith(">>"):
            t = t[2:].strip()
        for w in t.split():
            words.append(w)
            word_seg.append(idx)
    return words, word_seg


def _locate_boundary_word(raw_words: list[str], tail_words: list[str], guess_idx: int) -> int | None:
    """Search `raw_words` for `tail_words` in order (gaps between them are OK
    — a couple may be speech fillers present in the raw transcript but
    stripped from chunk_texts before splitting), closest to `guess_idx`.

    Returns the raw word index right after the match, or None when not found
    in the search window.
    """
    if not tail_words or not raw_words:
        return None
    window = max(80, len(raw_words) // 8)
    lo = max(0, guess_idx - window)
    hi = min(len(raw_words), guess_idx + window)
    first = tail_words[0]
    best: int | None = None
    best_dist: int | None = None
    max_gap = len(tail_words) + 6  # tolerate a handful of stripped fillers
    for i in range(lo, hi):
        if raw_words[i] != first:
            continue
        j, k = i, 0
        while j < len(raw_words) and k < len(tail_words) and (j - i) < max_gap:
            if raw_words[j] == tail_words[k]:
                k += 1
            j += 1
        if k == len(tail_words):
            dist = abs(i - guess_idx)
            if best_dist is None or dist < best_dist:
                best, best_dist = j, dist
    return best


def _map_chunks_to_segments(
    chunk_texts: list[str], segments: list[dict]
) -> list[tuple[int | None, int | None]]:
    """Map each chunk to a range of raw transcript segment indices.

    chunk_texts is split (at sentence boundaries) from text that has already
    had speech fillers stripped and, for multi-speaker transcripts, speaker
    labels inserted (document_analysis_service steps 5-6) — it has diverged
    character-for-character from the untouched raw `segments`, so a blind
    character-count proportion can land a chunk boundary mid-sentence when
    segments have uneven lengths.

    For each chunk boundary this looks for the actual words ending that
    chunk inside `segments`, searched near the proportional estimate
    (_locate_boundary_word) — falling back to the plain proportion only when
    no match is found nearby (e.g. the boundary falls in a filler-heavy
    stretch), so an unmatched chunk still gets a computed range rather than
    an error.
    """
    total = sum(len(c) for c in chunk_texts)
    if not total or not segments:
        return [(None, None)] * len(chunk_texts)
    n = len(segments)
    raw_words, raw_word_seg = _flatten_segment_words(segments)

    def _word_to_seg(word_idx: int) -> int:
        if not raw_words:
            return n
        if word_idx <= 0:
            return 0
        if word_idx >= len(raw_words):
            return n
        return raw_word_seg[word_idx]

    boundaries: list[int] = []  # segment index each chunk (but the last) ends at
    cum_chars = 0
    for chunk in chunk_texts[:-1]:
        cum_chars += len(chunk)
        guess_seg = round(n * cum_chars / total)
        guess_word_idx = round(len(raw_words) * cum_chars / total) if raw_words else 0
        tail_words = chunk.split()[-8:]
        match = _locate_boundary_word(raw_words, tail_words, guess_word_idx)
        boundary = _word_to_seg(match) if match is not None else guess_seg
        boundaries.append(min(max(boundary, 0), n))

    result: list[tuple[int, int]] = []
    prev = 0
    for boundary in boundaries:
        result.append((prev, max(boundary, prev)))
        prev = max(boundary, prev)
    result.append((prev, n))
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


def _extract_text(doc: Document, prefer_md: bool = False) -> tuple[str, str]:
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
    # New transcripts use Markdown H2 chapter headings; accept legacy bare
    # title lines too, so older documents remain chapter-aware for analysis.
    def block_title(block: str) -> str:
        first_line = block.split("\n", 1)[0].strip()
        return re.sub(r"^#{1,6}\s+", "", first_line).strip()

    found = sum(1 for b in blocks if block_title(b) in title_set)
    if found < (len(chapter_titles) + 1) // 2:  # require a strict majority
        return None

    def cap(piece: str) -> list[str]:
        return [piece] if len(piece) <= chunk_size else split_text_into_sentence_chunks(piece, chunk_size)

    chunks: list[str] = []
    current = ""
    for block in blocks:
        starts_chapter = block_title(block) in title_set
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
        "Fragmenty źródłowe (ZRODLA), reklamowe (REKLAMA) i szum techniczny (SZUM) możesz pominąć lub zgrupować\n"
        "razem pod jedną sekcją odpowiednio ZRODLA, REKLAMA lub SZUM.\n\n"
        "Zwróć TYLKO tablicę JSON bez żadnego dodatkowego tekstu, w formacie:\n"
        '[{"title": "Tytuł sekcji tematycznej", "type": "TEMAT", "chunks": [1, 2]}]\n'
        'Gdzie "chunks" to numery fragmentów (numeracja od 1), "type" to "TEMAT", "ZRODLA", "REKLAMA" lub "SZUM".\n\n'
        f"Fragmenty:\n{chunk_list}"
    )
    try:
        response_text, _ = call_model(prompt, model, max_tokens=600, operation="topic_grouping")
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
        response_text, _ = call_model(prompt, model, SYNTHESIS_MAX_TOKENS, operation="document_synthesis")
        return response_text.strip()
    except Exception:
        logger.exception("synthesis LLM call failed")
        return ""


def _apply_tags(doc: Document, text: str) -> None:
    """Thematic + country tagging.

    Merges newly detected tags into doc.tags rather than overwriting: repeat
    analysis runs (e.g. one run per book chapter) should accumulate tags
    across runs, not clobber ones set by a previous run.
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
        reclean: bool = False,
        scope_chapter: int | None = None,
        document_enriched: bool = False,
        reuse_existing_entities: bool = False,
    ) -> DocumentAnalysisRun:
        """Create a new analysis run for an existing document and persist to DB.

        Args:
            doc_id:       ID of document in documents.
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
            extract_speaker_info, remove_speech_fillers,
        )
        from library.text_functions import split_markdown_into_chunks, split_text_into_sentence_chunks

        if mode not in ANALYSIS_MODES:
            raise ValueError(f"Invalid mode: {mode!r} (expected one of {ANALYSIS_MODES})")
        is_transcript = mode == "transcript"
        if scope_chapter is not None and is_transcript:
            raise ValueError("scope_chapter requires article mode")
        if reclean and is_transcript:
            raise ValueError("reclean requires article mode")
        proposal_only = split_only

        def log(msg: str) -> None:
            logger.info(msg)
            if progress_fn:
                progress_fn(msg)

        session = self.session

        # 1. Load document
        doc = Document.get_by_id(session, doc_id)
        if doc is None:
            raise ValueError(f"Document {doc_id} not found")

        # 2. Extract text (article mode prefers text_md — headers drive the split)
        text, text_field = _extract_text(doc, prefer_md=not is_transcript)
        if not text:
            raise ValueError(f"Document {doc_id} has no usable text (checked: text, text_md, text_raw)")

        log(f"doc={doc_id} mode={mode} field={text_field} len={len(text):,}")

        # 2b. Backfill published_on from a relative-date artifact in the raw
        # text (e.g. interia.pl's "Wczoraj, HH:MM") resolved against
        # ingested_at — never overwrites an already-known date. getattr()
        # throughout: fixture/fake Document doubles in tests don't define
        # these columns, mirroring the existing doc.url lookup above.
        if not is_transcript and getattr(doc, "published_on", None) is None:
            from library.article_cleaner import resolve_relative_publication_date

            resolved = resolve_relative_publication_date(text, getattr(doc, "ingested_at", None))
            if resolved is not None:
                doc.published_on = resolved
                doc.published_on_method = "relative"
                log(f"published_on backfilled from relative-date artifact: {resolved.isoformat()}")

        if reclean:
            from library.article_cleaner import clean_article_text

            original_length = len(text)
            text = clean_article_text(text, getattr(doc, "url", "") or "")["text"]
            if not text:
                raise ValueError(f"Document {doc_id} is empty after deterministic cleanup")
            log(f"reclean: {original_length:,} -> {len(text):,} chars (source unchanged)")

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

            article_body, author_bio = extract_trailing_author_biography(text, getattr(doc, "byline", None))
            chunk_texts = split_markdown_into_chunks(article_body, chunk_size)
            if author_bio:
                chunk_texts.append(author_bio)
                author_bio_position = len(chunk_texts) - 1
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
                    "type": "SZUM" if i == author_bio_position else "TEMAT",
                    "topic": "Notka biograficzna autora" if i == author_bio_position else None,
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

        def _analyze_one(i: int, chunk_text: str) -> dict:
            if i == author_bio_position:
                return {
                    "type": "SZUM",
                    "topic": "Notka biograficzna autora",
                    "corrected_text": None,
                    "summary": None,
                    "rewrite_ratio": None,
                }
            if is_transcript:
                return analyze_chunk(
                    chunk_text, model,
                    position=i + 1, total=total,
                    speakers=speakers or None,
                    prev_context=_sentence_tail(chunk_texts[i - 1]) if i > 0 else "",
                    next_context=_sentence_head(chunk_texts[i + 1]) if i < total - 1 else "",
                )
            return analyze_article_chunk(chunk_text, model, position=i + 1, total=total)

        # Chunks are independent LLM calls (boundary context comes from the raw
        # split, not from a neighbor's result), so they can run concurrently.
        # ai_ask() tags each usage row from a contextvar (llm_usage_context, set
        # by the caller around create_run()) — contextvars are NOT inherited by
        # new threads, so it must be re-entered explicitly inside each worker or
        # parallel chunks would silently lose document_id/analysis_job_id on
        # their llm_usage_logs rows.
        results: list[dict] = [{}] * len(chunk_texts_iter)
        if chunk_texts_iter:
            from concurrent.futures import ThreadPoolExecutor, as_completed

            from library.llm_usage.context import current_usage_context, llm_usage_context

            usage_document_id, usage_job_id, usage_run_id = current_usage_context()

            def _run(i: int, chunk_text: str) -> dict:
                with llm_usage_context(
                    document_id=usage_document_id, analysis_job_id=usage_job_id, analysis_run_id=usage_run_id,
                ):
                    return _analyze_one(i, chunk_text)

            log(f"analyzing {total} chunks (up to {CHUNK_ANALYSIS_MAX_WORKERS} concurrent)...")
            max_workers = min(CHUNK_ANALYSIS_MAX_WORKERS, len(chunk_texts_iter))
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_index = {
                    executor.submit(_run, i, chunk_text): i
                    for i, chunk_text in enumerate(chunk_texts_iter)
                }
                first_error: tuple[int, Exception] | None = None
                for future in as_completed(future_to_index):
                    i = future_to_index[future]
                    try:
                        results[i] = future.result()
                        log(f"chunk {i + 1}/{total} done ({len(chunk_texts_iter[i]):,} chars)")
                    except Exception as exc:
                        if first_error is None or i < first_error[0]:
                            first_error = (i, exc)
                if first_error is not None:
                    fail_i, exc = first_error
                    raise RuntimeError(f"LLM call failed for chunk {fail_i + 1}/{total}: {exc}") from exc

        for i, chunk_text in enumerate(chunk_texts_iter):
            result = results[i]
            sections.append({
                "type": result["type"],
                "topic": result["topic"],
                "original": chunk_text,
                "text": result["corrected_text"],
                "ratio": result["rewrite_ratio"],
                "summary": result["summary"],
            })

        # 10. Group chunks into logical topic sections (skip LLM grouping for
        #     split_only, and for a single chunk — nothing to group, and asking
        #     the LLM to merge one fragment into "usually 5-10 sections" tends to
        #     come back with no valid group, silently starving 11b's tagging input)
        topic_groups = [] if proposal_only or len(sections) <= 1 else _merge_topics(sections, model, mode=mode)
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

        # 11b. Thematic + country tagging — uses the synthesis as input when
        #      available (concise, already LLM-summarized), else falls back to
        #      concatenated topic summaries. Skipped for split_only: no LLM
        #      output exists yet.
        if not proposal_only:
            tagging_text = (
                synthesis
                or "\n\n".join(ts["summary"] for ts in topic_sections_data if ts["summary"])
                # Last-resort fallback straight from per-chunk analysis (step 9) —
                # covers cases where topic_sections_data itself ends up empty
                # (e.g. _merge_topics returning no valid group).
                or "\n\n".join(s["summary"] for s in sections if s["type"] == "TEMAT" and s["summary"])
            )
            if tagging_text:
                log("tagging document...")
                _apply_tags(doc, tagging_text)

            # 11b2. Article author fallback (LLM) — article_metadata.extract_article_author()
            #       (deterministic, WP.pl only) already ran at import time; this is a
            #       fallback for everything else. Never overwrites an existing doc.byline
            #       (deterministic or manually entered). Whole-document runs only — a
            #       single chapter excerpt is not a reliable place to look for a byline.
            if not is_transcript and scope is None and not (getattr(doc, "byline", None) or "").strip():
                try:
                    from library.author_biography import (
                        extract_trailing_author_biography,
                        process_author_biography,
                    )
                    from library.author_service import set_document_authors
                    from library.chunk_llm_analysis import extract_author_info, head_tail_excerpt

                    author_names = extract_author_info(head_tail_excerpt(text), model)
                    if author_names:
                        set_document_authors(self.session, doc, author_names, method="llm")
                        log(f"author detected: {', '.join(author_names)}")

                        # The byline wasn't known yet when this run's text was split
                        # above (11b2 runs after chunking), so extract_trailing_author_biography()
                        # never got a chance to isolate the "o autorze" widget from
                        # doc.text_md the way it does when the byline is already known
                        # (see the article-mode split earlier in this function). Do it
                        # now against the stored text_md — cheap (regex, no LLM) and
                        # keeps the NEXT run/reclean from re-surfacing it as its own
                        # chunk; this run's already-created chunks are unaffected.
                        stripped_md, bio = extract_trailing_author_biography(
                            doc.text_md or "", author_names[0]
                        )
                        if bio:
                            doc.text_md = stripped_md
                            process_author_biography(self.session, doc, bio, model)
                            log("author biography isolated from doc.text_md for future runs")
                except Exception:
                    logger.exception("author extraction failed, continuing without author")

            # 11f. Article quality ("staranność") scoring — deterministic
            #      penalties + one LLM rubric call (library/article_quality.py).
            #      Whole-document article runs only: a transcript or a single
            #      chapter is not a fair sample of the article's care.
            if not is_transcript and scope is None:
                try:
                    from library.article_quality import compute_quality

                    doc.quality = compute_quality(doc, sections, model=model, session=self.session)
                    log(f"quality: {doc.quality['score']}/100 "
                        f"(penalties: {doc.quality['penalties'] or '-'})")
                except Exception:
                    logger.exception("quality scoring failed, continuing without quality")

        # 11c. NER entities (persons/places) on the full document text — offline
        #      (no LLM), stored in document_entities with replace semantics, so
        #      chapter-scoped runs skip it (a single chapter's entities must not
        #      clobber the whole document's). ``reuse_existing_entities`` means
        #      the user already ran the explicit entity stage on this unchanged
        #      document; do not make it (and its place/person follow-ups) pay twice.
        if scope is None and not document_enriched:
            if reuse_existing_entities:
                log("entities: reusing earlier document-level NER result")
            else:
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

            if not proposal_only:
                if author_bio:
                    try:
                        from library.author_biography import process_author_biography

                        bio_summary = process_author_biography(session, doc, author_bio, model)
                        log(f"author biography: {bio_summary['status']}")
                    except Exception:
                        logger.exception("author biography processing failed, continuing")

                # Information provenance is a reader enrichment, not a
                # prerequisite for chunk review or search.  It is requested
                # explicitly through POST /document/<id>/enrich.

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

        created_chunks = []
        for i, s in enumerate(sections):
            seg_start, seg_end = seg_map[i]
            created_chunk = DocumentChunk(
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
            )
            session.add(created_chunk)
            created_chunks.append(created_chunk)

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

        session.flush()
        try:
            from library.cited_publications import refresh_document_cited_publications

            citations = refresh_document_cited_publications(session, doc_id, created_chunks)
            log(f"cited publications: {len(citations['publications'])}")
        except Exception:
            logger.exception("cited-publication extraction failed, continuing")

        try:
            session.commit()
        except Exception as exc:
            session.rollback()
            raise RuntimeError(f"DB commit failed: {exc}") from exc

        log(f"saved run_id={run.id} chunks={len(sections)} topic_sections={len(topic_sections_data)}")
        return run


def _document_has_markdown_chapters(doc: Document) -> bool:
    from library.text_functions import detect_chapters

    text, _field = _extract_text(doc, prefer_md=True)
    return bool(detect_chapters(text)) if text else False


def paragraphize_run_transcript_chunks(
    session, run_id: int, *, model: str | None = None,
    progress_fn: Callable[[str], None] | None = None,
) -> dict:
    """Add LLM-selected paragraph spacing to a transcript run's TEMAT chunks.

    Only for YouTube videos with no source chapters: the reader's TEMAT-chunk
    fallback (chunk_review_routes._chunk_based_chapters) renders each chunk's
    corrected_text as a single wall of text, because the rewrite step
    (chunk_llm_analysis.rewrite_chunk_text) only fixes punctuation/sentence
    boundaries, never paragraph breaks. Chaptered videos already get paragraph
    spacing earlier in the pipeline, on doc.text before chunking (see
    paragraphize_transcript() / POST /document/<id>/paragraphize_transcript) —
    this covers the chunk-based fallback that mechanism can't reach.

    No-op (zero LLM calls) for: article-mode runs, movies, chaptered YouTube
    videos, and any chunk whose corrected_text already has a blank line
    (idempotent — safe to call again, e.g. on every "Generuj embeddingi").
    """
    from sqlalchemy import select

    from library.transcript_paragraphs import paragraphize_chunk_text

    def log(msg: str) -> None:
        logger.info("[paragraphize run=%d] %s", run_id, msg)
        if progress_fn:
            progress_fn(msg)

    run = session.get(DocumentAnalysisRun, run_id)
    if run is None:
        raise ValueError(f"Run {run_id} not found")
    doc = session.get(Document, run.document_id)
    if doc is None:
        raise ValueError(f"Document {run.document_id} not found")

    summary = {
        "run_id": run_id, "document_id": doc.id,
        "chunks_processed": 0, "chunks_changed": 0, "paragraphs_added": 0, "model_calls": 0,
    }
    if doc.document_type != "youtube" or run.mode != "transcript":
        return summary
    if _document_has_markdown_chapters(doc):
        return summary

    chunks = session.scalars(
        select(DocumentChunk)
        .where(DocumentChunk.run_id == run_id, DocumentChunk.type == "TEMAT")
        .order_by(DocumentChunk.position)
    ).all()

    use_model = model or run.model
    for chunk in chunks:
        text = (chunk.corrected_text or "").strip()
        if not text or re.search(r"\n\s*\n", text):
            continue
        summary["chunks_processed"] += 1
        result = paragraphize_chunk_text(
            text, document_id=doc.id, analysis_run_id=run_id, model=use_model,
        )
        summary["model_calls"] += result.model_calls
        if result.text != text:
            chunk.corrected_text = result.text
            summary["chunks_changed"] += 1
            summary["paragraphs_added"] += result.paragraph_count
            session.commit()
        log(f"chunk {chunk.position}: {result.paragraph_count} paragraphs, {result.model_calls} LLM calls")

    return summary


EMBEDDING_BATCH_SIZE = 32


def generate_embeddings_from_run(
    session, run_id: int, progress_fn: Callable[[str], None] | None = None,
) -> dict:
    """Generate embeddings from a run's approved TEMAT chunks.

    For each chunk with type == "TEMAT" and status == "approved": takes
    corrected_text (transcript mode) or original_text (article mode), splits it
    into embedding-sized pieces (md_split_for_emb, same splitter used by
    document_md_decode.py), strips markdown syntax, and stores one
    DocumentEmbedding row per piece with chunk_id set. REKLAMA/SZUM chunks and
    non-approved TEMAT chunks are skipped.

    Pieces are embedded in batches of EMBEDDING_BATCH_SIZE (one provider API
    call per batch where the provider supports it — a 400-chunk book used to
    take ~5 h as one HTTP round-trip per piece) and the session is committed
    after every batch, so a crash mid-run keeps the embeddings finished so far
    instead of discarding hours of work.

    Re-running deletes this run's previously chunk-linked embeddings first, so
    it is safe to call again after a chunk is re-approved or edited.
    """
    from sqlalchemy import delete, select

    from library.config_loader import load_config
    from library.db.models import DocumentEmbedding
    from library.lenie_markdown import md_remove_markdown, md_split_for_emb
    from library.article_quality import remove_photo_caption_lines
    from library.models.stalker_document_status import StalkerDocumentStatus
    from library.document_repository import DocumentRepository
    import library.embedding as embedding

    def log(msg: str) -> None:
        logger.info("[embeddings run=%d] %s", run_id, msg)
        if progress_fn:
            progress_fn(msg)

    run = session.get(DocumentAnalysisRun, run_id)
    if run is None:
        raise ValueError(f"Run {run_id} not found")

    doc = session.get(Document, run.document_id)
    if doc is None:
        raise ValueError(f"Document {run.document_id} not found")

    try:
        paragraph_summary = paragraphize_run_transcript_chunks(session, run_id, progress_fn=progress_fn)
        if paragraph_summary["chunks_changed"]:
            log(
                f"paragraphized {paragraph_summary['chunks_changed']}/{paragraph_summary['chunks_processed']} "
                f"chunks before embedding ({paragraph_summary['paragraphs_added']} paragraph breaks added)"
            )
    except Exception:
        logger.exception("transcript paragraphization failed for run %s, continuing with embedding generation", run_id)

    model = load_config().require("EMBEDDING_MODEL")
    websites = DocumentRepository(session)

    all_chunks = session.scalars(
        select(DocumentChunk).where(DocumentChunk.run_id == run_id)
    ).all()
    eligible = [c for c in all_chunks if c.type == "TEMAT" and c.status == "approved"]

    chunk_ids = [c.id for c in all_chunks]
    if chunk_ids:
        session.execute(delete(DocumentEmbedding).where(DocumentEmbedding.chunk_id.in_(chunk_ids)))
        session.commit()

    if not doc.language:
        doc.language = "pl"

    skipped_empty = 0
    pieces: list[tuple[DocumentChunk, str]] = []
    for chunk in eligible:
        text = remove_photo_caption_lines(
            chunk.corrected_text or chunk.original_text or ""
        ).strip()
        if not text:
            skipped_empty += 1
            continue
        for part in md_split_for_emb(text):
            cleaned = md_remove_markdown(part).strip()
            if cleaned:
                pieces.append((chunk, cleaned))

    created = 0
    failed = 0
    total_batches = (len(pieces) + EMBEDDING_BATCH_SIZE - 1) // EMBEDDING_BATCH_SIZE
    for batch_number, start in enumerate(range(0, len(pieces), EMBEDDING_BATCH_SIZE), 1):
        batch = pieces[start:start + EMBEDDING_BATCH_SIZE]
        log(f"batch {batch_number}/{total_batches} ({len(batch)} fragments, {created} embeddings stored)...")
        results = embedding.get_embeddings(model, [piece_text for _, piece_text in batch])
        for (chunk, cleaned), result in zip(batch, results):
            if result.status != "success" or not result.embedding:
                failed += 1
                logger.warning(
                    "Embedding generation failed for chunk %d (run %d): %s",
                    chunk.id, run_id, result.error_message or result.status,
                )
                continue
            websites.embedding_add(
                document_id=doc.id,
                embedding=result.embedding,
                language=doc.language,
                text=cleaned,
                text_original=cleaned,
                model=model,
                chunk_id=chunk.id,
            )
            created += 1
        session.commit()

    if created:
        doc.processing_status = StalkerDocumentStatus.EMBEDDING_EXIST.name

    session.commit()
    log(f"done: {created} embeddings created from {len(eligible)} chunks")

    return {
        "run_id": run_id,
        "document_id": doc.id,
        "model": model,
        "chunks_considered": len(eligible),
        "chunks_skipped_empty": skipped_empty,
        "embeddings_created": created,
        "embeddings_failed": failed,
    }
