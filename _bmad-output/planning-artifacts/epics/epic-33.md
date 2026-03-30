## Epic 33: Import Pipeline Maturity — Cache Consolidation, Operation Logging & Article Review Tracking

Developer has a unified cache directory for all processing scripts, automatic tracking of import operations (no manual `--since` guessing), and database-backed tracking of article reviews and Obsidian notes — enabling efficient knowledge management workflows.

**Stories:** 33-1, 33-2, 33-3, 33-4

Implementation notes:
- Story 33-1 is independent and can be done first or in parallel with 33-2
- Story 33-2 must be completed before 33-3 (33-3 uses import_logs to auto-detect --since)
- Story 33-4 is independent (Alembic migration + article_browser.py changes)
- ADR-014 documents the design decision for Story 33-4: [docs/adr-014-article-review-tracking.md](../../docs/adr-014-article-review-tracking.md)

### Story 33.1: Consolidate Cache Directories Under Single CACHE_DIR

As a **developer**,
I want all processing scripts to use a single, configurable cache directory with well-defined subdirectories,
so that cached files are easy to find, manage, and clean up.

**Acceptance Criteria:**

**Given** multiple scripts use different tmp directories (`backend/tmp/`, `backend/imports/tmp/`, `backend/test_code/tmp/`, `backend/cache/`)
**When** the developer consolidates them
**Then** all scripts use `CACHE_DIR` from config (default: `backend/tmp`) as the root cache directory

**Given** cache is consolidated under one root
**When** the developer organizes subdirectories
**Then** the structure is:
```
{CACHE_DIR}/
├── markdown/{doc_id}/          # HTML→markdown processing (document_prepare, article_extractor)
├── youtube_to_text/{doc_id}/   # YouTube transcript processing
└── article_notes/{doc_id}/     # article_browser.py personal notes
```

**Given** scripts currently use hardcoded paths (`"tmp"`, `"tmp/markdown"`, `"cache"`)
**When** the developer updates them
**Then** all scripts resolve cache root via `cfg.get("CACHE_DIR") or "tmp"` — one pattern everywhere

**Given** `dynamodb_sync.py` has `--data-dir` CLI override
**When** the developer updates the default
**Then** default changes from `"tmp/markdown"` to `os.path.join(CACHE_DIR, "markdown")`

**Given** `youtube_processing.py` uses `os.getenv("CACHE_DIR", "cache")` fallback
**When** the developer updates it
**Then** it uses the same `cfg.get("CACHE_DIR") or "tmp"` pattern as other scripts

**Given** the consolidation is complete
**When** the developer verifies
**Then** `backend/imports/tmp/`, `backend/test_code/tmp/`, and `backend/cache/` are removed (contents migrated or confirmed empty)
**And** `.gitignore` covers `backend/tmp/` (already does)

**Files to update:** `dynamodb_sync.py`, `article_browser.py`, `web_documents_do_the_needful_new.py`, `webdocument_prepare_regexp_by_ai.py`, `markdown_to_embedding.py`, `youtube_processing.py`, `stalker_youtube_file.py`, `obsidian_clean_jurnal.py`, `migrate_data_to_cache.py`

**Technical notes:**
- `infra/aws/serverless/lambdas/tmp/` and `infra/aws/serverless/lambda_layers/tmp/` are build artifacts — NOT in scope (different purpose)
- Library modules (`document_prepare.py`, `article_extractor.py`) receive `cache_dir` as function parameter — no change needed in the library, only in callers

### Story 33.2: Create import_logs Table for Operation Tracking

As a **developer**,
I want all import scripts to log their operations to a database table,
so that I can see what was imported, when, and with what results — without manual tracking.

**Acceptance Criteria:**

**Given** no operation tracking exists for import scripts
**When** the developer creates an Alembic migration
**Then** a new table `import_logs` is created:

```sql
CREATE TABLE import_logs (
    id SERIAL PRIMARY KEY,
    script_name VARCHAR(100) NOT NULL,        -- e.g. 'dynamodb_sync', 'unknown_news_import'
    started_at TIMESTAMP NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMP,
    status VARCHAR(20) NOT NULL DEFAULT 'running',  -- running, success, error
    since_date DATE,                           -- --since parameter used
    until_date DATE,                           -- end of range (usually today)
    items_found INTEGER DEFAULT 0,
    items_added INTEGER DEFAULT 0,
    items_skipped INTEGER DEFAULT 0,
    items_error INTEGER DEFAULT 0,
    parameters JSONB DEFAULT '{}',            -- CLI args for reproducibility
    error_message TEXT,                        -- if status=error
    notes TEXT                                 -- optional human notes
);

CREATE INDEX idx_import_logs_script ON import_logs(script_name, started_at DESC);
```

**Given** `dynamodb_sync.py` finishes a sync
**When** the script writes to `import_logs`
**Then** a row is inserted with script_name='dynamodb_sync', counts, date range, and status

