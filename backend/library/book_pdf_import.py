"""Import a book PDF (with a usable text layer, see imports/check_pdf_text_layer.py)
into a Document with chapter-aware markdown.

Pure functions operate on bytes/text only — no local filesystem assumptions
beyond receiving the PDF as bytes. This keeps the pipeline portable: the same
`import_pdf_book()` call works whether the bytes come from a local file (today,
via imports/book_import_pdf_<slug>.py, one per book) or a future ObjectStorage.get_bytes()/job-queue
materialize() step (docs/deployment/nas/storage-and-jobs-migration-plan.md) —
only the caller that supplies the bytes changes, not this module.

Extraction uses PyMuPDF (fitz)'s plain per-page get_text() rather than pypdf:
it marks a genuine line-wrap hyphenation with an explicit U+00AD soft hyphen
(100% reliable dehyphenation, vs. guessing from a stray hyphen+space) and
correctly separates visually-stacked text elements that pypdf sometimes runs
together with no newline at all. PyMuPDF's "blocks" mode was also evaluated —
it nicely groups whole flowing paragraphs for plain prose, but was dropped
because it silently swallows repeated running-head occurrences (needed for
canonical chapter-title selection below) on some PDFs. See
docs/pdf-library-comparison.md for the full pypdf/pdfplumber/PyMuPDF comparison
(NOTE: PyMuPDF is AGPL-3.0/commercial-licensed — fine for this self-hosted,
non-SaaS use, but must be re-evaluated before any hosted/SaaS offering).

Chapter detection is heuristic and regex-driven per book (no universal PDF
chapter format exists) — the default pattern matches the "// ROZDZIAŁ NNN //"
running-head style used by Sekurak books. Pass --chapter-regex for other
layouts. The output markdown must satisfy library.text_functions.detect_chapters()
(H1/H2 headers), so chapter titles are emitted as "## <title>".
"""

from __future__ import annotations

import difflib
import logging
import re
import uuid
from collections import Counter
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from library.config_loader import load_config
from library.db.models import Document
from library.document_service import DocumentService
from library.storage import storage_from_config

logger = logging.getLogger(__name__)

DEFAULT_CHAPTER_REGEX = r"(?i)//\s*ROZDZIA[ŁL]\s*(\d+)\s*//"
_PAGE_NUMBER_LINE_RE = re.compile(r"(?m)^\s*\d{1,4}\s*$\n?")
# The "Spis tabel" back-matter page's dot-leader fill character (title ... N)
# uses a font encoding PyMuPDF can't map to a real codepoint at all — it comes
# out as genuine U+FFFD REPLACEMENT CHARACTER runs (confirmed: nowhere else in
# this book, ~4000 occurrences on that one page alone), not something any
# amount of post-processing can recover the "real" glyph for. Purely
# decorative filler either way, so it's dropped rather than shown as garbage.
_REPLACEMENT_CHAR_RUN_RE = re.compile(r"\s*�+")
# Stray C0 control characters PyMuPDF occasionally decodes a broken/custom
# glyph into instead of U+FFFD or the intended character — seen in this book
# as a BACKSPACE (U+0008) tacked onto "Spis tabel" entries (renders as a
# visible box in some browsers instead of vanishing) and a single SOH
# (U+0001) standing in for one bullet icon glyph that failed to decode. Never
# meaningful content, so dropped outright; \t/\n/\r are the only C0 codes
# this book's markdown actually uses.
_STRAY_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_BULLET_RE = re.compile(r"^\s*[▶▷•‣]|^\s*\d+[.)]\s")
_SENTENCE_END_RE = re.compile(r"[.!?”\"»]\s*$")
# Shell/config code samples in technical books often have lines like "# comment"
# or "## section" — library.text_functions.detect_chapters() treats ANY
# 1-2-hash line as a markdown H1/H2 header, so these must be neutralized before
# our own "## <title>" markers are inserted, or they swamp the real chapter count.
_LEADING_HASH_RE = re.compile(r"(?m)^(#{1,2})(?=\s)")
# Book-specific defaults for detect_heading_texts()/import_pdf_book() — tuned to
# "Twierdza Linux" (imports/book_import_pdf_twierdza_linux.py): its subheadings
# render in a distinct "display" font family at a size clearly above body text
# (body is NotoSerif @ 8.5pt; the chapter running-head title also uses
# BarlowCondensed but at 11pt/Regular weight, below this threshold, so it's
# excluded without extra bookkeeping). There's no universal PDF signal for
# "this line is a subheading" — a book with different subheading styling
# should pass its own heading_font_prefix/heading_min_size instead of relying
# on these defaults.
_HEADING_FONT_PREFIX = "BarlowCondensed"
_HEADING_MIN_SIZE = 12.0

# Thresholds separating real illustrations from decorative furniture (running-head
# logos, bullet icons, page masks). Like _HEADING_*, these may need retuning for
# a different book.
_IMAGE_MIN_PIXELS = 100  # applies to each dimension
_IMAGE_MIN_BYTES = 5 * 1024
_CAPTION_RE = re.compile(r"(?m)^\s*((?:Rysunek|Rys\.|Ilustracja|Tabela|Zdj\.)\s*\d+[.:].*)$")
_TABLE_CAPTION_RE = re.compile(r"(?m)^Tabela\s+(\d+)\.\s")
CONTENT_TYPE_BY_EXT = {"png": "image/png", "jpeg": "image/jpeg", "jpg": "image/jpeg"}

# Inline styling (apply_inline_styles()) — font-name signals for "Twierdza Linux"'s
# own documented typographic conventions (its "Konwencje stosowane w książce"
# section): monotype for commands/paths/terminal dumps, italic for foreign words
# and mechanism names. Font-name prefixes/substrings only — a different book's
# per-book script should pass its own.
_MONOSPACE_FONT_PREFIXES = ("consolas", "mplus-1m")
_ITALIC_FONT_NEEDLE = "ital"

# Callout boxes ("Konwencje..." documents two: green info / red warning) are
# rendered in the PDF as a colored graphic with no text-layer signal of its
# own — but each is preceded by a standalone icon glyph line that DOES survive
# plain text extraction: a real Unicode char for the green box, a private-use-area
# glyph from the book's icon font for the red one (not portable/renderable
# outside that font — used only as a detection signal, never rendered itself).
_INFO_ICON = "ℹ"
_WARNING_ICON = ""

