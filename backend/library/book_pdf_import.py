"""Import a book PDF (with a usable text layer, see imports/check_pdf_text_layer.py)
into a Document with chapter-aware markdown.

Pure functions operate on bytes/text only — no local filesystem assumptions
beyond receiving the PDF as bytes. This keeps the pipeline portable: the same
`import_pdf_book()` call works whether the bytes come from a local file (today,
via imports/book_import_pdf.py) or a future ObjectStorage.get_bytes()/job-queue
materialize() step (docs/deployment/nas/storage-and-jobs-migration-plan.md) —
only the caller that supplies the bytes changes, not this module.

Chapter detection is heuristic and regex-driven per book (no universal PDF
chapter format exists) — the default pattern matches the "// ROZDZIAŁ NNN //"
running-head style used by Sekurak books. Pass --chapter-regex for other
layouts. The output markdown must satisfy library.text_functions.detect_chapters()
(H1/H2 headers), so chapter titles are emitted as "## <title>".
"""

from __future__ import annotations

import io
import re
import uuid
from collections import Counter
from dataclasses import dataclass, field

from pypdf import PdfReader
from sqlalchemy.orm import Session

from library.config_loader import load_config
from library.db.models import Document
from library.document_service import DocumentService
from library.storage import storage_from_config

DEFAULT_CHAPTER_REGEX = r"//\s*ROZDZIA[ŁL]\s*(\d+)\s*//([^\n]*)"
_PAGE_NUMBER_LINE_RE = re.compile(r"(?m)^\s*\d{1,4}\s*$\n?")
_HYPHEN_LINEBREAK_RE = re.compile(r"(\w) -\s*\n(\w)", re.UNICODE)
# Shell/config code samples in technical books often have lines like "# comment"
# or "## section" — library.text_functions.detect_chapters() treats ANY
# 1-2-hash line as a markdown H1/H2 header, so these must be neutralized before
# our own "## <title>" markers are inserted, or they swamp the real chapter count.
_LEADING_HASH_RE = re.compile(r"(?m)^(#{1,2})(?=\s)")


def _escape_leading_hashes(text: str) -> str:
    return _LEADING_HASH_RE.sub(lambda m: "\\" + m.group(1), text)


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


def extract_pages(pdf_bytes: bytes) -> list[str]:
    """Extract text per page via pypdf. Requires an existing text layer —
    run imports/check_pdf_text_layer.py first if unsure."""
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return [page.extract_text() or "" for page in reader.pages]


def build_book_markdown(pages: list[str], chapter_regex: str = DEFAULT_CHAPTER_REGEX) -> BookMarkdownResult:
    """Turn raw per-page PDF text into chapter-marked markdown.

    Strips every occurrence of the chapter marker (real chapter-start header
    and repeated running heads alike), strips standalone page-number lines,
    joins words split by justified-text line-wrap hyphenation, and inserts a
    single clean "## <title>" at each chapter's first occurrence. The chapter
    title used is the most common cleaned rendition across all its
    occurrences (running heads render a clean single-line title; the actual
    chapter-start page often wraps the all-caps title across lines).
    """
    pattern = re.compile(chapter_regex)

    titles_by_chapter: dict[str, Counter] = {}
    first_page_by_chapter: dict[str, int] = {}
    for page_idx, page_text in enumerate(pages):
        for m in pattern.finditer(page_text):
            chapter_key = m.group(1)
            title = m.group(2).strip()
            if title:
                titles_by_chapter.setdefault(chapter_key, Counter())[title] += 1
            first_page_by_chapter.setdefault(chapter_key, page_idx)

    canonical_title = {
        key: counter.most_common(1)[0][0] for key, counter in titles_by_chapter.items()
    }
    chapter_start_pages = {page_idx: key for key, page_idx in first_page_by_chapter.items()}

    body_parts: list[str] = []
    for page_idx, page_text in enumerate(pages):
        cleaned = pattern.sub("", page_text)
        cleaned = _escape_leading_hashes(cleaned)
        chapter_key = chapter_start_pages.get(page_idx)
        if chapter_key is not None:
            body_parts.append(f"\n\n## {canonical_title[chapter_key]}\n\n")
        body_parts.append(cleaned)

    text = "".join(body_parts)
    text = _PAGE_NUMBER_LINE_RE.sub("", text)
    text = _HYPHEN_LINEBREAK_RE.sub(r"\1\2", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    chapters: list[ChapterInfo] = []
    header_re = re.compile(r"(?m)^## (.+)$")
    matches = list(header_re.finditer(text))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        chapters.append(ChapterInfo(position=i + 1, title=m.group(1).strip(), char_start=m.start(), char_end=end))

    return BookMarkdownResult(markdown=text, chapters=chapters)


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
) -> tuple[Document, BookMarkdownResult]:
    """Create a Document for a book PDF with chapter-aware text_md. Commits.

    Returns (document, markdown_result) so callers can report chapter stats.
    """
    pages = extract_pages(pdf_bytes)
    result = build_book_markdown(pages, chapter_regex=chapter_regex)
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

    session.commit()
    return doc, result
