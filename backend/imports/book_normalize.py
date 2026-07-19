# -*- coding: utf-8 -*-
"""Normalize OCR-ed book markdown so detect_chapters() yields a clean chapter list.

Mistral OCR output for scanned books has inconsistent heading levels (real chapters
appear randomly as H1/H2/bare lines), running heads (chapter title in ALL CAPS on
every page), standalone page numbers, and occasionally duplicated page ranges.
This tool rewrites the markdown according to a per-book JSON map:

    {
      "remove_blocks": [
        {"name": "toc", "start": "# Spis treści", "end_before": "GOSPODARCZA GONITWA",
         "start_occurrence": 1, "max_chars": 12000}
      ],
      "chapters": [
        {"title": "Wprowadzenie"},
        {"title": "Energia — Atom", "anchor": "Atom"}
      ],
      "running_heads": ["Spis treści", "Polska – potencjał i słabości"]
    }

Each chapter anchor is matched sequentially (first bare line or markdown heading
after the previous chapter) and rewritten to an H1 with the map's title. All other
H1 headings are demoted to H2. Standalone page numbers and ALL-CAPS running-head
lines (fuzzy-matched against chapter titles + running_heads) are dropped.

Usage:
    python imports/book_normalize.py --map imports/book_maps/polska_do_potegi.json \
        --input book.md --output book_norm.md
    python imports/book_normalize.py --map ... --doc-id 9204            # dry run (stats only)
    python imports/book_normalize.py --map ... --doc-id 9204 --write-db # update text_md
"""

import argparse
import json
import re
import sys
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_PAGE_NUMBER_RE = re.compile(r"^\d{1,4}$")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_RUNNING_HEAD_RATIO = 0.8


def norm_title(s: str) -> str:
    """Normalize a line/title for comparison: NFC, casefold, unify dashes/quotes/dots."""
    s = unicodedata.normalize("NFC", s).strip()
    s = re.sub(r"^#{1,6}\s+", "", s).rstrip("#").strip()
    s = s.replace("–", "-").replace("—", "-").replace("…", "...")
    s = s.replace("„", '"').replace("”", '"').replace("“", '"')
    s = re.sub(r"[\s\-]+", " ", s)
    return s.casefold()


def _find_line(lines: list[str], phrase: str, start_idx: int, occurrence: int = 1) -> int:
    """Index of the n-th line at/after start_idx whose stripped text starts with phrase."""
    seen = 0
    for i in range(start_idx, len(lines)):
        if lines[i].strip().startswith(phrase):
            seen += 1
            if seen == occurrence:
                return i
    raise ValueError(f"phrase not found (occurrence {occurrence}): {phrase[:60]!r}")


def remove_blocks(text: str, blocks: list[dict]) -> tuple[str, list[str]]:
    """Remove configured line ranges. Returns (text, log messages)."""
    log = []
    for blk in blocks:
        lines = text.split("\n")
        start = _find_line(lines, blk["start"], 0, blk.get("start_occurrence", 1))
        end = _find_line(lines, blk["end_before"], start + 1)
        removed = "\n".join(lines[start:end])
        max_chars = blk.get("max_chars", 12000)
        if len(removed) > max_chars:
            raise ValueError(
                f"block {blk.get('name', '?')}: removing {len(removed)} chars exceeds max_chars={max_chars}"
            )
        log.append(
            f"removed block {blk.get('name', '?')}: lines {start + 1}..{end}, {len(removed)} chars; "
            f"head={removed[:60]!r}"
        )
        text = "\n".join(lines[:start] + lines[end:])
    return text, log


def _is_running_head(line: str, known_norms: list[str]) -> bool:
    """True for a bare ALL-CAPS line that (fuzzy-)matches a known chapter/part title."""
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or any(c.islower() for c in stripped):
        return False
    if not any(c.isalpha() for c in stripped):
        return False
    n = norm_title(stripped)
    for known in known_norms:
        if n == known or SequenceMatcher(None, n, known).ratio() >= _RUNNING_HEAD_RATIO:
            return True
    return False


_PARA_BREAK_END = re.compile(r"[a-ząćęłńóśźż0-9,;–—-]$")
_PARA_BREAK_START = re.compile(r"^[a-ząćęłńóśźż]")


def join_broken_paragraphs(text: str) -> tuple[str, int]:
    """Rejoin paragraphs split by a removed page break (running head / page number).

    A paragraph continues across the gap when the previous long line ends
    mid-sentence (lowercase letter, comma, dash) and the next line starts with
    a lowercase letter. Headings, list items, footnotes and images never join.
    """
    paragraphs = re.split(r"\n\s*\n", text)
    out: list[str] = []
    joined = 0
    for para in paragraphs:
        if (
            out
            and len(out[-1]) > 80
            and not out[-1].lstrip().startswith(("#", "-", "!", "|"))
            and _PARA_BREAK_END.search(out[-1])
            and _PARA_BREAK_START.match(para)
        ):
            out[-1] = out[-1] + " " + para
            joined += 1
        else:
            out.append(para)
    return "\n\n".join(out), joined


