"""Wspólny pipeline: surowy markdown strony (step_1) + ekstrakcja artykułu przez LLM.

Używane przez:
- imports/dynamodb_sync.py (wsadowo: po synchronizacji z S3)
- imports/article_browser.py (interaktywnie: pobieranie tekstu i boundaries)

Konwencja cache: {CACHE_DIR}/markdown/{doc_id}/{doc_id}_step_1_all.md to surowy
markdown całej strony (wejście dla ekstrakcji LLM i porównania boundaries).
"""

import logging
import os

from library.llm_usage.context import llm_usage_context

logger = logging.getLogger(__name__)


def step1_path(cache_dir: str, document_id: int) -> str:
    """Ścieżka pliku surowego markdownu strony w katalogu cache dokumentu."""
    return os.path.join(cache_dir, f"{document_id}_step_1_all.md")


def ensure_raw_markdown(doc, cache_dir: str, verbose: bool = False) -> str | None:
    """Zwróć surowy markdown strony, pobierając i konwertując HTML gdy trzeba.

    Czyta {id}_step_1_all.md z cache jeśli istnieje. W przeciwnym razie pobiera
    HTML (cache/S3) przez prepare_markdown, zapisuje metadane dokumentu (_info.json)
    oraz plik step_1 i zwraca markdown. None gdy nie udało się pozyskać HTML.
    """
    # Lazy import: document_prepare ciągnie markitdown/html2text (extra "markdown"),
    # których nie chcemy ładować przy starcie skryptów nieużywających konwersji.
    from library.document_prepare import prepare_markdown, save_document_info

    os.makedirs(cache_dir, exist_ok=True)
    path = step1_path(cache_dir, doc.id)
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    save_document_info(doc.id, doc, cache_dir)
    markdown_text = prepare_markdown(doc.id, doc, cache_dir, verbose=verbose)
    if not markdown_text:
        return None

    with open(path, "w", encoding="utf-8") as f:
        f.write(markdown_text)
    return markdown_text


def extract_article(doc, cache_dir: str, verbose: bool = False, skip_llm: bool = False,
                    arklabs_first: bool = False,
                    operation: str = "article_extraction") -> tuple[str | None, str | None]:
    """Surowy markdown + ekstrakcja artykułu przez LLM (CloudFerro/ARK Labs fallback).

    Zwraca (raw_markdown, extracted_article):
    - (None, None) — nie udało się pozyskać markdownu (brak HTML w cache/S3)
    - (markdown, None) — markdown OK, ale LLM pominięty (skip_llm) lub nieudany
    - (markdown, artykuł) — pełny sukces
    """
    from library.article_extractor import process_article_with_llm_fallback

    markdown_text = ensure_raw_markdown(doc, cache_dir, verbose=verbose)
    if not markdown_text:
        return None, None

    if skip_llm:
        return markdown_text, None

    with llm_usage_context(document_id=doc.id):
        article = process_article_with_llm_fallback(
            markdown_text=markdown_text,
            document_id=doc.id,
            cache_dir=cache_dir,
            url=doc.url,
            arklabs_first=arklabs_first,
            operation=operation,
        )
    return markdown_text, article
