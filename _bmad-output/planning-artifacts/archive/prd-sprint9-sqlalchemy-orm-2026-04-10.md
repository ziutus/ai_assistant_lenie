---
stepsCompleted:
  - step-01-init
  - step-02-discovery
  - step-02b-vision
  - step-02c-executive-summary
  - step-03-success
  - step-04-journeys
  - step-05-domain
  - step-06-innovation
  - step-07-project-type
  - step-08-scoping
  - step-09-functional
  - step-10-nonfunctional
  - step-11-polish
  - step-12-complete
inputDocuments:
  - .claude/exports/plan-sqlalchemy-migration.md
  - docs/architecture-backend.md
  - docs/data-models-backend.md
  - docs/architecture-decisions.md
documentCounts:
  briefs: 0
  research: 1
  brainstorming: 0
  projectDocs: 3
classification:
  projectType: api_backend
  domain: personal_ai_knowledge_management
  complexity: low
  projectContext: brownfield
  deploymentScope: backend_refactor
workflowType: 'prd'
lastEdited: '2026-03-07'
---

# Product Requirements Document - lenie-server-2025

**Author:** Ziutus
**Date:** 2026-03-07

## Executive Summary

The backend data access layer of Project Lenie currently uses raw `psycopg2` queries with manual SQL construction. Adding or removing a column requires synchronized changes in 5+ locations: SELECT column lists, INSERT statements, UPDATE clauses, `dict()` serialization, `__clean_values()`, and the domain model constructor. Column positions are counted by hand — a single miscount silently corrupts data mapping. This fragility blocks the evolution of the data model: new tables (data sources, authors with biographies) and schema changes (splitting `web_documents` by document type) carry disproportionate risk and mental overhead.

This PRD defines the migration from raw psycopg2 to SQLAlchemy 2.x ORM with Alembic schema migrations. Columns are defined once in a declarative ORM model — SQLAlchemy generates all SQL automatically. Alembic auto-generates migration scripts from model diffs, replacing unversioned DDL scripts. The existing three-class architecture (StalkerWebDocument base model + StalkerWebDocumentDB persistence wrapper + WebsitesDBPostgreSQL query layer) is simplified to two layers: ORM model (data definition + domain methods) and repository (complex queries). The intermediate `StalkerWebDocumentDB` wrapper — originally designed to abstract over potential future database backends (ElasticSearch) — is eliminated, as PostgreSQL is the only planned backend.

ORM model inheritance (Single Table Inheritance) prepares for future table splitting by document type without requiring architectural changes — the split becomes an Alembic migration, not a rewrite. Pydantic v2 schemas for API serialization and structured AI outputs are explicitly out of scope and deferred to a future sprint.

### What Makes This Special

This is not a technology upgrade for its own sake. The migration eliminates the fear of changing the database schema. Today, every schema change triggers anxiety: "did I count the columns correctly in SELECT?" After the migration, adding a table, column, or relationship is a single-location change in the ORM model — Alembic handles the rest. This unblocks rapid experimentation with the data model at a stage where the project is actively discovering what reality it needs to represent (data sources, authors, document type hierarchies). The code has never run in production, making this the lowest-risk moment for an aggressive rewrite.

## Project Classification

| Dimension | Value |
|-----------|-------|
| **Project Type** | API backend (database access layer migration) |
| **Domain** | Personal AI knowledge management |
| **Complexity** | Low (single user, no regulatory requirements, early-stage codebase) |
| **Project Context** | Brownfield — rewriting existing data layer in Flask backend |
| **Deployment Scope** | Backend refactor (Docker + NAS primary, AWS secondary) |

## Success Criteria

### User Success

- Adding a new table or column is a single-location change in the ORM model — no manual SQL synchronization across SELECT/INSERT/UPDATE/dict/clean
- Alembic generates the migration script automatically from model diff — no hand-written DDL
- The developer (Ziutus) can modify the schema without anxiety about miscounted column positions or broken queries

### Business Success

- Developer time is the primary constraint. The migration must reduce time spent on schema changes from "careful manual work across 5+ files" to "one field in a model, one Alembic command"
- Unblocks future work: new tables (data sources, authors), TypeScript type synchronization (Pydantic → OpenAPI → TypeScript), and UI-driven data entry (e.g., selecting a source from a dynamic list)

