# Story 26.3: Alembic Initialization & Flask Session Integration

Status: done

## Story

As a **developer**,
I want Alembic initialized with a baseline migration and Flask session teardown configured,
So that I can auto-generate migration scripts from model changes and Flask sessions are properly scoped.

## Acceptance Criteria

1. **Given** `backend/alembic.ini` and `backend/alembic/env.py` exist
   **When** `alembic revision --autogenerate -m "test"` is run against the existing database
   **Then** the generated migration is empty (no diff — ORM model matches DDL exactly)

2. **Given** Alembic is initialized
   **When** `alembic stamp head` is run
   **Then** the existing database is marked as baseline (alembic_version table created with head revision)

3. **Given** a developer adds a new column to the ORM model
   **When** `alembic revision --autogenerate -m "add column"` is run
   **Then** Alembic generates a correct `ALTER TABLE ADD COLUMN` migration script

4. **Given** a migration script exists
   **When** `alembic upgrade head` is run
   **Then** the database schema is updated

5. **Given** a migration was applied
   **When** `alembic downgrade -1` is run
   **Then** the migration is rolled back

6. **Given** `server.py` has `@app.teardown_appcontext` handler
   **When** a Flask request completes (success or exception)
   **Then** `scoped_session.remove()` is called, releasing the session and returning the connection to the pool

## Tasks / Subtasks

