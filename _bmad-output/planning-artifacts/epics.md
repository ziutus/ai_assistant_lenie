---
stepsCompleted:
  - step-01-validate-prerequisites
  - step-02-design-epics
  - step-03-create-stories
  - step-04-final-validation
status: complete
completedAt: '2026-03-07'
inputDocuments:
  - _bmad-output/planning-artifacts/prd.md
  - _bmad-output/planning-artifacts/architecture.md
---

# lenie-server-2025 - Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for lenie-server-2025, decomposing the requirements from the PRD, Architecture (Sprint 6), and PRD Validation Report into implementable stories. The scope covers Sprint 9: SQLAlchemy ORM Migration — replacing raw psycopg2 queries with SQLAlchemy 2.x ORM, Alembic schema migrations, and pgvector-python native operators.

## Requirements Inventory

### Functional Requirements

FR1: Developer can define database table structure as a Python ORM model class in a single file
FR2: Developer can define column types, constraints, defaults, and nullability as model field attributes
FR3: Developer can define relationships between models (one-to-many, many-to-one) using ORM relationship declarations
FR4: Developer can define Single Table Inheritance hierarchy on `web_documents` with document type as discriminator
FR5: Developer can add domain methods (validate, analyze, set_document_type, set_document_state) directly on the ORM model
FR6: Developer can auto-generate migration scripts from ORM model changes via Alembic
FR7: Developer can apply migrations to the database with a single command (`alembic upgrade head`)
FR8: Developer can roll back migrations to a previous version (`alembic downgrade`)
FR9: Developer can initialize Alembic on an existing database by stamping the current state as baseline
FR10: Flask application can obtain thread-local database sessions scoped to the request lifecycle
FR11: Flask application can automatically clean up sessions on request teardown
FR12: Import scripts and batch pipeline can obtain, commit, and close their own database sessions (script-scoped lifecycle)
FR13: Engine can detect and recover from stale database connections (`pool_pre_ping`)
FR14: Consumer can create a new document by instantiating an ORM model and committing to session
FR15: Consumer can update an existing document by modifying ORM model attributes and committing
FR16: Consumer can delete a document via session, with cascade deletion of related embeddings
FR17: Consumer can look up a document by URL for duplicate detection
FR18: Consumer can look up a document by ID
FR19: Consumer can serialize a document to a dictionary for API responses
FR20: Consumer can add a vector embedding to a document via ORM relationship
FR21: Consumer can delete embeddings for a document filtered by model name
FR22: Repository can find documents needing embeddings (outer join on `websites_embeddings`)
FR23: Repository can perform similarity search using `pgvector-python` `cosine_distance()` operator
FR24: Repository can list documents with dynamic filters (document_type, document_state, source, project, limit, offset)
FR25: Repository can count documents by type and/or state
FR26: Repository can find documents ready for download (URL_ADDED state, webpage/link type)
FR27: Repository can find YouTube documents just added (URL_ADDED state, youtube type)
FR28: Repository can find documents with completed transcriptions
FR29: Repository can find the next document to correct (navigation by ID and type)
FR30: Repository can retrieve the last imported date for a given source
FR31: `dynamodb_sync.py` can create documents from DynamoDB items using ORM models
FR32: `dynamodb_sync.py` can set `created_at` and `chapter_list` via normal ORM attribute assignment (no direct SQL)
FR33: `unknown_news_import.py` can create documents from JSON feed entries using ORM models
FR34: `unknown_news_import.py` can detect and skip duplicate URLs via ORM query
FR35: `web_documents_do_the_needful_new.py` can process SQS messages and create documents via ORM
FR36: `web_documents_do_the_needful_new.py` can generate and store embeddings via ORM relationship
FR37: `web_documents_do_the_needful_new.py` can update document state through the processing lifecycle
FR38: YouTube processing pipeline can store transcript text and metadata via ORM
FR39: `/website_list` endpoint can return filtered, paginated document lists via repository
FR40: `/website_get` endpoint can return a single document with neighbor navigation via repository
FR41: `/website_save` endpoint can create or update documents via ORM model
FR42: `/website_delete` endpoint can remove documents with cascade embedding deletion via ORM
FR43: `/website_similar` endpoint can perform vector similarity search via `pgvector-python`