### Technical Success

- Import scripts function correctly after migration:
  - `backend/imports/dynamodb_sync.py` — loads documents from DynamoDB + S3 into PostgreSQL
  - `backend/imports/unknown_news_import.py` — imports curated links from unknow.news
- Batch processing pipeline works end-to-end:
  - `backend/web_documents_do_the_needful_new.py` — correctly creates embeddings for link documents (currently the only fully supported type)
  - YouTube video text is correctly fetched and stored in the database
- Flask API endpoints (`/website_list`, `/website_get`, `/website_save`, `/website_delete`, `/website_similar`) return identical data formats as before the migration
- All existing unit tests pass
- `ruff check backend/` reports zero warnings
- Old classes (`StalkerWebDocument`, `StalkerWebDocumentDB`, `StalkerWebDocumentDB` wrapper layer) are removed — no dead code left behind

### Measurable Outcomes

- Lines of code to add a new column: 1 (ORM model field) + 1 (Alembic autogenerate) vs. current 5+ manual edits
- Import scripts run end-to-end with exit code 0 on test data
- Zero raw `cursor.execute()` calls remaining in production code — all vector operations use `pgvector-python` native operators

## User Journeys

### Journey 1: "New Column Without Fear" — Developer Modifying the Schema

**Persona:** Ziutus — sole developer of Project Lenie, working evenings and weekends on a personal AI knowledge management system.

**Opening Scene:** Ziutus decides that documents need an `author` field linked to a new `authors` table with biographies. In the old world, this meant: add column to SQL init script, update SELECT column list (count positions carefully), update INSERT, update UPDATE, update `dict()`, update `__clean_values()`, update the domain model constructor, and pray nothing was miscounted.

**Rising Action:** Ziutus opens `backend/library/db/models.py` and adds a single field: `author_id: Mapped[int | None] = mapped_column(ForeignKey("authors.id"))`. He creates a new `Author` model class with `name`, `bio`, `url` fields. He runs `alembic revision --autogenerate -m "add authors table"` — Alembic inspects the model diff and generates the migration script with `CREATE TABLE authors` and `ALTER TABLE web_documents ADD COLUMN author_id`.

**Climax:** `alembic upgrade head` — the database schema matches the model. No manual column counting. No cross-referencing 5 files. The ORM handles SELECT, INSERT, UPDATE automatically. Ziutus writes zero SQL.

**Resolution:** The entire operation took minutes instead of an anxious hour. Ziutus moves on to building the UI for selecting authors from a list — the part he actually cares about — instead of wrestling with SQL plumbing.

### Journey 2: "The Import Run" — Operator Running Data Import Scripts

**Persona:** Ziutus — running the weekly unknow.news import to pull curated Polish tech links into the knowledge base.

**Opening Scene:** Ziutus runs `cd backend && ./imports/unknown_news_import.py --since 2026-03-01`. The script starts, connects to PostgreSQL, downloads the unknow.news archive JSON, and begins processing entries.

**Rising Action:** For each new URL, the script creates an ORM model instance via `WebDocument(url=entry['url'])`. The session queries the database to check for duplicates. New documents are populated with fields (`title`, `summary`, `language`, `source`, `date_from`, `document_type`, `document_state`) and added to the session. `session.commit()` persists them — SQLAlchemy generates the INSERT with exactly the right columns.

**Climax:** The script processes 47 new entries. Summary: "Added: 47, Exist: 112, Ignored: 1,834." Exit code 0. The output format is identical to before the migration — Ziutus notices no difference in behavior.

**Resolution:** The import works exactly as before but the underlying code is simpler. If Ziutus later adds an `author` column to `web_documents`, the import script doesn't need any changes — the new column defaults to NULL and the ORM handles the rest.

### Journey 3: "Embeddings Pipeline" — Batch Processing End-to-End

**Persona:** `web_documents_do_the_needful_new.py` — the batch pipeline script, orchestrated by Ziutus.

**Opening Scene:** Ziutus runs the pipeline with `--only-links`. The script needs to: find link documents in `READY_FOR_EMBEDDING` state, generate embeddings via the configured model, and store vectors in `websites_embeddings`.

