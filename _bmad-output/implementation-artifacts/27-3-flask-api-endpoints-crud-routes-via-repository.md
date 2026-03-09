# Story 27.3: Flask API Endpoints — CRUD Routes via Repository

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **developer**,
I want Flask route handlers updated to use the ORM repository with scoped session,
so that the React frontend receives identical API responses after the migration.

## Acceptance Criteria

1. **Given** Flask app with scoped session **When** `GET /website_list?document_type=link&limit=20` is called **Then** route creates `WebsitesDBPostgreSQL(scoped_session())`, calls `get_list()`, returns JSON response identical to pre-migration format

2. **Given** a document with ID exists **When** `GET /website_get?id=42` is called **Then** route returns full document dict with navigation fields (`next_id`, `next_type`, `previous_id`, `previous_type`) populated via `load_neighbors()`

3. **Given** valid document data in request body **When** `POST /website_save` is called **Then** route creates or updates document via ORM model and `session.commit()`, returns success response

4. **Given** a document ID **When** `DELETE /website_delete?id=42` is called **Then** route deletes document via `session.delete()` with cascade (embeddings removed), returns success response

5. **Given** any Flask endpoint completes (success or error) **When** request teardown occurs **Then** `scoped_session.remove()` is called via `@app.teardown_appcontext`

6. **Given** frontend makes API calls before and after migration **When** response JSON is compared **Then** field names, value types, and date formats are identical

**Covers:** FR39, FR40, FR41, FR42 | NFR1 (partial)

## Tasks / Subtasks

