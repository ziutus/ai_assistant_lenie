"""Import a book PDF (with a usable text layer, see imports/check_pdf_text_layer.py)
into a Document with chapter-aware markdown.

Pure functions operate on bytes/text only — no local filesystem assumptions
beyond receiving the PDF as bytes. This keeps the pipeline portable: the same
`import_pdf_book()` call works whether the bytes come from a local file (today,
via imports/book_import_pdf.py) or a future ObjectStorage.get_bytes()/job-queue
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

import re
import uuid
from collections import Counter
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from library.config_loader import load_config
from library.db.models import Document
from library.document_service import DocumentService
from library.storage import storage_from_config

DEFAULT_CHAPTER_REGEX = r"(?i)//\s*ROZDZIA[ŁL]\s*(\d+)\s*//"
_PAGE_NUMBER_LINE_RE = re.compile(r"(?m)^\s*\d{1,4}\s*$\n?")
_BULLET_RE = re.compile(r"^\s*[▶▷•‣]|^\s*\d+[.)]\s")
_SENTENCE_END_RE = re.compile(r"[.!?”\"»]\s*$")
# Shell/config code samples in technical books often have lines like "# comment"
# or "## section" — library.text_functions.detect_chapters() treats ANY
# 1-2-hash line as a markdown H1/H2 header, so these must be neutralized before
# our own "## <title>" markers are inserted, or they swamp the real chapter count.
_LEADING_HASH_RE = re.compile(r"(?m)^(#{1,2})(?=\s)")
# Book-specific: this book's subheadings render in a distinct "display" font
# family at a size clearly above body text (body is NotoSerif @ 8.5pt; the
# chapter running-head title also uses BarlowCondensed but at 11pt/Regular
# weight, below this threshold, so it's excluded without extra bookkeeping).
# A book with different subheading styling needs different constants here —
# there's no universal PDF signal for "this line is a subheading".
_HEADING_FONT_PREFIX = "BarlowCondensed"
_HEADING_MIN_SIZE = 12.0

# Thresholds separating real illustrations from decorative furniture (running-head
# logos, bullet icons, page masks). Like _HEADING_*, these may need retuning for
# a different book.
_IMAGE_MIN_PIXELS = 100  # applies to each dimension
_IMAGE_MIN_BYTES = 5 * 1024
_CAPTION_RE = re.compile(r"(?m)^\s*((?:Rysunek|Rys\.|Ilustracja|Tabela|Zdj\.)\s*\d+[.:].*)$")
CONTENT_TYPE_BY_EXT = {"png": "image/png", "jpeg": "image/jpeg", "jpg": "image/jpeg"}


def _escape_leading_hashes(text: str) -> str:
    return _LEADING_HASH_RE.sub(lambda m: "\\" + m.group(1), text)


def detect_heading_texts(pdf_bytes: bytes) -> set[str]:
    """Collect the exact text of lines styled as book subheadings, using
    PyMuPDF's per-span font metadata (name + size) — plain text extraction
    throws this away, so a subheading like "Nazewnictwo w książce" otherwise
    blends into the surrounding paragraph text with no visual distinction.
    A line counts only when EVERY span on it matches the heading style, so a
    bolded word inside an ordinary sentence (same font family/size as body
    text, just a different weight) is never mistaken for a heading.
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
                    s["font"].startswith(_HEADING_FONT_PREFIX) and s["size"] >= _HEADING_MIN_SIZE
                    for s in spans
                ):
                    text = "".join(s["text"] for s in spans).strip()
                    if text:
                        headings.add(text)
    return headings


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
    return "\n".join(out)


def _page_chapter_positions(
    page_count: int, chapter_start_pages: dict[int, str], has_preamble: bool,
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

    Chapter start pages, sorted, correspond 1:1 (by rank) to the ChapterInfo
    entries build_book_markdown() emits — both are ordered by page position.
    """
    starts = sorted(chapter_start_pages.keys())
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
    """
    pattern = re.compile(chapter_regex)
    heading_texts = heading_texts or set()
    images_by_page = images_by_page or {}

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
        image_numbers = images_by_page.get(page_idx)
        if image_numbers:
            cleaned = _insert_image_markers(cleaned, image_numbers)
        chapter_key = chapter_start_pages.get(page_idx)
        if chapter_key is not None:
            body_parts.append(f"\n\n## {canonical_title[chapter_key]}\n\n")
        body_parts.append(cleaned)

    text = "".join(body_parts)
    text = _PAGE_NUMBER_LINE_RE.sub("", text)
    # Soft hyphen marks a genuine line-wrap split — join directly, no hyphen kept.
    text = text.replace("\xad\n", "").replace("\xad", "")
    text = _insert_paragraph_breaks(text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

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
    page_chapter_positions = _page_chapter_positions(len(pages), chapter_start_pages, has_preamble)
    return BookMarkdownResult(markdown=text, chapters=chapters, page_chapter_positions=page_chapter_positions)


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
) -> tuple[Document, BookMarkdownResult]:
    """Create a Document for a book PDF with chapter-aware text_md. Commits.

    Returns (document, markdown_result) so callers can report chapter stats.
    """
    pages = extract_pages(pdf_bytes)
    heading_texts = detect_heading_texts(pdf_bytes)
    page_images = extract_page_images(pdf_bytes) if extract_images else []
    images_by_page: dict[int, list[int]] = {}
    for position, page_image in enumerate(page_images):
        images_by_page.setdefault(page_image.page_index, []).append(position)

    result = build_book_markdown(
        pages, chapter_regex=chapter_regex, heading_texts=heading_texts, images_by_page=images_by_page,
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