**Rising Action:** The repository method `get_documents_needing_embedding(model)` executes a SQLAlchemy query with an outer join on `websites_embeddings` — replacing a hand-written SQL string with a composable query object. For each document, the script loads the ORM model by ID, calls `embedding_add(model)`, which creates a `WebsiteEmbedding` instance and adds it to the document's `embeddings` relationship. `session.commit()` persists both the embedding and the document state update in a single transaction.

**Climax:** 23 link documents processed, embeddings generated and stored. The pgvector similarity search uses `pgvector-python`'s native `cosine_distance()` operator — zero raw SQL anywhere in the codebase.

**Resolution:** The pipeline produces identical results. The embedding storage code is shorter and safer — no manual `cursor.execute()` with hand-built INSERT statements. The `websites_embeddings` table is managed through the ORM relationship, so cascade deletes work automatically.

### Journey 4: "API Request" — Flask Endpoint Serving the Frontend

**Persona:** React frontend making a `GET /website_list?document_type=link&limit=20` request.

**Opening Scene:** A user opens the Lenie React UI and navigates to the document list filtered by "links." The frontend sends an authenticated request to the Flask backend.

**Rising Action:** The Flask route handler calls the repository method `get_list(document_type='link', limit=20)`. The repository builds a SQLAlchemy `select()` query with dynamic filters — `where(WebDocument.document_type == 'link')`, `.limit(20)`, `.order_by(WebDocument.created_at.desc())`. The session executes the query and returns ORM model instances.

**Climax:** Each `WebDocument` instance is serialized via its `dict()` method. The API response format is functionally equivalent to the old output — the frontend may need minor adjustments if field naming evolves, but the data is correct and complete.

**Resolution:** The frontend displays the list. The API contract is preserved at the data level while the implementation underneath is completely rewritten. Any future format improvements (cleaner field names, nested objects) can be made incrementally.

### Journey Requirements Summary

| Journey | Capabilities Required |
|---------|----------------------|
| Schema Modification | ORM model definition, Alembic autogenerate, migration execution |
| Data Import | ORM instance creation, session-based persistence, duplicate detection by URL, backward-compatible field mapping |
| Embeddings Pipeline | Repository queries with joins, ORM relationship management (document → embeddings), `pgvector-python` `cosine_distance()`, transaction management |
| API Request | Repository with dynamic filters, ORM-to-dict serialization, response format backward compatibility |

## Technical Context

### Architectural Position

Database access layer migration within the existing Flask backend. Replaces raw `psycopg2` queries with SQLAlchemy 2.x ORM. All consumers (Flask API, import scripts, batch pipeline) use the same ORM models and session management.

### Target Architecture

```
Flask Route / Script
  |
  v
Repository (stalker_web_documents_db_postgresql.py)
  |  - complex queries: get_list(), get_similar(), get_count()
  |  - uses SQLAlchemy select(), func.count(), joins
  |
  v
ORM Models (library/db/models.py)
  |  - WebDocument (STI base) -> LinkDocument, YouTubeDocument, etc.
  |  - WebsiteEmbedding (Vector(), cosine_distance())
  |  - domain methods: set_document_type(), validate(), analyze(), dict()
  |
  v
SQLAlchemy Engine (library/db/engine.py)
  |  - get_engine() with pool_pre_ping=True
  |  - get_session() for scripts
  |  - get_scoped_session() for Flask (thread-local)
  |
  v
PostgreSQL 18 + pgvector
```

### Session Management

| Context | Strategy |
|---------|----------|
| Flask API | `get_scoped_session()` — thread-local, `@app.teardown_appcontext` calls `session.remove()` |
| Import scripts | `get_session()` — script-scoped, explicit `session.close()` at exit |
| Batch pipeline | `get_session()` — script-scoped, commit per document |

### Key Technology Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| ORM style | SQLAlchemy 2.x `mapped_column()` declarative | Modern, type-hint native, best IDE support |
| Vector operations | `pgvector-python` native integration | `cosine_distance()` operator, dimensionless `Vector()` type — zero raw SQL |
| Inheritance | Single Table Inheritance on `web_documents` | Matches current schema (one table), prepares for future Joined Table split |
| Migration tool | Alembic with autogenerate | Reads ORM model diffs, generates migration scripts |
| DB wrapper | Eliminated | `StalkerWebDocumentDB` wrapper removed — ORM model + repository directly |
| Pydantic | Deferred (out of scope) | Not needed until API serialization or structured AI outputs become priority |

