# Story 34.2: Backend & Frontend Code Rename s3_uuid to uuid

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer,
I want all Python code references to `s3_uuid` renamed to `uuid` across backend scripts, services, and documentation,
so that the codebase consistently uses the canonical column name established by the Alembic migration in Story 34-1.

## Acceptance Criteria

1. **Given** the backend Python files listed in Dev Notes,
   **When** all `s3_uuid` references are renamed to `uuid`,
   **Then** zero occurrences of `s3_uuid` remain in production Python code (excluding Alembic migration file and AWS Lambda files).

2. **Given** `dynamodb_sync.py` reads items from DynamoDB where the field is still named `s3_uuid`,
   **When** the code is updated,
   **Then** it uses backward-compatible mapping: `item.get("uuid") or item.get("s3_uuid")` to handle both old and new DynamoDB items.

3. **Given** documentation files (`backend/imports/CLAUDE.md`, `docs/api-type-sync-strategy.md`, `_bmad-output/planning-artifacts/architecture.md`),
   **When** updated,
   **Then** they reference `uuid` instead of `s3_uuid`.

4. **Given** `docs/aws-sync-backlog.md`,
   **When** reviewed,
   **Then** it is updated to note that the backend rename is complete and only Lambda code remains for future sync.

5. **Given** the rename is complete,
   **When** `cd backend && PYTHONPATH=. uvx pytest tests/unit/ -v` is run,
   **Then** all existing tests pass with zero regressions.

6. **Given** the rename is complete,
   **When** `uvx ruff check backend/` is run,
   **Then** zero warnings are reported.

7. **Given** AWS Lambda files (`sqs-into-rds`, `sqs-weblink-put-into`),
   **When** this story is complete,
   **Then** they are NOT modified (deferred per `docs/aws-sync-backlog.md`).

## Tasks / Subtasks

