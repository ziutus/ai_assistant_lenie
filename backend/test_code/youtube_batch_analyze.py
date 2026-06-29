#!/usr/bin/env python3
"""
Batch analysis of long YouTube transcripts using Bielik LLM via CloudFerro Sherlock.

Pipeline (two passes per chunk — tasks separated to avoid summarizing instead of rewriting):
  Pass 1 — rewrite:   label section (REKLAMA/TEMAT) + correct transcript verbatim
  Pass 2 — summarize: 2-3 sentence summary of corrected text (skipped for REKLAMA)
  Final  — synthesis: overall conclusions from all summaries

Why two passes:
  - Single prompt mixing "rewrite + summarize" caused Bielik to skip rewriting and jump
    straight to a summary. Separating tasks forces the model to do each job fully.

Why ~5,000 chars (≈1,500 tokens) per chunk:
  - Rewrite output ≈ same size as input → needs max_tokens=2,500 (fits comfortably)
  - Summary output is small → max_tokens=400

Cost at 0.56 EUR/M tokens: ~0.05 EUR for a 90K-char transcript
  (19 chunks × ~4,700 tok/chunk = 89K tokens).

Text splitting: library.text_functions.split_text_into_chunks (shared utility).

Usage (from backend/ directory):
    # Windows PowerShell
    $env:PYTHONPATH="."; $env:PYTHONIOENCODING="utf-8"; .venv/Scripts/python test_code/youtube_batch_analyze.py --doc_id 9158
    $env:PYTHONPATH="."; $env:PYTHONIOENCODING="utf-8"; .venv/Scripts/python test_code/youtube_batch_analyze.py --doc_id 9158 --dry_run
    $env:PYTHONPATH="."; $env:PYTHONIOENCODING="utf-8"; .venv/Scripts/python test_code/youtube_batch_analyze.py --doc_id 9158 --no_synthesis

    # WSL / Linux (Bash)
    PYTHONPATH=. .venv/bin/python test_code/youtube_batch_analyze.py --doc_id 9158
"""

import argparse
import os
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unified_config_loader import load_config
from library.db.engine import get_session
from library.db.models import WebDocument, DocumentAnalysisRun, DocumentChunk, DocumentTopicSection
from library.api.cloudferro.sherlock.sherlock import sherlock_get_completion
from library.api.arklabs.arklabs_completion import arklabs_get_completion
from library.text_functions import split_text_into_sentence_chunks


CHUNK_CHARS = 5_000          # ≈1,500 text tokens — safe for verbatim reproduction
REWRITE_MAX_TOKENS = 2_500   # rewrite task: reproduce full text with corrections
REWRITE_MIN_RATIO = 0.80     # retry rewrite if output < 80% of input length
SUMMARY_MAX_TOKENS = 400     # summarize task: 2-3 sentences only
SYNTHESIS_MAX_TOKENS = 2_000
SYNTHESIS_MAX_INPUT_CHARS = 20_000

SECTION_HEADER_RE = re.compile(r'^### (REKLAMA|TEMAT): ?(.+)$', re.MULTILINE)

# Filler words common in YouTube auto-transcripts (Polish hesitation sounds)
_FILLER_RE = re.compile(r'\b[Yy]{2,}\b|\b[Ee]{3,}\b|\b[Mm]{3,}\b', re.IGNORECASE)
_STANDALONE_Y_RE = re.compile(r'(?<!\w)[Yy](?!\w)')


def clean_fillers(text: str) -> str:
    """Remove YouTube transcript filler sounds (yyy, eee, standalone y) and fix spacing."""
    text = _FILLER_RE.sub('', text)
    text = _STANDALONE_Y_RE.sub('', text)
    text = re.sub(r'[ \t]{2,}', ' ', text)
    text = re.sub(r' ([,.])', r'\1', text)
    return text


def _tail(text: str, max_chars: int = 300) -> str:
    """Last up to max_chars of text, preferring a sentence boundary start."""
    if len(text) <= max_chars:
        return text
    seg = text[-max_chars:]
    for sep in ('. ', '.\n', '? ', '! '):
        idx = seg.find(sep)
        if idx != -1:
            return seg[idx + len(sep):]
    return seg


def _head(text: str, max_chars: int = 300) -> str:
    """First up to max_chars of text, preferring a sentence boundary end."""
    if len(text) <= max_chars:
        return text
    seg = text[:max_chars]
    for sep in ('. ', '.\n', '? ', '! '):
        idx = seg.rfind(sep)
        if idx != -1:
            return seg[:idx + 1]
    return seg

SHERLOCK_MODELS = ["Bielik-11B-v3.0-Instruct"]
ARKLABS_PREFIX = "arklabs/"
ARKLABS_MODELS = [f"{ARKLABS_PREFIX}Bielik-11B-v3.0-Instruct"]
ALL_MODELS = SHERLOCK_MODELS + ARKLABS_MODELS


def detect_format(text: str) -> dict:
    """Detect monologue vs conversation by counting >> speaker-change markers."""
    changes = len(re.findall(r'>>', text))
    return {"is_multi_speaker": changes > 0, "speaker_changes": changes}


