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
_SECTION_HEADER_RE = re.compile(r'^### (REKLAMA|TEMAT): ?(.+)$', re.MULTILINE)


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


def _extract_text(doc: WebDocument) -> tuple[str, str]:
    """Return (text, field_name) from best available field.

    Priority: text → text_md → text_raw (JSON transcript → plain text).
    Returns ("", "") when no usable text found.
    """
    for field in ("text", "text_md"):
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
        "Fragmenty reklamowe (REKLAMA) możesz pominąć lub zgrupować razem pod jedną sekcją REKLAMA.\n\n"
        "Zwróć TYLKO tablicę JSON bez żadnego dodatkowego tekstu, w formacie:\n"
        '[{"title": "Tytuł sekcji tematycznej", "type": "TEMAT", "chunks": [1, 2]}]\n'
        'Gdzie "chunks" to numery fragmentów (numeracja od 1), "type" to "TEMAT" lub "REKLAMA".\n\n'
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

        def log(msg: str) -> None:
            logger.info(msg)
            if progress_fn:
                progress_fn(msg)

        session = self.session

        # 1. Load document
        doc = WebDocument.get_by_id(session, doc_id)
        if doc is None:
            raise ValueError(f"Document {doc_id} not found")

        # 2. Extract text
        text, text_field = _extract_text(doc)
        if not text:
            raise ValueError(f"Document {doc_id} has no usable text (checked: text, text_md, text_raw)")

        log(f"doc={doc_id} mode={mode} field={text_field} len={len(text):,}")

        if is_transcript:
            # 3. Detect format (multi-speaker = has >> speaker markers)
            speaker_changes = len(re.findall(r'>>', text))
            is_multi_speaker = speaker_changes > 0
            log(f"format={'multi-speaker' if is_multi_speaker else 'monologue'} ({speaker_changes} >>)")

            # 4. Extract speakers from intro text (only for multi-speaker conversations),
            #    unless the caller already provided them
            if speakers is None:
                speakers = []
                if is_multi_speaker:
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

            # 7. Split into chunks at sentence boundaries
            chunk_texts = split_text_into_sentence_chunks(text, chunk_size)

            # 8. Map chunks to transcript segments (for timestamp links)
            segments = _load_segments(getattr(doc, "text_raw", None) or "")
        else:
            # Article mode: text is already clean — no speakers, no fillers,
            # split at markdown headers, no transcript segments to map.
            speakers = speakers or []
            chunk_texts = split_markdown_into_chunks(text, chunk_size)
            segments = []
        log(f"split={len(chunk_texts)} chunks, max {chunk_size:,} chars")

        seg_map = (
            _map_chunks_to_segments(chunk_texts, segments)
            if segments else [(None, None)] * len(chunk_texts)
        )

        # 9. Analyze each chunk via LLM (with boundary context from adjacent chunks)
        sections: list[dict] = []
        total = len(chunk_texts)
        for i, chunk_text in enumerate(chunk_texts):
            log(f"chunk {i + 1}/{total} ({len(chunk_text):,} chars)...")
            try:
                if is_transcript:
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

        # 10. Group chunks into logical topic sections
        topic_groups = _merge_topics(sections, model, mode=mode)
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
        if not no_synthesis:
            log("generating synthesis...")
            synthesis = _synthesize(sections, doc.title or f"Dokument {doc_id}", model, mode=mode)

        # 12. Persist to DB
        run = DocumentAnalysisRun(
            document_id=doc_id,
            model=model,
            chunk_size=chunk_size,
            synthesis=synthesis or None,
            speakers=speakers,
            mode=mode,
            status="created",
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
