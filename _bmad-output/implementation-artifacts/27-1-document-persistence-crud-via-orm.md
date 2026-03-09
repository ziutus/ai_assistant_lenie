# Story 27.1: Document Persistence — CRUD via ORM

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **developer**,
I want to create, read, update, and delete documents via ORM session operations and classmethods,
so that I no longer need manual SQL for basic document operations.

## Acceptance Criteria

1. **Given** a session and document data **When** `WebDocument(url="https://...")` is created and `session.add(doc)` + `session.commit()` is called **Then** the document is persisted in `web_documents` table

2. **Given** an existing document in the database **When** `doc.title = "New title"` is set and `session.commit()` is called **Then** SQLAlchemy dirty tracking generates UPDATE for the changed column only

3. **Given** a document with related embeddings **When** `session.delete(doc)` + `session.commit()` is called **Then** the document AND all related embeddings are deleted (cascade)

4. **Given** a URL string **When** `WebDocument.get_by_url(session, url)` is called **Then** returns the matching document or `None` (for duplicate detection)

5. **Given** a document ID **When** `WebDocument.get_by_id(session, id)` is called **Then** returns the matching document or `None`

6. **Given** a `WebDocument` instance **When** `doc.dict()` is called **Then** output matches exact format: dates as `"YYYY-MM-DD HH:MM:SS"`, enums as `.name`, all existing keys preserved including transient navigation fields when populated

**Covers:** FR14, FR15, FR16, FR17, FR18, FR19 | NFR5

## Tasks / Subtasks

