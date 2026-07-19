"""Download missing markdown for documents already in the database.

Re-downloads the webpage HTML, uploads it to S3, converts to markdown via
library.document_prepare.prepare_markdown (MarkItDown -> html2markdown ->
html2text cascade, cached in {CACHE_DIR}/markdown/{doc_id}/) and stores the
cleaned result in the database.

Usage:
    cd backend
    python documents_fix_missing_markdown.py [--dry-run] [--limit N]
"""

import argparse
import os
import uuid

import boto3

from library.config_loader import load_config
from library.db.engine import get_session
from library.db.models import Document
from library.document_prepare import prepare_markdown
from library.models.stalker_document_status import StalkerDocumentStatus
from library.models.stalker_document_status_error import StalkerDocumentStatusError
from library.document_repository import DocumentRepository
from library.website.website_download_context import download_raw_html, webpage_text_clean

cfg = load_config()

# TODO: sprawdzić, dlaczego jest problem z pobraniem poniższych stron
problems = [38, 89, 150, 157, 191, 208, 220, 311, 371, 376, 396,
            443, 456, 465, 470, 486, 497, 499, 503, 531, 553, 581, 592, 600, 601, 602, 611, 662,
            664, 668, 686, 694, 1013, 6735, 6863, 6878, 6883, 6904, 6913, 6918, 6923, 6926, 6930, 7025]

# 611 certificate expired


def decode_html(raw: bytes) -> str:
    """Decode raw HTML bytes: UTF-8 first, then chardet detection, then latin-1 fallback."""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        import chardet

        detected_encoding = chardet.detect(raw)['encoding']
        print(f"Detected encoding: {detected_encoding}")
        if detected_encoding:
            return raw.decode(detected_encoding, errors="replace")
        print("Encoding detection failed, using replacement characters.")
        return raw.decode("latin-1", errors="replace")


def main():
    parser = argparse.ArgumentParser(description="Download missing markdown for documents in the database")
    parser.add_argument("--dry-run", action="store_true", help="List documents only, no downloads or DB writes")
    parser.add_argument("--limit", type=int, help="Max documents to process")
    args = parser.parse_args()

    if not cfg.get("AWS_S3_WEBSITE_CONTENT"):
        print("The S3 bucket for text and html files is not set, exiting.")
        exit(1)

    session = get_session()
    try:
        websites = DocumentRepository(session=session)

        print("Adding missing markdown entries")

        document_id_start = max(problems) if len(problems) > 0 else 0
        md_needed = websites.get_documents_md_needed(min_id=document_id_start)
        if args.limit:
            md_needed = md_needed[:args.limit]
        print(md_needed)

        if args.dry_run:
            print(f"[dry-run] {len(md_needed)} documents would be processed.")
            return

        s3 = boto3.client('s3')

        for document_id in md_needed:
            doc = Document.get_by_id(session, document_id)
            if doc is None:
                print(f"Document {document_id} not found, skipping")
                continue

            if doc.paywall:
                print("Need manual download")
                continue

            if doc.id in problems:
                print(f"Skipping problem on {document_id}")
                continue

            print(f"Downloading {doc.id} {doc.url}, md len({len(doc.text_md or '')})")

            html = download_raw_html(url=doc.url)
            if not html:
                print("empty response! [ERROR]")
                doc.processing_status = StalkerDocumentStatus.ERROR.name
                doc.processing_error_code = StalkerDocumentStatusError.ERROR_DOWNLOAD.name
                session.commit()
                continue

            html = decode_html(html)

            doc_uuid = doc.uuid or str(uuid.uuid4())
            file_name = f"{doc_uuid}.html"

            try:
                s3.put_object(Bucket=cfg.get("AWS_S3_WEBSITE_CONTENT"), Key=file_name, Body=html)
                print(f"Successfully uploaded {file_name} to {cfg.get('AWS_S3_WEBSITE_CONTENT')}")
            except Exception as e:
                error_message = f"Failed to upload {file_name} to {cfg.get('AWS_S3_WEBSITE_CONTENT')}: {str(e)}"
                print(error_message)
                exit(1)

            # Cache in the {CACHE_DIR}/markdown/{doc_id}/{doc_id}.ext convention
            # (same as document_prepare.py), so downstream tools can reuse the files.
            doc_cache_dir = os.path.join(cfg.get("CACHE_DIR") or "tmp", "markdown", str(doc.id))
            os.makedirs(doc_cache_dir, exist_ok=True)
            page_file = os.path.join(doc_cache_dir, f"{doc.id}.html")
            with open(page_file, 'w', encoding="utf-8") as file:
                file.write(html)

            # Drop stale cached markdown so prepare_markdown converts the fresh HTML
            stale_md = os.path.join(doc_cache_dir, f"{doc.id}.md")
            if os.path.exists(stale_md):
                os.remove(stale_md)

            # MarkItDown -> html2markdown -> html2text cascade; writes {id}.md to cache
            markdown_text = prepare_markdown(doc.id, doc, doc_cache_dir)
            if not markdown_text:
                print(f"[ERROR] markdown conversion failed for {doc.id}")
                continue

            doc.text_md = webpage_text_clean(doc.url, markdown_text)
            doc.uuid = doc_uuid

            session.commit()

        print("All done.")
    finally:
        session.close()


if __name__ == '__main__':
    main()
