"""Download missing markdown for documents already in the database.

Re-downloads the webpage HTML, uploads it to S3, converts to markdown
via MarkItDown, and stores the result in the database.

Usage:
    cd backend
    python web_documents_fix_missing_markdown.py
"""

import uuid

import boto3
from markitdown import MarkItDown

from library.config_loader import load_config
from library.stalker_web_document import StalkerDocumentStatus, StalkerDocumentStatusError
from library.stalker_web_document_db import StalkerWebDocumentDB
from library.stalker_web_documents_db_postgresql import WebsitesDBPostgreSQL
from library.website.website_download_context import download_raw_html

cfg = load_config()

# TODO: sprawdzić, dlaczego jest problem z pobraniem poniższych stron
problems = [38, 89, 150, 157, 191, 208, 220, 311, 371, 376, 396,
            443, 456, 465, 470, 486, 497, 499, 503, 531, 553, 581, 592, 600, 601, 602, 611, 662,
            664, 668, 686, 694, 1013, 6735, 6863, 6878, 6883, 6904, 6913, 6918, 6923, 6926, 6930, 7025]

# 611 certificate expired

if __name__ == '__main__':
    if not cfg.get("AWS_S3_WEBSITE_CONTENT"):
        print("The S3 bucket for text and html files is not set, exiting.")
        exit(1)

    websites = WebsitesDBPostgreSQL()

    print("Adding missing markdown entries")

    document_id_start = max(problems) if len(problems) > 0 else 0
    md_needed = websites.get_documents_md_needed(min=document_id_start)
    print(md_needed)

    s3 = boto3.client('s3')

    for document_id in md_needed:
        web_doc = StalkerWebDocumentDB(document_id=document_id)

        if web_doc.paywall:
            print("Need manual download")
            continue

        if web_doc.id in problems:
            print(f"Skipping problem on {document_id}")
            continue

        print(f"Downloading {web_doc.id} {web_doc.url}, md len({len(web_doc.text_md)})")

        html = download_raw_html(url=web_doc.url)
        if not html:
            print("empty response! [ERROR]")
            web_doc.document_state = StalkerDocumentStatus.ERROR
            web_doc.document_state_error = StalkerDocumentStatusError.ERROR_DOWNLOAD
            web_doc.save()
            continue

        try:
            html = html.decode("utf-8")
        except UnicodeDecodeError:
            import chardet

            detected_encoding = chardet.detect(html)['encoding']
            print(f"Detected encoding: {detected_encoding}")
            if detected_encoding:
                html = html.decode(detected_encoding, errors="replace")
            else:
                print("Encoding detection failed, using replacement characters.")
                html = html.decode("latin-1", errors="replace")

        s3_uuid = str(uuid.uuid4())
        file_name = f"{s3_uuid}.html"

        try:
            s3.put_object(Bucket=cfg.get("AWS_S3_WEBSITE_CONTENT"), Key=file_name, Body=html)
            print(f"Successfully uploaded {file_name} to {cfg.get('AWS_S3_WEBSITE_CONTENT')}")
        except Exception as e:
            error_message = f"Failed to upload {file_name} to {cfg.get('AWS_S3_WEBSITE_CONTENT')}: {str(e)}"
            print(error_message)
            exit(1)

        page_file = f"tmp/{s3_uuid}.html"
        with open(f"{page_file}", 'w', encoding="utf-8") as file:
            file.write(html)

        md = MarkItDown()
        result = md.convert(page_file)

        md_file = f"tmp/{s3_uuid}.md"
        with open(f"{md_file}", 'w', encoding="utf-8") as file:
            file.write(result.text_content)

        md_cleaned = result.text_content

        web_doc.text_md = md_cleaned
        web_doc.s3_uuid = s3_uuid

        web_doc.save()

    websites.close()
    print("All done.")