def extract_speaker_info(intro_text: str, model: str) -> list[dict]:
    """Ask LLM to extract speaker names/roles/descriptions from transcript intro.

    Returns list of dicts: [{"name": ..., "role": ..., "description": ...}]
    Returns [] if extraction fails.
    """
    import json as _json
    prompt = f"""Z poniższego fragmentu transkrypcji podcastu wyekstrahuj informacje o rozmówcach.
Zwróć TYLKO tablicę JSON bez żadnego dodatkowego tekstu, w formacie:
[{{"name": "Imię Nazwisko", "role": "prowadzący", "description": "krótki opis stanowiska/roli"}}]

Jeśli nie możesz zidentyfikować rozmówców, zwróć pustą tablicę: []

Fragment transkrypcji:
{intro_text}"""

    print("  [meta] Ekstrakcja rozmówców z intro...", flush=True)
    response_text, _ = call_model(prompt, model, max_tokens=300)
    try:
        match = re.search(r'\[.*\]', response_text, re.DOTALL)
        if match:
            return _json.loads(match.group())
    except (ValueError, AttributeError):
        pass
    return []


def assign_speakers(text: str, speaker1: str, speaker2: str) -> str:
    """Parse >> speaker-change markers from YouTube auto-transcript and label each turn.

    YouTube inserts >> when it detects a speaker change. The first segment belongs to
    speaker1 (the host / first voice), then speakers alternate.
    Short segments (< 10 chars) that are just acknowledgments are still labeled.
    """
    segments = re.split(r'\s*>>\s*', text)
    speakers = [speaker1, speaker2]
    labeled = []
    for i, seg in enumerate(segments):
        seg = seg.strip()
        if not seg:
            continue
        label = speakers[i % 2]
        labeled.append(f"[{label}]: {seg}")
    return "\n\n".join(labeled)


