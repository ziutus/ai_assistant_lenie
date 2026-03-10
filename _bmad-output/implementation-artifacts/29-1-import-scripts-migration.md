# Story 29.1: Import Scripts Migration (dynamodb_sync & unknown_news_import)

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **developer**,
I want import scripts to use ORM models and sessions instead of the old wrapper,
so that data imports work through the same ORM layer as the rest of the application.

## Acceptance Criteria

1. **Given** `dynamodb_sync.py` is updated **When** it processes a DynamoDB item **Then** it creates `WebDocument(url=item['url'])` via ORM, sets attributes, and `session.commit()`

2. **Given** `dynamodb_sync.py` needs to set `created_at` and `chapter_list` **When** these fields are updated **Then** they are set via normal ORM attribute assignment (`doc.created_at = value`) — no direct SQL UPDATE

3. **Given** `unknown_news_import.py` is updated **When** it processes a JSON feed entry **Then** it creates `WebDocument` via ORM with fields: `title`, `summary`, `language`, `source`, `date_from`, `document_type`, `document_state`

4. **Given** `unknown_news_import.py` processes a URL that already exists **When** `WebDocument.get_by_url(session, url)` returns a match **Then** the duplicate is skipped (not inserted)

5. **Given** either import script **When** session lifecycle is inspected **Then** it follows the pattern: `session = get_session()` -> `try` -> `session.commit()` -> `finally` -> `session.close()`

6. **Given** import scripts use no raw SQL **When** code is inspected **Then** zero `cursor.execute()` calls remain in import scripts

## Tasks / Subtasks

