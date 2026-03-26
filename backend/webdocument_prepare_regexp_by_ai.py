"""
Skrypt do przygotowania reguł regex dla artykułów za pomocą LLM.

Pobiera HTML z S3, konwertuje do markdown, a następnie:
1. Próbuje wyekstrahować artykuł za pomocą LLM (Bielik)
2. Generuje plik .regex.draft do ręcznej weryfikacji
3. Zapisuje wyekstrahowany artykuł i metadane do cache

Użycie:
    uv run python webdocument_prepare_regexp_by_ai.py 8779 8786
"""

import sys
import os.path
import logging

from library.db.engine import get_session
from library.db.models import WebDocument
from library.stalker_web_documents_db_postgresql import WebsitesDBPostgreSQL
from library.config_loader import load_config
from library.article_extractor import process_article_with_llm_fallback
from library.document_prepare import prepare_markdown, save_document_info

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def parse_document_ids():
    """Parsuj ID dokumentów z argumentów CLI."""
    if len(sys.argv) < 2:
        print(f"Użycie: {sys.argv[0]} <document_id> [document_id ...]")
        print(f"Przykład: {sys.argv[0]} 8779 8786")
        sys.exit(1)

    ids = []
    for arg in sys.argv[1:]:
        try:
            ids.append(int(arg))
        except ValueError:
            print(f"Błąd: '{arg}' nie jest prawidłowym ID dokumentu")
            sys.exit(1)
    return ids


if __name__ == '__main__':
    documents = parse_document_ids()

    cfg = load_config()
    cache_dir_base = cfg.get("CACHE_DIR") or "tmp/markdown"

    session = get_session()

    logger.info(f"Documents to process: {documents}")

    try:
        for document_id in documents:
            doc = WebDocument.get_by_id(session, document_id)
            if doc is None:
                logger.warning(f"document_id: {document_id} Not found, skipping")
                continue

            logger.info(f"document_id: {document_id} URL: {doc.url}")
            logger.info(f"document_id: {document_id} Title: {doc.title}")
            logger.info(f"document_id: {document_id} State: {doc.document_state}")

            cache_dir = os.path.join(cache_dir_base, str(document_id))
            os.makedirs(cache_dir, exist_ok=True)

            save_document_info(document_id, doc, cache_dir)

            markdown_text = prepare_markdown(document_id, doc, cache_dir)
            if markdown_text is None:
                continue

            result = process_article_with_llm_fallback(
                markdown_text=markdown_text,
                document_id=document_id,
                cache_dir=cache_dir,
                url=doc.url,
            )

            if result:
                lines = [l for l in result.splitlines() if l.strip()]
                logger.info(f"document_id: {document_id} Extracted: {len(result)} chars, {len(lines)} non-empty lines")
                logger.info(f"document_id: {document_id} FIRST: {lines[0][:100]}")
                logger.info(f"document_id: {document_id} LAST:  {lines[-1][:100]}")
            else:
                logger.error(f"document_id: {document_id} Extraction FAILED")

    finally:
        session.close()