# Front/back-matter "part" sections (Od Autora, Wstęp, Słownik pojęć, ...) get a
# big standalone opening-page title, same tier as a numbered chapter's but with
# no "// ROZDZIAŁ N //"-style marker to regex-match — detect_named_sections()
# instead matches by exact font/size + an explicit per-book title allowlist.
# Two tiers observed in this book: an ALL-CAPS "eyebrow" (own running head,
# e.g. "OD AUTORA") and/or a title-case opening title with no separate eyebrow
# (e.g. "Podziękowania") — a section may have either or both.
_SECTION_EYEBROW_FONT = "ChakraPetch-Bold"
_SECTION_EYEBROW_SIZE = 18.0
_SECTION_TITLE_FONT = "ChakraPetch-Regular"
_SECTION_TITLE_SIZE = 16.0


def _escape_leading_hashes(text: str) -> str:
    return _LEADING_HASH_RE.sub(lambda m: "\\" + m.group(1), text)


def detect_heading_texts(
    pdf_bytes: bytes, font_prefix: str = _HEADING_FONT_PREFIX, min_size: float = _HEADING_MIN_SIZE,
) -> set[str]:
    """Collect the exact text of lines styled as book subheadings, using
    PyMuPDF's per-span font metadata (name + size) — plain text extraction
    throws this away, so a subheading like "Nazewnictwo w książce" otherwise
    blends into the surrounding paragraph text with no visual distinction.
    A line counts only when EVERY span on it matches the heading style, so a
    bolded word inside an ordinary sentence (same font family/size as body
    text, just a different weight) is never mistaken for a heading.

    font_prefix/min_size default to the Sekurak-style "Twierdza Linux" book
    this module was built against — there is no universal PDF signal for
    "this line is a subheading", so a different book's per-book import script
    (imports/book_import_pdf_<slug>.py) should pass its own tuned values.
    """
    import fitz

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    headings: set[str] = set()
    for page in doc:
        for block in page.get_text("dict")["blocks"]:
            if block.get("type") != 0:
                continue
            for line in block["lines"]:
                spans = [s for s in line["spans"] if s["text"].strip()]
                if not spans:
                    continue
                if all(
                    s["font"].startswith(font_prefix) and s["size"] >= min_size
                    for s in spans
                ):
                    text = "".join(s["text"] for s in spans).strip()
                    if text:
                        headings.add(text)
    return headings


def detect_named_sections(
    pdf_bytes: bytes,
    eyebrow_titles: dict[str, str],
    title_titles: dict[str, str],
    eyebrow_font: str = _SECTION_EYEBROW_FONT,
    eyebrow_size: float = _SECTION_EYEBROW_SIZE,
    title_font: str = _SECTION_TITLE_FONT,
    title_size: float = _SECTION_TITLE_SIZE,
) -> dict[int, list[tuple[str, str]]]:
    """Locate front/back-matter "part" section openers (Od Autora, Wstęp,
    Słownik pojęć, ...) that get the same big standalone-title-page treatment
    as a numbered chapter but have no "// ROZDZIAŁ N //"-style marker to
    regex-match. Two font/size tiers are checked (a section may use either):
    an ALL-CAPS "eyebrow" running head (eyebrow_titles, keyed by that exact
    ALL-CAPS text) and/or a title-case opening title with no separate eyebrow
    (title_titles, keyed by that exact text). Both dicts map the exact text as
    it appears in the PDF to the canonical title to use as the "## " header —
    an explicit allowlist, not "any line in this font/size", since numbered
    chapters and the printed "SPIS TREŚCI" page itself also use this tier and
    must NOT become extra chapters.

    Returns {page_index: [(source_text, canonical_title), ...]} in reading
    order per page — build_book_markdown() locates source_text within that
    page's own extracted text and splices in "## canonical_title" there.
    """
    import fitz

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    found: dict[int, list[tuple[str, str]]] = {}
    for page_idx, page in enumerate(doc):
        for block in page.get_text("dict")["blocks"]:
            if block.get("type") != 0:
                continue
            for line in block["lines"]:
                spans = [s for s in line["spans"] if s["text"].strip()]
                if not spans:
                    continue
                text = "".join(s["text"] for s in spans).strip()
                canonical = None
                if text in eyebrow_titles and all(
                    s["font"] == eyebrow_font and abs(s["size"] - eyebrow_size) < 0.5 for s in spans
                ):
                    canonical = eyebrow_titles[text]
                elif text in title_titles and all(
                    s["font"] == title_font and abs(s["size"] - title_size) < 0.5 for s in spans
                ):
                    canonical = title_titles[text]
                if canonical:
                    found.setdefault(page_idx, []).append((text, canonical))
    return found


def _word_style(font: str, monospace_prefixes: tuple[str, ...], italic_needle: str) -> str | None:
    font_lower = font.lower()
    if font_lower.startswith(monospace_prefixes):
        return "mono"
    if italic_needle in font_lower:
        return "ital"
    return None


_INLINE_MARKER = {"mono": "`", "ital": "*"}


def apply_inline_styles(
    pdf_bytes: bytes,
    pages: list[str],
    monospace_font_prefixes: tuple[str, ...] = _MONOSPACE_FONT_PREFIXES,
    italic_font_needle: str = _ITALIC_FONT_NEEDLE,
) -> list[str]:
    """Wrap monospace runs in backticks and italic runs in asterisks, per this
    book's own documented typographic conventions ("Konwencje stosowane w
    książce": monotype for commands/paths/terminal dumps, italic for foreign
    words and mechanism names) — font name only, see _MONOSPACE_FONT_PREFIXES/
    _ITALIC_FONT_NEEDLE.

    PyMuPDF's per-span dict-mode text can silently drop trailing punctuation
    that plain get_text() keeps (observed: an italic word immediately
    followed by a period lost the period entirely in dict-mode spans) — so
    this never rebuilds page text from spans. Instead it takes page.get_text()
    (or, if the page's text already differs from that — e.g. a table region
    already replaced by insert_page_tables() — whatever `pages[i]` currently
    is) as the one ground truth, aligns its whitespace-delimited tokens
    against page.get_text("words") (same content, independently tokenized) via
    difflib, and only wraps runs the alignment is confident about. Unmatched
    regions (word reordering — seen on multi-column donor-name-list pages —
    or content already replaced by an earlier pipeline step) are left exactly
    as they were: this can only omit styling, never corrupt or lose text.
    """
    import fitz

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    out: list[str] = []
    for page_idx, page in enumerate(doc):
        current = pages[page_idx] if page_idx < len(pages) else page.get_text()
        tokens = [(m.start(), m.end(), m.group()) for m in re.finditer(r"\S+", current)]
        if not tokens:
            out.append(current)
            continue

        spans: list[tuple[tuple[float, float, float, float], str]] = []
        for block in page.get_text("dict")["blocks"]:
            if block.get("type") != 0:
                continue
            for line in block["lines"]:
                for s in line["spans"]:
                    spans.append((s["bbox"], s["font"]))

        styled_words: list[tuple[str, str | None]] = []
        for x0, y0, x1, y1, text, *_rest in page.get_text("words"):
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            style = None
            for (bx0, by0, bx1, by1), font in spans:
                if bx0 - 1 <= cx <= bx1 + 1 and by0 - 1 <= cy <= by1 + 1:
                    style = _word_style(font, monospace_font_prefixes, italic_font_needle)
                    break
            styled_words.append((text, style))

        matcher = difflib.SequenceMatcher(
            None, [t[2] for t in tokens], [w[0] for w in styled_words], autojunk=False,
        )
        token_style: dict[int, str] = {}
        for block in matcher.get_matching_blocks():
            for k in range(block.size):
                style = styled_words[block.b + k][1]
                if style:
                    token_style[block.a + k] = style

        runs: list[tuple[int, int, str]] = []
        run_style: str | None = None
        run_start = run_end = 0
        for i, (start, end, _word) in enumerate(tokens):
            style = token_style.get(i)
            if style == run_style and style is not None:
                run_end = end
            else:
                if run_style is not None:
                    runs.append((run_start, run_end, run_style))
                run_style = style
                run_start, run_end = (start, end) if style else (0, 0)
        if run_style is not None:
            runs.append((run_start, run_end, run_style))

        parts: list[str] = []
        cursor = 0
        for start, end, style in runs:
            marker = _INLINE_MARKER[style]
            parts.append(current[cursor:start])
            parts.append(f"{marker}{current[start:end]}{marker}")
            cursor = end
        parts.append(current[cursor:])
        out.append("".join(parts))
    return out


