# Story 26.1: Dependencies, Engine & Session Factories

Status: done

## Story

As a **developer**,
I want SQLAlchemy engine and session factory functions (`get_engine`, `get_session`, `get_scoped_session`),
So that all consumers have a unified, thread-safe way to access the database.

## Acceptance Criteria

1. **Given** `pyproject.toml` is updated with `sqlalchemy>=2.0,<3.0`, `pgvector>=0.3.0`, `alembic>=1.13`
   **When** `uv lock` is run
   **Then** lock file is valid and dependencies resolve

2. **Given** `library/db/engine.py` exists
   **When** `get_engine()` is called
   **Then** returns a SQLAlchemy engine with `pool_pre_ping=True` using `POSTGRESQL_*` config keys (via `load_config()`)

3. **Given** engine is initialized
   **When** `get_session()` is called
   **Then** returns a new `Session` bound to the engine (for scripts)

4. **Given** engine is initialized
   **When** `get_scoped_session()` is called
   **Then** returns a thread-local `scoped_session` (for Flask)

5. **Given** `.venv_wsl` exists
   **When** dependencies change
   **Then** `.venv_wsl` is synchronized

## Tasks / Subtasks

- [x] Task 1: Add SQLAlchemy, pgvector, and Alembic dependencies to pyproject.toml (AC: #1)
  - [x] 1.1: Add `sqlalchemy>=2.0,<3.0` to base dependencies in `pyproject.toml`
  - [x] 1.2: Add `pgvector>=0.3.0` to base dependencies
  - [x] 1.3: Add `alembic>=1.13` to base dependencies
  - [x] 1.4: Add the same 3 dependencies to the `docker` and `all` optional extras
  - [x] 1.5: Run `uv lock` and verify lock file is valid
  - [x] 1.6: Verify imports work: `python -c "import sqlalchemy; import pgvector; import alembic"`
- [x] Task 2: Create `backend/library/db/` package with engine and session factories (AC: #2, #3, #4)
  - [x] 2.1: Create `backend/library/db/__init__.py` (empty package init)
  - [x] 2.2: Create `backend/library/db/engine.py` with `Base` (DeclarativeBase), `get_engine()`, `get_session()`, `get_scoped_session()`
  - [x] 2.3: `get_engine()` builds connection URL from `POSTGRESQL_*` config keys (via `load_config()`), sets `pool_pre_ping=True`, returns thread-safe singleton Engine
  - [x] 2.4: `get_engine()` supports optional `POSTGRESQL_SSLMODE` via `connect_args`
  - [x] 2.5: `get_session()` returns a new plain `Session` via `sessionmaker(bind=engine)()`
  - [x] 2.6: `get_scoped_session()` returns a thread-local `scoped_session` via `scoped_session(sessionmaker(bind=engine))`
  - [x] 2.7: `Base` is declared as `class Base(DeclarativeBase): pass` for use by ORM models (Story 26.2)
- [x] Task 3: Write unit tests for engine and session factories (AC: #2, #3, #4)
  - [x] 3.1: Test `get_engine()` returns Engine instance with correct `pool_pre_ping` setting
  - [x] 3.2: Test `get_engine()` returns singleton (same instance on multiple calls)
  - [x] 3.3: Test `get_session()` returns new Session instances (different on each call)
  - [x] 3.4: Test `get_scoped_session()` returns scoped_session instance
  - [x] 3.5: Test engine URL construction from config (mock `load_config`)
  - [x] 3.6: Test `POSTGRESQL_SSLMODE` is applied to `connect_args` when set
  - [x] 3.7: Test `Base` is importable and is a DeclarativeBase subclass
- [x] Task 4: Sync `.venv_wsl` and run quality checks (AC: #5)
  - [x] 4.1: Sync `.venv_wsl` in WSL with new dependencies
  - [x] 4.2: Verify import works in WSL: `import sqlalchemy, pgvector, alembic`
  - [x] 4.3: Run `ruff check backend/` — zero warnings (for new files)
  - [x] 4.4: Run existing unit tests — no regressions (234 passed)

## Dev Notes

### Architecture Requirements

This story implements **Phase A (Dependencies)** of the SQLAlchemy ORM migration sequence defined in the [SQLAlchemy migration plan](../../.claude/exports/plan-sqlalchemy-migration.md). It is the foundation — all subsequent stories (26.2 models, 26.3 Alembic, Epic 27-29) depend on this.

**Key architectural decisions:**

1. **Engine Singleton Pattern** — Module-level lazy initialization with `threading.Lock`. One engine per process. Thread-safe by design.

2. **Dual Session Strategy:**
   - **Flask requests** → `get_scoped_session()` returns thread-local `scoped_session`. Cleaned up via `@app.teardown_appcontext` → `scoped_session.remove()` (will be wired in Story 26.3).
   - **Scripts/batch** → `get_session()` returns a plain Session. Caller manages lifecycle: `session = get_session()` → `try/finally` → `session.close()`.

3. **Session Injection** — Repository receives session via constructor: `WebsitesDBPostgreSQL(session)`. Repository NEVER creates, commits, or rolls back sessions — caller controls transactions.

4. **Configuration via `load_config()`** — Connection parameters read via the project's unified config loader (supports Vault, env, AWS SSM backends). Required keys: `POSTGRESQL_HOST`, `POSTGRESQL_DATABASE`, `POSTGRESQL_USER`, `POSTGRESQL_PASSWORD`. Optional: `POSTGRESQL_PORT`, `POSTGRESQL_SSLMODE` (used for AWS RDS connections).

5. **`Base` Declaration** — `DeclarativeBase` subclass exported from `engine.py` for use in `models.py` (Story 26.2). All ORM models will inherit from this Base.

### Current Database Layer (what exists today)

The current system uses **raw psycopg2** with NO ORM:

- `backend/library/stalker_web_documents_db_postgresql.py` — Creates `psycopg2.connect()` in `__init__()`, uses `cursor.execute()` for all queries. Module-level singleton `websites = WebsitesDBPostgreSQL()` in `server.py`.
- `backend/library/stalker_web_document_db.py` — Class-level static `db_conn = None` for single-document CRUD. Uses `os.getenv()` directly for connection params.
- Both use `connect_kwargs` dict with identical env var patterns.

**This story does NOT modify any existing code.** It only ADDS new files. Existing psycopg2 code continues to work unchanged. Migration of consumers happens in Epic 27-29.

### File Structure

```
backend/library/db/           # NEW directory (does not exist yet)
├── __init__.py               # Empty package init
└── engine.py                 # Engine singleton, Base, session factories
```

No other files should be created or modified by this story (except `pyproject.toml` and tests).

### SQLAlchemy 2.x API Reference

**Engine creation (SQLAlchemy 2.1):**
```python
from sqlalchemy import create_engine
engine = create_engine("postgresql+psycopg2://user:pass@host:port/db", pool_pre_ping=True)
```

**Session factories:**
```python
from sqlalchemy.orm import sessionmaker, scoped_session, Session, DeclarativeBase

SessionLocal = sessionmaker(bind=engine)
session = SessionLocal()  # plain session for scripts

ScopedSession = scoped_session(SessionLocal)
session = ScopedSession()  # thread-local for Flask
ScopedSession.remove()  # cleanup on request teardown
```

**DeclarativeBase (2.x style):**
```python
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass
```

### Database Schema (for reference)

**`web_documents`** — 25 columns (after column removals in PR #70):
`id` (serial PK), `url` (text NOT NULL), `document_type` (varchar(50) NOT NULL), `document_state` (varchar(50) NOT NULL, default 'URL_ADDED'), `document_state_error` (text), `title` (text), `text` (text), `text_raw` (text), `text_md` (text), `summary` (text), `language` (varchar(10)), `tags` (text), `source` (text), `author` (text), `note` (text), `paywall` (boolean, default false), `date_from` (date), `created_at` (timestamp, default CURRENT_TIMESTAMP), `document_length` (integer), `chapter_list` (text), `original_id` (text), `transcript_job_id` (text), `ai_summary_needed` (boolean, default false), `s3_uuid` (varchar(100)), `project` (varchar(100)), `transcript_needed` (boolean, default false)

**`websites_embeddings`** — 8 columns:
`id` (serial PK), `website_id` (integer NOT NULL, FK → web_documents.id ON DELETE CASCADE), `language` (varchar(10)), `text` (text), `text_original` (text), `embedding` (vector, dimensionless), `model` (varchar(100) NOT NULL), `created_at` (timestamp, default CURRENT_TIMESTAMP)

### Testing Strategy

**Unit tests only** (no database required):
- Mock `load_config()` to control POSTGRESQL_* config values
- Test engine creation with mocked `create_engine`
- Test session factory return types
- Test singleton behavior of `get_engine()`
- Test SSL mode handling, port validation, missing config detection
- `pytest.importorskip("sqlalchemy")` for graceful skip in environments without SQLAlchemy

**Test location:** `backend/tests/unit/test_db_engine.py`

**Test framework:** pytest (project convention: `cd backend && PYTHONPATH=. uvx pytest tests/unit/ -v`)

### Dependency Version Notes

- **SQLAlchemy >=2.0,<3.0** — Required for `DeclarativeBase`, `Mapped[type]`, `mapped_column()` (2.x ORM API). Version 2.1 is latest stable (March 2026).
- **pgvector >=0.3.0** — Required for `cosine_distance()` native operator support. Used in Story 28 but installed now to avoid future dependency conflicts.
- **Alembic >=1.13** — Required for `--autogenerate` with SQLAlchemy 2.x models. Used in Story 26.3 but installed now as foundation.
- **psycopg2-binary** — Already present, continues to serve as the DBAPI driver for both raw queries AND SQLAlchemy (`postgresql+psycopg2://` dialect).

### WSL Sync Command

After updating dependencies, sync `.venv_wsl`:
```bash
wsl bash -c "export PATH=\"\$HOME/.local/bin:\$PATH\" && cd /mnt/c/Users/ziutus/git/_lenie-all/lenie-server-2025/backend && uv sync --python .venv_wsl/bin/python --active"
```

Verify in WSL:
```bash
wsl bash -c "cd /mnt/c/Users/ziutus/git/_lenie-all/lenie-server-2025/backend && .venv_wsl/bin/python -c 'import sqlalchemy; import pgvector; import alembic; print(\"OK\")"
```

### Project Structure Notes

- `backend/library/db/` is a NEW sub-package within the existing `backend/library/` module hierarchy
- Follows existing pattern: `library/models/`, `library/api/`, `library/website/` are existing sub-packages
- `engine.py` file name chosen over `session.py` because it contains the engine, Base, AND session factories — engine is the foundation
- No conflicts with existing files or modules

### References

- [Source: .claude/exports/plan-sqlalchemy-migration.md — SQLAlchemy ORM migration plan]
- [Source: _bmad-output/planning-artifacts/epics.md — Epic 26, Story 26.1]
- [Source: backend/pyproject.toml — Current dependencies]
- [Source: backend/library/stalker_web_documents_db_postgresql.py — Current psycopg2 connection pattern]
- [Source: backend/library/stalker_web_document_db.py — Current CRUD pattern]
- [Source: backend/database/init/03-create-table.sql — web_documents DDL]
- [Source: backend/database/init/04-create-table.sql — websites_embeddings DDL]
- [Source: SQLAlchemy 2.1 docs — create_engine, sessionmaker, scoped_session, DeclarativeBase]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6 (claude-opus-4-6)

### Debug Log References

- `uv sync --active` with `--python .venv_wsl/bin/python` inadvertently replaced Windows `.venv` with a Linux venv. Fixed by removing via WSL and recreating with `uv sync` on Windows. For future: use `uv pip install` directly into `.venv_wsl` instead of `uv sync --active`.
- `pgvector` package has no `__version__` attribute — adjusted import verification accordingly.
- `pool_pre_ping` is stored as `engine.pool._pre_ping` (private attribute) in SQLAlchemy 2.0.48, not as a public pool attribute.

### Completion Notes List

- Added SQLAlchemy 2.0.48, pgvector 0.4.2, Alembic 1.18.4 to base, docker, and all dependency groups
- Created `backend/library/db/` package with `engine.py` containing: `Base` (DeclarativeBase), `get_engine()` (singleton), `get_session()` (plain Session), `get_scoped_session()` (thread-local scoped_session), `dispose_engine()` (cleanup)
- Engine uses lazy initialization with module-level singleton pattern
- Connection URL built via `sqlalchemy.engine.URL.create()` for safe password encoding
- Config values read via `load_config()` (supports Vault/env/AWS SSM backends)
- Thread-safe singleton initialization with `threading.Lock`
- 17 unit tests covering all public API, singleton behavior, URL construction, SSL mode, special char passwords, port validation, missing config detection, dispose, and Base class
- All 234 unit tests pass
- `.venv_wsl` synchronized and verified in WSL
- Ruff clean for all new files

### Senior Developer Review (AI)

**Review Date:** 2026-03-08
**Review Outcome:** Approve (after fixes)
**Reviewer Model:** Claude Opus 4.6

**Action Items (all resolved):**
- [x] [H1] Password not URL-encoded — switched to `URL.create()`
- [x] [H2] Default values mask misconfiguration — removed all defaults, uses `os.getenv()` (returns None)
- [x] [M1] Weak sslmode test — now mocks `create_engine` and verifies `connect_args`
- [x] [M2] Private `_pre_ping` access — now mocks `create_engine` and verifies `pool_pre_ping` kwarg
- [x] [M3] No public cleanup API — added `dispose_engine()` function, test fixture uses it

### File List

- `backend/pyproject.toml` — Modified (added sqlalchemy, pgvector, alembic to base/docker/all deps)
- `backend/uv.lock` — Modified (updated lock file)
- `backend/library/db/__init__.py` — New (empty package init)
- `backend/library/db/engine.py` — New (engine singleton, Base, session factories, dispose)
- `backend/tests/unit/test_db_engine.py` — New (17 unit tests)

### Change Log

- 2026-03-08: Story 26.1 implemented — SQLAlchemy engine/session foundation for ORM migration (Phase A)
- 2026-03-08: Code review #1 fixes — URL.create() for safe passwords, removed default env values, added dispose_engine(), improved tests (11→15), mocked create_engine for proper argument verification
- 2026-03-08: Code review #2 fixes — switched from os.getenv() to load_config() (Vault/env/AWS SSM support), added threading.Lock for thread-safe singleton, port validation with clear error message, pytest.importorskip for uvx compatibility, improved tests (15→17), fixed story documentation accuracy
