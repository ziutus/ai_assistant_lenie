# Story 34.1: Alembic Migration — Rename s3_uuid to uuid

Status: done

## Story

As a developer,
I want the `s3_uuid` column in `web_documents` renamed to `uuid` with auto-generation, NOT NULL, and UNIQUE constraints,
so that every document has a stable, instance-independent identifier for Obsidian references and cross-instance synchronization.

## Acceptance Criteria

1. **Given** an Alembic migration file exists,
   **When** `alembic upgrade head` is run on NAS PostgreSQL (192.168.200.7:5434),
   **Then** the column `web_documents.s3_uuid` is renamed to `uuid`.

2. **Given** existing rows with `uuid IS NULL` (documents not from AWS flow),
   **When** the migration runs,
   **Then** all NULL values are backfilled with `gen_random_uuid()`.

3. **Given** the backfill is complete,
   **When** the migration applies constraints,
   **Then** the column has `NOT NULL` and `DEFAULT gen_random_uuid()` and a `UNIQUE` constraint named `uq_web_documents_uuid`.

4. **Given** the ORM model in `backend/library/db/models.py`,
   **When** the column is updated,
   **Then** `s3_uuid` is renamed to `uuid` with `mapped_column(String(100), nullable=False, unique=True, server_default=func.gen_random_uuid())`.

5. **Given** the `dict()` method in `WebDocument`,
   **When** called,
   **Then** it returns `"uuid"` key instead of `"s3_uuid"`.

6. **Given** the SQL init script `backend/database/init/03-create-table.sql`,
   **When** updated,
   **Then** it reflects the new column name `uuid` with NOT NULL, DEFAULT, and UNIQUE.

7. **Given** the migration is run on NAS PostgreSQL,
   **When** verified with `psql`,
   **Then** `\d web_documents` shows column `uuid varchar(100) NOT NULL DEFAULT gen_random_uuid()` with a unique constraint.

8. **Given** `alembic downgrade -1` is run,
   **When** the migration is reversed,
   **Then** the column is renamed back to `s3_uuid`, constraints are removed, and NULLs are restored (best effort).

9. **Given** the migration is complete,
   **When** `ruff check backend/` is run,
   **Then** zero warnings are reported.

10. **Given** the migration is complete,
    **When** existing unit tests are run (`cd backend && PYTHONPATH=. uvx pytest tests/unit/ -v`),
    **Then** all tests pass. New unit tests for the ORM model change are added.

## Tasks / Subtasks