def _seconds_to_ts(secs: float) -> str:
    """Convert float seconds to HH:MM:SS or MM:SS string."""
    h = int(secs // 3600)
    m = int((secs % 3600) // 60)
    s = int(secs % 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def _load_transcript_segments(text_raw: str) -> list[dict] | None:
    """Parse YouTube transcript JSON from text_raw.

    Returns list of {text, start, duration} dicts, or None if not valid JSON.
    """
    import json as _json
    if not text_raw or not text_raw.strip().startswith('['):
        return None
    try:
        segs = _json.loads(text_raw.strip())
        if isinstance(segs, list) and segs and isinstance(segs[0], dict) and 'start' in segs[0]:
            return segs
    except (ValueError, KeyError, IndexError):
        pass
    return None


def _map_chunks_to_segments(chunk_texts: list[str], segments: list[dict]) -> list[tuple[int, int]]:
    """Map each chunk to an approximate range of segment indices (proportional by chars).

    Returns list of (start_seg_idx, end_seg_idx) per chunk.
    """
    total = sum(len(c) for c in chunk_texts)
    if not total:
        return [(0, len(segments))] * len(chunk_texts)
    n = len(segments)
    result = []
    cum = 0
    for chunk in chunk_texts:
        start = round(n * cum / total)
        cum += len(chunk)
        end = round(n * cum / total)
        result.append((min(start, n), min(end, n)))
    return result


def get_text_for_analysis(doc: WebDocument) -> tuple[str, str]:
    # Primary: plain text fields — LLM must receive plain text, not JSON
    for field in ("text", "text_md"):
        value = getattr(doc, field, None)
        if value and len(value) > 100:
            return value, field
    # text_raw may be YouTube transcript JSON — extract plain text for LLM
    raw = getattr(doc, "text_raw", None)
    if raw and len(raw) > 100:
        segs = _load_transcript_segments(raw)
        if segs:
            return "\n".join(s["text"] for s in segs), "text_raw (JSON→plain)"
        return raw, "text_raw"
    return "", ""


def call_model(prompt: str, model: str, max_tokens: int) -> tuple[str, int]:
    if model.startswith(ARKLABS_PREFIX):
        actual_model = f"speakleash/{model.removeprefix(ARKLABS_PREFIX)}"
        result = arklabs_get_completion(prompt, model=actual_model, max_tokens=max_tokens, temperature=0.2)
    else:
        result = sherlock_get_completion(prompt, model=model, max_tokens=max_tokens, temperature=0.2)
    tokens_in = getattr(result, "prompt_tokens", 0) or 0
    return result.response_text, tokens_in


def rewrite_chunk(chunk: str, chunk_num: int, total: int, model: str,
                  prev_context: str = "", next_context: str = "") -> str:
    """Pass 1: label section + correct transcript verbatim (no summarizing).

    prev_context / next_context: boundary sentences from adjacent chunks — shown to the model
    as read-only context to improve coherence at chunk boundaries, not to be reproduced.
    Retries once if output is shorter than REWRITE_MIN_RATIO of input — keeps the longer result.
    """
    ctx_prev = (
        f"\n[KONTEKST — koniec poprzedniego fragmentu, NIE przepisuj tego]:\n{prev_context}\n"
        if prev_context else ""
    )
    ctx_next = (
        f"\n[KONTEKST — początek następnego fragmentu, NIE przepisuj tego]:\n{next_context}\n"
        if next_context else ""
    )
    prompt = f"""Fragment {chunk_num}/{total} surowej transkrypcji podcastu YouTube.
{ctx_prev}
Wykonaj DWIE rzeczy — nic więcej:

1. W PIERWSZEJ LINII wpisz etykietę sekcji (tylko jedną z dwóch opcji):
   ### REKLAMA: nazwa_sponsora      (gdy to blok reklamowy lub sponsorski)
   ### TEMAT: opis_3_4_słowa        (gdy to merytoryczna treść rozmowy)

2. Przepisz poniższy tekst DOSŁOWNIE — każde słowo musi zostać zachowane. Popraw tylko:
   - Interpunkcję i podział na zdania.
   - Oczywiste błędy transkrypcji (zamienione lub zlepione wyrazy).
   - Zachowaj etykiety [Mówca]: na początku każdej wypowiedzi — nie usuwaj ich.
   NIE skracaj. NIE streszczaj. NIE pomijaj żadnej informacji.

--- FRAGMENT DO PRZEPISANIA ---
{chunk}
--- KONIEC FRAGMENTU ---
{ctx_next}"""

    best = ""
    for attempt in range(1, 3):  # max 2 attempts
        print(f"  [{chunk_num:>2}/{total}] rewrite ({len(chunk):,} znaków, próba {attempt})...", flush=True)
        response_text, tokens_in = call_model(prompt, model, REWRITE_MAX_TOKENS)
        out_len = len(response_text)
        ratio = round(out_len / len(chunk) * 100)
        print(f"  [{chunk_num:>2}/{total}] rewrite gotowe — {out_len:,} znaków ({ratio}% wejścia), tokeny: {tokens_in}",
              flush=True)
        if len(response_text) > len(best):
            best = response_text
        if out_len >= len(chunk) * REWRITE_MIN_RATIO:
            break
        if attempt < 2:
            print(f"  [{chunk_num:>2}/{total}] Wynik zbyt krótki ({ratio}% < {round(REWRITE_MIN_RATIO*100)}%) — ponawiam...",
                  flush=True)
    return best


def summarize_chunk(corrected_text: str, chunk_num: int, total: int, model: str) -> str:
    """Pass 2: summarize the already-corrected text in 2-3 sentences."""
    prompt = f"""Napisz streszczenie poniższego fragmentu merytorycznej rozmowy w 2-3 zdaniach.
Skup się na głównych tezach i wnioskach. Odpowiedz po polsku.

--- TEKST ---
{corrected_text}
--- KONIEC ---"""

    print(f"  [{chunk_num:>2}/{total}] summarize ({len(corrected_text):,} znaków)...", flush=True)
    response_text, tokens_in = call_model(prompt, model, SUMMARY_MAX_TOKENS)
    print(f"  [{chunk_num:>2}/{total}] summarize gotowe — tokeny: {tokens_in}", flush=True)
    return response_text.strip()


def parse_rewritten_chunk(raw: str) -> tuple[str, str, str]:
    """Extract (section_type, topic, corrected_text) from rewrite output."""
    header_match = SECTION_HEADER_RE.search(raw)
    section_type = header_match.group(1) if header_match else "TEMAT"
    topic = header_match.group(2).strip() if header_match else "Nieznany"
    text = raw[header_match.end():].strip() if header_match else raw.strip()
    return section_type, topic, text


def merge_topics(sections: list[dict], model: str) -> list[dict]:
    """Ask LLM to group adjacent chunks into logical topic sections.

    Returns list of dicts: [{"title": ..., "type": ..., "chunks": [1, 2, ...]}]
    where chunk numbers are 1-based. Returns [] if LLM call fails.
    """
    import json as _json
    chunk_list = "\n".join(
        f"{i + 1}. [{s['type']}] {s['topic']}"
        for i, s in enumerate(sections)
    )
    prompt = f"""Poniżej lista {len(sections)} fragmentów transkrypcji podcastu z ich tematami.
Pogrupuj SĄSIADUJĄCE fragmenty w logiczne sekcje tematyczne (zwykle 5-10 sekcji).
Fragmenty reklamowe (REKLAMA) możesz pominąć lub zgrupować razem pod jedną sekcją REKLAMA.

Zwróć TYLKO tablicę JSON bez żadnego dodatkowego tekstu, w formacie:
[{{"title": "Tytuł sekcji tematycznej", "type": "TEMAT", "chunks": [1, 2]}}]
Gdzie "chunks" to numery fragmentów (numeracja od 1), "type" to "TEMAT" lub "REKLAMA".

Fragmenty:
{chunk_list}"""

    print("  [tematy] Grupowanie fragmentów w logiczne sekcje...", flush=True)
    response_text, _ = call_model(prompt, model, max_tokens=600)
    try:
        match = re.search(r'\[.*\]', response_text, re.DOTALL)
        if match:
            groups = _json.loads(match.group())
            print(f"  [tematy] {len(groups)} sekcji tematycznych.", flush=True)
            return groups
    except (ValueError, AttributeError):
        pass
    print("  [tematy] Nie udało się zgrupować — fallback do chunków.", flush=True)
    return []


def build_topic_sections(sections: list[dict], topic_groups: list[dict]) -> list[dict]:
    """Merge chunk texts and summaries according to topic grouping from merge_topics()."""
    result = []
    for group in topic_groups:
        indices = [i - 1 for i in group.get("chunks", [])]
        valid = [i for i in indices if 0 <= i < len(sections)]
        if not valid:
            continue
        merged_text = "\n\n".join(s["text"] for i in valid if (s := sections[i])["text"])
        merged_summary = " ".join(s["summary"] for i in valid if (s := sections[i])["summary"])
        result.append({
            "title": group.get("title", ""),
            "type": group.get("type", "TEMAT"),
            "chunk_indices": [i + 1 for i in valid],  # 1-based for display
            "text": merged_text,
            "summary": merged_summary.strip(),
        })
    return result


def build_toc(topic_sections: list[dict]) -> str:
    """Build table of contents from logical topic sections."""
    lines = ["## SPIS TREŚCI\n"]
    for i, s in enumerate(topic_sections, 1):
        marker = "📢" if s["type"] == "REKLAMA" else "💬"
        chunks_label = f"  *(fragmenty: {', '.join(str(c) for c in s['chunk_indices'])})*"
        lines.append(f"{i:>2}. {marker} {s['title']}{chunks_label}")
    return "\n".join(lines)


def synthesize(sections: list[dict], title: str, model: str) -> str:
    content_sections = [s for s in sections if s["type"] == "TEMAT" and s["summary"]]
    if not content_sections:
        return ""

    summaries = "\n\n".join(
        [f"**{s.get('title') or s.get('topic', '')}**: {s['summary']}" for s in content_sections]
    )

    if len(summaries) > SYNTHESIS_MAX_INPUT_CHARS:
        print(f"  [synteza] Streszczenia zbyt długie ({len(summaries):,} znaków) — pomijam.")
        return ""

    prompt = f"""Poniżej są streszczenia kolejnych sekcji merytorycznych podcastu YouTube pt.: „{title}".

Na ich podstawie przygotuj:
1. GŁÓWNE WNIOSKI: 5-7 najważniejszych wniosków (lista punktowana).
2. SYNTEZA: Spójne streszczenie całości (6-8 zdań).

Odpowiedz wyłącznie po polsku.

--- STRESZCZENIA SEKCJI ---
{summaries}
--- KONIEC ---"""

    print(f"  [synteza] ({len(prompt):,} znaków)...", flush=True)
    response_text, _ = call_model(prompt, model, SYNTHESIS_MAX_TOKENS)
    print("  [synteza] Gotowe.", flush=True)
    return response_text


def save_html(doc_id: int, title: str, model: str,
              topic_sections: list[dict], sections: list[dict],
              segments: list[dict], video_id: str,
              timestamp: str,
              fmt: dict | None = None, speaker_info: list[dict] | None = None) -> str:
    """Generate HTML review table: per topic section, original transcript (with YT links) vs summary."""
    import html as _html
    exports_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", ".claude", "exports")
    )
    os.makedirs(exports_dir, exist_ok=True)
    filename = os.path.join(exports_dir, f"youtube_view_{doc_id}_{timestamp}.html")

    chunk_seg_map = _map_chunks_to_segments([s["original"] for s in sections], segments)

    def yt_url(secs: float) -> str:
        t = int(secs)
        return f"https://www.youtube.com/watch?v={video_id}&t={t}" if video_id else "#"

    def render_segments(seg_list: list[dict]) -> str:
        """Group segments into sentences; each sentence: speaker + timestamp on its own line, then full text."""
        if not seg_list:
            return ""

        MAX_SEGS_PER_GROUP = 8  # fallback grouping when no sentence boundary found

        sp_names = [sp["name"] for sp in (speaker_info or [])] if speaker_info else []
        cur_sp_idx = 0  # index into sp_names; alternates on each >>

        groups: list[dict] = []
        cur_texts: list[str] = []
        cur_start: float | None = None

        def flush_group(sp_idx: int) -> None:
            nonlocal cur_texts, cur_start
            if cur_texts:
                groups.append({
                    "start": cur_start,
                    "text": " ".join(cur_texts),
                    "speaker": sp_names[sp_idx] if sp_names else None,
                    "sp_idx": sp_idx,
                })
                cur_texts = []
                cur_start = None

        for seg in seg_list:
            raw = seg["text"].strip()
            if not raw:
                continue
            is_sc = raw.startswith(">>")
            text = raw[2:].strip() if is_sc else raw
            if is_sc:
                if cur_texts:
                    flush_group(cur_sp_idx)
                if sp_names:
                    cur_sp_idx = 1 - cur_sp_idx  # alternate between 0 and 1
            if cur_start is None:
                cur_start = seg["start"]
            cur_texts.append(text)
            ends_sentence = text.rstrip().endswith((".", "?", "!", "...", "…"))
            if ends_sentence or len(cur_texts) >= MAX_SEGS_PER_GROUP:
                flush_group(cur_sp_idx)

        flush_group(cur_sp_idx)

        parts = []
        for grp in groups:
            label = _seconds_to_ts(grp["start"])
            url = yt_url(grp["start"])
            ts_link = f'<a href="{url}" target="_blank" class="ts">[{label}]</a>'
            escaped = _html.escape(grp["text"])
            sp_class = f'sp{grp["sp_idx"] + 1}' if grp["speaker"] else ""
            sp_label = (
                f'<span class="spname {sp_class}">{_html.escape(grp["speaker"])}</span> '
                if grp["speaker"] else ""
            )
            parts.append(f'<p class="seg">{sp_label}{ts_link}<br>{escaped}</p>')

        return "\n".join(parts)

    date_str = f"{timestamp[:4]}-{timestamp[4:6]}-{timestamp[6:8]} {timestamp[9:11]}:{timestamp[11:13]}"
    fmt_str = ""
    if fmt and fmt.get("is_multi_speaker"):
        fmt_str = f" | Rozmowa ({fmt['speaker_changes']} zmian mówcy)"

    speakers_html = ""
    if speaker_info:
        sp_parts = []
        for sp in speaker_info:
            name = _html.escape(sp["name"])
            role = _html.escape(sp.get("role", ""))
            sp_parts.append(f"<b>{name}</b>" + (f" ({role})" if role else ""))
        speakers_html = f'<p class="meta">Rozmówcy: {" | ".join(sp_parts)}</p>'

    sections_html_parts = []
    for i, section in enumerate(topic_sections, 1):
        is_ad = section["type"] == "REKLAMA"
        icon = "📢" if is_ad else "💬"
        sec_class = ' class="ad-sec"' if is_ad else ""

        chunk_indices_0 = [c - 1 for c in section["chunk_indices"] if 0 <= c - 1 < len(sections)]
        if chunk_indices_0:
            seg_start = chunk_seg_map[chunk_indices_0[0]][0]
            seg_end = chunk_seg_map[chunk_indices_0[-1]][1]
        else:
            seg_start, seg_end = 0, 0
        sec_segments = segments[seg_start:seg_end] if segments else []

        first_link = ""
        if sec_segments:
            label0 = _seconds_to_ts(sec_segments[0]["start"])
            url0 = yt_url(sec_segments[0]["start"])
            first_link = f' <a href="{url0}" target="_blank" class="ts">[{label0}]</a>'

        summary_html = _html.escape(section["summary"]).replace("\n", "<br>") if section["summary"] else "<em>brak streszczenia</em>"

        sections_html_parts.append(f"""
<div{sec_class}>
<h2>{i}. {icon} {_html.escape(section['title'])}{first_link}</h2>
<table>
<tr><th class="tc">Transkrypcja oryginalna</th><th class="sc-col">Streszczenie</th></tr>
<tr>
<td class="tc">{render_segments(sec_segments)}</td>
<td class="sc-col">{summary_html}</td>
</tr>
</table>
</div>""")

    html = f"""<!DOCTYPE html>
<html lang="pl">
<head>
<meta charset="UTF-8">
<title>{_html.escape(title)}</title>
<style>
body {{ font-family: Arial, sans-serif; max-width: 1400px; margin: 20px auto; padding: 0 20px; color: #222; }}
h1 {{ font-size: 1.2em; border-bottom: 3px solid #c00; padding-bottom: 6px; }}
h2 {{ font-size: 1em; color: #333; margin-top: 36px; margin-bottom: 6px; }}
.meta {{ color: #666; font-size: 0.88em; margin: 4px 0; }}
table {{ width: 100%; border-collapse: collapse; margin-bottom: 10px; font-size: 0.88em; }}
th {{ background: #444; color: #fff; padding: 7px 10px; text-align: left; }}
td {{ vertical-align: top; padding: 9px 11px; border: 1px solid #ddd; }}
.tc {{ width: 58%; line-height: 1.65; }}
.sc-col {{ width: 42%; background: #f8f8f8; line-height: 1.6; }}
.ts {{ color: #c00; text-decoration: none; font-weight: bold; font-size: 0.82em; white-space: nowrap; }}
.ts:hover {{ text-decoration: underline; }}
.sc {{ color: #aaa; }}
.seg {{ margin: 0 0 10px 0; }}
.spname {{ font-size: 0.78em; font-weight: bold; padding: 1px 5px; border-radius: 3px; margin-right: 4px; }}
.sp1 {{ background: #dbeafe; color: #1d4ed8; }}
.sp2 {{ background: #dcfce7; color: #15803d; }}
.ad-sec h2 {{ color: #999; }}
.ad-sec th {{ background: #999; }}
</style>
</head>
<body>
<h1>{_html.escape(title)}</h1>
<p class="meta">ID: {doc_id} | Model: {_html.escape(model)} | Data: {date_str}{fmt_str}</p>
{speakers_html}
{"".join(sections_html_parts)}
</body>
</html>"""

    with open(filename, "w", encoding="utf-8") as f:
        f.write(html)
    return filename


def save_results(doc_id: int, title: str, model: str,
                 toc: str, topic_sections: list[dict], synthesis: str, timestamp: str,
                 fmt: dict | None = None, speaker_info: list[dict] | None = None) -> str:
    exports_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", ".claude", "exports")
    )
    os.makedirs(exports_dir, exist_ok=True)
    filename = os.path.join(exports_dir, f"youtube_analysis_{doc_id}_{timestamp}.md")

    content_count = sum(1 for s in topic_sections if s["type"] == "TEMAT")
    ad_count = sum(1 for s in topic_sections if s["type"] == "REKLAMA")

    with open(filename, "w", encoding="utf-8") as f:
        f.write(f"# Analiza YouTube: {title or f'Dokument {doc_id}'}\n\n")
        f.write(f"**ID**: {doc_id} | **Model**: {model} | **Data**: {timestamp[:4]}-{timestamp[4:6]}-{timestamp[6:8]} {timestamp[9:11]}:{timestamp[11:13]}\n\n")
        f.write(f"**Sekcji merytorycznych**: {content_count} | **Reklam**: {ad_count}\n\n")

        if fmt:
            if fmt["is_multi_speaker"]:
                f.write(f"**Format**: Rozmowa ({fmt['speaker_changes']} zmian mówcy)\n\n")
            else:
                f.write("**Format**: Monolog\n\n")
        if speaker_info:
            f.write("**Rozmówcy**:\n\n")
            for sp in speaker_info:
                role = sp.get("role", "")
                desc = sp.get("description", "")
                line = f"- **{sp['name']}**"
                if role:
                    line += f" ({role})"
                if desc:
                    line += f" — {desc}"
                f.write(line + "\n")
            f.write("\n")

        f.write("---\n\n")

        f.write(toc)
        f.write("\n\n---\n\n")

        if synthesis:
            f.write("## SYNTEZA KOŃCOWA\n\n")
            f.write(synthesis)
            f.write("\n\n---\n\n")

        f.write("## TRANSKRYPCJA TEMATYCZNA\n\n")
        for i, s in enumerate(topic_sections, 1):
            marker = "📢" if s["type"] == "REKLAMA" else "💬"
            chunks_ref = ", ".join(str(c) for c in s["chunk_indices"])
            f.write(f"### {i}. {marker} {s['title']}\n\n")
            f.write(f"*fragmenty źródłowe: {chunks_ref}*\n\n")
            if s["summary"] and s["type"] == "TEMAT":
                f.write(f"**Streszczenie sekcji**: {s['summary']}\n\n")
            if s["text"]:
                f.write(s["text"])
                f.write("\n\n")

    return filename


def save_json(doc_id: int, title: str, model: str,
              sections: list[dict], topic_sections: list[dict],
              synthesis: str, timestamp: str,
              fmt: dict | None = None, speaker_info: list[dict] | None = None) -> str:
    """Save full analysis as JSON for programmatic processing."""
    exports_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", ".claude", "exports")
    )
    os.makedirs(exports_dir, exist_ok=True)
    filename = os.path.join(exports_dir, f"youtube_analysis_{doc_id}_{timestamp}.json")

    import json
    payload = {
        "meta": {
            "doc_id": doc_id,
            "title": title,
            "model": model,
            "timestamp": timestamp,
            "chunk_count": len(sections),
            "content_chunks": sum(1 for s in sections if s["type"] == "TEMAT"),
            "ad_chunks": sum(1 for s in sections if s["type"] == "REKLAMA"),
            "short_chunks": sum(1 for s in sections if s["ratio"] < 80),
            "format": fmt or {"is_multi_speaker": False, "speaker_changes": 0},
            "speakers": speaker_info or [],
        },
        "synthesis": synthesis,
        "topics": [
            {
                "index": i + 1,
                "title": s["title"],
                "type": s["type"],
                "chunk_indices": s["chunk_indices"],
                "summary": s["summary"],
            }
            for i, s in enumerate(topic_sections)
        ],
        "chunks": [
            {
                "index": i + 1,
                "type": s["type"],
                "topic": s["topic"],
                "ratio": s["ratio"],
                "original": s["original"],
                "corrected": s["text"],
                "summary": s["summary"],
            }
            for i, s in enumerate(sections)
        ],
    }

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    return filename