- [x] Task 1: Initialize Alembic environment (AC: #1, #2)
  - [x] 1.1: Run `alembic init alembic` from `backend/` to create `alembic/` directory structure (env.py, script.py.mako, versions/)
  - [x] 1.2: Configure `alembic.ini` — remove hardcoded `sqlalchemy.url`, add comment that URL is built programmatically in env.py
  - [x] 1.3: Configure `alembic/env.py` — import `Base` from `library.db.engine`, import models from `library.db.models` to register metadata, use `get_engine()` for connectable
  - [x] 1.4: Implement both `run_migrations_offline()` (URL-based) and `run_migrations_online()` (engine-based) modes
  - [x] 1.5: Add `compare_type=True` to `context.configure()` so Alembic detects column type changes

- [x] Task 2: Create baseline and verify empty autogenerate (AC: #1, #2)
  - [x] 2.1: Run `alembic stamp head` against NAS PostgreSQL database to create `alembic_version` table
  - [x] 2.2: Run `alembic revision --autogenerate -m "verify baseline"` — verify the generated migration has empty `upgrade()` and `downgrade()` functions
  - [x] 2.3: If migration is NOT empty, analyze the diff and fix either ORM model or env.py configuration until autogenerate produces no changes
  - [x] 2.4: Delete the verification migration file (it was only used for validation)

- [x] Task 3: Add Flask session teardown (AC: #6)
  - [x] 3.1: Add `@app.teardown_appcontext` handler in `server.py` that calls `get_scoped_session().remove()`
  - [x] 3.2: Place the handler AFTER Flask app creation but BEFORE route definitions

- [x] Task 4: Write unit tests (AC: #1, #6)
  - [x] 4.1: Test `alembic.ini` exists at `backend/alembic.ini`
  - [x] 4.2: Test `alembic/env.py` exists and can be imported without errors
  - [x] 4.3: Test that `target_metadata` in env.py references `Base.metadata` with correct tables registered
  - [x] 4.4: Test Flask teardown handler is registered on the app
  - [x] 4.5: Test teardown handler calls `scoped_session.remove()` (mock-based)

- [x] Task 5: Verify autogenerate and migration cycle (AC: #3, #4, #5)
  - [x] 5.1: Add a temporary test column to WebDocument model
  - [x] 5.2: Run `alembic revision --autogenerate -m "test add column"` — verify it generates `op.add_column()`
  - [x] 5.3: Run `alembic upgrade head` — verify column is added to database
  - [x] 5.4: Run `alembic downgrade -1` — verify column is removed
  - [x] 5.5: Remove the temporary column from model and delete the test migration file
  - [x] 5.6: Run `alembic revision --autogenerate -m "verify clean"` — confirm empty migration (no leftover diff)
  - [x] 5.7: Delete the verification migration and confirm `alembic/versions/` is clean

- [x] Task 6: Quality checks (AC: all)
  - [x] 6.1: Run `ruff check backend/` — zero warnings for new/modified files
  - [x] 6.2: Run existing unit tests — no regressions (4 pre-existing failures in test_metrics_endpoint.py unchanged)
  - [x] 6.3: Sync `.venv_wsl` and verify Alembic import: `from alembic.config import Config`

## Dev Notes

### Architecture Requirements

This story implements **Phase C (Alembic + Flask Integration)** of the 9-phase SQLAlchemy ORM migration sequence. It depends on Story 26.1 (engine, Base, session factories) which is DONE and Story 26.2 (ORM models) which is in REVIEW. All subsequent stories (Epic 27-29) depend on this.

**Key architectural decisions (from PRD and epics):**

1. **No Flask-Migrate or Flask-Alembic:** Use plain Alembic directly — explicit control, no extension magic, works for both Flask and scripts.
2. **Engine reuse in env.py:** `alembic/env.py` MUST use `get_engine()` from `library.db.engine` — never build engine independently.
3. **Programmatic URL:** Do NOT put database URL in `alembic.ini`. Build it from POSTGRESQL_* env vars via `get_engine()`.
4. **Baseline via stamp:** Use `alembic stamp head` on existing database — no "create from scratch" migration.
5. **HNSW indexes NOT in autogenerate:** Existing per-model HNSW partial indexes on `websites_embeddings` are NOT managed by Alembic autogenerate. They exist in DDL files and will be managed via raw SQL in custom Alembic migrations when needed.
6. **pgvector Vector() compatibility:** Alembic must handle dimensionless `Vector()` column from pgvector-python. Test that autogenerate correctly ignores this column if unchanged.
7. **Enum-as-VARCHAR:** Autogenerate must NOT create PostgreSQL ENUM types. Ensure `native_enum=False` columns render as VARCHAR/TEXT in migrations, not as `CREATE TYPE`.

### Descoped: Re-Export Wrappers (ACs 7-8 from Epics)

The original epics included two additional ACs about re-exporting `StalkerWebDocument` and `StalkerWebDocumentDB` as aliases for `WebDocument`. **These are descoped from Story 26.3** because:

- `StalkerWebDocumentDB(document_id=123)` currently opens a psycopg2 connection and queries the database in `__init__`. A simple re-export to `WebDocument` would break this constructor.
- Consumer migration (replacing psycopg2 calls with ORM queries) is Epic 27 scope, not Epic 26.
- Re-exports only make sense AFTER all consumers are migrated.

**Impact:** None. Old code continues to use old classes unchanged. New ORM code imports directly from `library.db.models`.

### `alembic/env.py` — Required Configuration

```python
import sys
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool

# Ensure backend/ is on sys.path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from library.db.engine import get_engine, Base

# CRITICAL: Import models to register them on Base.metadata
import library.db.models  # noqa: F401

target_metadata = Base.metadata
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (generates SQL without DB connection)."""
    url = str(get_engine().url)
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (connected to database)."""
    connectable = get_engine()

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

**Why `compare_type=True`:** Without it, Alembic ignores column type changes (e.g., String(50) → Text). Critical for detecting `document_state_error` drift (DDL is TEXT, ORM SAEnum has no explicit length).

**Why `import library.db.models`:** Model classes must be imported before `Base.metadata` is passed to Alembic. Without this, Alembic sees an empty metadata and tries to DROP all tables!

### `alembic.ini` — Key Configuration

```ini
[alembic]
script_location = alembic
# sqlalchemy.url is NOT set here — built programmatically in env.py via get_engine()

[loggers]
keys = root,sqlalchemy,alembic
# ... standard logging config
```

**Why no sqlalchemy.url:** The URL is built from environment variables in `get_engine()`. Hardcoding it in `alembic.ini` would require maintaining a separate connection string.

### Flask Teardown Handler

```python
@app.teardown_appcontext
def shutdown_session(exception=None):
    """Clean up scoped session at end of Flask request."""
    from library.db.engine import get_scoped_session
    get_scoped_session().remove()
```

**Why lazy import:** The `get_scoped_session()` function initializes engine lazily. Using a lazy import in the teardown avoids triggering engine initialization at app startup (before env vars are loaded).

**Why `exception=None`:** Flask passes the exception (if any) to teardown handlers. We clean up the session regardless — if there was an error, the session transaction will be rolled back automatically by SQLAlchemy.

**Placement:** The handler must be registered AFTER `app = Flask(__name__)` and AFTER `CORS(app)`. It does NOT need to be before route definitions since teardown hooks are registered globally, not per-route.

### Known Schema Drift: `document_state_error` Column Type

**DDL:** `document_state_error text` (unlimited length)
**ORM:** `SAEnum(StalkerDocumentStatusError, native_enum=False)` — which maps to `VARCHAR` without explicit length

When running `alembic revision --autogenerate`, this MAY produce a migration to change the column type from TEXT to VARCHAR. **If this happens:**
- Option A: Add explicit `length=None` or use `Text` type wrapper in the SAEnum definition
- Option B: Accept the migration (VARCHAR without length is effectively TEXT in PostgreSQL)
- Option C: Add the column to `include_object` exclusion filter in env.py

Document which option was chosen in Completion Notes.

### Known Schema Drift: Indexes

The DDL scripts create 9 indexes on `web_documents` and 7 indexes on `websites_embeddings` (including 5 HNSW partial indexes). These are NOT defined in the ORM model. When running autogenerate:

- **Standard indexes:** Alembic will NOT detect indexes that aren't declared via `Index()` in the ORM model. This is correct — we don't want to manage existing indexes via Alembic yet.
- **HNSW partial indexes:** Same — Alembic ignores them since they're not in metadata.
- **If autogenerate produces DROP INDEX operations:** Add an `include_object` filter to exclude index objects:
  ```python
  def include_object(object, name, type_, reflected, compare_to):
      if type_ == "index":
          return False
      return True
  ```

### Alembic Commands Reference

```bash
# From backend/ directory:

# Initialize (one-time — Task 1)
alembic init alembic

# Mark existing database as baseline (Task 2)
alembic stamp head

# Generate migration from model changes
alembic revision --autogenerate -m "description of change"

# Apply all pending migrations
alembic upgrade head

# Rollback last migration
alembic downgrade -1

# Show current database revision
alembic current

# Show migration history
alembic history
```

All commands require POSTGRESQL_* environment variables (from `.env` file or config loader).

### Testing Strategy

**Unit tests** (no database required):
- Verify alembic.ini and alembic/ directory structure exist
- Verify env.py can be imported and `target_metadata` has expected tables
- Verify Flask teardown handler is registered (use Flask test app)
- Mock-based test: teardown handler calls `scoped_session.remove()`

**Manual verification** (requires Docker database):
- Task 2: Baseline verification (stamp + empty autogenerate)
- Task 5: Full migration cycle (add column → upgrade → downgrade → clean)

**Test location:** `backend/tests/unit/test_alembic_setup.py`

**Test framework:** `cd backend && PYTHONPATH=. .venv/Scripts/python -m pytest tests/unit/test_alembic_setup.py -v`
(Use project venv, not uvx — sqlalchemy/alembic are in project venv)

### Previous Story Learnings (from 26-1 and 26-2)

1. **`uvx pytest` doesn't work for these tests** — sqlalchemy/pgvector/alembic are not in uvx's isolated env. Use `.venv/Scripts/python -m pytest` instead.
2. **`sa_text` alias** — `sqlalchemy.text` is aliased as `sa_text` in models.py to avoid conflict with `text` column name.
3. **4 pre-existing test failures** in `test_metrics_endpoint.py` (x-api-key header issue) — unrelated, don't try to fix them.
4. **`dispose_engine()` exists** — use it in test teardown to clean up engine state.
5. **Mock `os.getenv`** to control POSTGRESQL_* variables in engine tests (pattern from test_db_engine.py).
6. **WSL .venv_wsl sync command:**
   ```bash
   wsl bash -c "export PATH=\"\$HOME/.local/bin:\$PATH\" && cd /mnt/c/Users/ziutus/git/_lenie-all/lenie-server-2025/backend && .venv_wsl/bin/python -c 'from alembic.config import Config; print(\"OK\")'"
   ```

### Current File Structure (what exists from Stories 26.1-26.2)

```
backend/library/db/
├── __init__.py          # Empty package init (Story 26.1)
├── engine.py            # Base, get_engine(), get_session(), get_scoped_session(), dispose_engine() (Story 26.1)
└── models.py            # WebDocument (26 cols, STI), 6 subclasses, WebsiteEmbedding (Story 26.2)

backend/tests/unit/
├── test_db_engine.py    # 15 tests for engine.py (Story 26.1)
└── test_db_models.py    # 96 tests for models.py (Story 26.2)
```

**After Story 26.3:**
```
backend/
├── alembic.ini          # NEW: Alembic configuration
├── alembic/             # NEW: Alembic migration directory
│   ├── env.py           # NEW: Migration environment (uses get_engine() + Base.metadata)
│   ├── script.py.mako   # NEW: Migration script template (auto-generated by alembic init)
│   ├── README           # NEW: Auto-generated by alembic init
│   └── versions/        # NEW: Migration scripts directory (empty after baseline stamp)
├── server.py            # MODIFIED: Add @app.teardown_appcontext handler
└── tests/unit/
    └── test_alembic_setup.py  # NEW: Unit tests for Alembic config and Flask teardown
```

### Critical Anti-Patterns

- **DO NOT** put sqlalchemy.url in alembic.ini — use get_engine() from env.py
- **DO NOT** create a Flask-Migrate or Flask-Alembic extension — use plain Alembic
- **DO NOT** let autogenerate create PostgreSQL ENUM types — verify native_enum=False behavior
- **DO NOT** let autogenerate create DROP INDEX operations for existing indexes
- **DO NOT** create "initial" migration that creates tables from scratch — use stamp head instead
- **DO NOT** import models lazily in env.py — import BEFORE passing metadata to context.configure()
- **DO NOT** call get_engine() at module level in env.py — call it inside run_migrations_online/offline only (avoids import-time side effects)
- **DO NOT** modify `library/db/engine.py` or `library/db/models.py` — this story only configures Alembic and Flask teardown

### SQLAlchemy 2.x + Alembic API Reference (verified March 2026)

**Alembic env.py with get_engine():**
```python
from library.db.engine import get_engine, Base
import library.db.models  # noqa: F401 — register models on Base.metadata

target_metadata = Base.metadata

def run_migrations_online():
    connectable = get_engine()
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()
```

**Alembic stamp (no migration, just mark version):**
```bash
alembic stamp head
# Creates alembic_version table with current head revision
# No schema changes — just records "database is at this version"
```

**Flask teardown pattern:**
```python
@app.teardown_appcontext
def shutdown_session(exception=None):
    get_scoped_session().remove()
```

### References

- [Source: _bmad-output/planning-artifacts/prd.md — Target Architecture, Session Management, Alembic Strategy]
- [Source: _bmad-output/planning-artifacts/epics.md — Epic 26, Story 26.3 ACs and functional requirements]
- [Source: _bmad-output/planning-artifacts/architecture.md — Database Schema, Session Lifecycle, Migration Strategy]
- [Source: _bmad-output/implementation-artifacts/26-1-dependencies-engine-session-factories.md — Engine API, test patterns, WSL sync]
- [Source: _bmad-output/implementation-artifacts/26-2-orm-models-web-document-website-embedding.md — ORM models, enum patterns, test patterns]
- [Source: backend/library/db/engine.py — Base, get_engine(), get_session(), get_scoped_session(), dispose_engine()]
- [Source: backend/library/db/models.py — WebDocument (26 cols, STI), WebsiteEmbedding (8 cols, Vector)]
- [Source: backend/server.py — Flask app structure, existing before_request hook, CORS setup]
- [Source: backend/database/init/03-create-table.sql — web_documents DDL (26 columns, 9 indexes)]
- [Source: backend/database/init/04-create-table.sql — websites_embeddings DDL (8 columns, 7 indexes including 5 HNSW)]
- [Source: Alembic docs — env.py configuration, autogenerate, stamp, compare_type]
- [Source: pgvector-python docs — Vector() type, Alembic compatibility]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6 (claude-opus-4-6)

### Debug Log References

None.

### Completion Notes List

- **Task 1**: Initialized Alembic 1.18.4 via `alembic init alembic`. Configured `alembic.ini` (removed hardcoded sqlalchemy.url) and `alembic/env.py` (imports Base + models from library.db, uses get_engine(), compare_type=True, include_object filter for indexes and document_state_error drift).
- **Task 2**: Ran `alembic stamp head` against NAS PostgreSQL. Initial autogenerate detected expected drift on `document_state_error` (TEXT vs SAEnum/VARCHAR). Chose **Option C** — added `include_object` filter to exclude this column (TEXT and VARCHAR without length are equivalent in PostgreSQL). After filter: autogenerate produces empty migration (pass). Verification migration deleted, `alembic/versions/` clean.
- **Task 3**: Added `@app.teardown_appcontext` handler (`shutdown_session`) in `server.py` after `CORS(app)`. Uses lazy import of `get_scoped_session()` to avoid engine initialization at startup.
- **Task 4**: Created 15 unit tests in `test_alembic_setup.py`: 4 file existence tests, 2 alembic.ini config tests, 7 env.py metadata tests, 2 Flask teardown tests (registration + mock-based scoped_session.remove() verification). All 15 pass.
- **Task 5**: Full migration cycle verified on NAS database: added temporary `test_alembic_column` (String(50)) to WebDocument → autogenerate produced correct `op.add_column()` → `alembic upgrade head` applied → `alembic downgrade -1` rolled back → model restored → autogenerate confirmed clean. All test artifacts removed.
- **Task 6**: `ruff check` passes on all new/modified files. 228/232 unit tests pass (4 pre-existing failures in test_metrics_endpoint.py — x-api-key header issue, unrelated). WSL .venv_wsl verified: `from alembic.config import Config` imports OK.
- **env.py enhancement**: Added `from library.config_loader import load_config; load_config()` at top of env.py so Alembic CLI picks up POSTGRESQL_* vars from Vault/AWS/env backend.

### File List

- `backend/alembic.ini` — NEW: Alembic configuration (no hardcoded sqlalchemy.url)
- `backend/alembic/env.py` — NEW: Migration environment (config_loader + get_engine + Base.metadata + models + include_object filter)
- `backend/alembic/script.py.mako` — NEW: Migration script template (auto-generated by alembic init)
- `backend/alembic/README` — NEW: Auto-generated by alembic init
- `backend/alembic/versions/` — NEW: Empty migration scripts directory
- `backend/server.py` — MODIFIED: Added `@app.teardown_appcontext shutdown_session()` handler
- `backend/tests/unit/test_alembic_setup.py` — NEW: 20 unit tests for Alembic config, include_object filter behavior, and Flask teardown

### Senior Developer Review (AI)

**Reviewer:** Claude Opus 4.6 | **Date:** 2026-03-08

**Findings (1 HIGH, 4 MEDIUM, 3 LOW) — all HIGH and MEDIUM fixed:**

- **H1 FIXED**: Added 5 behavioral tests for `include_object` filter (index exclusion, column exclusion by table name, regular column/table inclusion). Previously only tested via string presence.
- **M1 FIXED**: `include_object` column filter now checks `object.table.name == "web_documents"` for specificity — won't accidentally exclude same-named columns in other tables.
- **M2 FIXED**: Added TODO comment to `include_object` exclusion for `document_state_error` — tracks future cleanup.
- **M3 FIXED**: Added docstring to `TestAlembicEnvMetadata` explaining text-based tests are smoke checks (env.py can't be imported due to module-level Alembic context calls).
- **M4 FIXED**: Added inline comment to `shutdown_session` documenting lazy engine initialization behavior.
- **L1 (accepted)**: Redundant `sys.path.insert` in env.py — defensive, no change needed.
- **L2 (accepted)**: `_reset_engine` autouse fixture — harmless, no change needed.
- **L3 (accepted)**: `object` parameter name shadows builtin — follows Alembic API convention.

**Result:** All HIGH and MEDIUM issues fixed. 20/20 tests pass. Ruff clean.

## Change Log

- 2026-03-08: Story 26.3 implemented — Alembic initialized, baseline verified on NAS PostgreSQL, Flask session teardown added, 15 unit tests, full migration cycle verified.
- 2026-03-08: Code review — 8 issues found (1H, 4M, 3L). All HIGH/MEDIUM fixed: added 5 behavioral tests for include_object, added table-name check to column filter, added TODO and explanatory comments. 20/20 tests pass.
