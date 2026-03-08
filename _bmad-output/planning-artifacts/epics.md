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
| FR1 | Epic 26 | Define table structure as ORM model class |
| FR2 | Epic 26 | Define column types, constraints, defaults |
| FR3 | Epic 26 | Define relationships between models |
| FR4 | Epic 26 | Define STI hierarchy on web_documents |
| FR5 | Epic 26 | Add domain methods on ORM model |
| FR6 | Epic 26 | Auto-generate migration scripts via Alembic |
| FR7 | Epic 26 | Apply migrations with single command |
| FR8 | Epic 26 | Roll back migrations |
| FR9 | Epic 26 | Initialize Alembic on existing database |
| FR10 | Epic 26 | Thread-local sessions for Flask |
| FR11 | Epic 26 | Auto cleanup sessions on teardown |
| FR12 | Epic 26 | Script-scoped sessions for imports/batch |
| FR13 | Epic 26 | Stale connection recovery (pool_pre_ping) |
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

### Epic 26: ORM Foundation & Schema Management
Developer can define database schema as SQLAlchemy 2.x ORM models, manage database sessions for Flask and scripts, and use Alembic for schema migrations — eliminating the fear of schema changes.
**FRs covered:** FR1, FR2, FR3, FR4, FR5, FR6, FR7, FR8, FR9, FR10, FR11, FR12, FR13
**NFRs covered:** NFR4, NFR5, NFR6, NFR7, NFR8, NFR10, NFR11, NFR12
**Details:** [epic-26.md](epics/epic-26.md)

### Epic 27: Document CRUD & API Serving
Developer can create, update, delete, and query documents through the ORM repository, and all Flask API endpoints (`/website_list`, `/website_get`, `/website_save`, `/website_delete`) return identical data formats as before. Old wrapper classes replaced with re-exports.
**FRs covered:** FR14, FR15, FR16, FR17, FR18, FR19, FR24, FR25, FR26, FR27, FR28, FR29, FR30, FR39, FR40, FR41, FR42
**NFRs covered:** NFR1 (partial), NFR5
**Builds on:** Epic 26
**Details:** [epic-27.md](epics/epic-27.md)

### Epic 28: Vector Embeddings & Similarity Search
Developer can manage vector embeddings via ORM relationship and perform similarity search using pgvector-python native `cosine_distance()` operator — zero raw SQL for vector operations.
**FRs covered:** FR20, FR21, FR22, FR23, FR43
**NFRs covered:** NFR1 (partial)
**Builds on:** Epic 26, Epic 27
**Details:** [epic-28.md](epics/epic-28.md)

### Epic 29: Data Pipeline Migration & Cleanup
Import scripts and batch pipeline work with ORM models and sessions. YouTube pipeline stores transcripts via ORM. Old wrapper code fully removed, all quality gates pass.
**FRs covered:** FR31, FR32, FR33, FR34, FR35, FR36, FR37, FR38
**NFRs covered:** NFR1 (complete), NFR2, NFR3, NFR9
**Builds on:** Epic 26, Epic 27, Epic 28
**Details:** [epic-29.md](epics/epic-29.md)
