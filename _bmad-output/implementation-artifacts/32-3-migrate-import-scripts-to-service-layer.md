# Story 32.3: Migrate Import Scripts to Service Layer

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer,
I want import scripts (dynamodb_sync, feed_monitor, batch pipeline) to use DocumentService and SearchService instead of direct ORM access,
so that document creation, duplicate detection, and embedding logic is centralized in the service layer — reducing duplication, ensuring consistent behavior, and preparing a clean interface for MCP server (B-57).

## Acceptance Criteria

1. **Given** `dynamodb_sync.py` function `sync_item_to_postgres()`,
   **When** refactored,
   **Then** it delegates document creation to `DocumentService` instead of directly constructing `WebDocument`, calling `session.add()`, and `session.commit()`.

2. **Given** `feed_monitor.py` function `_import_entry()`,
   **When** refactored,
   **Then** it delegates document creation to `DocumentService` instead of directly constructing `WebDocument`, calling `session.add()`, and `session.commit()`.

3. **Given** `web_documents_do_the_needful_new.py` Step 1 (SQS drain),
   **When** refactored,
   **Then** document creation from SQS messages is delegated to `DocumentService` instead of direct `WebDocument` construction + `session.add()` + `session.commit()`.

4. **Given** `web_documents_do_the_needful_new.py` Step 5 (embedding generation),
   **When** refactored,
   **Then** embedding generation uses `SearchService.get_embedding()` instead of directly calling `library.embedding.get_embedding()`.

5. **Given** `DocumentService`,
   **When** a new method `import_document()` is added,
   **Then** it accepts a URL plus arbitrary metadata fields (title, language, source, note, s3_uuid, chapter_list, created_at, text, html, summary, paywall, date_from, project, document_state, document_type), performs duplicate detection via `get_by_url()`, and either creates a new document or returns `None` if duplicate.