### Data Flow — Import Script

```
DynamoDB/JSON feed
  -> Script creates WebDocument(url=...)
  -> session.add(doc) + session.commit()
  -> SQLAlchemy generates INSERT with correct columns
  -> New columns auto-default to NULL (no script changes needed)
```

### Data Flow — Similarity Search

```
Query vector (dimensions vary by model)
  -> Repository: select(WebsiteEmbedding)
       .order_by(WebsiteEmbedding.embedding.cosine_distance(query_vector))
       .limit(limit)
  -> pgvector IVFFlat index (cosine similarity)
  -> ORM instances returned
```

### Dependencies (new)

| Package | Version | Purpose |
|---------|---------|---------|
| `sqlalchemy` | >=2.0,<3.0 | ORM, query builder, session management |
| `pgvector` | >=0.3.0 | Vector type, cosine_distance operator |
| `alembic` | >=1.13 | Schema migration management |

Existing `psycopg2-binary` retained as SQLAlchemy driver.

### Files — Summary

**New:**
- `backend/library/db/__init__.py`
- `backend/library/db/engine.py` — engine, session factories, Base
- `backend/library/db/models.py` — WebDocument (STI), WebsiteEmbedding
- `backend/alembic.ini`
- `backend/alembic/env.py`
- `backend/alembic/versions/` — migration scripts

**Rewritten:**
- `backend/library/stalker_web_documents_db_postgresql.py` — SQLAlchemy session queries
- `backend/imports/dynamodb_sync.py` — ORM model instead of wrapper
- `backend/imports/unknown_news_import.py` — ORM model instead of wrapper
- `backend/web_documents_do_the_needful_new.py` — ORM model instead of wrapper
- `backend/server.py` — add `teardown_appcontext`, update route handlers

**Removed:**
- `backend/library/stalker_web_document_db.py` — wrapper eliminated
- `backend/library/stalker_web_document.py` — replaced by ORM model (re-export enums only)

### Implementation Considerations

- `StalkerDocumentStatus`, `StalkerDocumentType`, `StalkerDocumentStatusError` enums are preserved as-is — they are used across the codebase and stored as strings in the database
- The `langauge` typo in `websites_embeddings` has been fixed in migration `08-fix-language-typo.sql` — ORM model uses correct `language` spelling
- `dynamodb_sync.py` has a direct SQL UPDATE for `created_at` and `chapter_list` (line 210) — this becomes a normal ORM attribute assignment + commit
- pgvector HNSW/IVFFlat partial indexes: managed by Alembic migrations, not defined in ORM model

## Project Scoping & Risk Mitigation

### MVP Strategy

**Approach:** Big-bang rewrite of the data access layer. All consumers (Flask API, import scripts, batch pipeline) migrate to SQLAlchemy ORM simultaneously. The codebase has never run in production, so there is no live system to break — this is the safest moment for an aggressive rewrite.

**Resource Requirements:** Solo developer (Ziutus), Claude Code as implementation partner.

### MVP Feature Set (Phase 1)

**Core Journeys Supported:**
- All four journeys: schema modification, data import, embeddings pipeline, API request

**Must-Have Capabilities:**
1. ORM models (`WebDocument` with STI, `WebsiteEmbedding` with dimensionless `Vector()`)
2. Engine + session management (`get_engine()`, `get_session()`, `get_scoped_session()`)
3. Alembic initialized with baseline migration
4. Repository rewritten with SQLAlchemy queries
5. All import scripts (`dynamodb_sync.py`, `unknown_news_import.py`) working with ORM
6. Batch pipeline (`web_documents_do_the_needful_new.py`) working with ORM
7. Flask endpoints functional
8. Old wrapper classes removed

### Post-MVP Features

**Phase 2 (Growth):**
- Pydantic v2 schemas for API serialization
- TypeScript type synchronization (Pydantic → OpenAPI → `openapi-typescript`)
- New tables: `data_sources`, `authors`
- Pydantic structured outputs for LLM calls

**Phase 3 (Expansion):**
- Joined Table Inheritance (split `web_documents` by document type)
- MCP server for Claude Desktop backed by SQLAlchemy queries
- ElasticSearch as secondary search backend (if needed)

### Out of Scope

