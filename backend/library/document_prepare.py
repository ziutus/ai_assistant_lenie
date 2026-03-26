"""Wspólne funkcje do pobierania HTML z S3 i konwersji do markdown.

Używane przez:
- webdocument_prepare_regexp_by_ai.py
- imports/article_browser.py
- webdocument_md_decode.py
"""

import json
import logging
import os

from markitdown import MarkItDown
from html2markdown import convert
import html2text

from library.api.aws.s3_aws import s3_file_exist, s3_take_file
from library.config_loader import load_config

logger = logging.getLogger(__name__)


def calculate_reduction(html_size, markdown_size):
    return ((html_size - markdown_size) / html_size) * 100


def prepare_markdown(document_id, doc, cache_dir, verbose: bool = False) -> str | None:
    """Pobierz HTML z S3 i skonwertuj do markdown. Zwraca tekst markdown lub None."""
    cfg = load_config()
    s3_bucket = cfg.get("AWS_S3_WEBSITE_CONTENT")

    cache_file_html = os.path.join(cache_dir, f"{document_id}.html")
    cache_file_md = os.path.join(cache_dir, f"{document_id}.md")

    def _log(msg):
        logger.info(msg)
        if verbose:
            print(f"    {msg}")

    if os.path.isfile(cache_file_md):
        _log(f"[1/3] Markdown w cache: {cache_file_md}")
        with open(cache_file_md, "r", encoding="utf-8") as f:
            return f.read()

    if not os.path.isfile(cache_file_html):
        if not doc.s3_uuid:
            _log("Brak s3_uuid — nie mogę pobrać HTML")
            return None

        s3_key = f"{doc.s3_uuid}.html"
        _log(f"[1/3] Sprawdzam HTML w S3...")
        if not s3_file_exist(s3_bucket, s3_key):
            _log("HTML nie znaleziony w S3")
            return None

        _log(f"[2/3] Pobieram HTML z S3 ({s3_key[:40]}...)")
        if not s3_take_file(s3_bucket, s3_key, cache_file_html):
            _log("Nie udało się pobrać HTML z S3")
            return None
    else:
        _log(f"[1/3] HTML w cache: {cache_file_html}")

    html_size = os.path.getsize(cache_file_html)
    _log(f"[3/3] Konwertuję HTML ({html_size // 1024} KB) do markdown (MarkItDown)...")

    mdit = MarkItDown()
    markdown_text = mdit.convert(cache_file_html).text_content
    reduction = calculate_reduction(html_size, len(markdown_text))

    if reduction < 30:
        _log(f"  MarkItDown: redukcja {reduction:.0f}% — za mało, próbuję html2markdown...")
        with open(cache_file_html, "r", encoding="utf-8") as f:
            html = f.read()
        markdown_text = convert(html)
        reduction = calculate_reduction(html_size, len(markdown_text))

        if reduction < 30:
            _log(f"  html2markdown: redukcja {reduction:.0f}% — za mało, próbuję html2text...")
            h = html2text.HTML2Text()
            h.ignore_links = False
            h.ignore_images = False
            markdown_text = h.handle(html)

    with open(cache_file_md, "w", encoding="utf-8") as f:
        f.write(markdown_text)
    _log(f"  Markdown zapisany ({len(markdown_text)} znaków, redukcja {reduction:.0f}%)")

    return markdown_text


def save_document_info(document_id, doc, cache_dir):
    """Zapisz metadane dokumentu do JSON."""
    cache_file_info = os.path.join(cache_dir, f"{document_id}_info.json")
    doc_info = {
        "id": doc.id,
        "url": doc.url,
        "title": doc.title,
        "language": doc.language,
        "s3_uuid": doc.s3_uuid,
        "created_at": doc.created_at.strftime("%Y-%m-%d %H:%M:%S") if doc.created_at else None,
        "document_type": doc.document_type if doc.document_type else None,
        "document_state": doc.document_state if doc.document_state else None,
    }
    with open(cache_file_info, "w", encoding="utf-8") as f:
        json.dump(doc_info, f, ensure_ascii=False, indent=2)