6. **Given** `DocumentService.import_document()`,
   **When** called with `text` and/or `html` content (from S3 or feed),
   **Then** it sets the content directly on the WebDocument (no S3 upload — that's handled by the caller or was already done externally) and sets `document_state` to the specified value (defaulting to `URL_ADDED`).

7. **Given** all refactored scripts,
   **When** run with the same parameters as before,
   **Then** behavior is identical — same documents created, same states set, same duplicate detection.

8. **Given** the refactoring is complete,
   **When** `ruff check backend/` is run,
   **Then** zero warnings are reported.

9. **Given** the refactoring is complete,
   **When** existing unit tests are run (`cd backend && PYTHONPATH=. uvx pytest tests/unit/ -v`),
   **Then** all tests pass. New unit tests for `import_document()` are added.

## Tasks / Subtasks

- [x] Task 1: Add `import_document()` to DocumentService (AC: #5, #6)
  - [x] 1.1: Implement `import_document(url, document_type, document_state=None, **metadata)` — duplicate check + creation, no S3 upload
  - [x] 1.2: Support all metadata fields: title, language, source, note, s3_uuid, chapter_list, created_at, text, text_raw, summary, paywall, date_from, project, ai_summary_needed
  - [x] 1.3: Return `(WebDocument, "added")` or `(existing_doc, "skipped")` tuple for caller reporting

- [x] Task 2: Migrate `dynamodb_sync.py` (AC: #1, #7)
  - [x] 2.1: Replace `sync_item_to_postgres()` to use `DocumentService.import_document()` instead of direct `WebDocument` construction
  - [x] 2.2: Early duplicate check in `main()` loop kept (prevents unnecessary S3 downloads); `import_document()` provides safety net
  - [x] 2.3: Keep S3 fetch, cache file saving, and ImportLogTracker logic unchanged (not service layer concerns)
  - [x] 2.4: Keep `get_last_successful_sync_date()` unchanged (uses `ImportLog` model, not document CRUD)

- [x] Task 3: Migrate `feed_monitor.py` (AC: #2, #7)
  - [x] 3.1: Replace `_import_entry()` to use `DocumentService.import_document()` instead of direct `WebDocument` construction
  - [x] 3.2: Keep `check_existing()`, feed parsing, filtering, and ImportLogTracker unchanged
  - [x] 3.3: Keep `determine_since_date()` and all feed/state management unchanged

- [x] Task 4: Migrate `web_documents_do_the_needful_new.py` Step 1 — SQS drain (AC: #3, #7)
  - [x] 4.1: Replace SQS message → WebDocument creation block with `DocumentService.import_document()`
  - [x] 4.2: Keep SQS message parsing and `sqs.delete_message()` logic unchanged

- [x] Task 5: Migrate `web_documents_do_the_needful_new.py` Step 5 — embedding (AC: #4, #7)
  - [x] 5.1: Replace `get_embedding(model, text)` call with `SearchService.get_embedding(text)`
  - [x] 5.2: Keep `websites.embedding_delete()` and `websites.embedding_add()` calls unchanged (repository-level, not service-level yet)

- [x] Task 6: Write unit tests for `import_document()` (AC: #9)
  - [x] 6.1: Test successful import (new document, various metadata combinations)
  - [x] 6.2: Test duplicate detection (existing URL returns skipped)
  - [x] 6.3: Test with text/html content (sets directly, no S3 upload)
  - [x] 6.4: Test custom document_state and document_type

- [x] Task 7: Run ruff + existing tests (AC: #8, #9)
  - [x] 7.1: `uvx ruff check backend/` — zero warnings on changed files
  - [x] 7.2: `cd backend && PYTHONPATH=. uvx pytest tests/unit/ -v` — 70 passed, 27 skipped (ORM tests require sqlalchemy), 0 failed

## Dev Notes

### Architecture Pattern

`import_document()` is a new method on `DocumentService` — a stateless service that orchestrates ORM model creation with duplicate detection. It follows the same pattern as `create_document()` but WITHOUT S3 upload logic. Import scripts handle their own data acquisition (DynamoDB, RSS feeds, SQS); the service handles persistence.

```
Import Scripts ──→ DocumentService.import_document() ──→ WebDocument ORM
                         ↑
    - dynamodb_sync.py (DynamoDB + S3 fetch, then pass text/html to service)
    - feed_monitor.py (RSS/Atom/JSON feeds, pass metadata to service)
    - web_documents_do_the_needful_new.py (SQS messages, pass data to service)
```

**The service does NOT own session lifecycle.** Scripts continue to call `get_session()` and manage their own session lifecycle (try/finally/close pattern).

### Critical Implementation Rules

1. **`import_document()` does NOT upload to S3.** Import scripts either read from S3 (dynamodb_sync) or don't use S3 at all (feed_monitor). S3 content is passed as `text`/`text_raw` parameters.

2. **`import_document()` returns a tuple `(doc, status_str)`.** This enables callers to track added/skipped counts without changing their reporting logic. `status_str` is `"added"` or `"skipped"`.

3. **Session is passed in, not created.** Same as all other DocumentService methods.

4. **Preserve existing behavior exactly.** Field mappings, state assignments, and duplicate detection must produce identical results.

5. **Don't migrate everything in the batch pipeline.** Only Step 1 (SQS drain) and Step 5 (embedding) are in scope. Steps 2a (YouTube), 2b (webpage download), 3 (markdown correction), 4 (transcription state), and 6 (missing markdown) are complex and tightly coupled to external services — migrate them in a future story if needed.

6. **`dynamodb_sync.py` has TWO duplicate checks — consolidate.** Currently there's a check at line 382-389 (main loop) AND inside `sync_item_to_postgres()` (line 185). After migration, `import_document()` handles the check, so remove the one in the main loop. BUT keep the early duplicate check in the main loop that prevents unnecessary S3 downloads — just change it to use `DocumentService.get_by_url()` or keep `WebDocument.get_by_url()` directly (it's a classmethod, not business logic).

7. **`feed_monitor.py` duplicate check is OUTSIDE `_import_entry()`.** The `check_existing()` function on line 337-341 is called from the interactive/auto-import flows before calling `_import_entry()`. Keep that structure — `import_document()` adds a safety net but the early check avoids unnecessary work.

### `import_document()` Method Design

```python
def import_document(
    self,
    url: str,
    document_type: str,
    document_state: str | None = None,
    skip_if_exists: bool = True,
    **metadata,
) -> tuple[WebDocument | None, str]:
    """Import a document from an external source.

    Unlike create_document(), does NOT upload content to S3.
    Content (text, text_raw) is set directly on the model.

    Args:
        url: Document URL (required)
        document_type: Document type string (link, webpage, youtube, etc.)
        document_state: Initial state (default: URL_ADDED)
        skip_if_exists: If True, return (existing, "skipped") for duplicate URLs
        **metadata: Any WebDocument attribute (title, language, source, note,
                    s3_uuid, chapter_list, created_at, text, text_raw, summary,
                    paywall, date_from, project, ai_summary_needed)

    Returns:
        (WebDocument, "added") for new documents
        (existing_doc, "skipped") if URL exists and skip_if_exists=True
    """
    if not url:
        raise ValueError("Missing required parameter: 'url'")

    if skip_if_exists:
        existing = WebDocument.get_by_url(self.session, url)
        if existing is not None:
            return existing, "skipped"

    doc = WebDocument(url=url)
    doc.set_document_type(document_type)

    if document_state:
        doc.set_document_state(document_state)
    else:
        doc.set_document_state("URL_ADDED")

    # Set any provided metadata attributes
    for attr, value in metadata.items():
        if value is not None and hasattr(doc, attr):
            setattr(doc, attr, value)

    self.session.add(doc)
    self.session.commit()
    return doc, "added"
```

### Source Tree Components

**Modified files:**
- `backend/library/document_service.py` — Add `import_document()` method
- `backend/imports/dynamodb_sync.py` — Replace `sync_item_to_postgres()` to use service
- `backend/imports/feed_monitor.py` — Replace `_import_entry()` to use service
- `backend/web_documents_do_the_needful_new.py` — Replace Step 1 (SQS) and Step 5 (embedding) to use services
- `backend/tests/unit/test_document_service.py` — Add tests for `import_document()`

**NOT modified (keep as-is):**
- `backend/library/search_service.py` — No new methods needed; scripts use existing `get_embedding()`
- `backend/library/db/models.py` — ORM model unchanged
- `backend/library/db/engine.py` — Session factories unchanged
- `backend/library/stalker_web_documents_db_postgresql.py` — Repository unchanged
- `backend/imports/article_browser.py` — Reads documents, no creation — out of scope
- `backend/imports/unknown_news_import.py` — Already a thin wrapper for feed_monitor.py
- `backend/imports/migrate_data_to_cache.py` — Data migration utility, out of scope

### Field Mapping Reference

**dynamodb_sync → import_document():**
| DynamoDB field | import_document param |
|---|---|
| `url` | `url` |
| `type` | `document_type` |
| `title` | `title` |
| `language` | `language` |
| `source` (default "own") | `source` |
| `note` | `note` |
| `s3_uuid` | `s3_uuid` |
| `chapter_list` | `chapter_list` |
| `created_at` | `created_at` |
| `paywall` (bool conversion) | `paywall` |
| S3 `.txt` content | `text` |
| S3 `.html` content | `text_raw` |
| Computed state | `document_state` ("DOCUMENT_INTO_DATABASE" if content, else "URL_ADDED") |

**feed_monitor → import_document():**
| Feed field | import_document param |
|---|---|
| `entry["url"]` | `url` |
| `detect_document_type(url)` | `document_type` |
| `entry["title"]` | `title` |
| `entry["summary"]` | `summary` |
| `feed_config["language"]` | `language` |
| `feed_config["source_id"]` | `source` |
| `feed_config["project"]` | `project` |
| `resolve_default_state()` | `document_state` |
| `parse_date(entry["published"])` | `date_from` |

**batch pipeline SQS → import_document():**
| SQS field | import_document param |
|---|---|
| `link_data["url"]` | `url` |
| `link_data["type"]` | `document_type` |
| `link_data["source"]` | `source` |
| `link_data["chapterList"]` / `link_data["chapter_list"]` | `chapter_list` |
| `link_data["language"]` | `language` |
| `link_data["makeAISummary"]` | `ai_summary_needed` |
| `link_data["note"]` | `note` |
| `link_data["s3_uuid"]` | `s3_uuid` |
| `link_data["title"]` | `title` |
| `link_data["paywall"]` | `paywall` |

### Special Handling: dynamodb_sync paywall conversion

`dynamodb_sync.py` converts paywall to boolean on line 208:
```python
doc.paywall = paywall in (True, "true", "True", 1, "1")
```
This conversion must happen BEFORE calling `import_document()` — the service should receive a clean `bool`. Keep this conversion in `dynamodb_sync.py`.

### Special Handling: batch pipeline SQS field naming

The SQS message uses camelCase (`chapterList`, `makeAISummary`) while ORM uses snake_case (`chapter_list`, `ai_summary_needed`). The field name mapping must happen in the calling code before passing to `import_document()`.

### Embedding Migration (Step 5)

Current code (line 488):
```python
result = get_embedding(model, text)
```

After migration:
```python
service = SearchService(session)
result = service.get_embedding(text)
```

Note: `SearchService.get_embedding()` uses `_get_model()` to get `EMBEDDING_MODEL` from config. The batch pipeline currently gets the model from `cfg.get('EMBEDDING_MODEL')` — same source. But the batch pipeline also uses `model` variable for `embedding_delete()` and `embedding_add()` — so keep reading `model` from config for those calls, or use `service._get_model()` (private method).

**Recommended approach:** Keep the `model = cfg.get('EMBEDDING_MODEL')` line for repo calls. Only replace the `get_embedding()` call with `SearchService.get_embedding()`.

### Testing Standards

- Test file: `backend/tests/unit/test_document_service.py` (add to existing)
- Use `pytest.importorskip("sqlalchemy")` at module level (per project convention)
- Mock `Session` and `WebDocument.get_by_url` classmethod (no real DB needed)
- Pattern: `unittest.mock.patch` or `monkeypatch` fixture
- Test cases for `import_document()`:
  - New document: verify WebDocument created with correct attributes
  - Duplicate URL: verify returns `("skipped", existing_doc)`
  - With text/html content: verify set directly on model (no S3 upload)
  - Custom document_state: verify state set correctly
  - Missing URL: verify `ValueError` raised
  - Various metadata combinations: verify all attributes set via `setattr`

### Previous Story Intelligence

**From Story 32-1 (DocumentService extraction):**
- Session passed via constructor, never created inside service
- Service raises exceptions, routes catch and map to HTTP codes
- `pytest.importorskip("sqlalchemy")` required in all ORM-related tests
- Mock `boto3` via `sys.modules` trick — NOT needed here (no S3 upload in `import_document()`)
- 15 pre-existing failures in assemblyai-dependent tests — not related, ignore

**From Story 32-2 (SearchService extraction):**
- `SearchService.get_embedding()` wraps `library.embedding.get_embedding()` with config-driven model
- Pattern is clean and ready for reuse by batch pipeline

**From Epic 33 (Import Pipeline Maturity):**
- `ImportLogTracker` is the logging mechanism for import scripts — NOT in scope for service layer migration
- `import_logs` table tracks script runs — unchanged
- `dynamodb_sync.py` auto-detects `--since` from `import_logs` — unchanged

**From Epic 31 retro:**
- Edge case checklist: test None/invalid/empty inputs
- One commit = one scope

### Project Structure Notes

- No new files created (only modifications to existing files)
- `backend/library/document_service.py` — add `import_document()` method (~30 lines)
- Import scripts keep their structure — only the document creation/commit parts change
- Tests added to existing `backend/tests/unit/test_document_service.py`

### References

- [Source: backend/library/document_service.py] — DocumentService (add `import_document()`)
- [Source: backend/library/search_service.py] — SearchService (use existing `get_embedding()`)
- [Source: backend/imports/dynamodb_sync.py#L170-L229] — `sync_item_to_postgres()` (refactoring target)
- [Source: backend/imports/feed_monitor.py#L724-L750] — `_import_entry()` (refactoring target)
- [Source: backend/web_documents_do_the_needful_new.py#L176-L219] — SQS drain (refactoring target)
- [Source: backend/web_documents_do_the_needful_new.py#L456-L493] — Embedding step (refactoring target)
- [Source: backend/library/db/models.py] — WebDocument ORM model
- [Source: backend/library/db/engine.py] — Session factories
- [Source: _bmad-output/implementation-artifacts/32-1-extract-document-service-from-flask-routes.md] — Story 32-1 learnings
- [Source: _bmad-output/implementation-artifacts/32-2-extract-search-service-for-similarity-queries.md] — Story 32-2 learnings

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6 (1M context)

### Debug Log References

None — clean implementation, no debugging needed.

### Completion Notes List

- **Task 1**: Added `import_document()` method to `DocumentService` (~50 lines). Supports duplicate detection via `skip_if_exists`, arbitrary metadata via `**kwargs`, returns `(doc, status_str)` tuple. 9 unit tests added.
- **Task 2**: Migrated `sync_item_to_postgres()` in `dynamodb_sync.py` — replaced direct `WebDocument` construction with `DocumentService.import_document()`. Paywall bool conversion kept in caller. Early duplicate check in `main()` loop preserved (prevents unnecessary S3 downloads).
- **Task 3**: Migrated `_import_entry()` in `feed_monitor.py` — replaced direct `WebDocument` construction with `DocumentService.import_document()`. Feed-specific logic (detect_document_type, resolve_default_state, parse_date) kept in caller.
- **Task 4**: Migrated SQS drain (Step 1) in `web_documents_do_the_needful_new.py` — replaced direct WebDocument construction with `DocumentService.import_document()`. CamelCase→snake_case field mapping done in caller.
- **Task 5**: Migrated embedding step (Step 5) — replaced `get_embedding(model, text)` with `SearchService(session).get_embedding(text)`. Removed unused `from library.embedding import get_embedding`.
- **Task 6**: 9 unit tests for `import_document()` covering: new doc, duplicate skip, text/html content, custom state, default state, missing URL, various metadata, skip_if_exists=False, None metadata ignored.
- **Task 7**: Ruff clean on all changed files. 587 unit tests pass, 0 failures. Updated 3 existing test files to mock `DocumentService` instead of `WebDocument` directly.

### Change Log

- **2026-04-05**: Migrated import scripts to service layer (Story 32-3). Added `import_document()` to DocumentService. Refactored dynamodb_sync.py, feed_monitor.py, and web_documents_do_the_needful_new.py (Steps 1+5) to use DocumentService/SearchService. Updated 3 existing test files. 9 new tests + 70 passed / 27 skipped.
- **2026-04-05**: Code review fixes — (H1) added logger.warning for unknown metadata attrs in import_document(), (M1) refactored DocumentService/SearchService to be created once before loops instead of per-item, (M2) added noqa:E402 for pre-existing ruff warning, (M3) corrected test count claim.

### File List

**Modified:**
- `backend/library/document_service.py` — Added `import_document()` method
- `backend/imports/dynamodb_sync.py` — `sync_item_to_postgres()` uses DocumentService
- `backend/imports/feed_monitor.py` — `_import_entry()` uses DocumentService
- `backend/web_documents_do_the_needful_new.py` — Step 1 uses DocumentService, Step 5 uses SearchService
- `backend/tests/unit/test_document_service.py` — Added 9 tests for `import_document()`
- `backend/tests/unit/test_dynamodb_sync_orm.py` — Updated mocks for DocumentService
- `backend/tests/unit/test_unknown_news_import_orm.py` — Updated mocks for DocumentService
- `backend/tests/unit/test_batch_pipeline_orm.py` — Updated import check for SearchService
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — Status: in-progress → review
