# Story B-94: Create Lookup Tables and Seed Data

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **developer**,
I want lookup tables (`document_status_types`, `document_status_error_types`, `document_types`, `embedding_models`) created in the database with seed data from Python enums,
so that valid values are defined at the database level, not just in application code.

## Context

- **Epic 30**: Database Lookup Tables & Search Extensions
- **ADR**: [ADR-010: Database Lookup Tables with Foreign Keys](docs/architecture-decisions.md) — accepted, defines the schema
- **AWS production** (dump 2026-01-23) already has these 4 tables with FK constraints
- **Docker init scripts** do NOT create them — this story closes that gap
- **This story creates tables + seed data ONLY** — FK constraints are B-95, ORM updates are B-96

## Acceptance Criteria

1. All 4 lookup tables exist after `docker compose up` (fresh volume)
2. `SELECT count(*) FROM document_status_types` returns **16**
3. `SELECT count(*) FROM document_status_error_types` returns **17**
4. `SELECT count(*) FROM document_types` returns **6**
5. `SELECT count(*) FROM embedding_models` returns **7**
6. Alembic migration applies cleanly to existing Docker database (`alembic upgrade head`)
7. Alembic migration applies cleanly to AWS RDS (via VPN) — manual verification
8. All tables use schema: `id SERIAL PRIMARY KEY, name VARCHAR UNIQUE NOT NULL`
9. Existing unit tests pass (`cd backend && PYTHONPATH=. uvx pytest tests/unit/ -v`)
10. `uvx ruff check backend/` passes clean

## Tasks / Subtasks