def _table_to_markdown(rows: list[list[str | None]]) -> str | None:
    """Render a find_tables() row grid as a markdown table. None/blank first
    row cells become an empty header cell; a completely empty table (header
    only, no data rows, or a header with no non-blank cell) is not a real
    table — return None so the caller falls back to leaving the raw text."""
    if len(rows) < 2:
        return None
    cleaned = [[(cell or "").replace("\n", " ").strip().replace("|", "\\|") for cell in row] for row in rows]
    if not any(cell for cell in cleaned[0]):
        return None
    width = max(len(row) for row in cleaned)
    cleaned = [row + [""] * (width - len(row)) for row in cleaned]
    lines = [
        "| " + " | ".join(cleaned[0]) + " |",
        "| " + " | ".join(["---"] * width) + " |",
    ]
    for row in cleaned[1:]:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def insert_page_tables(pdf_bytes: bytes, pages: list[str]) -> list[str]:
    """Replace each page's flattened table text with a real markdown table.

    PyMuPDF's plain get_text() reads a table's cells in visual flow order with
    no row/column delimiters at all — unreadable (header cells and data cells
    of a multi-column table run together as if they were prose). find_tables()
    gives real grid structure instead; page.get_text(clip=table.bbox) is used
    to find exactly which slice of the page's own already-extracted text the
    table occupies, so the (single, in-place) replacement can't drift out of
    sync with whatever pipeline stage produced `pages` (this runs before
    apply_inline_styles(), against the plain extract_pages() output).

    A table split across a page boundary (a repeated header row on the next
    page, common in this book) is NOT merged — each page's fragment becomes
    its own markdown table, the continuation repeating its header. Still a
    large readability improvement over the fully flattened original; merging
    is a possible future refinement, not attempted here.
    """
    import fitz

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    out: list[str] = []
    for page_idx, page in enumerate(doc):
        current = pages[page_idx] if page_idx < len(pages) else page.get_text()
        for table in page.find_tables().tables:
            rows = table.extract()
            markdown = _table_to_markdown(rows)
            if markdown is None:
                continue
            clip_text = page.get_text(clip=table.bbox).strip()
            if not clip_text or clip_text not in current:
                continue
            current = current.replace(clip_text, markdown, 1)
        out.append(current)
    return out


def _link_table_captions(text: str) -> str:
    """Give each "Tabela N. <title>" caption a #tabela-N anchor at its real
    occurrence (the one immediately followed by a markdown table, from
    insert_page_tables()) and turn every other occurrence of that same
    caption text — in practice, the "Spis tabel" back-matter index, which
    lists the identical caption with no table underneath — into a link to
    that anchor. The link only encodes the anchor id, not a chapter position:
    chapter numbering is computed fresh by detect_chapters() on every read
    (GET /document/<id>/chapters), not fixed at import time, so the reader
    resolves anchor -> chapter position at click time via
    GET /document/<id>/anchor/<anchor_id> instead of trusting a number baked
    in here. A table find_tables() failed to detect keeps its plain
    unlinked caption text everywhere (nothing to jump to).
    """
    lines = text.split("\n")
    real_occurrence_line: dict[str, int] = {}
    for i, line in enumerate(lines):
        match = _TABLE_CAPTION_RE.match(line)
        if not match or match.group(1) in real_occurrence_line:
            continue
        next_nonblank = next((ln for ln in lines[i + 1:i + 3] if ln.strip()), "")
        if next_nonblank.startswith("|"):
            real_occurrence_line[match.group(1)] = i

    out: list[str] = []
    for i, line in enumerate(lines):
        match = _TABLE_CAPTION_RE.match(line)
        number = match.group(1) if match else None
        if number is None or number not in real_occurrence_line:
            out.append(line)
        elif real_occurrence_line[number] == i:
            out.extend([f"[#tabela-{number}]", "", f"**{line}**", ""])
        else:
            out.append(f"[{line}](anchor:tabela-{number})")
    return "\n".join(out)


_HEADER_LINE_RE = re.compile(r"(?m)^(#{2,3}) (.+)$")
# A printed book's own "SPIS TREŚCI" page — extracted as plain prose — renders
# each entry as "Title . . . . . . . . 19" (a dot-leader fill to the page
# number). 4+ repeated ". "/".  " groups is a strong, specific signal: normal
# prose never runs that many dots in a row, so this can't misfire on an
# ordinary sentence or ellipsis. `.*?` is non-greedy so it stops at the
# FIRST run long enough to qualify, rather than swallowing a shorter one
# inside a longer title.
_TOC_ENTRY_RE = re.compile(r"(?m)^(?P<title>\S.*?)\s+(?:\.\s?){4,}(?P<page>\d{1,4})[ \t]*$")
_TOC_CHAPTER_NUM_RE = re.compile(r"^\d+\.\s+")
# The printed TOC page's own eyebrow line — plain text, deliberately never
# itself turned into a "## " header (see detect_named_sections()'s docstring:
# the SPIS TREŚCI page must not become an extra chapter). Bounds _toc_region()
# below.
_TOC_HEADING_RE = re.compile(r"(?im)^\s*spis\s+tre[śs]ci\s*$")
_TOC_ALREADY_LINKED_RE = re.compile(r"^\[(?P<label>[^\]]+)\]\(anchor:toc-\d+\)$")
# Detects an anchor a PREVIOUS link_toc_entries() run already placed right
# before a header, so a re-run reuses it instead of stacking a duplicate.
_TOC_ANCHOR_TAIL_RE = re.compile(r"\[#(toc-\d+)\]\s*$")