def normalize_book(text: str, book_map: dict) -> tuple[str, list[str]]:
    """Apply the full normalization pipeline. Returns (normalized text, log)."""
    text = text.replace("\r\n", "\n")
    text, log = remove_blocks(text, book_map.get("remove_blocks", []))

    chapters = book_map["chapters"]
    anchors = [(ch["title"], norm_title(ch.get("anchor", ch["title"]))) for ch in chapters]
    known_norms = [norm_title(ch["title"]) for ch in chapters]
    known_norms += [norm_title(a) for _, a in [(c["title"], c.get("anchor", c["title"])) for c in chapters]]
    known_norms += [norm_title(t) for t in book_map.get("running_heads", [])]
    known_norms = sorted(set(known_norms))

    out: list[str] = []
    next_anchor = 0
    dropped_pages = dropped_heads = demoted = 0
    for line in text.split("\n"):
        stripped = line.strip()
        if next_anchor < len(anchors) and stripped and norm_title(stripped) == anchors[next_anchor][1]:
            out.append(f"# {anchors[next_anchor][0]}")
            log.append(f"chapter {next_anchor + 1}: {anchors[next_anchor][0]!r} <- {stripped[:60]!r}")
            next_anchor += 1
            continue
        if _PAGE_NUMBER_RE.match(stripped):
            dropped_pages += 1
            continue
        if _is_running_head(line, known_norms):
            dropped_heads += 1
            continue
        m = _HEADING_RE.match(stripped)
        if m and len(m.group(1)) == 1:
            out.append(f"## {m.group(2)}")
            demoted += 1
            continue
        out.append(line)

    if next_anchor < len(anchors):
        missing = [t for t, _ in anchors[next_anchor:]]
        raise ValueError(f"{len(missing)} chapter anchors not found: {missing[:5]}")

    result = re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip() + "\n"
    joined = 0
    if book_map.get("join_broken_paragraphs", True):
        result, joined = join_broken_paragraphs(result)
    log.append(
        f"dropped {dropped_pages} page numbers, {dropped_heads} running heads; "
        f"demoted {demoted} H1 headings; joined {joined} broken paragraphs; "
        f"{len(anchors)} chapters anchored"
    )
    return result, log


def _print_chapter_stats(text: str) -> None:
    from library.text_functions import detect_chapters

    chapters = detect_chapters(text)
    print(f"\ndetect_chapters: {len(chapters)} chapters")
    for ch in chapters:
        print(f"  {ch['position']:3d}. {ch['title'][:70]:70s} {ch['length']:>8,} chars")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--map", required=True, help="book map JSON path")
    parser.add_argument("--input", help="input markdown file (alternative to --doc-id)")
    parser.add_argument("--output", help="output markdown file (with --input)")
    parser.add_argument("--doc-id", type=int, help="documents.id to read text_md from")
    parser.add_argument("--write-db", action="store_true", help="update text_md in DB (with --doc-id)")
    args = parser.parse_args()

    book_map = json.loads(Path(args.map).read_text(encoding="utf-8"))

    if args.input:
        text = Path(args.input).read_text(encoding="utf-8-sig")
        normalized, log = normalize_book(text, book_map)
        for msg in log:
            print(msg)
        if args.output:
            Path(args.output).write_text(normalized, encoding="utf-8")
            print(f"\nwritten {len(normalized):,} chars -> {args.output}")
        _print_chapter_stats(normalized)
        return

    if not args.doc_id:
        parser.error("either --input or --doc-id is required")

    from library.db.engine import get_session
    from library.db.models import Document

    session = get_session()
    try:
        doc = session.get(Document, args.doc_id)
        if doc is None or not doc.text_md:
            raise SystemExit(f"document {args.doc_id} not found or has empty text_md")
        normalized, log = normalize_book(doc.text_md, book_map)
        for msg in log:
            print(msg)
        print(f"\ntext_md: {len(doc.text_md):,} -> {len(normalized):,} chars")
        _print_chapter_stats(normalized)
        if args.write_db:
            doc.text_md = normalized
            session.commit()
            print(f"document {args.doc_id}: text_md updated in DB")
        else:
            print("dry run — pass --write-db to persist")
    finally:
        session.close()


if __name__ == "__main__":
    main()