def save_debug(doc_id: int, title: str, model: str, sections: list[dict], timestamp: str) -> str:
    """Save per-chunk debug file: original → rewritten → summary."""
    exports_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", ".claude", "exports")
    )
    os.makedirs(exports_dir, exist_ok=True)
    filename = os.path.join(exports_dir, f"youtube_debug_{doc_id}_{timestamp}.md")

    ok = sum(1 for s in sections if s["ratio"] >= 80)
    short = sum(1 for s in sections if s["ratio"] < 80)

    with open(filename, "w", encoding="utf-8") as f:
        f.write(f"# DEBUG: {title or f'Dokument {doc_id}'}\n\n")
        f.write(f"**Model**: {model} | **Data**: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
        f.write(f"**Chunki**: {len(sections)} | **OK (≥80%)**: {ok} | **Skrócone (<80%)**: {short}\n\n")

        ratio_list = " | ".join(
            f"[{i+1}] {s['ratio']}%{'⚠' if s['ratio'] < 80 else ''}"
            for i, s in enumerate(sections)
        )
        f.write(f"**Ratio**: {ratio_list}\n\n")
        f.write("---\n\n")

        for i, s in enumerate(sections, 1):
            marker = "📢 REKLAMA" if s["type"] == "REKLAMA" else "💬 TEMAT"
            f.write(f"## Chunk {i:>2} — {marker}: {s['topic']}  (ratio: {s['ratio']}%)\n\n")

            f.write(f"### ORYGINAŁ ({len(s['original']):,} znaków)\n\n")
            f.write("```\n")
            f.write(s["original"])
            f.write("\n```\n\n")

            f.write(f"### POPRAWIONY ({len(s['text']):,} znaków)\n\n")
            f.write(s["text"] or "_brak_")
            f.write("\n\n")

            if s["summary"]:
                f.write(f"### STRESZCZENIE\n\n")
                f.write(s["summary"])
                f.write("\n\n")

            f.write("---\n\n")

    return filename


def save_to_db(
    session,
    doc: WebDocument,
    model: str,
    chunk_size: int,
    sections: list[dict],
    topic_sections: list[dict],
    synthesis: str,
    segments: list[dict] | None,
) -> DocumentAnalysisRun:
    """Persist analysis results to DB: one run + N chunks + M topic sections."""
    seg_map = (
        _map_chunks_to_segments([s["original"] for s in sections], segments)
        if segments else [(None, None)] * len(sections)
    )

    run = DocumentAnalysisRun(
        document_id=doc.id,
        model=model,
        chunk_size=chunk_size,
        synthesis=synthesis or None,
    )
    session.add(run)
    session.flush()  # get run.id before adding children

    for i, s in enumerate(sections):
        seg_start, seg_end = seg_map[i]
        session.add(DocumentChunk(
            run_id=run.id,
            document_id=doc.id,
            position=i + 1,
            type=s["type"],
            topic=s["topic"],
            original_text=s["original"],
            corrected_text=s["text"] or None,
            summary=s["summary"] or None,
            seg_start=seg_start,
            seg_end=seg_end,
            rewrite_ratio=s["ratio"],
            status="pending",
        ))

    for i, ts in enumerate(topic_sections):
        session.add(DocumentTopicSection(
            run_id=run.id,
            document_id=doc.id,
            position=i + 1,
            type=ts["type"],
            title=ts["title"] or None,
            summary=ts["summary"] or None,
            chunk_positions=ts["chunk_indices"],
        ))

    session.commit()
    return run


def main():
    parser = argparse.ArgumentParser(
        description="YouTube transcript: correct + segment + summarize (Bielik LLM)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--doc_id", type=int, required=True,
                        help="Document ID in the database")
    parser.add_argument("--model", default="Bielik-11B-v3.0-Instruct",
                        choices=ALL_MODELS,
                        help="Model to use")
    parser.add_argument("--chunk_size", type=int, default=CHUNK_CHARS,
                        help="Characters per chunk (≈1,500 tokens at default 5,000)")
    parser.add_argument("--speaker1", default="",
                        help="Name of first speaker (segments before first >>). "
                             "If omitted, >> markers are not parsed.")
    parser.add_argument("--speaker2", default="",
                        help="Name of second speaker (segments after first >>).")
    parser.add_argument("--no_synthesis", action="store_true",
                        help="Skip final synthesis step")
    parser.add_argument("--dry_run", action="store_true",
                        help="Show chunk breakdown without calling the API")
    args = parser.parse_args()

    load_config()

    print(f"Pobieranie dokumentu {args.doc_id}...")
    session = get_session()
    doc = WebDocument.get_by_id(session, args.doc_id)
    if doc is None:
        print(f"BŁĄD: Dokument {args.doc_id} nie znaleziony.")
        sys.exit(1)

    print(f"Tytuł  : {doc.title}")
    print(f"Typ    : {doc.document_type} | Stan: {doc.document_state}")
    if doc.author:
        print(f"Autor  : {doc.author}")

    video_id = getattr(doc, "original_id", "") or ""
    segments = _load_transcript_segments(getattr(doc, "text_raw", "") or "")
    if segments:
        print(f"Segm.  : {len(segments)} segmentów z timestampami w text_raw")
    else:
        print("Segm.  : brak JSON w text_raw — widok HTML bez linków YT")

    text, text_field = get_text_for_analysis(doc)
    if not text:
        print("BŁĄD: Brak tekstu w polach text / text_raw / text_md.")
        sys.exit(1)
    fmt = detect_format(text)
    speaker_info: list[dict] = []

    if fmt["is_multi_speaker"]:
        print(f"Format : Rozmowa ({fmt['speaker_changes']} zmian mówcy)")
        if args.speaker1 and args.speaker2:
            speaker_info = [
                {"name": args.speaker1, "role": "prowadzący", "description": ""},
                {"name": args.speaker2, "role": "gość", "description": ""},
            ]
        elif not args.dry_run:
            # Sponsor ads typically fill the first ~900 chars; the host intro
            # with speaker names follows immediately after in the same segment.
            # Take chars 800-2400 to reliably capture names without ad noise.
            intro_text = text[800:2400].strip()
            speaker_info = extract_speaker_info(intro_text, args.model)
            if len(speaker_info) >= 2:
                args.speaker1 = speaker_info[0]["name"]
                args.speaker2 = speaker_info[1]["name"]
                print(f"  → [{args.speaker1}] / [{args.speaker2}]")
    else:
        print("Format : Monolog (brak znaczników >>)")

    if args.speaker1 and args.speaker2:
        text = assign_speakers(text, args.speaker1, args.speaker2)
        turns = text.count(f"[{args.speaker1}]:") + text.count(f"[{args.speaker2}]:")
        print(f"Mówcy  : [{args.speaker1}] / [{args.speaker2}] — {turns} wypowiedzi")

    cleaned_text = clean_fillers(text)
    saved = len(text) - len(cleaned_text)
    print(f"Tekst  : pole '{text_field}', {len(text):,} znaków → po usunięciu fillerów: {len(cleaned_text):,} znaków (zaoszczędzono {saved:,})\n")

    chunks = split_text_into_sentence_chunks(cleaned_text, args.chunk_size)
    est_tokens_total = len(chunks) * (args.chunk_size // 3 * 2)  # rough: in+out
    est_cost = est_tokens_total / 1_000_000 * 0.56
    print(f"Podział: {len(chunks)} fragmentów po max {args.chunk_size:,} znaków")
    print(f"Szacowany koszt: ~{est_tokens_total:,} tokenów ≈ {est_cost:.3f} EUR\n")
    for i, ch in enumerate(chunks):
        print(f"  [{i + 1:>2}] {len(ch):>6,} znaków")

    if args.dry_run:
        print("\n[dry_run] Tryb podglądu — API nie zostało wywołane.")
        return

    print(f"\n=== PRZETWARZANIE: {len(chunks)} fragmentów → {args.model} ===\n")
    sections: list[dict] = []
    for i, chunk in enumerate(chunks):
        prev_ctx = _tail(chunks[i - 1]) if i > 0 else ""
        next_ctx = _head(chunks[i + 1]) if i < len(chunks) - 1 else ""
        rewritten = rewrite_chunk(chunk, i + 1, len(chunks), args.model, prev_ctx, next_ctx)
        section_type, topic, corrected_text = parse_rewritten_chunk(rewritten)

        summary = ""
        if section_type == "TEMAT" and corrected_text:
            summary = summarize_chunk(corrected_text, i + 1, len(chunks), args.model)

        ratio = round(len(corrected_text) / len(chunk) * 100) if chunk else 0
        sections.append({
            "type": section_type,
            "topic": topic,
            "original": chunk,
            "text": corrected_text,
            "ratio": ratio,
            "summary": summary,
        })
    print("\n=== GRUPOWANIE TEMATYCZNE ===\n")
    topic_groups = merge_topics(sections, args.model)
    if topic_groups:
        topic_sections = build_topic_sections(sections, topic_groups)
    else:
        topic_sections = [
            {
                "title": s["topic"],
                "type": s["type"],
                "chunk_indices": [i + 1],
                "text": s["text"],
                "summary": s["summary"],
            }
            for i, s in enumerate(sections)
        ]

    toc = build_toc(topic_sections)
    print(f"\n{toc}\n")

    synthesis = ""
    if not args.no_synthesis:
        print("=== SYNTEZA ===\n")
        synthesis = synthesize(topic_sections, doc.title or f"Dokument {args.doc_id}", args.model)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = save_results(
        args.doc_id, doc.title or "", args.model, toc, topic_sections, synthesis, timestamp,
        fmt=fmt, speaker_info=speaker_info,
    )
    json_file = save_json(
        args.doc_id, doc.title or "", args.model, sections, topic_sections, synthesis, timestamp,
        fmt=fmt, speaker_info=speaker_info,
    )
    debug_file = save_debug(args.doc_id, doc.title or "", args.model, sections, timestamp)
    html_file = None
    if segments:
        html_file = save_html(
            args.doc_id, doc.title or "", args.model,
            topic_sections, sections, segments, video_id,
            timestamp, fmt=fmt, speaker_info=speaker_info,
        )
    print("\n=== ZAPIS DO BAZY DANYCH ===\n")
    run = save_to_db(
        session, doc, args.model, args.chunk_size,
        sections, topic_sections, synthesis, segments,
    )
    print(f"  Run ID: {run.id} ({len(sections)} chunków, {len(topic_sections)} sekcji tematycznych)")

    print(f"\n✓ Analiza (MD):  {output_file}")
    print(f"✓ Dane (JSON):   {json_file}")
    print(f"✓ Debug (MD):    {debug_file}")
    if html_file:
        print(f"✓ Widok HTML:    {html_file}")
    print(f"✓ DB Run ID:     {run.id}")


if __name__ == "__main__":
    main()