- [x] Task 1: Rename s3_uuid in batch processing scripts (AC: #1)
  - [x] 1.1: `backend/web_documents_do_the_needful_new.py` — rename 19 occurrences of `s3_uuid` to `uuid`
  - [x] 1.2: `backend/imports/migrate_data_to_cache.py` — rename 16 occurrences of `s3_uuid` to `uuid`
  - [x] 1.3: `backend/web_documents_fix_missing_markdown.py` — rename 6 occurrences of `s3_uuid` to `uuid`
  - [x] 1.4: `backend/webdocument_md_decode.py` — rename 4 occurrences of `s3_uuid` to `uuid`
- [x] Task 2: Rename s3_uuid in library/imports code (AC: #1, #2)
  - [x] 2.1: `backend/library/document_prepare.py` — rename 4 occurrences of `s3_uuid` to `uuid`
  - [x] 2.2: `backend/imports/dynamodb_sync.py` — rename 6 occurrences; add backward-compat `item.get("uuid") or item.get("s3_uuid")` for DynamoDB field reads (line ~199)
- [x] Task 3: Rename s3_uuid in test/experimental code (AC: #1)
  - [x] 3.1: `backend/test_code/gcloud_firestore.py` — rename 11 occurrences of `s3_uuid` to `uuid`
- [x] Task 4: Update documentation (AC: #3, #4)
  - [x] 4.1: `backend/imports/CLAUDE.md` — update 2 occurrences of `s3_uuid` to `uuid`
  - [x] 4.2: `docs/api-type-sync-strategy.md` — update 2 occurrences of `s3_uuid` to `uuid`
  - [x] 4.3: `_bmad-output/planning-artifacts/architecture.md` — update 2 occurrences of `s3_uuid` to `uuid`
  - [x] 4.4: `docs/aws-sync-backlog.md` — add note that backend rename is complete (Story 34-2); only Lambda code remains
- [x] Task 5: Run linting and tests (AC: #5, #6)
  - [x] 5.1: `uvx ruff check backend/` — zero warnings on changed files
  - [x] 5.2: `cd backend && PYTHONPATH=. uvx pytest tests/unit/ -v` — all tests pass

## Dev Notes

### Architecture Decision

This story completes the code-level rename started in [ADR-015](docs/adr/adr-015-uuid-as-global-document-identifier.md). Story 34-1 handled the database migration (Alembic), ORM model, SQL init script, service layer, and query layer. This story handles the remaining ~66 occurrences in batch scripts, import scripts, and documentation.

### Nature of Changes

This is a **mechanical find-replace** operation. All files use `s3_uuid` as a Python attribute name or dict key that maps to the ORM `WebDocument.uuid` attribute (renamed in 34-1). The rename is safe because:
- The ORM model already uses `uuid` (done in 34-1)
- The `dict()` method already returns `"uuid"` key (done in 34-1)
- The DB column is already `uuid` (Alembic migration in 34-1)

### DynamoDB Backward Compatibility (CRITICAL)

`dynamodb_sync.py` line ~199 reads `s3_uuid` directly from DynamoDB items. DynamoDB is schemaless — existing items still have the field named `s3_uuid`. New items written by Lambda (also not yet renamed) will also use `s3_uuid`. The code MUST use:

```python
uuid_value = item.get("uuid") or item.get("s3_uuid")
```

This ensures compatibility with both old items (field `s3_uuid`) and future items (when Lambda is eventually updated to use `uuid`).

### Files NOT to Modify

- `backend/alembic/versions/d4e5f6a7b8c9_rename_s3_uuid_to_uuid.py` — migration file references old name intentionally
- `infra/aws/serverless/lambdas/sqs-into-rds/lambda_function.py` — AWS deferred
- `infra/aws/serverless/lambdas/sqs-weblink-put-into/lambda_function.py` — AWS deferred
- `docs/adr/adr-015-uuid-as-global-document-identifier.md` — historical documentation, references old name intentionally
- `_bmad-output/implementation-artifacts/34-1-*.md` — story file, historical record
- Other `_bmad-output/implementation-artifacts/` story files — historical records
- JSON cache files in `backend/tmp/` — temporary data, will be regenerated

### Project Structure Notes

- All changes are in `backend/` directory (Python code + docs)
- No frontend/TypeScript changes needed (0 occurrences confirmed)
- No shared/ package changes needed
- Import scripts in `backend/imports/` use service layer (since Epic 32) but some still reference `s3_uuid` directly for DynamoDB/S3 field mapping

### Testing Standards

- Run `cd backend && PYTHONPATH=. uvx pytest tests/unit/ -v` for all unit tests
- Run `uvx ruff check backend/` for linting
- `pytest.importorskip("sqlalchemy")` required in ORM-related tests (from Epic 31 retro)
- No new tests expected — this is a mechanical rename of already-tested code

### Previous Story Intelligence

**From Story 34-1 (done):**
- ORM model, dict() method, service layer, query layer already renamed
- document_service.py was silently losing UUID data when using old `s3_uuid` attribute — caught in code review
- `stalker_web_documents_db_postgresql.py` scope was extended from 34-2 to 34-1 because it's a direct ORM dependency
- 587 tests passed after all 34-1 changes

**From Story 34-1 Change Log:**
- Code review found that `document_service.py` was writing to non-mapped attribute `doc.s3_uuid` — this was already fixed in 34-1
- `test_document_service.py` and `test_flask_endpoints_orm.py` already updated in 34-1

### References

- [Source: docs/adr/adr-015-uuid-as-global-document-identifier.md] — ADR for this change
- [Source: _bmad-output/implementation-artifacts/34-1-alembic-migration-rename-s3-uuid-to-uuid.md] — Previous story with scope boundaries
- [Source: docs/aws-sync-backlog.md] — AWS Lambda deferred work tracking

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6 (1M context)

### Debug Log References

### Completion Notes List

- ✅ Task 1: Renamed `s3_uuid` in 4 batch processing scripts. Local variables renamed to `doc_uuid` (in files with `import uuid`) to avoid shadowing the standard library module. ORM attribute access changed to `.uuid`.
- ✅ Task 2: Renamed in `document_prepare.py` (4 occurrences) and `dynamodb_sync.py` (6 occurrences). Added backward-compat `item.get("uuid") or item.get("s3_uuid")` in dynamodb_sync.py for both metadata dict and S3 content fetch. Metadata key changed from `"s3_uuid"` to `"uuid"` to match ORM attribute used by `import_document()`.
- ✅ Task 3: Renamed 11 occurrences in `gcloud_firestore.py` — function `migrate_s3_uuid_to_storage_uuid` → `migrate_uuid_to_storage_uuid`, local variables updated. Firestore field name references (`'s3_uuid'` in `doc_data` checks and `DELETE_FIELD`) preserved — these are external data field names, not Python attributes.
- ✅ Task 4: Updated documentation in 4 files. `aws-sync-backlog.md` DB schema item marked as complete with note that only Lambda code remains.
- ✅ Task 5: Ruff linting passes on all changed files (zero new warnings). All 70 unit tests pass with 0 regressions.
- ⚠️ Note: Pre-existing ruff warnings (F541 f-strings without placeholders) exist in `test_code/gcloud_firestore.py` and `library/document_prepare.py` — these are not introduced by this story and tracked in B-103.

### File List

- backend/web_documents_do_the_needful_new.py (modified)
- backend/imports/migrate_data_to_cache.py (modified)
- backend/web_documents_fix_missing_markdown.py (modified)
- backend/webdocument_md_decode.py (modified)
- backend/library/document_prepare.py (modified)
- backend/imports/dynamodb_sync.py (modified)
- backend/test_code/gcloud_firestore.py (modified)
- backend/imports/CLAUDE.md (modified)
- docs/api-type-sync-strategy.md (modified)
- _bmad-output/planning-artifacts/architecture.md (modified)
- docs/aws-sync-backlog.md (modified)

## Change Log

- 2026-04-07: Story 34-2 implementation — renamed all `s3_uuid` references to `uuid` across 7 Python files and 4 documentation files. Added DynamoDB backward-compat mapping in dynamodb_sync.py. Local variables use `doc_uuid` to avoid shadowing `import uuid`. Metadata keys updated to `"uuid"` for ORM compatibility.
- 2026-04-07: Code review fixes — (1) Reverted Firestore field name checks in `gcloud_firestore.py:migrate_uuid_to_storage_uuid` back to `'s3_uuid'` — these reference external Firestore document field names, not Python attributes. (2) Added forward-compat pattern in `web_documents_do_the_needful_new.py` to accept both `uuid` and `s3_uuid` keys from input JSON (matching `dynamodb_sync.py` pattern).