The following are explicitly excluded from this sprint and deferred to future work:

- **Pydantic v2 schemas** — API serialization, OpenAPI generation, structured AI outputs (Phase 2)
- **TypeScript type synchronization** — Pydantic → OpenAPI → `openapi-typescript` pipeline (Phase 2)
- **New tables** — `data_sources`, `authors` (Phase 2 — ORM makes these trivial to add later)
- **Joined Table Inheritance split** — splitting `web_documents` by document type into separate tables (Phase 3)
- **MCP server** — Claude Desktop integration backed by SQLAlchemy queries (Phase 3)
- **ElasticSearch** — secondary search backend (Phase 3, if needed)
- **Lambda/AWS compatibility** — SQLAlchemy adds ~30MB to Lambda layers; Lambda deployment deferred
- **Flask-SQLAlchemy extension** — using plain SQLAlchemy with manual session management instead
- **Database schema changes** — this migration preserves the existing schema exactly; new columns/tables are future work

### Risk Mitigation Strategy

**Technical Risk — Big-Bang Migration:**
All consumers switch to SQLAlchemy simultaneously. No gradual migration path. **Mitigation:** The code has never run in production. Verification is done by running import scripts on test data and confirming correct database state. If something breaks, the old code is in git history.

**Technical Risk — pgvector Compatibility:**
`pgvector-python` must produce identical similarity search results to the current raw SQL `<=>` operator. **Mitigation:** Run `get_similar()` with known test vectors before and after migration, compare results.

**Technical Risk — Session Lifecycle:**
SQLAlchemy sessions in Flask must be properly scoped (thread-local) and cleaned up. Leaked sessions cause connection pool exhaustion. **Mitigation:** `@app.teardown_appcontext` with `session.remove()` — standard Flask-SQLAlchemy pattern.

**Technical Risk — Alembic Baseline:**
Existing database schema must match the ORM model exactly for `alembic stamp head` to work. Any drift causes migration failures. **Mitigation:** Compare `alembic revision --autogenerate` output against existing DDL scripts (`backend/database/init/03-create-table.sql`, `04-create-table.sql`). Fix any discrepancies before stamping.

**Dependency Risk — Lambda Package Size:**
SQLAlchemy adds ~30MB to Lambda layers. **Mitigation:** Deferred — Lambda/AWS is secondary. NAS deployment has no package size constraints. Lambda compatibility addressed in a future sprint if needed.

## Assumptions & Dependencies

### Assumptions

- Existing database schema in `backend/database/init/03-create-table.sql` and `04-create-table.sql` matches the live database — ORM model will be built from these DDL scripts
- `pgvector-python` `cosine_distance()` operator produces identical similarity search results to the current raw SQL `<=>` operator
- No production data exists — the codebase has never run in production, making a big-bang rewrite safe
- `psycopg2-binary` works as SQLAlchemy's PostgreSQL driver without additional configuration
- The `langauge` typo in `websites_embeddings` has already been fixed (migration `08-fix-language-typo.sql`) — ORM model uses correct `language` spelling

### Dependencies

- SQLAlchemy >= 2.0 supports `mapped_column()` declarative style and type-hint native `Mapped[]`
- `pgvector` Python package >= 0.3.0 provides SQLAlchemy `Vector()` type and `cosine_distance()` operator
- Alembic >= 1.13 supports autogenerate from SQLAlchemy 2.x models
- PostgreSQL 18 (Docker/NAS and RDS) supports pgvector extension

## Functional Requirements

### ORM Model Definition

- FR1: Developer can define database table structure as a Python ORM model class in a single file
- FR2: Developer can define column types, constraints, defaults, and nullability as model field attributes
- FR3: Developer can define relationships between models (one-to-many, many-to-one) using ORM relationship declarations
- FR4: Developer can define Single Table Inheritance hierarchy on `web_documents` with document type as discriminator
- FR5: Developer can add domain methods (validate, analyze, set_document_type, set_document_state) directly on the ORM model

### Schema Migration

- FR6: Developer can auto-generate migration scripts from ORM model changes via Alembic
- FR7: Developer can apply migrations to the database with a single command (`alembic upgrade head`)
- FR8: Developer can roll back migrations to a previous version (`alembic downgrade`)
- FR9: Developer can initialize Alembic on an existing database by stamping the current state as baseline