- [x] Task 1: Remove global `websites` variable and module-level DB call (AC: #1, #5)
  - [x] 1.1 Remove line 49: `websites = WebsitesDBPostgreSQL()` — this legacy psycopg2 global instance is replaced by per-request scoped session
  - [x]1.2 Remove line 60: `logging.info(f"all pages in database: {websites.get_count()}")` — this startup validation call uses the global instance. If startup count is desired, add it as a lazy log inside the first `/website_list` call or remove entirely (it triggers DB connection at module import time)
  - [x]1.3 Verify all other references to global `websites` variable are migrated in subsequent tasks

- [x]Task 2: Migrate `/website_list` endpoint (AC: #1, #6)
  - [x]2.1 Replace `websites.get_list(...)` with per-request `session = get_scoped_session(); repo = WebsitesDBPostgreSQL(session); repo.get_list(...)`
  - [x]2.2 Replace `websites.get_list(..., count=True)` with `repo.get_list(..., count=True)` using same repo instance
  - [x]2.3 Preserve exact response format: `{"status": "success", "message": "Dane odczytane pomyślnie.", "encoding": "utf8", "websites": [...], "all_results_count": N}`
  - [x]2.4 Preserve all query parameters: `type`, `document_state`, `search_in_document`
  - [x]2.5 Write unit test: verify response format with mocked session and repo

- [x]Task 3: Migrate `/website_count` endpoint (AC: #1)
  - [x]3.1 Replace `websites.get_count_by_type()` with per-request `session = get_scoped_session(); repo = WebsitesDBPostgreSQL(session); repo.get_count_by_type()`
  - [x]3.2 Preserve exact response format: `{"status": "success", "counts": {...}}`

- [x]Task 4: Migrate `/website_get` endpoint (AC: #2, #6)
  - [x]4.1 Replace `StalkerWebDocumentDB(document_id=int(link_id), reach=True)` with `session = get_scoped_session(); doc = WebDocument.get_by_id(session, int(link_id), reach=True)`
  - [x]4.2 Add `None` check: if `doc is None`, return `{"status": "error", "message": "Document not found"}`, 404
  - [x]4.3 Return `doc.dict()` — WebDocument.dict() already matches StalkerWebDocumentDB.dict() format (verified in Story 27.1 AC#6)
  - [x]4.4 Write unit test: found (with reach), not found (404)

- [x]Task 5: Migrate `/website_get_next_to_correct` endpoint (AC: #1)
  - [x]5.1 Replace `websites.get_next_to_correct(link_id)` with per-request `session = get_scoped_session(); repo = WebsitesDBPostgreSQL(session); repo.get_next_to_correct(link_id)`
  - [x]5.2 Preserve exact response format: `{"status": "success", "next_id": N, "next_type": "..."}`
  - [x]5.3 Handle `-1` return (not found) — current behavior returns `next_id: -1`

- [x]Task 6: Migrate `/website_save` endpoint (AC: #3, #6)
  - [x]6.1 Replace `StalkerWebDocumentDB(document_id=int(link_id))` and `StalkerWebDocumentDB(url=url)` with ORM lookups: `session = get_scoped_session(); doc = WebDocument.get_by_id(session, int(link_id))` or `doc = WebDocument.get_by_url(session, url)`
  - [x]6.2 For new documents: `doc = WebDocument(url=url); session.add(doc)`
  - [x]6.3 Update attributes from `request.form`: text, title, language, tags, summary, source, author, note
  - [x]6.4 Call domain methods: `doc.set_document_state(...)`, `doc.set_document_type(...)`, `doc.analyze()`
  - [x]6.5 Call `session.commit()` explicitly to persist changes (scoped_session auto-commit is NOT guaranteed — Flask uses `remove()` not `commit()` in teardown)
  - [x]6.6 Call `session.flush()` after add for new documents to get `doc.id`
  - [x]6.7 Preserve exact response format: `{"status": "success", "message": "Dane strony {id} zaktualizowane pomyślnie."}`
  - [x]6.8 Preserve error handling: try/except with `{"status": "error", "message": str(e)}`, 500
  - [x]6.9 Write unit test: update existing doc, create new doc, error handling

- [x]Task 7: Migrate `/website_delete` endpoint (AC: #4, #6)
  - [x]7.1 Replace `StalkerWebDocumentDB(document_id=link_id)` with `session = get_scoped_session(); doc = WebDocument.get_by_id(session, link_id)`
  - [x]7.2 If `doc is None`: return same response as current code (`"Page doesn't exist in database"`, 200)
  - [x]7.3 Replace `web_document.delete()` with `session.delete(doc)` + `session.commit()` — cascade handles embedding deletion
  - [x]7.4 Preserve exact response format: `{"status": "success", "message": "Page has been deleted from database", "encoding": "utf8"}`
  - [x]7.5 Write unit test: delete existing, delete non-existent

- [x]Task 8: Migrate `/url_add` endpoint (AC: #3, #6)
  - [x]8.1 Replace `StalkerWebDocumentDB()` empty constructor + manual attribute assignment + `.save()` with `session = get_scoped_session(); doc = WebDocument(url=target_url); session.add(doc)`
  - [x]8.2 Set all attributes via ORM model: `doc.set_document_type(url_type)`, `doc.note = note`, `doc.title = title`, `doc.language = language`, `doc.paywall = paywall`, `doc.source = source`, `doc.ai_summary_needed = ai_summary`, `doc.chapter_list = chapter_list`, `doc.s3_uuid = s3_uuid`, `doc.set_document_state("URL_ADDED")`
  - [x]8.3 **Skip `ai_correction_needed`** — column does NOT exist in DB or ORM model (pre-existing bug, line 265)
  - [x]8.4 Call `session.commit()` explicitly, then `session.flush()` or check `doc.id` after commit
  - [x]8.5 Preserve exact response format: `{"status": "success", "message": "Successfully saved document with ID: {id}", "document_id": id}`
  - [x]8.6 Preserve S3 upload logic UNCHANGED — only the database save part is migrated
  - [x]8.7 Write unit test: successful add, missing required params

- [x]Task 9: Migrate `/website_similar` endpoint (AC: #1)
  - [x]9.1 Replace `websites.get_similar(...)` with per-request `session = get_scoped_session(); repo = WebsitesDBPostgreSQL(session); repo.get_similar(...)`
  - [x]9.2 **NOTE**: `get_similar()` is NOT yet migrated to ORM (Epic 28). It still uses legacy psycopg2 `self.conn`. The dual-mode constructor handles this — when `session` is provided, legacy methods that need `self.conn` will fail. **Decision**: Keep this endpoint using legacy global instance for now, OR pass `session=None` to trigger legacy mode
  - [x]9.3 **ALTERNATIVE**: Leave `/website_similar` using a separate legacy `WebsitesDBPostgreSQL()` instance (no session) specifically for `get_similar()`. Mark with TODO comment for Epic 28 migration
  - [x]9.4 Preserve exact response format unchanged

- [x]Task 10: Update import statements (AC: #1)
  - [x]10.1 Add import: `from library.db.models import WebDocument`
  - [x]10.2 Add import: `from library.db.engine import get_scoped_session`
  - [x]10.3 Keep import of `WebsitesDBPostgreSQL` (still used for repository queries)
  - [x]10.4 Evaluate if `StalkerWebDocumentDB` import can be removed entirely — check if any unmigrated endpoint still uses it. If all CRUD endpoints are migrated, remove the import
  - [x]10.5 Keep `StalkerWebDocumentDB` import if `/website_similar` still needs legacy mode via `StalkerWebDocumentDB.db_conn` class-level connection

- [x]Task 11: Handle transaction boundaries (AC: #3, #4, #5)
  - [x]11.1 For read-only endpoints (`/website_list`, `/website_get`, `/website_count`, `/website_get_next_to_correct`): NO explicit commit needed
  - [x]11.2 For write endpoints (`/website_save`, `/website_delete`, `/url_add`): call `session.commit()` explicitly after successful mutation
  - [x]11.3 For error paths: call `session.rollback()` in except blocks for write endpoints
  - [x]11.4 Teardown `shutdown_session()` already calls `scoped_session.remove()` (Story 26.3) — this is cleanup, NOT commit

- [x]Task 12: Quality checks
  - [x]12.1 `uvx ruff check backend/` — zero new warnings
  - [x]12.2 All existing unit tests pass: `cd backend && PYTHONPATH=. .venv/Scripts/python -m pytest tests/unit/ -v`
  - [x]12.3 No new dependencies added — no `.venv_wsl` sync needed
  - [x]12.4 Integration tests (if available): verify response formats match pre-migration

## Dev Notes

### Architecture Decisions (MUST follow)

**Per-request session pattern** (from [architecture.md#Session Lifecycle, lines 1712-1728]):
```python
@app.route("/website_list")
def website_list():
    from library.db.engine import get_scoped_session
    session = get_scoped_session()
    repo = WebsitesDBPostgreSQL(session)
    results = repo.get_list(...)
    return jsonify(results)
    # Session cleaned up automatically by @app.teardown_appcontext
```

**Key rules:**
- Call `get_scoped_session()` inside each route handler (lazy initialization)
- Create repository with `WebsitesDBPostgreSQL(session)`
- DO NOT call `session.close()` in route handler — teardown handles it
- DO NOT create a global session variable
- `get_scoped_session()` is thread-local — calling it multiple times in same request returns same session

**Transaction boundaries** (from [architecture.md#Transaction Boundaries, lines 1749-1753]):
- Repository methods NEVER call `session.commit()` or `session.rollback()` — caller (route handler) controls transactions
- Read-only endpoints: no explicit commit
- Write endpoints: explicit `session.commit()` after successful mutation, `session.rollback()` in error paths
- **CRITICAL**: The `@app.teardown_appcontext` calls `.remove()`, NOT `.commit()`. Uncommitted changes are LOST. Always commit explicitly in write routes.

**Anti-patterns (NEVER do this):**
- Do NOT use `session.merge()` when `session.add()` suffices for new documents
- Do NOT create global `WebsitesDBPostgreSQL` with session — create per-request
- Do NOT call `session.commit()` inside repository methods — only in route handlers
- Do NOT manually delete embeddings before document — CASCADE handles it via `session.delete(doc)`

### Endpoint Migration Map

| Endpoint | Current Implementation | New Implementation | DB Operation |
|----------|----------------------|-------------------|-------------|
| `GET /website_list` | `websites.get_list()` (global instance) | `WebsitesDBPostgreSQL(session).get_list()` | Read |
| `GET /website_count` | `websites.get_count_by_type()` (global instance) | `WebsitesDBPostgreSQL(session).get_count_by_type()` | Read |
| `GET /website_get` | `StalkerWebDocumentDB(document_id=..., reach=True).dict()` | `WebDocument.get_by_id(session, id, reach=True).dict()` | Read |
| `GET /website_get_next_to_correct` | `websites.get_next_to_correct(id)` | `WebsitesDBPostgreSQL(session).get_next_to_correct(id)` | Read |
| `POST /website_save` | `StalkerWebDocumentDB(document_id=...).save()` | `WebDocument.get_by_id()` + attrs + `session.commit()` | Write |
| `GET /website_delete` | `StalkerWebDocumentDB(document_id=...).delete()` | `WebDocument.get_by_id()` + `session.delete()` + `session.commit()` | Write |
| `POST /url_add` | `StalkerWebDocumentDB().save()` | `WebDocument(url=...)` + `session.add()` + `session.commit()` | Write |
| `POST /website_similar` | `websites.get_similar()` (global instance) | **DEFERRED to Epic 28** — keep legacy for `get_similar()` | Read |

### `/website_similar` — Special Handling

`get_similar()` is NOT yet migrated to ORM (it uses raw psycopg2 with pgvector). This endpoint cannot use `WebsitesDBPostgreSQL(session)` because `get_similar()` accesses `self.conn` which is only initialized in the legacy `session=None` constructor path.

**Recommended approach**: Create a separate legacy `WebsitesDBPostgreSQL()` instance (no session) specifically for the `get_similar()` call. This avoids the global variable but preserves backward compatibility:

```python
@app.route('/website_similar', methods=['POST'])
def search_similar():
    # ... extract text, get embedding ...
    # Legacy instance — get_similar() not yet migrated (Epic 28)
    legacy_repo = WebsitesDBPostgreSQL()  # No session → psycopg2 mode
    websites_list = legacy_repo.get_similar(embedds.embedding, embedding_model, limit=limit)
    legacy_repo.close()
    return {"status": "success", ...}
```

**Alternative**: Keep the global `websites` variable ONLY for `/website_similar` with a clear TODO comment. Less clean but simpler.

### `ai_correction_needed` — Pre-existing Bug

Line 265 of `server.py`: `web_doc.ai_correction_needed = ai_correction` — this column does NOT exist in the database table or ORM model. The old `StalkerWebDocumentDB` silently accepted it as a Python attribute (no DB persistence). In the ORM migration, simply skip this assignment. Do NOT add it to the model.

### `StalkerWebDocumentDB` Removal Assessment

After migrating all endpoints in this story, check if `StalkerWebDocumentDB` is still used anywhere in `server.py`:
- If NO remaining usages → remove the import from `server.py` line 10
- If `/url_add`'s embedding methods are needed → they are separate from CRUD, keep import
- Note: `StalkerWebDocumentDB` is still used by batch scripts (`web_documents_do_the_needful_new.py`, etc.) — do NOT delete the class itself, only clean up `server.py` imports

### Existing ORM Infrastructure (from Stories 26.1–26.3, 27.1–27.2)

| Component | File | Status |
|-----------|------|--------|
| Engine & sessions | `backend/library/db/engine.py` | Done (26.1) |
| `get_scoped_session()` | `backend/library/db/engine.py:114-123` | Done (for Flask) |
| `WebDocument` model | `backend/library/db/models.py` | Done (26.2, 27.1) — 26 columns, STI, `dict()`, classmethods |
| `WebDocument.get_by_id()` | `backend/library/db/models.py:153-165` | Done (27.1) — includes `reach=True` navigation |
| `WebDocument.get_by_url()` | `backend/library/db/models.py:167-172` | Done (27.1) |
| `WebDocument.dict()` | `backend/library/db/models.py:280-316` | Done (26.2) — dates as `"YYYY-MM-DD HH:MM:SS"`, enums as `.name` |
| `WebDocument.populate_neighbors()` | `backend/library/db/models.py:124-151` | Done (27.2) — shared DRY navigation logic |
| Domain methods | `backend/library/db/models.py:174-249` | Done — `set_document_type()`, `set_document_state()`, `set_document_state_error()`, `analyze()` |
| `WebsitesDBPostgreSQL` dual-mode | `backend/library/stalker_web_documents_db_postgresql.py` | Done (27.2) — accepts `session` param, ORM query methods |
| `load_neighbors()` | `backend/library/stalker_web_documents_db_postgresql.py` | Done (27.2) — delegates to `WebDocument.populate_neighbors()` |
| Flask teardown | `backend/server.py:80-85` | Done (26.3) — `scoped_session.remove()` |

### Current `server.py` Structure (Lines to Modify)

| Lines | Current Code | Change |
|-------|-------------|--------|
| 10 | `from library.stalker_web_document_db import StalkerWebDocumentDB` | Evaluate removal (see assessment above) |
| 49 | `websites = WebsitesDBPostgreSQL()` | **REMOVE** — replace with per-request instances |
| 60 | `logging.info(f"all pages in database: {websites.get_count()}")` | **REMOVE** — uses global instance |
| 109-298 | `/url_add` | Migrate DB save portion (keep S3 logic unchanged) |
| 300-323 | `/website_list` | Migrate to scoped session + repo |
| 326-331 | `/website_count` | Migrate to scoped session + repo |
| 376-390 | `/website_get` | Migrate to `WebDocument.get_by_id()` |
| 393-417 | `/website_get_next_to_correct` | Migrate to scoped session + repo |
| 441-477 | `/website_similar` | **SPECIAL**: Keep legacy or use separate instance (see above) |
| 615-644 | `/website_delete` | Migrate to `WebDocument.get_by_id()` + `session.delete()` |
| 647-689 | `/website_save` | Migrate to ORM model + `session.commit()` |

### Response Format Reference (MUST preserve exactly)

**`/website_list`** response:
```json
{
    "status": "success",
    "message": "Dane odczytane pomyślnie.",
    "encoding": "utf8",
    "websites": [{"id": 1, "url": "...", "title": "...", "document_type": "webpage", "created_at": "2026-03-09 10:30:45", "document_state": "URL_ADDED", "document_state_error": "NONE", "note": "...", "project": "...", "s3_uuid": "..."}],
    "all_results_count": 42
}
```

**`/website_get`** response: `WebDocument.dict()` output — full document with all 26+ columns including transient navigation fields.

**`/website_save`** response:
```json
{"status": "success", "message": "Dane strony 42 zaktualizowane pomyślnie."}
```

**`/website_delete`** response:
```json
{"status": "success", "message": "Page has been deleted from database", "encoding": "utf8"}
```

**`/url_add`** response:
```json
{"status": "success", "message": "Successfully saved document with ID: 42", "document_id": 42}
```

### Known Issues to Be Aware Of

1. **`ai_correction_needed` column** — does NOT exist in DB/model. Skip assignment in `/url_add`. Pre-existing bug tracked separately.

2. **`/website_delete` uses GET method** — this is a pre-existing REST anti-pattern. Do NOT change the HTTP method in this story (would break frontend). Tracked in backlog (11-5 was a review, not a fix).

3. **`/website_save` UPDATE only sets non-None columns** — current `StalkerWebDocumentDB.save()` skips None values in UPDATE. With ORM dirty tracking, assigning `None` to a previously non-None attribute WILL generate an UPDATE setting it to NULL. Be careful: `request.form.get('text')` returns `None` if field not submitted. Only set attributes that are explicitly provided in the request.

4. **`/website_save` has no explicit `session.add()` for existing documents** — SQLAlchemy tracks dirty state for objects already in session. Only `session.add()` for newly created documents.

5. **Startup DB connection** — removing the global `websites` variable means no database connection at module import. This is DESIRED — lazy initialization via `get_scoped_session()` on first request.

### Testing Strategy

**Unit tests with Flask test client + mocked ORM layer:**

```python
import pytest
from unittest.mock import MagicMock, patch

@pytest.fixture
def client():
    # Import app with mocked config
    with patch.dict(os.environ, {...}):
        from server import app
        app.config['TESTING'] = True
        with app.test_client() as client:
            yield client

def test_website_list_returns_correct_format(client):
    with patch('server.get_scoped_session') as mock_session:
        mock_repo = MagicMock()
        mock_repo.get_list.return_value = [{"id": 1, ...}]
        # ...
```

**Important**: Use `pytest.importorskip("sqlalchemy")` pattern from previous stories. Run via `.venv/Scripts/python -m pytest` (not `uvx`).

**Test file location**: `backend/tests/unit/test_flask_endpoints_orm.py`

**Run command**: `cd backend && PYTHONPATH=. .venv/Scripts/python -m pytest tests/unit/test_flask_endpoints_orm.py -v`

### Previous Story Intelligence (from Stories 27.1 and 27.2)

Key learnings from previous stories in this epic:

1. **`uvx pytest` lacks SQLAlchemy** — use `pytest.importorskip("sqlalchemy")` and run via `.venv/Scripts/python -m pytest`
2. **Enum serialization** — always `.name` (string), never `.value` or enum object. Both `WebDocument.dict()` and `WebsitesDBPostgreSQL.get_list()` serialize correctly
3. **`hasattr(row[1], "name")` pattern** — safe enum-to-string conversion for Row objects
4. **Dual-mode constructor** — `WebsitesDBPostgreSQL(session=None)` triggers legacy psycopg2 path. Pass `session` for ORM mode
5. **No new dependencies** — no `.venv_wsl` sync needed for pure ORM work
6. **Module-level `WebsitesDBPostgreSQL()` call** — `server.py` line 49 creates a global instance at import. This was a known backward-compatibility requirement during 27.2. Now in 27.3 it gets removed
7. **`session.commit()` is caller's responsibility** — repository methods never commit. Route handlers must commit explicitly for writes
8. **`WebDocument.get_by_id(reach=True)`** — populates transient fields via `populate_neighbors()`. Returns complete dict with navigation fields
9. **SQL injection fixed** — all ORM query methods use parameterized queries (27.2). The migration eliminates remaining raw SQL in CRUD operations
10. **`get_similar()` not migrated** — remains psycopg2-only. Must handle separately in this story

### Git Intelligence

Recent commits show ORM foundation work (Epic 26) and YouTube fixes. The codebase is on `main` branch. Story 27.1 and 27.2 changes are already merged, providing the full ORM infrastructure this story depends on.

### Files to Modify

| File | Change |
|------|--------|
| `backend/server.py` | Migrate 7 endpoints from legacy CRUD to ORM, remove global `websites` variable, update imports |
| `backend/tests/unit/test_flask_endpoints_orm.py` | **NEW** — unit tests for migrated Flask endpoints |

### Files NOT to Modify (scope guard)

- `backend/library/db/models.py` — NOT modified (WebDocument model complete from 27.1)
- `backend/library/db/engine.py` — NOT modified (session factories complete from 26.1)
- `backend/library/stalker_web_documents_db_postgresql.py` — NOT modified (repository rewrite complete from 27.2)
- `backend/library/stalker_web_document_db.py` — NOT modified (legacy class, still used by batch scripts)
- `backend/library/stalker_web_document.py` — NOT modified (domain model)

### Project Structure Notes

- Alignment with unified project structure: all changes in `server.py` (existing file, no new modules)
- ORM code stays in `library/db/` (engine, models) — no new ORM files
- Per-request session pattern follows Flask best practices for thread-local scoped session
- No new packages or dependencies required — SQLAlchemy 2.0.48 already installed (Story 26.1)

### References

- [Source: _bmad-output/planning-artifacts/epics/epic-27.md — Story 27.3 AC]
- [Source: _bmad-output/planning-artifacts/architecture.md#Session Lifecycle — lines 1712-1728]
- [Source: _bmad-output/planning-artifacts/architecture.md#Transaction Boundaries — lines 1749-1753]
- [Source: _bmad-output/planning-artifacts/architecture.md#ORM Pattern — lines 1755-1774]
- [Source: _bmad-output/planning-artifacts/architecture.md#Enforcement Guidelines — lines 1776-1793]
- [Source: backend/server.py — current Flask endpoints (migration target)]
- [Source: backend/library/stalker_web_document_db.py — legacy CRUD class being replaced]
- [Source: backend/library/db/models.py — WebDocument ORM model with classmethods and dict()]
- [Source: backend/library/db/engine.py — engine singleton, get_scoped_session()]
- [Source: backend/library/stalker_web_documents_db_postgresql.py — dual-mode repository (27.2)]
- [Source: _bmad-output/implementation-artifacts/27-1-document-persistence-crud-via-orm.md — previous story]
- [Source: _bmad-output/implementation-artifacts/27-2-repository-queries-list-count-state-lookups.md — previous story]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6 (claude-opus-4-6)

### Debug Log References

None — implementation completed without debug issues.

### Completion Notes List

- Removed global `websites = WebsitesDBPostgreSQL()` variable and startup `get_count()` call from `server.py` — replaced with per-request scoped session pattern
- Removed `StalkerWebDocumentDB` import from `server.py` — all CRUD endpoints now use `WebDocument` ORM model
- Migrated 7 endpoints to ORM: `/website_list`, `/website_count`, `/website_get`, `/website_get_next_to_correct`, `/website_save`, `/website_delete`, `/url_add`
- `/website_similar` kept on legacy `WebsitesDBPostgreSQL()` instance (no session) — `get_similar()` deferred to Epic 28
- Added 404 handling for `/website_get` (was missing — returned empty dict before)
- Added -1 handling for `/website_get_next_to_correct` (pre-existing crash on no results)
- Removed `ai_correction_needed` assignment in `/url_add` (column doesn't exist — pre-existing bug)
- `/website_save` now only sets attributes explicitly provided in the form (prevents ORM dirty tracking from NULLing existing values)
- Write endpoints (`/website_save`, `/website_delete`, `/url_add`) have explicit `session.commit()` and `session.rollback()` on error
- Read-only endpoints use scoped session with no explicit commit (teardown handles cleanup)
- Moved `get_scoped_session` import from inline (teardown handler) to module-level
- Updated `test_alembic_setup.py` to match new import location (`server.get_scoped_session` instead of `library.db.engine.get_scoped_session`)
- Created 18 unit tests in `test_flask_endpoints_orm.py` covering all migrated endpoints
- All 333 unit tests pass, ruff clean, no new dependencies
- **[Code Review Fix]** Added try/except with session.rollback() to `/website_delete` (was missing error handling for write endpoint)
- **[Code Review Fix]** Fixed `/website_delete` id validation — moved int() conversion after null check to prevent ValueError crash on non-numeric input
- **[Code Review Fix]** Reordered `/website_save` — `set_document_type()` now called BEFORE `analyze()` so analyze() operates on the correct document type
- **[Code Review Fix]** Replaced `print()` with `logging.error()` in `/website_save` document_type error path
- **[Code Review Fix]** Added 3 new tests: delete error/rollback, delete missing id, /website_similar legacy instance verification
- All 336 unit tests pass after review fixes

### Change Log

- 2026-03-09: Migrated 7 Flask CRUD endpoints from legacy psycopg2 to ORM scoped session pattern. Removed `StalkerWebDocumentDB` usage from `server.py`. Added 18 endpoint unit tests.
- 2026-03-09: Code review fixes — added error handling to /website_delete, fixed analyze() ordering in /website_save, added 3 missing tests. Total: 336 tests pass.

### File List

- `backend/server.py` — Modified: migrated 7 endpoints to ORM, removed global `websites` variable, updated imports
- `backend/tests/unit/test_flask_endpoints_orm.py` — New: 18 unit tests for migrated Flask endpoints
- `backend/tests/unit/test_alembic_setup.py` — Modified: updated mock target for teardown test (`server.get_scoped_session`)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — Modified: story status ready-for-dev → in-progress → review
- `_bmad-output/implementation-artifacts/27-3-flask-api-endpoints-crud-routes-via-repository.md` — Modified: tasks marked complete, Dev Agent Record updated
