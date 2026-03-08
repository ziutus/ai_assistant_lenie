## Epic 26: ORM Foundation & Schema Management

Developer can define database schema as SQLAlchemy 2.x ORM models, manage database sessions for Flask and scripts, and use Alembic for schema migrations — eliminating the fear of schema changes.

### Story 26.1: Dependencies, Engine & Session Factories

As a **developer**,
I want SQLAlchemy engine and session factory functions (`get_engine`, `get_session`, `get_scoped_session`),
So that all consumers have a unified, thread-safe way to access the database.

**Acceptance Criteria:**

**Given** `pyproject.toml` is updated with `sqlalchemy>=2.0,<3.0`, `pgvector>=0.3.0`, `alembic>=1.13`
**When** `uv lock` is run
**Then** lock file is valid and dependencies resolve

**Given** `library/db/engine.py` exists
**When** `get_engine()` is called
**Then** returns a SQLAlchemy engine with `pool_pre_ping=True` using `POSTGRESQL_*` env vars

**Given** engine is initialized
**When** `get_session()` is called
**Then** returns a new `Session` bound to the engine (for scripts)

**Given** engine is initialized
**When** `get_scoped_session()` is called
**Then** returns a thread-local `scoped_session` (for Flask)

**Given** `.venv_wsl` exists
**When** dependencies change
**Then** `.venv_wsl` is synchronized

**Covers:** FR10, FR12, FR13 | NFR10, NFR11, NFR12

### Story 26.2: ORM Models — WebDocument (STI) & WebsiteEmbedding

As a **developer**,
I want `WebDocument` and `WebsiteEmbedding` defined as SQLAlchemy 2.x ORM models in `library/db/models.py`,
So that database schema is defined once in Python and I can add columns/tables with a single-file change.

**Acceptance Criteria:**

**Given** `library/db/models.py` exists
**When** `WebDocument` model is inspected
**Then** it maps all 28 columns from `web_documents` table with exact column names and types matching DDL (`03-create-table.sql`)

**Given** `WebDocument` has STI configured
**When** `__mapper_args__` is inspected
**Then** `document_type` is the polymorphic discriminator

**Given** `WebDocument` has domain methods
**When** `set_document_type()`, `set_document_state()`, `validate()`, `dict()` are called
**Then** they behave identically to current `StalkerWebDocumentDB` methods

**Given** `dict()` is called on a `WebDocument` instance
**When** the result is inspected
**Then** dates are formatted as `"YYYY-MM-DD HH:MM:SS"`, enums as `.name`, all existing keys preserved

**Given** `WebsiteEmbedding` model exists
**When** inspected
**Then** it has dimensionless `Vector()` column, `web_document_id` FK, `language`, `model`, `text` columns matching DDL (`04-create-table.sql`)

**Given** `WebDocument` has a relationship to `WebsiteEmbedding`
**When** relationship is inspected
**Then** `cascade="all, delete-orphan"` is configured

**Given** enums are needed by ORM model
**When** imports are inspected
**Then** enums are imported from `library.models.stalker_document_status` (original location, not moved)

**Given** all ORM model columns use type hints
**When** code is inspected
**Then** all columns use `Mapped[type]` with `mapped_column()` (not older `Column()` style)

**Given** navigation fields exist
**When** `next_id`, `next_type`, `previous_id`, `previous_type` are inspected
**Then** they are plain Python class attributes (`= None`), NOT `mapped_column()`

**Covers:** FR1, FR2, FR3, FR4, FR5 | NFR4, NFR5, NFR7

### Story 26.3: Alembic Initialization & Flask Session Integration

As a **developer**,
I want Alembic initialized with a baseline migration and Flask session teardown configured,
So that I can auto-generate migration scripts from model changes and Flask sessions are properly scoped.

**Acceptance Criteria:**

**Given** `backend/alembic.ini` and `backend/alembic/env.py` exist
**When** `alembic revision --autogenerate -m "test"` is run against existing database
**Then** the generated migration is empty (no diff — model matches DDL exactly)

**Given** Alembic is initialized
**When** `alembic stamp head` is run
**Then** existing database is marked as baseline (no migrations needed)

**Given** developer adds a new column to the ORM model
**When** `alembic revision --autogenerate -m "add column"` is run
**Then** Alembic generates correct `ALTER TABLE` migration script

**Given** a migration exists
**When** `alembic upgrade head` is run
**Then** database schema is updated

**Given** a migration was applied
**When** `alembic downgrade -1` is run
**Then** migration is rolled back

**Given** `server.py` has `@app.teardown_appcontext`
**When** a Flask request completes
**Then** `scoped_session.remove()` is called, releasing the session

**Given** re-export files exist
**When** `from library.stalker_web_document import StalkerWebDocument` is used
**Then** it returns the `WebDocument` ORM model (backward compatibility)

**Given** re-export files exist
**When** `from library.stalker_web_document_db import StalkerWebDocumentDB` is used
**Then** it returns the `WebDocument` ORM model (backward compatibility)

**Covers:** FR6, FR7, FR8, FR9, FR10, FR11 | NFR5, NFR6, NFR8