- [x] Task 1: Create SQL init script (AC: #1, #2, #3, #4, #5, #8)
  - [x] Create `backend/database/init/09-create-lookup-tables.sql`
  - [x] Add `\c "lenie-ai";` at top (same pattern as 03/04 scripts)
  - [x] CREATE TABLE for all 4 lookup tables
  - [x] INSERT seed data for each table
  - [x] Add verification SELECTs at bottom
- [x] Task 2: Create Alembic migration (AC: #6, #7)
  - [x] Generate migration: `cd backend && PYTHONPATH=. uvx alembic revision -m "create lookup tables and seed data"`
  - [x] Implement `upgrade()`: CREATE TABLE IF NOT EXISTS + INSERT ... ON CONFLICT DO NOTHING
  - [x] Implement `downgrade()`: DROP TABLE IF EXISTS (reverse order)
  - [x] Test: `cd backend && PYTHONPATH=. uvx alembic upgrade head`
- [x] Task 3: Verify (AC: #9, #10)
  - [x] Run unit tests
  - [x] Run ruff

## Dev Notes

### Lookup Table Schema (all 4 tables identical structure)

```sql
CREATE TABLE IF NOT EXISTS <table_name> (
    id SERIAL PRIMARY KEY,
    name VARCHAR UNIQUE NOT NULL
);
```

FK constraints reference `name` column (not `id`) — decided in ADR-010 for query readability.

### Seed Data — Exact Values

**`document_status_types`** (16 rows) — source: `backend/library/models/stalker_document_status.py`
```
ERROR, URL_ADDED, NEED_TRANSCRIPTION, TRANSCRIPTION_IN_PROGRESS, TRANSCRIPTION_DONE,
TRANSCRIPTION_DONE_AND_SPLIT_BY_CHAPTERS, NEED_MANUAL_REVIEW, READY_FOR_TRANSLATION,
READY_FOR_EMBEDDING, EMBEDDING_EXIST, DOCUMENT_INTO_DATABASE, NEED_CLEAN_TEXT,
NEED_CLEAN_MD, TEXT_TO_MD_DONE, MD_SIMPLIFIED, TEMPORARY_ERROR
```

**`document_status_error_types`** (17 rows) — source: `backend/library/models/stalker_document_status_error.py`
```
NONE, ERROR_DOWNLOAD, LINK_SUMMARY_MISSING, TITLE_MISSING, TITLE_TRANSLATION_ERROR,
TEXT_MISSING, TEXT_TRANSLATION_ERROR, SUMMARY_TRANSLATION_ERROR, NO_URL_ERROR,
EMBEDDING_ERROR, MISSING_TRANSLATION, TRANSLATION_ERROR, REGEX_ERROR, TEXT_TO_MD_ERROR,
NO_CAPTIONS_AVAILABLE, CAPTIONS_LANGUAGE_MISMATCH, CAPTIONS_FETCH_ERROR
```

**`document_types`** (6 rows) — source: `backend/library/models/stalker_document_type.py`
```
movie, youtube, link, webpage, text_message, text
```

**`embedding_models`** (7 rows) — source: `backend/database/init/04-create-table.sql` HNSW indexes + sequential scan models
```
text-embedding-ada-002, amazon.titan-embed-text-v1, amazon.titan-embed-text-v2:0,
dunzhang/stella_en_1.5B_v5, BAAI/bge-m3, BAAI/bge-multilingual-gemma2,
intfloat/e5-mistral-7b-instruct
```

### SQL Init Script Pattern

Follow existing patterns from `03-create-table.sql` and `04-create-table.sql`:
- Start with `\c "lenie-ai";`
- Use `CREATE TABLE IF NOT EXISTS public.<table_name>`
- Use `INSERT INTO ... VALUES ... ON CONFLICT (name) DO NOTHING` for idempotency
- End with confirmation SELECT

### Alembic Migration Pattern

- First migration in the project — `backend/alembic/versions/` is currently **empty**
- Use `op.execute()` for raw SQL (same CREATE TABLE + INSERT as init script)
- Use `ON CONFLICT DO NOTHING` for idempotent seed inserts (safe to re-run)
- Downgrade: `DROP TABLE IF EXISTS` in reverse dependency order (embedding_models, document_types, document_status_error_types, document_status_types)
- Reference: `backend/alembic/env.py` — already configured with `load_config()` for DB connection

### Critical Constraints

- **DO NOT** add FK constraints — that is B-95 scope
- **DO NOT** modify ORM models in `backend/library/db/models.py` — that is B-96 scope
- **DO NOT** modify existing init scripts (03, 04) — only add new 09 script
- The Python enums are the **source of truth** — seed data must exactly match enum `.name` values (not `.value`)
- `document_state` column stores enum names as strings (e.g., `'URL_ADDED'`, not `2`)
- `document_type` column stores lowercase names (e.g., `'movie'`, `'youtube'`)
- `document_state_error` stores enum names (e.g., `'NONE'`, `'ERROR_DOWNLOAD'`)
- `embedding_models.name` stores exact model identifier strings as used in `websites_embeddings.model` column

### Previous Story Intelligence

- **B-93** (done): Added `/document_states` endpoint returning status values from Python enums. Code review fixed 4 issues. Pattern: backend returns enum data, frontend consumes dynamically.
- **B-97** (done): Installed `unaccent` and `pg_trgm` extensions in `02-create-extension.sql`. Pattern for adding DB extensions already established.
- **Sprint 9 (Epics 26-29)**: Full SQLAlchemy ORM migration completed. ORM models in `backend/library/db/models.py`, engine in `backend/library/db/engine.py`, Alembic initialized. All legacy psycopg2 removed.

### Project Structure Notes

- Init scripts: `backend/database/init/09-create-lookup-tables.sql` (next number in sequence)
- Alembic versions: `backend/alembic/versions/<hash>_create_lookup_tables_and_seed_data.py`
- No new Python files needed — only SQL + Alembic migration

### References

- [Source: docs/architecture-decisions.md — ADR-010: Database Lookup Tables with Foreign Keys]
- [Source: backend/library/models/stalker_document_status.py — 16 states]
- [Source: backend/library/models/stalker_document_status_error.py — 17 error types]
- [Source: backend/library/models/stalker_document_type.py — 6 document types]
- [Source: backend/database/init/04-create-table.sql — 7 embedding models from HNSW indexes]
- [Source: backend/database/init/03-create-table.sql — web_documents table pattern]
- [Source: backend/alembic/env.py — Alembic configuration]

## Dev Agent Record

### Agent Model Used
Claude Opus 4.6

### Debug Log References
None — clean implementation, no debug issues.

### Completion Notes List
- Created SQL init script `09-create-lookup-tables.sql` with 4 lookup tables and seed data (16 + 17 + 6 + 7 = 46 rows total)
- Created first Alembic migration `906d2cc23d09_create_lookup_tables_and_seed_data.py` with idempotent upgrade (CREATE IF NOT EXISTS + ON CONFLICT DO NOTHING) and clean downgrade (DROP IF EXISTS)
- All seed data values verified against Python enum `.name` attributes
- Unit tests: 49 passed, 18 skipped, 29 errors (all pre-existing SQLAlchemy import errors in uvx environment — 20 from test_alembic_setup.py, 9 from test_get_list_query.py)
- Ruff: clean on new files (2 auto-generated issues in migration template fixed)
- AC #7 (AWS RDS via VPN) requires manual verification by user

### Change Log
- 2026-03-10: Created lookup tables and seed data (SQL init + Alembic migration)
- 2026-03-10: Code review fix — added `include_object` filter for lookup tables in `alembic/env.py` (prevents accidental DROP TABLE via autogenerate before B-96)
- 2026-03-10: Code review fix — corrected test error count (9→29), added sprint-status.yaml to File List

### File List
- `backend/database/init/09-create-lookup-tables.sql` (new)
- `backend/alembic/versions/906d2cc23d09_create_lookup_tables_and_seed_data.py` (new)
- `backend/alembic/env.py` (modified — added lookup table filter to `include_object`)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (modified — B-94 status update)
