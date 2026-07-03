#!/usr/bin/env python3
"""
Batch analysis of long YouTube transcripts using Bielik LLM via CloudFerro Sherlock.

The LLM pipeline (chunk splitting, speaker extraction/labeling, two-pass
rewrite + summarize, topic grouping, synthesis, DB persistence) lives in
library/document_analysis_service.py + library/chunk_llm_analysis.py and is
shared with the Flask API (chunk_review_routes.py). This script is a thin CLI
on top of it, adding:
  - dry-run preview (chunk breakdown + cost estimate, no API calls)
  - explicit --speaker1/--speaker2 override (skips LLM speaker extraction)
  - file exports to .claude/exports/: analysis (MD), data (JSON), debug (MD),
    review view (HTML with YouTube timestamp links)

Cost at 0.56 EUR/M tokens: ~0.05 EUR for a 90K-char transcript
  (19 chunks × ~4,700 tok/chunk = 89K tokens).

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
from library.db.models import WebDocument
from library.chunk_llm_analysis import assign_speakers, remove_speech_fillers
from library.document_analysis_service import (
    CHUNK_CHARS,
    DocumentAnalysisService,
    _extract_text,
    _load_segments,
    _map_chunks_to_segments,
)
from library.text_functions import split_text_into_sentence_chunks


SHERLOCK_MODELS = ["Bielik-11B-v3.0-Instruct"]
ARKLABS_PREFIX = "arklabs/"
ARKLABS_MODELS = [f"{ARKLABS_PREFIX}Bielik-11B-v3.0-Instruct"]
ALL_MODELS = SHERLOCK_MODELS + ARKLABS_MODELS


def _seconds_to_ts(secs: float) -> str:
    """Convert float seconds to HH:MM:SS or MM:SS string."""
    h = int(secs // 3600)
    m = int((secs % 3600) // 60)
    s = int(secs % 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def build_toc(topic_sections: list[dict]) -> str:
    """Build table of contents from logical topic sections."""
    lines = ["## SPIS TREŚCI\n"]
    for i, s in enumerate(topic_sections, 1):
        marker = "📢" if s["type"] == "REKLAMA" else "💬"
        chunks_label = f"  *(fragmenty: {', '.join(str(c) for c in s['chunk_indices'])})*"
        lines.append(f"{i:>2}. {marker} {s['title']}{chunks_label}")
    return "\n".join(lines)


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
                f.write("### STRESZCZENIE\n\n")
                f.write(s["summary"])
                f.write("\n\n")

            f.write("---\n\n")

    return filename


def _sections_from_run(run) -> tuple[list[dict], list[dict]]:
    """Rebuild the export data structures from a persisted DocumentAnalysisRun."""
    chunks_sorted = sorted(run.chunks, key=lambda c: c.position)
    sections = [
        {
            "type": c.type,
            "topic": c.topic or "",
            "original": c.original_text or "",
            "text": c.corrected_text or "",
            "ratio": c.rewrite_ratio if c.rewrite_ratio is not None else 0,
            "summary": c.summary or "",
        }
        for c in chunks_sorted
    ]
    by_pos = {c.position: c for c in chunks_sorted}
    topic_sections = [
        {
            "title": ts.title or "",
            "type": ts.type,
            "chunk_indices": list(ts.chunk_positions or []),
            "text": "\n\n".join(
                by_pos[p].corrected_text
                for p in (ts.chunk_positions or [])
                if p in by_pos and by_pos[p].corrected_text
            ),
            "summary": ts.summary or "",
        }
        for ts in sorted(run.topic_sections, key=lambda t: t.position)
    ]
    return sections, topic_sections


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
                             "If omitted, speakers are auto-extracted via LLM.")
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
    try:
        doc = WebDocument.get_by_id(session, args.doc_id)
        if doc is None:
            print(f"BŁĄD: Dokument {args.doc_id} nie znaleziony.")
            sys.exit(1)

        print(f"Tytuł  : {doc.title}")
        print(f"Typ    : {doc.document_type} | Stan: {doc.document_state}")
        if doc.author:
            print(f"Autor  : {doc.author}")

        video_id = getattr(doc, "original_id", "") or ""
        segments = _load_segments(getattr(doc, "text_raw", "") or "")
        if segments:
            print(f"Segm.  : {len(segments)} segmentów z timestampami w text_raw")
        else:
            print("Segm.  : brak JSON w text_raw — widok HTML bez linków YT")

        text, text_field = _extract_text(doc)
        if not text:
            print("BŁĄD: Brak tekstu w polach text / text_raw / text_md.")
            sys.exit(1)

        speaker_changes = len(re.findall(r">>", text))
        fmt = {"is_multi_speaker": speaker_changes > 0, "speaker_changes": speaker_changes}
        if fmt["is_multi_speaker"]:
            print(f"Format : Rozmowa ({speaker_changes} zmian mówcy)")
        else:
            print("Format : Monolog (brak znaczników >>)")
        print(f"Tekst  : pole '{text_field}', {len(text):,} znaków")

        speakers_override = None
        if args.speaker1 and args.speaker2:
            speakers_override = [
                {"name": args.speaker1, "role": "prowadzący", "description": ""},
                {"name": args.speaker2, "role": "gość", "description": ""},
            ]

        if args.dry_run:
            preview_text = text
            if fmt["is_multi_speaker"] and speakers_override:
                preview_text = assign_speakers(preview_text, args.speaker1, args.speaker2)
            cleaned_text = remove_speech_fillers(preview_text)
            chunks = split_text_into_sentence_chunks(cleaned_text, args.chunk_size)
            est_tokens_total = len(chunks) * (args.chunk_size // 3 * 2)  # rough: in+out
            est_cost = est_tokens_total / 1_000_000 * 0.56
            print(f"\nPodział: {len(chunks)} fragmentów po max {args.chunk_size:,} znaków")
            print(f"Szacowany koszt: ~{est_tokens_total:,} tokenów ≈ {est_cost:.3f} EUR\n")
            for i, ch in enumerate(chunks):
                print(f"  [{i + 1:>2}] {len(ch):>6,} znaków")
            print("\n[dry_run] Tryb podglądu — API nie zostało wywołane.")
            return

        print(f"\n=== PRZETWARZANIE → {args.model} (DocumentAnalysisService) ===\n")
        service = DocumentAnalysisService(session)
        run = service.create_run(
            doc_id=args.doc_id,
            model=args.model,
            chunk_size=args.chunk_size,
            no_synthesis=args.no_synthesis,
            progress_fn=lambda msg: print(f"  {msg}", flush=True),
            speakers=speakers_override,
        )

        sections, topic_sections = _sections_from_run(run)
        synthesis = run.synthesis or ""
        speaker_info = run.speakers or []
        run_id = run.id

        toc = build_toc(topic_sections)
        print(f"\n{toc}\n")

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
    finally:
        session.close()

    print(f"\n✓ Analiza (MD):  {output_file}")
    print(f"✓ Dane (JSON):   {json_file}")
    print(f"✓ Debug (MD):    {debug_file}")
    if html_file:
        print(f"✓ Widok HTML:    {html_file}")
    print(f"✓ DB Run ID:     {run_id}")


if __name__ == "__main__":
    main()