### Session & Connection Management

- FR10: Flask application can obtain thread-local database sessions scoped to the request lifecycle
- FR11: Flask application can automatically clean up sessions on request teardown
- FR12: Import scripts and batch pipeline can obtain, commit, and close their own database sessions (script-scoped lifecycle)
- FR13: Engine can detect and recover from stale database connections (`pool_pre_ping`)

### Document Persistence

- FR14: Consumer can create a new document by instantiating an ORM model and committing to session
- FR15: Consumer can update an existing document by modifying ORM model attributes and committing
- FR16: Consumer can delete a document via session, with cascade deletion of related embeddings
- FR17: Consumer can look up a document by URL for duplicate detection
- FR18: Consumer can look up a document by ID
- FR19: Consumer can serialize a document to a dictionary for API responses

### Embedding Operations

- FR20: Consumer can add a vector embedding to a document via ORM relationship
- FR21: Consumer can delete embeddings for a document filtered by model name
- FR22: Repository can find documents needing embeddings (outer join on `websites_embeddings`)
- FR23: Repository can perform similarity search using `pgvector-python` `cosine_distance()` operator

### Repository Queries

- FR24: Repository can list documents with dynamic filters (document_type, document_state, source, project, limit, offset)
- FR25: Repository can count documents by type and/or state
- FR26: Repository can find documents ready for download (URL_ADDED state, webpage/link type)
- FR27: Repository can find YouTube documents just added (URL_ADDED state, youtube type)
- FR28: Repository can find documents with completed transcriptions
- FR29: Repository can find the next document to correct (navigation by ID and type)
- FR30: Repository can retrieve the last imported date for a given source

### Import Script Compatibility

- FR31: `dynamodb_sync.py` can create documents from DynamoDB items using ORM models
- FR32: `dynamodb_sync.py` can set `created_at` and `chapter_list` via normal ORM attribute assignment (no direct SQL)
- FR33: `unknown_news_import.py` can create documents from JSON feed entries using ORM models
- FR34: `unknown_news_import.py` can detect and skip duplicate URLs via ORM query

### Batch Pipeline Compatibility

- FR35: `web_documents_do_the_needful_new.py` can process SQS messages and create documents via ORM
- FR36: `web_documents_do_the_needful_new.py` can generate and store embeddings via ORM relationship
- FR37: `web_documents_do_the_needful_new.py` can update document state through the processing lifecycle
- FR38: YouTube processing pipeline can store transcript text and metadata via ORM

### Flask API Compatibility

- FR39: `/website_list` endpoint can return filtered, paginated document lists via repository
- FR40: `/website_get` endpoint can return a single document with neighbor navigation via repository
- FR41: `/website_save` endpoint can create or update documents via ORM model
- FR42: `/website_delete` endpoint can remove documents with cascade embedding deletion via ORM
- FR43: `/website_similar` endpoint can perform vector similarity search via `pgvector-python`

## Non-Functional Requirements

### Code Quality

- NFR1: Zero raw `cursor.execute()` calls in production code — all database operations via SQLAlchemy ORM or `pgvector-python` operators
- NFR2: Code passes `ruff check backend/` with zero warnings (line-length=120)
- NFR3: All existing unit tests pass without modification (tests that don't touch DB layer)
- NFR4: ORM models use type hints (`Mapped[type]`) for IDE autocompletion and static analysis

### Backward Compatibility

- NFR5: Enum classes (`StalkerDocumentStatus`, `StalkerDocumentType`, `StalkerDocumentStatusError`) are preserved with identical values — no import changes needed in consumers
- NFR6: Database schema after migration is identical to before — Alembic baseline produces no diff against existing DDL scripts

### Maintainability

- NFR7: Adding a new column requires changes in exactly one file (`backend/library/db/models.py`)
- NFR8: Adding a new table requires changes in exactly one file plus one Alembic migration command
- NFR9: No dead code from old architecture remains (`stalker_web_document_db.py` wrapper fully removed)

### Dependency Management

- NFR10: New dependencies (`sqlalchemy`, `pgvector`, `alembic`) added to `pyproject.toml` with version pins
- NFR11: `uv lock` produces a valid lock file after dependency changes
- NFR12: `.venv_wsl` synchronized after dependency changes