- [x] Task 1: Add `get_by_id()` classmethod to `WebDocument` (AC: #5)
  - [x] 1.1 Implement `get_by_id(session, id, reach=False)` using `session.get(WebDocument, id)`
  - [x] 1.2 When `reach=True`, populate transient navigation fields (`next_id`, `next_type`, `previous_id`, `previous_type`) — use two separate SELECT queries (next document with `id > doc.id`, previous document with `id < doc.id`, ordered by id, matching `document_type` filter from current `stalker_web_document_db.py` logic)
  - [x] 1.3 Return `None` if document not found
  - [x] 1.4 Write unit tests: found, not found, reach=True with neighbors, reach=True without neighbors

- [x] Task 2: Add `get_by_url()` classmethod to `WebDocument` (AC: #4)
  - [x] 2.1 Implement `get_by_url(session, url)` using `session.scalars(select(WebDocument).where(WebDocument.url == url)).first()`
  - [x] 2.2 Return `None` if no match
  - [x] 2.3 Write unit tests: found, not found, URL with special characters

- [x] Task 3: Verify ORM Create flow (AC: #1)
  - [x] 3.1 Write tests: create `WebDocument(url=..., document_type=...)`, `session.add()`, `session.flush()`, verify `doc.id` is populated (auto-increment)
  - [x] 3.2 Test that all 26 columns are correctly persisted (use `doc.dict()` comparison)
  - [x] 3.3 Test creating each STI subclass (`LinkDocument`, `YouTubeDocument`, etc.) sets correct `document_type`

- [x] Task 4: Verify ORM Update flow (AC: #2)
  - [x] 4.1 Write tests: modify single attribute, flush, verify only that column changed
  - [x] 4.2 Test that enum fields can be updated via `set_document_state()` and persisted
  - [x] 4.3 Test that `None` values are correctly stored (nullable columns)

- [x] Task 5: Verify ORM Delete with cascade (AC: #3)
  - [x] 5.1 Write tests: create document + embedding, delete document, verify both removed
  - [x] 5.2 Test that `cascade="all, delete-orphan"` on `WebDocument.embeddings` relationship works
  - [x] 5.3 Verify FK constraint `ON DELETE CASCADE` on `websites_embeddings.website_id` aligns with ORM cascade

- [x] Task 6: Verify `dict()` backward compatibility (AC: #6)
  - [x] 6.1 Write comparison test: create `StalkerWebDocumentDB` and `WebDocument` with identical data, compare `dict()` outputs
  - [x] 6.2 Verify date format: `"YYYY-MM-DD HH:MM:SS"` (NOT `isoformat()`)
  - [x] 6.3 Verify enum format: `.name` string (NOT `.value`, NOT enum object)
  - [x] 6.4 Verify transient fields appear in `dict()` when populated
  - [x] 6.5 Verify all keys present (including `None` values — no omission)

- [x] Task 7: Quality checks
  - [x] 7.1 `uvx ruff check backend/` — zero warnings
  - [x] 7.2 All existing unit tests pass: `cd backend && PYTHONPATH=. .venv/Scripts/python -m pytest tests/unit/ -v` (275 passed)
  - [x] 7.3 No new dependencies added — no `.venv_wsl` sync needed

## Dev Notes

### Architecture Decisions (MUST follow)

**Classmethods on `WebDocument` model** (from architecture.md):
- `get_by_id(session, id, reach=False)` — simple primary key lookup, uses `session.get()`
- `get_by_url(session, url)` — duplicate detection, uses `select().where()`
- These are the ONLY classmethods added in this story. Complex queries belong in the repository (Story 27.2)

**CRUD pattern** (from architecture.md, enforced):
```python
# CREATE:
doc = WebDocument(url="https://...")
session.add(doc)
session.commit()

# READ:
doc = WebDocument.get_by_id(session, 42)
doc = WebDocument.get_by_url(session, "https://...")
doc = session.get(WebDocument, 42)  # also valid

# UPDATE:
doc.title = "New title"
session.commit()  # SQLAlchemy dirty tracking handles UPDATE

# DELETE:
session.delete(doc)
session.commit()  # CASCADE deletes embeddings
```

**Anti-patterns (NEVER do this):**
- Do NOT add `save()` or `delete()` methods to `WebDocument` — use `session.add()` / `session.delete()`
- Do NOT add `session` attribute to ORM model — session belongs to caller
- Do NOT use `session.merge()` when `session.add()` suffices
- Do NOT manually delete embeddings before document — CASCADE handles it
- Do NOT call `session.commit()` inside classmethods — caller controls transactions

### Navigation Fields (`reach=True`)

The `reach` parameter in `get_by_id()` triggers population of transient navigation fields. Current implementation in `stalker_web_document_db.py` (lines 83-95):
- Queries next document: `SELECT id, document_type FROM web_documents WHERE id > {id} ORDER BY id ASC LIMIT 1`
- Queries previous document: `SELECT id, document_type FROM web_documents WHERE id < {id} ORDER BY id DESC LIMIT 1`
- Results stored in `next_id`, `next_type`, `previous_id`, `previous_type`

**ORM equivalent** (use SQLAlchemy `select()`):
```python
@classmethod
def get_by_id(cls, session, doc_id, reach=False):
    doc = session.get(cls, doc_id)
    if doc is None:
        return None
    if reach:
        # Next document
        next_doc = session.scalars(
            select(cls.id, cls.document_type)
            .where(cls.id > doc_id)
            .order_by(cls.id.asc())
            .limit(1)
        ).first()
        # ... populate transient attrs
    return doc
```

**Note:** The `reach` query selects from `select(cls)` or `select(cls.id, cls.document_type)` — use lightweight column-only select to avoid loading full documents.

### Existing ORM Infrastructure (from Stories 26.1–26.3)

| Component | File | Status |
|-----------|------|--------|
| Engine & sessions | `backend/library/db/engine.py` | Done (26.1) |
| `Base` (DeclarativeBase) | `backend/library/db/engine.py:29-30` | Done (26.1) |
| `get_engine()` | `backend/library/db/engine.py:48-99` | Done (singleton, `pool_pre_ping=True`) |
| `get_session()` | `backend/library/db/engine.py:102-111` | Done (for scripts) |
| `get_scoped_session()` | `backend/library/db/engine.py:114-123` | Done (for Flask) |
| `dispose_engine()` | `backend/library/db/engine.py:126-139` | Done (cleanup) |
| `WebDocument` model | `backend/library/db/models.py:40-275` | Done (26.2) — 26 columns, STI, domain methods, `dict()` |
| STI subclasses | `backend/library/db/models.py:282-303` | Done (6 subclasses) |
| `WebsiteEmbedding` model | `backend/library/db/models.py:311-329` | Done (26.2) |
| Cascade relationship | `backend/library/db/models.py:105-110` | Done (`cascade="all, delete-orphan"`) |
| Alembic setup | `backend/alembic/env.py` | Done (26.3) |
| Flask teardown | `backend/server.py:80-85` | Done (`scoped_session.remove()`) |

### Files to Modify

| File | Change |
|------|--------|
| `backend/library/db/models.py` | Add `get_by_id()` and `get_by_url()` classmethods to `WebDocument` |
| `backend/tests/unit/test_orm_crud.py` | **NEW** — CRUD tests for create, read, update, delete, dict() compatibility |

### Files NOT to Modify (scope guard)

- `backend/library/stalker_web_document_db.py` — NOT modified in this story (re-export happens in 27.3)
- `backend/library/stalker_web_documents_db_postgresql.py` — NOT modified (repository rewrite is Story 27.2)
- `backend/server.py` — NOT modified (Flask endpoint migration is Story 27.3)
- `backend/library/stalker_web_document.py` — NOT modified

### Current Code Reference (Migration Target)

**`StalkerWebDocumentDB` raw SQL patterns** (`backend/library/stalker_web_document_db.py`):
- Constructor (lines 16-102): Loads document via `SELECT * FROM web_documents WHERE url = %s` or `WHERE id = %s`
- `save()` (lines 139-205): INSERT with 23 columns (RETURNING id) or UPDATE with non-None values
- `delete()` (lines 239-245): `DELETE FROM web_documents WHERE id = %s`
- `dict()` (lines 104-137): Serializes with formatted timestamps and enum `.name`

**Key difference**: `StalkerWebDocumentDB` uses class-level `db_conn` singleton (thread-unsafe). ORM uses session-per-request via `get_scoped_session()`.

### Known Issues to Be Aware Of

1. **`ai_correction_needed` column** — referenced in `server.py:265` but does NOT exist in database table or ORM model. Do NOT add it — this is a pre-existing bug to be tracked separately.

2. **`document_state_error` type drift** — DDL: TEXT, ORM: VARCHAR (implicit). Alembic `include_object()` filter already handles this. Do not attempt to fix.

3. **Enum storage** — `document_type`, `document_state`, `document_state_error` are stored as VARCHAR strings, not PostgreSQL native enums. ORM model uses `SAEnum(..., native_enum=False)`.

### Testing Strategy

**All tests are unit tests with mocked sessions** — no database required:
- Use `unittest.mock.MagicMock` for `session`
- For `session.get()` tests: mock return value
- For `select().where()` tests: mock `session.scalars().first()`
- For `dict()` comparison: create `WebDocument` instances directly with known data

**Test file location**: `backend/tests/unit/test_orm_crud.py`

**Run command**: `cd backend && PYTHONPATH=. uvx pytest tests/unit/test_orm_crud.py -v`

### Project Structure Notes

- Alignment with unified project structure: `library/db/` package for all ORM code (engine, models)
- Classmethods on model (not separate service layer) — per architecture decision
- No new packages or dependencies required — SQLAlchemy 2.0.48 and pgvector 0.4.2 already installed (Story 26.1)

### References

- [Source: _bmad-output/planning-artifacts/epics/epic-27.md — Story 27.1 AC]
- [Source: _bmad-output/planning-artifacts/architecture.md#Query Location Strategy — lines 1489-1507]
- [Source: _bmad-output/planning-artifacts/architecture.md#ORM Model Save/Delete Pattern — lines 1755-1774]
- [Source: _bmad-output/planning-artifacts/architecture.md#Navigation Fields Strategy — lines 1542-1560]
- [Source: _bmad-output/planning-artifacts/architecture.md#Enforcement Guidelines — lines 1776-1793]
- [Source: _bmad-output/planning-artifacts/prd.md#Document Persistence — FR14-FR19]
- [Source: backend/library/db/models.py — WebDocument ORM model with STI, 26 columns, domain methods]
- [Source: backend/library/db/engine.py — engine singleton, session factories]
- [Source: backend/library/stalker_web_document_db.py — current raw SQL CRUD (migration target)]
- [Source: SQLAlchemy 2.x docs — session.get() for PK lookup, select().where() for filtered queries]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

- Initial cascade test failed: SQLAlchemy expands `cascade="all, delete-orphan"` into individual options (`delete,delete-orphan,save-update,merge,...`), not literal "all" string. Fixed assertion to check individual cascade options.
- `uvx pytest` environment lacks SQLAlchemy — ORM tests use `pytest.importorskip("sqlalchemy")` and run via `.venv/Scripts/python -m pytest` instead.

### Completion Notes List

- Added `get_by_id(session, doc_id, reach=False)` classmethod to `WebDocument` — uses `session.get()` for PK lookup, `session.execute(select(...))` for navigation fields
- Added `get_by_url(session, url)` classmethod to `WebDocument` — uses `session.scalars(select().where())` for URL matching
- `reach=True` populates `next_id`, `next_type`, `previous_id`, `previous_type` using lightweight column-only SELECT (matches `stalker_web_document_db.py` behavior)
- 28 unit tests covering all 6 acceptance criteria: get_by_id (6 tests), get_by_url (3 tests), create flow (3 tests), update flow (3 tests), delete cascade (3 tests), dict() compatibility (10 tests)
- All 275 unit tests pass (28 new + 247 existing)
- Ruff clean, no new dependencies

### File List

- `backend/library/db/models.py` — Modified: added `select` and `Session` imports, `get_by_id()` and `get_by_url()` classmethods
- `backend/tests/unit/test_orm_crud.py` — New: 29 unit tests for CRUD operations
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — Modified: updated story status

### Change Log

- 2026-03-09: Implemented Story 27.1 — Document Persistence CRUD via ORM. Added `get_by_id()` and `get_by_url()` classmethods, 28 unit tests covering all ACs.
- 2026-03-09: Code review fixes — added return type annotations to classmethods, renamed misleading test, clarified shallow test docstrings, added `test_reach_true_with_string_type_fallback` for hasattr branch coverage, updated File List with sprint-status.yaml. 29 tests total.