### NonFunctional Requirements

NFR1: Zero raw `cursor.execute()` calls in production code — all database operations via SQLAlchemy ORM or `pgvector-python` operators
NFR2: Code passes `ruff check backend/` with zero warnings (line-length=120)
NFR3: All existing unit tests pass without modification (tests that don't touch DB layer)
NFR4: ORM models use type hints (`Mapped[type]`) for IDE autocompletion and static analysis
NFR5: Enum classes (`StalkerDocumentStatus`, `StalkerDocumentType`, `StalkerDocumentStatusError`) are preserved with identical values — no import changes needed in consumers
NFR6: Database schema after migration is identical to before — Alembic baseline produces no diff against existing DDL scripts
NFR7: Adding a new column requires changes in exactly one file (`backend/library/db/models.py`)
NFR8: Adding a new table requires changes in exactly one file plus one Alembic migration command
NFR9: No dead code from old architecture remains (`stalker_web_document_db.py` wrapper fully removed)
NFR10: New dependencies (`sqlalchemy`, `pgvector`, `alembic`) added to `pyproject.toml` with version pins
NFR11: `uv lock` produces a valid lock file after dependency changes
NFR12: `.venv_wsl` synchronized after dependency changes

### Additional Requirements

From Architecture (Sprint 6):

- Wrapper elimination via re-export only — `stalker_web_document.py` re-exports `WebDocument as StalkerWebDocument`, `stalker_web_document_db.py` re-exports `WebDocument as StalkerWebDocumentDB`
- Session injection — session passed as constructor parameter to repository (`WebsitesDBPostgreSQL(session)`)
- Hybrid query location — simple lookups (`get_by_id`, `get_by_url`) as classmethods on model, complex queries in repository
- `dict()` backward compatibility — exact match required: dates as `"YYYY-MM-DD HH:MM:SS"` strings, enums as `.name`, navigation as transient attributes
- pgvector-python native operators as primary — `cosine_distance()` for similarity, `text()` fallback for edge cases only
- Navigation fields — repository method `load_neighbors(doc)` populates transient attributes (`next_id`, `next_type`, `previous_id`, `previous_type`)
- Enum preservation — enums stay in `library/models/` unchanged, ORM model imports from original locations
- Transaction boundaries — repository methods NEVER commit or rollback, caller controls transactions
- pgvector HNSW partial indexes — managed by Alembic migrations only, not defined in ORM model
- Implementation sequence — 9 phases: dependencies -> models -> repository -> re-exports -> Flask -> consumers -> Alembic -> cleanup -> verification
- No starter template — work within existing Flask backend structure
- 28 columns in `web_documents` (including `transcript_needed`) must all be mapped in ORM model
- `langauge` typo already fixed (migration 08) — ORM model uses correct `language` spelling
- Enum storage as varchar — string-backed enum mapping in ORM model (not PostgreSQL enum types)
- Singleton connection anti-pattern eliminated — replaced by SQLAlchemy session factory with proper scoping

From PRD Validation Report:

- No additional requirements — validation confirmed PRD as 5/5 Excellent with 0 critical issues
- Post-validation fixes already applied to PRD (FR12 specificity, Out of Scope section, Assumptions & Dependencies section, dimensionless Vector())

### FR Coverage Map

| FR | Epic | Description |
|----|------|-------------|
| FR1 | Epic 276 | Define table structure as ORM model class |
| FR2 | Epic 276 | Define column types, constraints, defaults |
| FR3 | Epic 276 | Define relationships between models |
| FR4 | Epic 276 | Define STI hierarchy on web_documents |
| FR5 | Epic 276 | Add domain methods on ORM model |
| FR6 | Epic 276 | Auto-generate migration scripts via Alembic |
| FR7 | Epic 276 | Apply migrations with single command |
| FR8 | Epic 276 | Roll back migrations |
| FR9 | Epic 276 | Initialize Alembic on existing database |
| FR10 | Epic 276 | Thread-local sessions for Flask |
| FR11 | Epic 276 | Auto cleanup sessions on teardown |
| FR12 | Epic 276 | Script-scoped sessions for imports/batch |
| FR13 | Epic 276 | Stale connection recovery (pool_pre_ping) |
| FR14 | Epic 27 | Create document via ORM |
| FR15 | Epic 27 | Update document via ORM attributes |
| FR16 | Epic 27 | Delete document with cascade |
| FR17 | Epic 27 | Look up document by URL |
| FR18 | Epic 27 | Look up document by ID |
| FR19 | Epic 27 | Serialize document to dict for API |
| FR20 | Epic 28 | Add embedding via ORM relationship |
| FR21 | Epic 28 | Delete embeddings by model name |
| FR22 | Epic 28 | Find documents needing embeddings |
| FR23 | Epic 28 | Similarity search via cosine_distance() |
| FR24 | Epic 27 | List documents with dynamic filters |
| FR25 | Epic 27 | Count documents by type/state |
| FR26 | Epic 27 | Find documents ready for download |
| FR27 | Epic 27 | Find YouTube documents just added |
| FR28 | Epic 27 | Find documents with completed transcriptions |
| FR29 | Epic 27 | Find next document to correct |
| FR30 | Epic 27 | Retrieve last imported date for source |
| FR31 | Epic 29 | dynamodb_sync.py creates documents via ORM |
| FR32 | Epic 29 | dynamodb_sync.py sets created_at via ORM |
| FR33 | Epic 29 | unknown_news_import.py creates documents via ORM |
| FR34 | Epic 29 | unknown_news_import.py detects duplicates via ORM |
| FR35 | Epic 29 | Batch pipeline processes SQS messages via ORM |
| FR36 | Epic 29 | Batch pipeline stores embeddings via ORM |
| FR37 | Epic 29 | Batch pipeline updates document state via ORM |
| FR38 | Epic 29 | YouTube pipeline stores transcript via ORM |
| FR39 | Epic 27 | /website_list returns filtered lists via repository |
| FR40 | Epic 27 | /website_get returns document with navigation |
| FR41 | Epic 27 | /website_save creates/updates via ORM |
| FR42 | Epic 27 | /website_delete removes with cascade |
| FR43 | Epic 28 | /website_similar performs vector search |

**Coverage: 43/43 FRs — 100%**

## Epic List

### Epic 276: ORM Foundation & Schema Management
Developer can define database schema as SQLAlchemy 2.x ORM models, manage database sessions for Flask and scripts, and use Alembic for schema migrations — eliminating the fear of schema changes.
**FRs covered:** FR1, FR2, FR3, FR4, FR5, FR6, FR7, FR8, FR9, FR10, FR11, FR12, FR13
**NFRs covered:** NFR4, NFR5, NFR6, NFR7, NFR8, NFR10, NFR11, NFR12

### Epic 27: Document CRUD & API Serving
Developer can create, update, delete, and query documents through the ORM repository, and all Flask API endpoints (`/website_list`, `/website_get`, `/website_save`, `/website_delete`) return identical data formats as before. Old wrapper classes replaced with re-exports.
**FRs covered:** FR14, FR15, FR16, FR17, FR18, FR19, FR24, FR25, FR26, FR27, FR28, FR29, FR30, FR39, FR40, FR41, FR42
**NFRs covered:** NFR1 (partial), NFR5
**Builds on:** Epic 276

### Epic 28: Vector Embeddings & Similarity Search
Developer can manage vector embeddings via ORM relationship and perform similarity search using pgvector-python native `cosine_distance()` operator — zero raw SQL for vector operations.
**FRs covered:** FR20, FR21, FR22, FR23, FR43
**NFRs covered:** NFR1 (partial)
**Builds on:** Epic 276, Epic 27

### Epic 29: Data Pipeline Migration & Cleanup
Import scripts and batch pipeline work with ORM models and sessions. YouTube pipeline stores transcripts via ORM. Old wrapper code fully removed, all quality gates pass.
**FRs covered:** FR31, FR32, FR33, FR34, FR35, FR36, FR37, FR38
**NFRs covered:** NFR1 (complete), NFR2, NFR3, NFR9
**Builds on:** Epic 276, Epic 27, Epic 28

---

## Epic 276: ORM Foundation & Schema Management

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

---

## Epic 27: Document CRUD & API Serving

Developer can create, update, delete, and query documents through the ORM repository, and all Flask API endpoints (`/website_list`, `/website_get`, `/website_save`, `/website_delete`) return identical data formats as before. Old wrapper classes replaced with re-exports.

### Story 27.1: Document Persistence — CRUD via ORM

As a **developer**,
I want to create, read, update, and delete documents via ORM session operations and classmethods,
So that I no longer need manual SQL for basic document operations.

**Acceptance Criteria:**

**Given** a session and document data
**When** `WebDocument(url="https://...")` is created and `session.add(doc)` + `session.commit()` is called
**Then** the document is persisted in `web_documents` table

**Given** an existing document in the database
**When** `doc.title = "New title"` is set and `session.commit()` is called
**Then** SQLAlchemy dirty tracking generates UPDATE for the changed column only

**Given** a document with related embeddings
**When** `session.delete(doc)` + `session.commit()` is called
**Then** the document AND all related embeddings are deleted (cascade)

**Given** a URL string
**When** `WebDocument.get_by_url(session, url)` is called
**Then** returns the matching document or `None` (for duplicate detection)

**Given** a document ID
**When** `WebDocument.get_by_id(session, id)` is called
**Then** returns the matching document or `None`

**Given** a `WebDocument` instance
**When** `doc.dict()` is called
**Then** output matches exact format: dates as `"YYYY-MM-DD HH:MM:SS"`, enums as `.name`, all existing keys preserved including transient navigation fields when populated

**Covers:** FR14, FR15, FR16, FR17, FR18, FR19 | NFR5

### Story 27.2: Repository Queries — List, Count, State-Based Lookups

As a **developer**,
I want all repository query methods rewritten with SQLAlchemy `select()` queries,
So that document listing, counting, and state-based lookups work without raw SQL.

**Acceptance Criteria:**

**Given** `WebsitesDBPostgreSQL` receives session via constructor (`WebsitesDBPostgreSQL(session)`)
**When** any query method is called
**Then** it uses `session.execute(select(...))` — no raw `cursor.execute()`

**Given** repository method `get_list(document_type='link', limit=20)`
**When** called
**Then** returns list of subset dicts (id, url, title, document_type, created_at, document_state, document_state_error, note, project, s3_uuid) with dynamic filters applied

**Given** repository method `get_count(document_type='link')`
**When** called
**Then** returns integer count using `func.count()`

**Given** repository method `get_count_by_type()`
**When** called
**Then** returns dict with counts per document type

**Given** repository method `get_ready_for_download()`
**When** called
**Then** returns documents in URL_ADDED state with webpage/link type

**Given** repository method `get_youtube_just_added()`
**When** called
**Then** returns YouTube documents in URL_ADDED state

**Given** repository method `get_transcription_done()`
**When** called
**Then** returns documents with completed transcriptions

**Given** repository method `get_next_to_correct(id, document_type)`
**When** called
**Then** returns the next document for navigation

**Given** repository method `get_last_unknown_news()`
**When** called
**Then** returns the last imported date for unknow.news source

**Given** repository method `load_neighbors(doc)`
**When** called
**Then** populates `doc.next_id`, `doc.next_type`, `doc.previous_id`, `doc.previous_type` transient attributes

**Given** any repository method
**When** inspected
**Then** it NEVER calls `session.commit()` or `session.rollback()` — caller controls transactions

**Covers:** FR24, FR25, FR26, FR27, FR28, FR29, FR30

### Story 27.3: Flask API Endpoints — CRUD Routes via Repository

As a **developer**,
I want Flask route handlers updated to use the ORM repository with scoped session,
So that the React frontend receives identical API responses after the migration.

**Acceptance Criteria:**

**Given** Flask app with scoped session
**When** `GET /website_list?document_type=link&limit=20` is called
**Then** route creates `WebsitesDBPostgreSQL(scoped_session())`, calls `get_list()`, returns JSON response identical to pre-migration format

**Given** a document with ID exists
**When** `GET /website_get?id=42` is called
**Then** route returns full document dict with navigation fields (`next_id`, `next_type`, `previous_id`, `previous_type`) populated via `load_neighbors()`

**Given** valid document data in request body
**When** `POST /website_save` is called
**Then** route creates or updates document via ORM model and `session.commit()`, returns success response

**Given** a document ID
**When** `DELETE /website_delete?id=42` is called
**Then** route deletes document via `session.delete()` with cascade (embeddings removed), returns success response

**Given** any Flask endpoint completes (success or error)
**When** request teardown occurs
**Then** `scoped_session.remove()` is called via `@app.teardown_appcontext`

**Given** frontend makes API calls before and after migration
**When** response JSON is compared
**Then** field names, value types, and date formats are identical

**Covers:** FR39, FR40, FR41, FR42 | NFR1 (partial)

---

## Epic 28: Vector Embeddings & Similarity Search

Developer can manage vector embeddings via ORM relationship and perform similarity search using pgvector-python native `cosine_distance()` operator — zero raw SQL for vector operations.

### Story 28.1: Embedding CRUD & Documents Needing Embeddings

As a **developer**,
I want to add, delete, and query embeddings via ORM relationship and repository,
So that embedding management no longer requires hand-written INSERT/DELETE SQL.

**Acceptance Criteria:**

**Given** a `WebDocument` instance and an embedding vector
**When** a `WebsiteEmbedding` is created and added via ORM relationship (`doc.embeddings.append(embedding)`) and `session.commit()` is called
**Then** the embedding is persisted in `websites_embeddings` table with correct `web_document_id` FK

**Given** a document with embeddings for multiple models
**When** embeddings are deleted filtered by model name via repository
**Then** only embeddings for the specified model are removed, others remain

**Given** documents exist with and without embeddings
**When** repository method `get_documents_needing_embedding(model)` is called
**Then** returns documents that have no embedding for the specified model (outer join on `websites_embeddings`)

**Given** the query uses SQLAlchemy
**When** `get_documents_needing_embedding()` is inspected
**Then** it uses `select()` with `outerjoin()` — no raw `cursor.execute()`

**Covers:** FR20, FR21, FR22

### Story 28.2: Similarity Search via pgvector-python & API Endpoint

As a **developer**,
I want similarity search implemented with pgvector-python native `cosine_distance()` operator and the `/website_similar` endpoint functional,
So that vector search works through ORM with zero raw SQL.

**Acceptance Criteria:**

**Given** a query vector and a limit
**When** repository method `get_similar(vector, limit, model)` is called
**Then** it uses `WebsiteEmbedding.embedding.cosine_distance(query_vector)` for ordering

**Given** similarity search results
**When** similarity score is computed
**Then** it is calculated as `1 - cosine_distance` using a SQLAlchemy SQL expression (`func.cast`), not Python-side computation

**Given** `get_similar()` returns results
**When** result format is inspected
**Then** each result is a dict with: `website_id`, `text`, `similarity` (float), `id`, `url`, `language`, `text_original`, `websites_text_length`, `embeddings_text_length`, `title`, `document_type`, `project`

**Given** a query vector
**When** `GET /website_similar` endpoint is called with vector and model parameters
**Then** Flask route creates repository, calls `get_similar()`, returns JSON response

**Given** no similar documents exist above threshold
**When** similarity search is performed
**Then** returns empty list (no error)

**Given** pgvector HNSW partial indexes exist in the database
**When** ORM model is inspected
**Then** indexes are NOT defined in the model — they are managed by Alembic migrations only

**Covers:** FR23, FR43 | NFR1 (partial)

---

## Epic 29: Data Pipeline Migration & Cleanup

Import scripts and batch pipeline work with ORM models and sessions. YouTube pipeline stores transcripts via ORM. Old wrapper code fully removed, all quality gates pass.

### Story 29.1: Import Scripts Migration (dynamodb_sync & unknown_news_import)

As a **developer**,
I want import scripts to use ORM models and sessions instead of the old wrapper,
So that data imports work through the same ORM layer as the rest of the application.

**Acceptance Criteria:**

**Given** `dynamodb_sync.py` is updated
**When** it processes a DynamoDB item
**Then** it creates `WebDocument(url=item['url'])` via ORM, sets attributes, and `session.commit()`

**Given** `dynamodb_sync.py` needs to set `created_at` and `chapter_list`
**When** these fields are updated
**Then** they are set via normal ORM attribute assignment (`doc.created_at = value`) — no direct SQL UPDATE

**Given** `unknown_news_import.py` is updated
**When** it processes a JSON feed entry
**Then** it creates `WebDocument` via ORM with fields: `title`, `summary`, `language`, `source`, `date_from`, `document_type`, `document_state`

**Given** `unknown_news_import.py` processes a URL that already exists
**When** `WebDocument.get_by_url(session, url)` returns a match
**Then** the duplicate is skipped (not inserted)

**Given** either import script
**When** session lifecycle is inspected
**Then** it follows the pattern: `session = get_session()` -> `try` -> `session.commit()` -> `finally` -> `session.close()`

**Given** import scripts use no raw SQL
**When** code is inspected
**Then** zero `cursor.execute()` calls remain in import scripts

**Covers:** FR31, FR32, FR33, FR34

### Story 29.2: Batch Pipeline & YouTube Processing Migration

As a **developer**,
I want `web_documents_do_the_needful_new.py` and YouTube processing to use ORM models,
So that the batch pipeline and transcript storage work through the same ORM layer.

**Acceptance Criteria:**

**Given** `web_documents_do_the_needful_new.py` is updated
**When** it processes an SQS message
**Then** it creates/retrieves `WebDocument` via ORM and `session.commit()`

**Given** batch pipeline needs to generate embeddings
**When** embeddings are created
**Then** they are stored via ORM relationship (`WebsiteEmbedding` added to document's embeddings collection)

**Given** batch pipeline processes a document through its lifecycle
**When** document state changes (e.g., `URL_ADDED` -> `DOCUMENT_INTO_DATABASE` -> `EMBEDDING_EXIST`)
**Then** state is updated via ORM attribute assignment (`doc.document_state = StalkerDocumentStatus.EMBEDDING_EXIST`) and `session.commit()`

**Given** YouTube processing pipeline receives transcript
**When** transcript text and metadata are stored
**Then** they are set via ORM attributes on `WebDocument` (not direct SQL)

**Given** batch pipeline session lifecycle
**When** inspected
**Then** uses script-scoped `get_session()` with commit per document

**Given** batch pipeline uses no raw SQL
**When** code is inspected
**Then** zero `cursor.execute()` calls remain

**Covers:** FR35, FR36, FR37, FR38

### Story 29.3: Old Code Removal & Final Verification

As a **developer**,
I want all old wrapper code removed and all quality gates verified,
So that the migration is complete with zero legacy code and a clean codebase.

**Acceptance Criteria:**

**Given** all consumers are migrated to ORM
**When** `stalker_web_document.py` is inspected
**Then** it contains only: `from library.db.models import WebDocument as StalkerWebDocument` (re-export)

**Given** all consumers are migrated
**When** `stalker_web_document_db.py` is inspected
**Then** it contains only: `from library.db.models import WebDocument as StalkerWebDocumentDB` (re-export)

**Given** old wrapper code
**When** codebase is searched for `cursor.execute()`
**Then** zero occurrences found in production code (NFR1 complete)

**Given** updated codebase
**When** `ruff check backend/` is run
**Then** zero warnings reported (line-length=120)

**Given** existing unit tests
**When** `cd backend && PYTHONPATH=. uvx pytest tests/unit/ -v` is run
**Then** all tests pass without modification

**Given** the complete migration
**When** codebase is searched for dead code from old architecture
**Then** no remnants of `StalkerWebDocumentDB` class definition, `db_conn` singleton, or `__clean_values()` method remain

**Covers:** NFR1 (complete), NFR2, NFR3, NFR9