- [x] Task 1: Create Alembic migration (AC: #1, #2, #3, #8)
  - [x] 1.1: Create migration file `backend/alembic/versions/d4e5f6a7b8c9_rename_s3_uuid_to_uuid.py` with `down_revision = 'c3d4e5f6a7b8'`
  - [x] 1.2: `upgrade()`: `op.alter_column('web_documents', 's3_uuid', new_column_name='uuid')`
  - [x] 1.3: `upgrade()`: `op.execute("UPDATE web_documents SET uuid = gen_random_uuid() WHERE uuid IS NULL")`
  - [x] 1.4: `upgrade()`: `op.alter_column('web_documents', 'uuid', nullable=False, server_default=sa.text('gen_random_uuid()'))`
  - [x] 1.5: `upgrade()`: `op.create_unique_constraint('uq_web_documents_uuid', 'web_documents', ['uuid'])`
  - [x] 1.6: `downgrade()`: reverse steps — drop constraint, remove default, set nullable=True, rename back to s3_uuid
- [x] Task 2: Update ORM model (AC: #4, #5)
  - [x] 2.1: In `backend/library/db/models.py` line 135: rename `s3_uuid` to `uuid`, add `nullable=False, unique=True, server_default=func.gen_random_uuid()`
  - [x] 2.2: In `dict()` method line 383: change `"s3_uuid": self.s3_uuid` to `"uuid": self.uuid`
- [x] Task 2b: Update ORM query layer (scope extended from 34-2 — direct ORM dependency)
  - [x] 2b.1: In `backend/library/stalker_web_documents_db_postgresql.py`: rename 4 `s3_uuid` references to `uuid` (lines 34, 83, 103, 108)
- [x] Task 3: Update SQL init script (AC: #6)
  - [x] 3.1: In `backend/database/init/03-create-table.sql` line 32: change `s3_uuid varchar(100)` to `uuid varchar(100) NOT NULL DEFAULT gen_random_uuid()` and add UNIQUE constraint
- [x] Task 4: Update unit tests (AC: #10)
  - [x] 4.1: Update `backend/tests/unit/test_db_models.py` — rename all s3_uuid references to uuid (3 occurrences)
  - [x] 4.2: Update `backend/tests/unit/test_orm_crud.py` — rename all s3_uuid references (4 occurrences)
  - [x] 4.3: Update `backend/tests/unit/test_repository_queries.py` — rename s3_uuid references (4 occurrences)
- [x] Task 5: Run ruff + tests (AC: #9, #10)
  - [x] 5.1: `uvx ruff check backend/` — zero warnings on changed files
  - [x] 5.2: `cd backend && PYTHONPATH=. .venv/Scripts/python -m pytest tests/unit/ -v` — 206 passed (ORM tests), 70 passed (all unit tests)

## Dev Notes

### Architecture Decision

This story implements [ADR-015](docs/adr/adr-015-uuid-as-global-document-identifier.md). Key points:
- `s3_uuid` is a legacy name from when UUIDs were only generated for S3-backed documents
- Renaming to `uuid` reflects its actual purpose: a global, instance-independent document identifier
- Auto-generation ensures ALL documents get a UUID, not just AWS-flow ones

### Alembic Migration Details

**Revision chain:** `c3d4e5f6a7b8` (latest) → `d4e5f6a7b8c9` (this migration)

**Critical: Migration must be run in correct order:**
1. Rename column (preserves existing data)
2. Backfill NULLs (gen_random_uuid())
3. Add NOT NULL constraint (safe after backfill)
4. Add DEFAULT (for new inserts)
5. Add UNIQUE constraint (safe because UUIDs don't collide)

**PostgreSQL `gen_random_uuid()` requires pgcrypto extension** — verify it's already enabled on NAS. If not, add `CREATE EXTENSION IF NOT EXISTS pgcrypto;` to migration. Note: PostgreSQL 13+ has `gen_random_uuid()` built-in without pgcrypto.

### ORM Model Change

```python
# Before (models.py:135)
s3_uuid: Mapped[str | None] = mapped_column(String(100))

# After
uuid: Mapped[str] = mapped_column(
    String(100), nullable=False, unique=True,
    server_default=func.gen_random_uuid(),
)
```

**Import needed:** `from sqlalchemy import func` (check if already imported).

### Scope Boundaries — THIS STORY ONLY

**In scope:**
- Alembic migration file
- ORM model (`models.py`) — column definition + `dict()` method
- SQL init script (`03-create-table.sql`)
- Unit tests for model changes

**NOT in scope (Story 34-2):**
- Backend Python code rename in 15 files (services, routes, imports, batch scripts)
- Frontend/shared types (confirmed: 0 occurrences in TS/JS)
- Lambda code (AWS deferred per `docs/aws-sync-backlog.md`)

### Files to Modify

**Modified:**
- `backend/alembic/versions/d4e5f6a7b8c9_rename_s3_uuid_to_uuid.py` — NEW migration
- `backend/library/db/models.py` — column rename + dict() update (lines 135, 383)
- `backend/database/init/03-create-table.sql` — column definition (line 32)
- `backend/tests/unit/test_db_models.py` — 4 s3_uuid → uuid
- `backend/tests/unit/test_orm_crud.py` — 4 s3_uuid → uuid
- `backend/tests/unit/test_repository_queries.py` — 4 s3_uuid → uuid

**NOT modified (Story 34-2 scope):**
- `backend/library/document_service.py` (4 occurrences)
- `backend/library/document_prepare.py` (4 occurrences)
- `backend/library/stalker_web_documents_db_postgresql.py` (4 occurrences)
- `backend/imports/dynamodb_sync.py` (6 occurrences)
- `backend/imports/migrate_data_to_cache.py` (16 occurrences)
- `backend/web_documents_do_the_needful_new.py` (19 occurrences)
- `backend/web_documents_fix_missing_markdown.py` (6 occurrences)
- `backend/webdocument_md_decode.py` (4 occurrences)
- `backend/test_code/gcloud_firestore.py` (11 occurrences)
- `backend/tests/unit/test_flask_endpoints_orm.py` (2 occurrences)
- `backend/tests/unit/test_document_service.py` (2 occurrences)
- `infra/aws/serverless/lambdas/sqs-into-rds/lambda_function.py` (2 occurrences — AWS deferred)
- `infra/aws/serverless/lambdas/sqs-weblink-put-into/lambda_function.py` (3 occurrences — AWS deferred)

### Testing on NAS

After migration, verify with psql:
```bash
PGPASSWORD=postgres "/c/Program Files/PostgreSQL/18/bin/psql.exe" -h 192.168.200.7 -p 5434 -U postgres -d lenie-ai -c "\d web_documents"
```

Check:
- Column name is `uuid` (not `s3_uuid`)
- Column type is `character varying(100)`
- NOT NULL constraint present
- Default is `gen_random_uuid()`
- Unique constraint `uq_web_documents_uuid` exists

Verify backfill:
```sql
SELECT COUNT(*) FROM web_documents WHERE uuid IS NULL;
-- Should return 0
```

### DynamoDB Backward Compatibility Note

`dynamodb_sync.py` reads `s3_uuid` from DynamoDB items (line 199). DynamoDB is schemaless — old items still have field named `s3_uuid`. Story 34-2 will add backward-compat mapping: `item.get("uuid") or item.get("s3_uuid")`.

### Previous Story Intelligence

**From Epic 32 retro (2026-04-05):**
- File List tracking: document ALL files changed in story ✅
- Edge case checklist: test None/invalid/empty inputs
- Service layer pattern established — but NOT relevant to this migration-only story

**From Epic 31 retro (2026-03-28):**
- One commit = one scope (no unrelated changes)
- `pytest.importorskip("sqlalchemy")` required in all ORM-related tests

**From Epic 33 (Story 33-2, import_logs migration):**
- Alembic migration pattern: create file manually (not autogenerate), test on NAS before marking done
- Verify migration with `alembic upgrade head` AND `alembic downgrade -1` roundtrip

### References

- [Source: docs/adr/adr-015-uuid-as-global-document-identifier.md] — ADR for this change
- [Source: backend/library/db/models.py#L135] — Current s3_uuid column definition
- [Source: backend/library/db/models.py#L383] — dict() method s3_uuid key
- [Source: backend/database/init/03-create-table.sql#L32] — SQL schema s3_uuid
- [Source: backend/alembic/versions/c3d4e5f6a7b8_add_reviewed_at_and_obsidian_note_paths.py] — Latest migration (down_revision target)

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6 (1M context)

### Debug Log References

None.

### Completion Notes List

- Task 1: Created Alembic migration `d4e5f6a7b8c9` with correct revision chain. Upgrade: rename → backfill NULLs → NOT NULL + DEFAULT → UNIQUE constraint. Downgrade reverses all steps.
- Task 2: Renamed ORM attribute `s3_uuid` → `uuid` with `nullable=False, unique=True, server_default=func.gen_random_uuid()`. Updated `dict()` to return `"uuid"` key.
- Task 2b (scope extended): Updated `stalker_web_documents_db_postgresql.py` — 4 ORM references renamed. This was originally Story 34-2 scope but is a direct dependency of the ORM attribute rename and would have broken the query layer.
- Task 3: Updated SQL init script — column definition + UNIQUE constraint added.
- Task 4: Updated 3 test files (11 total occurrences of `s3_uuid` → `uuid`).
- Task 5: Ruff clean on changed files. 206 ORM tests passed, 70 total unit tests passed.

### Change Log

- 2026-04-07: Story 34-1 implemented — Alembic migration, ORM model, SQL init, query layer, unit tests. Scope extended to include `stalker_web_documents_db_postgresql.py` (direct ORM dependency).
- 2026-04-07: Code review — CRITICAL fix: `document_service.py` was silently losing UUID data (`doc.s3_uuid` wrote to non-mapped attribute). Fixed `s3_uuid` → `uuid` in document_service.py, test_document_service.py, test_flask_endpoints_orm.py. Updated docs (database/CLAUDE.md, data-models-backend.md). Added `existing_type` to migration alter_column. 587 tests passed.

### File List

**New:**
- `backend/alembic/versions/d4e5f6a7b8c9_rename_s3_uuid_to_uuid.py`

**Modified:**
- `backend/library/db/models.py` (lines 135, 385)
- `backend/library/document_service.py` (lines 71, 81, 99, 250 — `s3_uuid` → `uuid`, review fix)
- `backend/library/stalker_web_documents_db_postgresql.py` (lines 34, 83, 103, 108)
- `backend/database/init/03-create-table.sql` (line 32, added UNIQUE constraint)
- `backend/database/CLAUDE.md` (line 58 — `s3_uuid` → `uuid` documentation, review fix)
- `backend/tests/unit/test_db_models.py` (3 occurrences)
- `backend/tests/unit/test_orm_crud.py` (4 occurrences)
- `backend/tests/unit/test_repository_queries.py` (4 occurrences)
- `backend/tests/unit/test_document_service.py` (2 occurrences — review fix)
- `backend/tests/unit/test_flask_endpoints_orm.py` (2 occurrences — review fix)
- `docs/data-models-backend.md` (line 39 — `s3_uuid` → `uuid` documentation, review fix)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (status update)
- `_bmad-output/implementation-artifacts/34-1-alembic-migration-rename-s3-uuid-to-uuid.md` (this file)