**Given** `unknown_news_import.py` finishes an import
**When** the script writes to `import_logs`
**Then** a row is inserted with script_name='unknown_news_import', counts, and status

**Given** an import script fails with an exception
**When** the error handler runs
**Then** the `import_logs` row is updated with `status='error'` and `error_message`

**Given** the table exists
**When** a developer queries recent operations
**Then** `SELECT * FROM import_logs ORDER BY started_at DESC LIMIT 10` shows the last 10 import runs with their results

**Technical notes:**
- ORM model: `ImportLog` in `backend/library/db/models.py`
- Helper: `ImportLogTracker` context manager — `with ImportLogTracker('dynamodb_sync', session, params) as tracker:` ... `tracker.set_counts(added=5, skipped=2)`
- Both scripts already use `get_session()` — reuse existing session for logging

### Story 33.3: Auto-detect --since in dynamodb_sync from import_logs

As a **developer**,
I want `dynamodb_sync.py` to automatically determine the `--since` date from the last successful run,
so that I don't have to remember or look up the date manually.

**Acceptance Criteria:**

**Given** `import_logs` has a previous successful run for 'dynamodb_sync'
**When** the developer runs `dynamodb_sync.py` without `--since`
**Then** the script queries `import_logs` for the most recent successful run and uses its `until_date` as the `--since` value
**And** prints: `Auto-detected --since 2026-03-25 from last successful sync`

**Given** `import_logs` has no previous runs for 'dynamodb_sync'
**When** the developer runs `dynamodb_sync.py` without `--since`
**Then** the script prints an error: `No previous sync found. Please provide --since YYYY-MM-DD for the first run.`
**And** exits with non-zero code

**Given** the developer provides `--since` explicitly
**When** the script runs
**Then** the explicit date overrides auto-detection
**And** prints: `Using explicit --since 2026-03-20 (overriding auto-detected 2026-03-25)`

**Given** `unknown_news_import.py` already auto-detects from the latest DB entry
**When** the developer reviews it
**Then** optionally add `import_logs` as a secondary source (lower priority — existing behavior is preserved)

**Technical notes:**
- Query: `SELECT until_date FROM import_logs WHERE script_name = 'dynamodb_sync' AND status = 'success' ORDER BY started_at DESC LIMIT 1`
- `--since` becomes optional (was required)
- `unknown_news_import.py` already has auto-detection via `get_last_unknown_news()` — `import_logs` is complementary, not a replacement

### Story 33.4: Add Article Review and Obsidian Note Tracking (B-101)

As a **developer**,
I want to track which articles I've reviewed and which have Obsidian notes in the database,
so that `article_browser.py` can filter to unprocessed articles and I don't duplicate knowledge work.

**Design decision:** [ADR-014](../../docs/adr-014-article-review-tracking.md) — Columns now, join table for multi-user in Phase 9.

**Acceptance Criteria:**

**Given** no review tracking exists
**When** the developer creates an Alembic migration
**Then** two columns are added to `web_documents`:
- `reviewed_at TIMESTAMP` (nullable, default NULL)
- `obsidian_note_paths JSONB NOT NULL DEFAULT '[]'`

**Given** the ORM model is updated
**When** the developer adds the columns to `WebDocument`
**Then** `reviewed_at` is `Mapped[datetime | None]` and `obsidian_note_paths` is `Mapped[list]` with JSONB type and `default=[]`

**Given** `article_browser.py` review mode
**When** the user presses `[d]` (mark as reviewed) on an article
**Then** `reviewed_at` is set to `NOW()` for that document

**Given** `article_browser.py` review mode
**When** the user presses `[o]` (obsidian) and creates a note
**Then** the Obsidian note path is appended to `obsidian_note_paths` array
**And** `reviewed_at` is also set if not already set

**Given** `article_browser.py` is invoked with `--not-reviewed`
**When** the document list is filtered
**Then** only documents with `reviewed_at IS NULL` are shown

**Given** `article_browser.py` is invoked with `--no-obsidian`
**When** the document list is filtered
**Then** only documents with `obsidian_note_paths = '[]'` are shown

**Given** `article_browser.py` list mode
**When** articles are displayed
**Then** each article shows review status (date or `-`) and Obsidian note count

**Given** a user creates multiple Obsidian notes from one article (e.g. per country, per topic)
**When** each note is created via `[o]` action
**Then** each path is appended to the JSONB array — no overwrite of previous notes

**Technical notes:**
- JSONB array example: `["02-wiedza/Geopolityka/Sankcje-UE.md", "02-wiedza/Wojsko/Wojna-dronowa.md"]`
- Append: `UPDATE web_documents SET obsidian_note_paths = obsidian_note_paths || '["path"]'::jsonb WHERE id = :id`
- Filter: `WHERE obsidian_note_paths = '[]'` (no GIN index needed — equality on empty array is fast)
- Multi-user migration plan documented in ADR-014 (Phase 9: split into `user_document_reviews` + `user_obsidian_notes` tables)
- Subsumes backlog item B-101