def _normalize_toc_title(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _toc_title_candidates(raw_title: str) -> list[str]:
    """Plausible normalized forms of a TOC entry's captured title, to look up
    against real header text. Two independent, book-observed quirks stack
    on top of "N. " chapter numbering: some front-matter entries print an
    extra "." right where the dot leader begins even though the real header
    has none (e.g. "Podziękowania." in the TOC vs "## Podziękowania"), so
    each variant is tried both with and without its own trailing period.
    """
    variants = [raw_title, _TOC_CHAPTER_NUM_RE.sub("", raw_title)]
    candidates: list[str] = []
    for variant in variants:
        variant = variant.strip()
        candidates.append(_normalize_toc_title(variant))
        if variant.endswith(".") and not variant.endswith(".."):
            candidates.append(_normalize_toc_title(variant[:-1]))
    return candidates


def _toc_region(text: str) -> tuple[int, int] | None:
    """Span of the book's own printed table-of-contents page(s): from its
    "SPIS TREŚCI" eyebrow line to the first real "## " header that follows
    it. None when no such eyebrow line exists — a book with a different (or
    no) printed TOC convention, or plain text that predates this feature
    entirely; callers fall back to scanning the whole document instead.
    """
    heading_match = _TOC_HEADING_RE.search(text)
    if not heading_match:
        return None
    rest = text[heading_match.end():]
    next_header = re.search(r"(?m)^## ", rest)
    end = heading_match.end() + (next_header.start() if next_header else len(rest))
    return heading_match.end(), end


def _toc_entry_titles(text: str) -> list[str]:
    """Every TOC entry's title text, whichever shape it currently has: a raw
    dot-leader line ("Tytuł . . . . 19", a fresh import this function hasn't
    processed yet — matched anywhere, since that exact shape doesn't occur
    outside a printed TOC page) or an already-processed block from an
    earlier link_toc_entries() run, either "[Label](anchor:toc-N)" (already
    linked) or a bare single-line paragraph (left unmatched last time — only
    read within _toc_region(), since a bare short paragraph isn't a reliable
    "this is a title" signal anywhere else in the book). This dual reading is
    what lets link_toc_entries() re-run on a document it has already
    processed and still recover anything a previous run left unmatched.
    """
    titles = [m.group("title").strip() for m in _TOC_ENTRY_RE.finditer(text)]
    region = _toc_region(text)
    if region:
        start, end = region
        for block in text[start:end].split("\n\n"):
            block = block.strip()
            if not block or "\n" in block or block.startswith("#") or block.startswith("[#"):
                continue
            link_match = _TOC_ALREADY_LINKED_RE.match(block)
            titles.append(link_match.group("label") if link_match else block)
    return titles


def _toc_derived_subheading_titles(text: str, known_titles: set[str]) -> set[str]:
    """Subheading titles the book's own printed TOC claims exist but that
    aren't already a real "## "/"### " header (known_titles — every existing
    header's normalized text, so real chapters/sections are never
    mistaken for a missing subheading). The PDF's font-based
    detect_heading_texts() only catches a subheading when its every span
    matches a specific font/size — real books have exceptions (a subheading
    set in a slightly different weight/size, e.g.) that font detection alone
    misses but the book's own table of contents still lists correctly. Only
    the fully-cleaned candidate ("N. " prefix and a lone trailing "."
    stripped, see _toc_title_candidates()) is proposed — the caller
    (_mark_headings(), via link_toc_entries()) still requires that exact
    text to recur as a standalone body line before promoting it to a real
    header, so a false-positive TOC read can at worst fail to match
    anything, never invent a heading out of nothing.
    """
    candidates: set[str] = set()
    for raw_title in _toc_entry_titles(text):
        variants = _toc_title_candidates(raw_title)
        if any(v in known_titles for v in variants):
            continue
        candidates.add(variants[-1])
    return candidates


def link_toc_entries(text: str) -> str:
    """Turn the book's own printed "SPIS TREŚCI" page — extracted as one
    dot-leader-filled prose line per entry ("Tytuł . . . . . . 19"), which
    reads as an unbroken wall of text once paragraph-joined for the reader —
    into one entry per line, clickable wherever its title exactly matches a
    real "## "/"### " header elsewhere in the book.

    Before anything else, the TOC's own entries are used to recover
    subheadings detect_heading_texts()'s font/size heuristic missed (see
    _toc_derived_subheading_titles()) — a real subheading the book's own
    contents page lists, but that never got its "### " marker at import
    time, could otherwise never be linked at all. This also means
    link_toc_entries() alone (no PDF/font info needed) can improve an
    already-imported book's heading coverage — see imports/book_relink_toc.py.
    Safe to call again on text a previous run already processed: an entry
    already turned into a link isn't a missing subheading (its title is
    already a real header — see _toc_derived_subheading_titles()'s
    known_titles check), and _toc_entry_titles() reads an unmatched entry's
    plain-paragraph form the same way it reads a fresh dot-leader line, so a
    second run can still recover something the first one didn't.

    Every "## "/"### " header (including ones just recovered above) gets a
    unique "[#toc-N]" anchor placed right before it (harmless — an invisible
    marker, same mechanism as _link_table_captions()'s "[#tabela-N]"). Each
    dot-leader-terminated line is then looked up by its (whitespace-
    normalized, leading "N. " stripped) title against those header texts; a
    match becomes "[title](anchor:toc-N)", resolved at click time via
    GET /document/<id>/anchor/<anchor_id> — computed fresh against the
    document's current chapter layout, never a position baked in here. An
    entry with no matching header (a running head bled into the line
    mid-book, back-matter not itself a "## "/"### ") still gets its dot
    leaders and printed page number stripped — that page number is the
    original PDF's own pagination, meaningless in this chapter-based reader,
    so dropping it beats showing a stale, confusing number. Each entry —
    matched or not — is wrapped in its own blank-line-delimited paragraph so
    the reader renders it on its own line instead of run together with its
    neighbors.

    The very first header, when it opens at the true start of the text
    (position 0 — no real front matter at all), gets no anchor: prefixing it
    would plant real, non-blank content before what detect_chapters() (both
    here and at read time, since this is the same text ultimately persisted
    to text_md) treats as "the first chapter", manufacturing a bogus, empty
    "(wstęp)" pseudo-chapter for books that otherwise have no preamble.
    """
    known_titles = {_normalize_toc_title(m.group(2)) for m in _HEADER_LINE_RE.finditer(text)}
    recovered = _toc_derived_subheading_titles(text, known_titles)
    if recovered:
        # Marking is scoped to AFTER the TOC page itself: on a re-run, an
        # unmatched entry's own bare-paragraph form (see _toc_entry_titles())
        # is textually identical to the real subheading it's supposed to
        # point at — without this split, _mark_headings() would turn the
        # TOC's own listing into a header too, not just the real occurrence.
        region = _toc_region(text)
        if region:
            _, region_end = region
            text = text[:region_end] + _mark_headings(text[region_end:], recovered)
        else:
            text = _mark_headings(text, recovered)

    anchors_by_title: dict[str, list[str]] = {}
    # A re-run's brand-new anchors (for just-recovered headers) must not
    # restart numbering from 1 — that would collide with anchor ids a
    # previous run already assigned elsewhere in the same text.
    existing_numbers = [int(n) for n in re.findall(r"\[#toc-(\d+)\]", text)]
    counter = max(existing_numbers, default=0)

    def _record_header(match: re.Match) -> str:
        nonlocal counter
        title = _normalize_toc_title(match.group(2))
        if match.start() == 0:
            return match.group(0)
        # A previous run may already have anchored this exact header — reuse
        # that id (matched against the still-untouched original `text`, safe
        # since re.sub() only builds the replacement text separately, never
        # mutating `text` mid-scan) instead of stacking a second one.
        existing = _TOC_ANCHOR_TAIL_RE.search(text[:match.start()])
        anchor_id = existing.group(1) if existing else None
        if anchor_id is None:
            counter += 1
            anchor_id = f"toc-{counter}"
        anchors_by_title.setdefault(title, []).append(anchor_id)
        if existing:
            return match.group(0)
        return f"[#{anchor_id}]\n\n{match.group(0)}"

    text = _HEADER_LINE_RE.sub(_record_header, text)

    def _replace_entry(match: re.Match) -> str:
        raw_title = match.group("title").strip()
        anchors = next(
            (anchors_by_title[key] for key in _toc_title_candidates(raw_title) if anchors_by_title.get(key)),
            None,
        )
        label = f"[{raw_title}](anchor:{anchors.pop(0)})" if anchors else raw_title
        return f"\n\n{label}\n\n"

    text = _TOC_ENTRY_RE.sub(_replace_entry, text)

    # _TOC_ENTRY_RE only ever matches a still-raw dot-leader line — a re-run's
    # bare, unmatched TOC-region paragraph (left over from a previous run
    # that couldn't match it, possibly just recovered as a real header
    # above) never has one to match. This is that shape's counterpart:
    # anything in the TOC region that's still a bare, unlinked, single-line
    # paragraph gets one more lookup against anchors_by_title.
    region = _toc_region(text)
    if region:
        start, end = region
        blocks = text[start:end].split("\n\n")
        for i, block in enumerate(blocks):
            stripped = block.strip()
            if not stripped or "\n" in stripped or stripped.startswith("#") or stripped.startswith("["):
                continue
            anchors = next(
                (anchors_by_title[key] for key in _toc_title_candidates(stripped) if anchors_by_title.get(key)),
                None,
            )
            if anchors:
                blocks[i] = f"[{stripped}](anchor:{anchors.pop(0)})"
        text = text[:start] + "\n\n".join(blocks) + text[end:]

    return re.sub(r"\n{3,}", "\n\n", text)


def _wrap_callout_boxes(text: str, info_icon: str = _INFO_ICON, warning_icon: str = _WARNING_ICON) -> str:
    """Wrap the paragraph following a standalone callout-icon line in
    "[!INFO]"/"[!WARN]" markers (read.tsx renders these as a green/red box) —
    see _INFO_ICON/_WARNING_ICON for what marks each color in the PDF text
    layer. The icon line itself is dropped (it carries no readable content on
    its own once separated from the box graphic)."""
    lines = text.split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        kind = "INFO" if stripped == info_icon else "WARN" if stripped == warning_icon else None
        if kind is None:
            out.append(lines[i])
            i += 1
            continue
        i += 1
        while i < len(lines) and not lines[i].strip():
            i += 1
        para_lines: list[str] = []
        while i < len(lines) and lines[i].strip() and lines[i].strip() not in (info_icon, warning_icon):
            para_lines.append(lines[i])
            i += 1
        if not para_lines:
            continue
        if out and out[-1].strip():
            out.append("")
        out.append(f"[!{kind}]")
        out.extend(para_lines)
        out.append(f"[!/{kind}]")
        out.append("")
    return "\n".join(out)


@dataclass
class PageImage:
    page_index: int
    xref: int
    data: bytes
    ext: str
    width: int
    height: int


def extract_page_images(pdf_bytes: bytes) -> list[PageImage]:
    """Extract real illustrations embedded in the PDF, in page order.

    A running-head logo or bullet icon reuses the same PDF xref across dozens
    of pages, so images are deduplicated by xref first (keeping the earliest
    occurrence), then filtered by pixel dimensions and byte size to drop
    decorative furniture that isn't a genuine figure.
    """
    import fitz

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    seen_xrefs: set[int] = set()
    images: list[PageImage] = []
    for page_index, page in enumerate(doc):
        for img in page.get_images(full=True):
            xref = img[0]
            if xref in seen_xrefs:
                continue
            seen_xrefs.add(xref)
            info = doc.extract_image(xref)
            width = info.get("width", 0)
            height = info.get("height", 0)
            if width < _IMAGE_MIN_PIXELS or height < _IMAGE_MIN_PIXELS:
                continue
            data = info["image"]
            if len(data) < _IMAGE_MIN_BYTES:
                continue
            images.append(PageImage(
                page_index=page_index, xref=xref, data=data,
                ext=info.get("ext", "png"), width=width, height=height,
            ))
    return images


def caption_for_page(page_text: str) -> str | None:
    """Figure caption on a PDF page ("Rysunek 5. ..."), if any."""
    match = _CAPTION_RE.search(page_text)
    return match.group(1).strip() if match else None


def _insert_image_markers(cleaned: str, image_numbers: list[int]) -> str:
    """Insert "[imgN]" markers into a page's cleaned text.

    A marker for the first image number lands right before the page's first
    caption line (captions sit under their figure in this book, so the
    marker ends up next to the right text). Any image numbers left over
    (more images than captions, or none at all) are appended at the end of
    the page.
    """
    if not image_numbers:
        return cleaned
    lines = cleaned.split("\n")
    caption_indices = [i for i, line in enumerate(lines) if _CAPTION_RE.match(line)]
    remaining = list(image_numbers)
    caption_ptr = 0
    out: list[str] = []
    for i, line in enumerate(lines):
        if caption_ptr < len(caption_indices) and i == caption_indices[caption_ptr] and remaining:
            number = remaining.pop(0)
            if out and out[-1].strip():
                out.append("")
            out.append(f"[img{number}]")
            out.append("")
            caption_ptr += 1
        out.append(line)
    for number in remaining:
        if out and out[-1].strip():
            out.append("")
        out.append(f"[img{number}]")
        out.append("")
    if remaining:
        # A marker with no following same-page line (no caption to anchor to)
        # ends up last in `out` — "\n".join() doesn't emit a trailing separator
        # for a final empty string, so without this the marker would only get
        # a single "\n" before whatever page comes next, merging it into that
        # page's first paragraph instead of standing alone (pages are
        # concatenated with no separator in build_book_markdown()).
        out.append("")
    return "\n".join(out)


def _page_chapter_positions(
    page_count: int, chapter_start_page_list: list[int], has_preamble: bool,
) -> list[int]:
    """Chapter position each page belongs to, in the reader's own numbering.

    Must match library.text_functions.detect_chapters() exactly, since that's
    what GET /document/<id>/chapter/<pos> actually uses to slice chapter text —
    not ChapterInfo.position. detect_chapters() inserts a "(wstęp)" pseudo-chapter
    at position 1 when there is real text before the first "## " header, which
    shifts every real chapter's reader position up by one relative to
    ChapterInfo.position (build_book_markdown()'s own, wstęp-unaware numbering).
    When has_preamble is True: pages before the first chapter marker get
    position 1 (the wstęp), and the i-th chapter (1-based) gets i + 1. When
    False, there is no wstęp and numbering is unshifted (pages before any
    marker — a degenerate case in practice — fall back to 0, "no chapter").

    chapter_start_page_list must be every "## " header's page, in the exact
    order those headers appear in the final text — numbered chapters AND
    extra_sections (front/back-matter) interleaved, not just numbered chapters
    (a page can carry more than one front-matter header, e.g. this book's "Od
    Wydawcy" and "Linux Early Access: podziękowania" both open on page 22 — a
    duplicate page number here is one "## " header each, not a bug). Sorted,
    it corresponds 1:1 (by rank) to the ChapterInfo entries build_book_markdown()
    emits — both are ordered by page position (then by within-page position for
    same-page entries, though this function only tracks page granularity).
    """
    starts = sorted(chapter_start_page_list)
    offset = 1 if has_preamble else 0
    positions: list[int] = []
    current = 1 if has_preamble else 0
    idx = 0
    for page_idx in range(page_count):
        while idx < len(starts) and starts[idx] <= page_idx:
            current = idx + 1 + offset
            idx += 1
        positions.append(current)
    return positions


def _mark_headings(text: str, heading_texts: set[str]) -> str:
    if not heading_texts:
        return text
    lines = text.split("\n")
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped in heading_texts and not stripped.startswith("#"):
            if out and out[-1].strip():
                out.append("")
            out.append(f"### {stripped}")
            out.append("")
        else:
            out.append(line)
    return "\n".join(out)


def _find_chapter_marker_spans(text: str, pattern: re.Pattern) -> list[tuple[int, int, str, str]]:
    """Locate each chapter-marker occurrence plus its title. Running heads
    (repeated on almost every page) render the title on its own line right
    after the marker; the actual chapter-start page instead wraps an all-caps
    title across the marker's own line and the following one — so the title
    is taken from whichever of those two lines is non-empty first.

    Returns (span_start, span_end, chapter_key, title) tuples, span covering the
    marker AND its title line so both can be removed from the body together
    (a running head's title is not real chapter content, just page furniture).
    """
    spans: list[tuple[int, int, str, str]] = []
    for m in pattern.finditer(text):
        line_end = text.find("\n", m.end())
        if line_end == -1:
            line_end = len(text)
        same_line_tail = text[m.end():line_end].strip()
        if same_line_tail:
            title, span_end = same_line_tail, line_end
        else:
            next_end = text.find("\n", line_end + 1)
            if next_end == -1:
                next_end = len(text)
            title, span_end = text[line_end + 1:next_end].strip(), next_end
        spans.append((m.start(), span_end, m.group(1), title))
    return spans


def _insert_paragraph_breaks(text: str) -> str:
    """Insert an extra blank line after a wrapped line that looks like the end of
    a prose paragraph (short + ends in sentence-final punctuation) and before
    bullet list markers. PyMuPDF (like pypdf) emits exactly one "\\n" for both a
    genuine paragraph break and a mid-paragraph line wrap, so without this a
    markdown renderer (soft line breaks collapse to a space) shows the whole
    chapter as one unbroken wall of text. Additive only — never merges or drops
    a line, so code/config samples (common in technical books) are never
    rewritten even where the heuristic misses a boundary.
    """
    lines = text.split("\n")
    lengths = [len(line) for line in lines if len(line.strip()) > 20]
    if not lengths:
        return text
    lengths.sort()
    typical_width = lengths[int(len(lengths) * 0.75)]
    short_threshold = typical_width * 0.75

    out: list[str] = []
    for i, line in enumerate(lines):
        out.append(line)
        stripped = line.strip()
        next_line = lines[i + 1].strip() if i + 1 < len(lines) else ""
        if not stripped or not next_line:
            continue
        next_is_bullet = bool(_BULLET_RE.match(next_line))
        ends_sentence = bool(_SENTENCE_END_RE.search(stripped))
        short_line = len(stripped) < short_threshold
        if next_is_bullet or (ends_sentence and short_line):
            out.append("")
    return "\n".join(out)


@dataclass
class ChapterInfo:
    position: int
    title: str
    char_start: int
    char_end: int

    @property
    def length(self) -> int:
        return self.char_end - self.char_start


@dataclass
class BookMarkdownResult:
    markdown: str
    chapters: list[ChapterInfo] = field(default_factory=list)
    # 1-based chapter position per source page (0 = before the first chapter);
    # same length as the `pages` list passed to build_book_markdown().
    page_chapter_positions: list[int] = field(default_factory=list)


def extract_pages(pdf_bytes: bytes) -> list[str]:
    """Extract text per page via PyMuPDF (fitz). Requires an existing text layer —
    run imports/check_pdf_text_layer.py first if unsure."""
    import fitz

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    return [page.get_text() for page in doc]


def build_book_markdown(
    pages: list[str],
    chapter_regex: str = DEFAULT_CHAPTER_REGEX,
    heading_texts: set[str] | None = None,
    images_by_page: dict[int, list[int]] | None = None,
    extra_sections: dict[int, list[tuple[str, str]]] | None = None,
    promote_subheadings: dict[str, str] | None = None,
) -> BookMarkdownResult:
    """Turn raw per-page PDF text into chapter-marked markdown.

    Strips every occurrence of the chapter marker (real chapter-start header
    and repeated running heads alike), strips standalone page-number lines,
    joins words split by a soft hyphen (U+00AD) at a line wrap, marks book
    subheadings as "### <title>" (see detect_heading_texts()), and inserts a
    single clean "## <title>" at each chapter's first occurrence. The chapter
    title used is the most common cleaned rendition across all its
    occurrences (running heads render a clean single-line title; the actual
    chapter-start page often wraps the all-caps title across lines).

    images_by_page (page index -> list of image numbers N) inserts "[imgN]"
    markers — see _insert_image_markers().

    extra_sections (see detect_named_sections()) inserts a "## <title>" at
    each given page's exact source-text position — unlike numbered chapters
    these aren't always alone at the top of their page (e.g. two front-matter
    sections opening on the same page), so each is spliced in precisely where
    its own source text was found, not just at page start. promote_subheadings
    upgrades specific already-"### "-marked subheadings (exact text match, see
    _mark_headings()/detect_heading_texts()) to real "## " chapters — this
    book's back matter (Spis tabel/Spis rysunków/Bibliografia) shares its
    styling with ordinary subheadings but is its own printed-TOC entry.

    The book's own printed "SPIS TREŚCI" page is left as ordinary prose here
    (it isn't itself a chapter) but is reformatted by link_toc_entries() —
    one entry per line, clickable where its title matches a real header.
    """
    pattern = re.compile(chapter_regex)
    heading_texts = heading_texts or set()
    images_by_page = images_by_page or {}
    extra_sections = extra_sections or {}
    promote_subheadings = promote_subheadings or {}

    page_spans = [_find_chapter_marker_spans(page_text, pattern) for page_text in pages]

    titles_by_chapter: dict[str, Counter] = {}
    first_page_by_chapter: dict[str, int] = {}
    for page_idx, spans in enumerate(page_spans):
        for _start, _end, chapter_key, title in spans:
            if title:
                titles_by_chapter.setdefault(chapter_key, Counter())[title] += 1
            first_page_by_chapter.setdefault(chapter_key, page_idx)

    canonical_title = {
        key: counter.most_common(1)[0][0] for key, counter in titles_by_chapter.items()
    }
    chapter_start_pages = {page_idx: key for key, page_idx in first_page_by_chapter.items()}
    # Page each promoted subheading (see promote_subheadings) lands on — needed
    # alongside chapter_start_pages/extra_sections below to keep
    # _page_chapter_positions()'s page->chapter mapping in sync with every kind
    # of "## " header this function can now produce, not just numbered chapters.
    promoted_start_pages: list[int] = []

    body_parts: list[str] = []
    for page_idx, page_text in enumerate(pages):
        cursor = 0
        page_parts = []
        for start, end, _chapter_key, _title in page_spans[page_idx]:
            page_parts.append(page_text[cursor:start])
            cursor = end
        page_parts.append(page_text[cursor:])
        cleaned = "".join(page_parts)
        cleaned = _escape_leading_hashes(cleaned)
        cleaned = _mark_headings(cleaned, heading_texts)
        for promoted_source_text in promote_subheadings:
            if f"### {promoted_source_text}" in cleaned:
                promoted_start_pages.append(page_idx)
        image_numbers = images_by_page.get(page_idx)
        if image_numbers:
            cleaned = _insert_image_markers(cleaned, image_numbers)
        page_extra_sections = extra_sections.get(page_idx)
        if page_extra_sections:
            extra_parts: list[str] = []
            extra_cursor = 0
            for source_text, section_title in page_extra_sections:
                idx = cleaned.find(source_text, extra_cursor)
                if idx == -1:
                    continue
                line_end = cleaned.find("\n", idx)
                if line_end == -1:
                    line_end = len(cleaned)
                extra_parts.append(cleaned[extra_cursor:idx])
                extra_parts.append(f"\n\n## {section_title}\n\n")
                extra_cursor = line_end + 1
            extra_parts.append(cleaned[extra_cursor:])
            cleaned = "".join(extra_parts)
        chapter_key = chapter_start_pages.get(page_idx)
        if chapter_key is not None:
            body_parts.append(f"\n\n## {canonical_title[chapter_key]}\n\n")
        body_parts.append(cleaned)

    text = "".join(body_parts)
    text = _PAGE_NUMBER_LINE_RE.sub("", text)
    text = _REPLACEMENT_CHAR_RUN_RE.sub("", text)
    text = _STRAY_CONTROL_CHAR_RE.sub("", text)
    # Soft hyphen marks a genuine line-wrap split — join directly, no hyphen kept.
    text = text.replace("\xad\n", "").replace("\xad", "")
    for source_text, promoted_title in promote_subheadings.items():
        text = text.replace(f"### {source_text}", f"## {promoted_title}", 1)
    # Paragraph breaks first — a callout paragraph's own end is often only
    # marked by _insert_paragraph_breaks()'s heuristic, not a blank line
    # already present in the raw extraction, so _wrap_callout_boxes() (which
    # scopes each box to "until the next blank line") needs that heuristic to
    # have already run or it swallows everything up to the next real one.
    text = _insert_paragraph_breaks(text)
    text = _wrap_callout_boxes(text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    text = _link_table_captions(text)
    text = link_toc_entries(text)

    chapters: list[ChapterInfo] = []
    header_re = re.compile(r"(?m)^## (.+)$")
    matches = list(header_re.finditer(text))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        chapters.append(ChapterInfo(position=i + 1, title=m.group(1).strip(), char_start=m.start(), char_end=end))

    # Mirrors detect_chapters()'s own "(wstęp)" condition exactly (same regex,
    # same text) — see _page_chapter_positions()'s docstring for why this must
    # stay in sync with the reader rather than being computed independently.
    has_preamble = bool(chapters) and bool(text[:chapters[0].char_start].strip())
    all_chapter_start_pages = (
        list(chapter_start_pages.keys())
        + [page_idx for page_idx, page_extra in extra_sections.items() for _ in page_extra]
        + promoted_start_pages
    )
    page_chapter_positions = _page_chapter_positions(len(pages), all_chapter_start_pages, has_preamble)
    return BookMarkdownResult(markdown=text, chapters=chapters, page_chapter_positions=page_chapter_positions)


def fetch_chapter_footnotes(url: str, timeout: float = 20.0, proxies: dict[str, str] | None = None) -> list[dict]:
    """Fetch a book's own per-chapter endnote page and parse its footnotes.

    Some publishers (Sekurak's "Twierdza Linux" companion microsite is the
    first observed case: https://twierdza.sekurak.pl/rN/, one page per
    chapter, r0 for the intro) publish each chapter's endnotes online as an
    ordered list of "<li class="footnote-end">" entries, each usually
    containing one "<a href>" link — e.g.:

        <li class="footnote-end">Stallman R., <em>What's in a Name?</em>,
        GNU Operating System, updated: 2021,
        <a href="https://www.gnu.org/gnu/why-gnu-linux.html">...</a></li>

    This is the authoritative, human-curated footnote text (with working
    URLs) — used instead of trying to reconstruct footnotes from the PDF
    text layer, where this book's inline markers don't carry any footnote
    body text at all (they render as a plain digit glued directly onto the
    preceding word, e.g. "esej2" — no separating space, no true Unicode
    superscript, nothing library.references's OCR-tuned heuristics can
    parse); only the online page has the actual reference text.

    List order is the footnote's printed number (1-based) — callers assign
    this as the "marker" for document_references.

    proxies: an optional requests-style {"http": ..., "https": ...} proxy
    dict — twierdza.sekurak.pl's Cloudflare front rate-limits/blocks some
    residential IPs with an opaque 520 (confirmed independently from two
    unrelated networks, so not a plain outage); routing through the
    project's existing Webshare rotating-residential proxy
    (library.webshare_ip_auth.get_proxy_credentials(), same one
    library.youtube_processing.py uses) reliably got a 200 in testing.
    Callers build this dict; this function stays proxy-agnostic.

    Returns [] (with a logged warning) on any HTTP/parse failure or when the
    page has no footnote-end entries — one missing/broken chapter page must
    never fail the whole run.
    """
    import requests
    from bs4 import BeautifulSoup

    try:
        resp = requests.get(
            url, timeout=timeout, proxies=proxies,
            headers={"User-Agent": "Mozilla/5.0 (compatible; LenieBot/1.0)"},
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("fetch_chapter_footnotes: %s failed: %s", url, exc)
        return []

    # resp.content (raw bytes), not resp.text: the site's Content-Type header
    # carries no charset param, so requests falls back to Latin-1 per the HTTP
    # spec default and silently mangles every non-ASCII character (observed:
    # "’" -> "â\x80\x99", "ą" -> "Ä…") even though the page is genuinely UTF-8
    # (its own <meta charset="utf-8">). BeautifulSoup's own encoding sniffer
    # (on raw bytes) reads that meta tag and gets it right.
    soup = BeautifulSoup(resp.content, "html.parser")
    footnotes: list[dict] = []
    for i, li in enumerate(soup.select("li.footnote-end"), start=1):
        text = li.get_text(" ", strip=True)
        if not text:
            continue
        link = li.find("a", href=True)
        footnotes.append({"marker": str(i), "text": text, "url": link["href"] if link else None})
    return footnotes


def slugify(value: str) -> str:
    from unidecode import unidecode

    value = unidecode(value).lower()
    value = re.sub(r"[^a-z0-9]+", "_", value).strip("_")
    return value or "book"


def import_pdf_book(
    session: Session,
    pdf_bytes: bytes,
    *,
    title: str,
    byline: str | None = None,
    source: str = "own",
    url: str | None = None,
    note: str = "default_note",
    chapter_regex: str = DEFAULT_CHAPTER_REGEX,
    extract_images: bool = True,
    heading_font_prefix: str = _HEADING_FONT_PREFIX,
    heading_min_size: float = _HEADING_MIN_SIZE,
    extra_section_eyebrows: dict[str, str] | None = None,
    extra_section_titles: dict[str, str] | None = None,
    promote_subheadings: dict[str, str] | None = None,
    detect_tables: bool = True,
    apply_styles: bool = True,
) -> tuple[Document, BookMarkdownResult]:
    """Create a Document for a book PDF with chapter-aware text_md. Commits.

    Pipeline order matters: tables are converted to markdown first (while
    `pages` still holds plain, untouched extract_pages() text — insert_page_tables()
    locates each table by an exact substring match against that text), then
    inline monospace/italic styling is layered on top of whatever `pages` is
    at that point (apply_inline_styles() re-derives its own alignment per
    page and simply won't match already-replaced table regions, so it can't
    corrupt them). extra_section_eyebrows/extra_section_titles/
    promote_subheadings feed detect_named_sections() and build_book_markdown()
    to turn this book's front/back-matter "part" sections into real, clickable
    chapters alongside the numbered ones — see their docstrings.

    Returns (document, markdown_result) so callers can report chapter stats.
    """
    pages = extract_pages(pdf_bytes)
    if detect_tables:
        pages = insert_page_tables(pdf_bytes, pages)
    if apply_styles:
        pages = apply_inline_styles(pdf_bytes, pages)
    heading_texts = detect_heading_texts(pdf_bytes, font_prefix=heading_font_prefix, min_size=heading_min_size)
    page_images = extract_page_images(pdf_bytes) if extract_images else []
    images_by_page: dict[int, list[int]] = {}
    for position, page_image in enumerate(page_images):
        images_by_page.setdefault(page_image.page_index, []).append(position)
    extra_sections = detect_named_sections(
        pdf_bytes, extra_section_eyebrows or {}, extra_section_titles or {},
    ) if (extra_section_eyebrows or extra_section_titles) else {}

    result = build_book_markdown(
        pages, chapter_regex=chapter_regex, heading_texts=heading_texts, images_by_page=images_by_page,
        extra_sections=extra_sections, promote_subheadings=promote_subheadings,
    )
    if not result.chapters:
        raise ValueError(
            "No chapters detected with the given --chapter-regex — adjust the pattern "
            "(preview with imports/check_pdf_text_layer.py --show-sample first)"
        )

    doc_url = url or f"file:///ksiazki/{slugify(title)}.pdf"

    service = DocumentService(session)
    doc = service.create_document(
        url=doc_url,
        url_type="text",
        title=title,
        note=note,
        source=source,
    )
    doc.byline = byline
    doc.text_md = result.markdown

    cfg = load_config()
    storage = storage_from_config(cfg)
    pdf_uid = doc.uuid or str(uuid.uuid4())
    storage.put_bytes(f"{pdf_uid}.pdf", pdf_bytes, "application/pdf")

    if page_images:
        from library.document_images import replace_storage_images

        image_rows = []
        for position, page_image in enumerate(page_images):
            storage_key = f"documents/{pdf_uid}/images/{position}.{page_image.ext}"
            content_type = CONTENT_TYPE_BY_EXT.get(page_image.ext, "application/octet-stream")
            storage.put_bytes(storage_key, page_image.data, content_type)
            chapter_position = (
                result.page_chapter_positions[page_image.page_index]
                if page_image.page_index < len(result.page_chapter_positions) else 0
            )
            image_rows.append({
                "storage_key": storage_key,
                "position": position,
                "page_number": page_image.page_index + 1,
                "chapter_position": chapter_position,
                "caption_text": caption_for_page(pages[page_image.page_index]),
            })
        replace_storage_images(session, doc.id, image_rows)

    session.commit()
    return doc, result