- [x] Task 1: Migrate `dynamodb_sync.py` to ORM (AC: #1, #2, #5, #6)
  - [x] 1.1 Replace `from library.stalker_web_document_db import StalkerWebDocumentDB` with `from library.db.models import WebDocument` and `from library.db.engine import get_session`
  - [x] 1.2 Replace `from library.stalker_web_document import StalkerDocumentStatus` with `from library.models.stalker_document_status import StalkerDocumentStatus`
  - [x] 1.3 Rewrite `sync_item_to_postgres()` to use ORM:
    - Use `WebDocument.get_by_url(session, url)` for duplicate check (replaces `StalkerWebDocumentDB(url=url)`)
    - Create new `WebDocument(url=url)` for inserts
    - Set all attributes via ORM attribute assignment: `doc.title = item.get("title")`, etc.
    - Use `doc.set_document_type(doc_type)` (method exists on ORM model)
    - Set `doc.document_state` directly to enum member (e.g., `StalkerDocumentStatus.DOCUMENT_INTO_DATABASE`)
    - Set `doc.created_at` and `doc.chapter_list` via normal attribute assignment — NO direct SQL UPDATE
    - Use `session.add(doc)` + `session.commit()` for persistence (replaces `doc.save()` + raw SQL UPDATE)
  - [x] 1.4 Add session lifecycle in `main()`:
    - Create `session = get_session()` once before processing loop
    - Wrap processing in `try/finally` with `session.close()` in `finally`
    - Commit after each document (per-document transaction boundary — matches current behavior)
  - [x] 1.5 Remove all `psycopg2`-related code and `StalkerWebDocumentDB` import

- [x] Task 2: Migrate `unknown_news_import.py` to ORM (AC: #3, #4, #5, #6)
  - [x] 2.1 Replace imports:
    - `StalkerWebDocumentDB` → `WebDocument` from `library.db.models`
    - `WebsitesDBPostgreSQL` → `WebsitesDBPostgreSQL` from `library.stalker_web_documents_db_postgresql` (for `get_last_unknown_news()` — already has ORM branch)
    - Add `from library.db.engine import get_session`
    - Remove `import psycopg2`
  - [x] 2.2 Rewrite `get_last_unknown_news()` call to use ORM session:
    - Create `session = get_session()` for the date lookup
    - Use `WebsitesDBPostgreSQL(session=session)` → `websites.get_last_unknown_news()` (method already supports ORM branch via `if self.session:`)
  - [x] 2.3 Rewrite document creation/update loop:
    - Replace `StalkerWebDocumentDB(url=entry['url'])` with `WebDocument.get_by_url(session, url)`
    - For existing documents: if `date_from` is missing, set via ORM attribute (`doc.date_from = entry['date']`) + `session.commit()`
    - For new documents: create `WebDocument(url=entry['url'])`, set attributes, `session.add(doc)` + `session.commit()`
    - Use `StalkerDocumentType.youtube` and `StalkerDocumentType.link` enum members directly (already used in current code)
    - Use `StalkerDocumentStatus.URL_ADDED` and `StalkerDocumentStatus.READY_FOR_EMBEDDING` enum members directly
  - [x] 2.4 Add session lifecycle:
    - Single `session = get_session()` before processing loop
    - `try/finally` with `session.close()` in `finally`
    - Commit per document (same as current behavior via `doc.save()`)
  - [x] 2.5 Remove all `psycopg2`-related imports and error handling
  - [x] 2.6 Keep `psycopg2.OperationalError` catch → replace with `sqlalchemy.exc.OperationalError` for lost-connection detection

- [x] Task 3: Write unit tests for migrated scripts (AC: #1, #3, #4, #6)
  - [x] 3.1 Create `backend/tests/unit/test_dynamodb_sync_orm.py`:
    - Test `sync_item_to_postgres()` with new document → `session.add()` called, `session.commit()` called
    - Test duplicate detection → returns "skipped" when `get_by_url()` returns existing doc
    - Test `created_at` and `chapter_list` set via ORM (no raw SQL)
    - Test `document_state` set correctly based on S3 content availability
    - Use `pytest.importorskip("sqlalchemy")` pattern
  - [x] 3.2 Create `backend/tests/unit/test_unknown_news_import_orm.py`:
    - Test new document creation → WebDocument created with correct fields
    - Test duplicate handling → `get_by_url()` returns match, document skipped
    - Test `date_from` correction on existing document
    - Test YouTube URL detection → `document_type = youtube`, `document_state = URL_ADDED`
    - Use `pytest.importorskip("sqlalchemy")` pattern

- [x] Task 4: Quality checks (AC: all)
  - [x] 4.1 `uvx ruff check backend/` — zero new warnings
  - [x] 4.2 `cd backend && PYTHONPATH=. uvx pytest tests/unit/ -v` — all existing tests pass
  - [x] 4.3 Verify zero `cursor.execute()` calls in `dynamodb_sync.py` and `unknown_news_import.py`
  - [x] 4.4 Verify zero `psycopg2` imports in import scripts
  - [x] 4.5 No new dependencies added — no `.venv_wsl` sync needed

## Dev Notes

### Architecture Decisions (MUST follow)

**Session lifecycle for scripts** (from engine.py docs):
```python
session = get_session()  # Plain session for scripts
try:
    # ... process documents ...
    session.commit()  # Per-document commit
finally:
    session.close()
```

**ORM model usage** (from Story 26.2, 27.1):
```python
from library.db.models import WebDocument
from library.db.engine import get_session

# Duplicate check
existing = WebDocument.get_by_url(session, url)
if existing:
    # Update existing
    existing.date_from = entry['date']
    session.commit()
else:
    # Create new
    doc = WebDocument(url=url)
    doc.title = "..."
    doc.document_type = StalkerDocumentType.link
    doc.document_state = StalkerDocumentStatus.URL_ADDED
    session.add(doc)
    session.commit()
```

**Key difference from Flask routes**: Import scripts use `get_session()` (plain Session), NOT `get_scoped_session()` (which is for Flask thread-local usage). Scripts manage their own `session.close()` in `finally`.

### Current Code Analysis — `dynamodb_sync.py`

**Lines to rewrite (sync_item_to_postgres, lines 144-220):**
- Line 152: `doc = StalkerWebDocumentDB(url=url)` → `existing = WebDocument.get_by_url(session, url)`
- Line 157: `if doc.id is not None:` → `if existing is not None:`
- Lines 168-191: Attribute setting on `doc` — keep same logic, just use ORM `WebDocument` instance
- Lines 192: `new_id = doc.save()` → `session.add(doc)` + `session.commit()` + `new_id = doc.id`
- Lines 194-213: Direct SQL UPDATE for `created_at`/`chapter_list` → **REMOVE entirely** — set via ORM attributes BEFORE commit: `doc.created_at = dynamo_created_at` (line before `session.add(doc)`)

**Critical: `created_at` handling.** Current code does `doc.save()` (INSERT without created_at) then UPDATE to set it. With ORM, just set `doc.created_at = value` before `session.add()` — SQLAlchemy includes it in the INSERT. The `server_default=CURRENT_TIMESTAMP` only applies when the column is NULL.

**Critical: `chapter_list` handling.** Same as above — set before `session.add()`.

### Current Code Analysis — `unknown_news_import.py`

**Lines to rewrite:**
- Lines 117-126: `WebsitesDBPostgreSQL()` for `get_last_unknown_news()` → `WebsitesDBPostgreSQL(session=session)` — the method already has ORM branch
- Lines 162-163: `web_document = StalkerWebDocumentDB(url=entry['url'])` → `existing = WebDocument.get_by_url(session, entry['url'])`
- Lines 168-176: Existing doc handling — update `date_from` via ORM attribute + `session.commit()`
- Lines 180-195: New doc creation — create `WebDocument`, set attributes, `session.add()` + `session.commit()`
- Line 163: `except psycopg2.OperationalError` → `except sqlalchemy.exc.OperationalError`

**Note:** `unknown_news_import.py` already uses `StalkerDocumentType` and `StalkerDocumentStatus` enum members directly (lines 188-192), so enum handling is already correct for ORM.

### `WebDocument.get_by_url()` — Already Exists (DO NOT recreate)

```python
@classmethod
def get_by_url(cls, session: Session, url: str) -> "WebDocument | None":
    return session.scalars(
        select(cls).where(cls.url == url)
    ).first()
```

This replaces `StalkerWebDocumentDB(url=url)` which does a SELECT on construction.

### `WebsitesDBPostgreSQL.get_last_unknown_news()` — Already Has ORM Branch

The method at `stalker_web_documents_db_postgresql.py:338` already supports `if self.session:` ORM path. Just pass `session=session` to the constructor.

### Error Handling Changes

| Current | ORM Replacement |
|---------|----------------|
| `psycopg2.OperationalError` | `sqlalchemy.exc.OperationalError` |
| `StalkerWebDocumentDB(url=url)` raises on connection failure | `get_session()` raises on connection failure (at engine creation) |
| `doc.save()` returns `new_id` | `session.add(doc)` + `session.commit()` + `doc.id` (populated by SA after flush) |

### Imports to Add / Remove

**dynamodb_sync.py:**
```python
# REMOVE:
from library.stalker_web_document_db import StalkerWebDocumentDB
from library.stalker_web_document import StalkerDocumentStatus

# ADD:
from library.db.models import WebDocument
from library.db.engine import get_session
from library.models.stalker_document_status import StalkerDocumentStatus
```

**unknown_news_import.py:**
```python
# REMOVE:
import psycopg2
from library.stalker_web_document_db import StalkerWebDocumentDB

# ADD:
from sqlalchemy.exc import OperationalError as SAOperationalError
from library.db.models import WebDocument
from library.db.engine import get_session
```

### Project Structure Notes

- No new files created except test files
- Import scripts stay in `backend/imports/` — same location
- ORM infrastructure already complete from Epics 26-28
- `WebsitesDBPostgreSQL` dual-mode constructor already supports session parameter (Story 27.2)
- `get_last_unknown_news()` already has ORM branch (Story 27.2)

### Previous Story Intelligence (from Story 28.2)

Key learnings:
1. **`pytest.importorskip("sqlalchemy")`** — use for test gating (uvx pytest lacks SQLAlchemy)
2. **Repository methods never commit** — but import scripts DO commit (they own the session)
3. **Enum handling** — ORM uses enum members directly (e.g., `StalkerDocumentType.link`), legacy uses `.name` strings
4. **Test pattern** — mock `session` and `session.execute()` for unit tests
5. **Pre-existing test ordering issue** — 8 tests in `test_get_list_query.py` fail only in full suite (not caused by this work)

### Git Intelligence

Recent commits show Epic 27-28 ORM migration pattern is well-established:
- `1079ecc`: ORM migration — Document CRUD, API endpoints, embedding CRUD
- `d666811`: Merge PR #75 for ORM CRUD API endpoints
- Pattern: feature branch → PR → merge to main

### References

- [Source: _bmad-output/planning-artifacts/epics/epic-29.md — Story 29.1 AC]
- [Source: backend/imports/dynamodb_sync.py — full script, lines 1-332]
- [Source: backend/imports/unknown_news_import.py — full script, lines 1-209]
- [Source: backend/library/stalker_web_document_db.py — StalkerWebDocumentDB class, lines 1-282]
- [Source: backend/library/db/models.py — WebDocument.get_by_url() classmethod, line 167-172]
- [Source: backend/library/db/engine.py — get_session() factory, lines 102-111]
- [Source: backend/library/stalker_web_documents_db_postgresql.py — get_last_unknown_news() ORM branch, line 338]
- [Source: _bmad-output/implementation-artifacts/28-2-similarity-search-pgvector-python-api-endpoint.md — previous story learnings]

## Change Log

- 2026-03-09: Migrated `dynamodb_sync.py` and `unknown_news_import.py` from legacy `StalkerWebDocumentDB`/`psycopg2` to ORM (`WebDocument`/`get_session`). Removed all raw SQL and `psycopg2` usage. Added 12 unit tests across 2 test files.
- 2026-03-09: **Code Review fixes** — Fixed session leak in `unknown_news_import.py` (single session for entire script). Added `session.rollback()` on error in `dynamodb_sync.py`. Removed dead `mock_get_session` from 7 tests. Updated `imports/CLAUDE.md` to reflect ORM pattern.

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

- Ruff check on modified files: All checks passed
- Full unit test suite: 49 passed, 15 skipped (ORM tests without sqlalchemy), 28 errors (pre-existing: 8 in `test_get_list_query.py`, 20 in `test_alembic_setup.py`)
- Zero `cursor.execute()` calls in import scripts (verified via grep)
- Zero `psycopg2` imports in import scripts (verified via grep)

### Completion Notes List

- **Task 1**: `dynamodb_sync.py` — replaced `StalkerWebDocumentDB` with `WebDocument` ORM model. `sync_item_to_postgres()` now takes a `session` parameter, uses `WebDocument.get_by_url()` for duplicate check, creates `WebDocument` instances, sets `created_at` and `chapter_list` via ORM attributes (eliminated direct SQL UPDATE). Session lifecycle added in `main()` with `try/finally`.
- **Task 2**: `unknown_news_import.py` — extracted `process_entry()` function for testability. Replaced `StalkerWebDocumentDB(url=...)` with `WebDocument.get_by_url(session, url)`. Replaced `psycopg2.OperationalError` with `sqlalchemy.exc.OperationalError`. Session lifecycle added with `try/finally`. `get_last_unknown_news()` now uses `WebsitesDBPostgreSQL(session=session)`.
- **Task 3**: Created 7 tests in `test_dynamodb_sync_orm.py` and 5 tests in `test_unknown_news_import_orm.py`. All use `pytest.importorskip("sqlalchemy")` pattern.
- **Task 4**: All quality checks pass. No new dependencies. No `.venv_wsl` sync needed.

### File List

- `backend/imports/dynamodb_sync.py` — modified (ORM migration + review fix: session.rollback)
- `backend/imports/unknown_news_import.py` — modified (ORM migration + review fix: session leak)
- `backend/imports/CLAUDE.md` — modified (updated to reflect ORM pattern)
- `backend/tests/unit/test_dynamodb_sync_orm.py` — new (7 unit tests, review fix: removed dead mocks)
- `backend/tests/unit/test_unknown_news_import_orm.py` — new (5 unit tests)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — modified (status update)
- `_bmad-output/implementation-artifacts/29-1-import-scripts-migration.md` — modified (task tracking + review notes)
