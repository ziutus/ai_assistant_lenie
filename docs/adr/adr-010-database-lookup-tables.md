# ADR-010: Database Lookup Tables with Foreign Keys for Enum-Like Fields

**Date:** 2026-03-10
**Status:** Accepted
**Decision Makers:** Ziutus

### Context

The project uses three Python enums to define constrained value sets for `web_documents` columns:

| Python Enum | Column | Values |
|-------------|--------|--------|
| `StalkerDocumentStatus` | `document_state` | 16 states (ERROR → TEMPORARY_ERROR) |
| `StalkerDocumentStatusError` | `document_state_error` | 17 error types |
| `StalkerDocumentType` | `document_type` | 6 types (movie, youtube, link, webpage, text_message, text) |

Additionally, `websites_embeddings.model` stores embedding model names as free-text `varchar`.

The AWS production database (dump from 2026-01-23) already has four lookup tables with FK constraints enforcing these values at the database level:

- `document_status_types` (FK on `web_documents.document_state`)
- `document_status_error_types` (FK on `web_documents.document_state_error`)
- `document_types` (FK on `web_documents.document_type`)
- `embedding_models` (FK on `websites_embeddings.model` and `embeddings_cache.model`)

The Docker init scripts (`03-create-table.sql`, `04-create-table.sql`) do **not** create these lookup tables — they store enum values as plain `varchar` strings with no FK constraints. The Python code comments confirm this gap: `# Those errors status are also defined in Postgresql table: document_status_types`.

The current SQLAlchemy ORM models (`db/models.py`) use `SAEnum(..., native_enum=False)` which stores values as VARCHAR with application-level validation only — the database does not enforce valid values.

### Decision

Create database lookup tables with FK constraints to enforce data integrity at the database level, matching the existing AWS production schema:

1. **`document_status_types`** — lookup for `web_documents.document_state`
2. **`document_status_error_types`** — lookup for `web_documents.document_state_error`
3. **`document_types`** — lookup for `web_documents.document_type`
4. **`embedding_models`** — lookup for `websites_embeddings.model` (and future `embeddings_cache.model`)

Each lookup table has `id SERIAL PRIMARY KEY` and `name VARCHAR UNIQUE NOT NULL`. FK constraints reference the `name` column (not `id`) for readability of raw queries and data exports.

Python enums (`StalkerDocumentStatus`, `StalkerDocumentStatusError`, `StalkerDocumentType`) remain the **source of truth** for values — an Alembic migration or init script seeds the lookup tables from the enum definitions.

### Rationale

1. **Data integrity.** Without FK constraints, a bug or manual SQL could insert `document_state = 'EMBEDING_EXIST'` (typo) and the database would accept it silently. FK constraints catch this immediately.

2. **Consistency with production.** The AWS database already has these tables and constraints. The Docker development environment should match production schema to avoid "works locally, breaks in prod" issues.

3. **ORM alignment.** SQLAlchemy supports FK-backed enums naturally. The ORM can be updated to define proper `relationship()` mappings to lookup tables, enabling JOIN queries (e.g., statistics per document type).

4. **Extensibility.** Adding a new document type or status becomes: (a) add to Python enum, (b) INSERT into lookup table (via Alembic migration). The FK constraint ensures both stay in sync.

5. **Query clarity.** `SELECT DISTINCT document_state FROM web_documents` is fragile (shows only used values). `SELECT name FROM document_status_types` shows all valid values regardless of usage.

### Implementation

**Phase 1 — Lookup tables & seed data (init scripts + Alembic migration):**

```sql
CREATE TABLE IF NOT EXISTS document_status_types (
    id SERIAL PRIMARY KEY,
    name VARCHAR UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS document_status_error_types (
    id SERIAL PRIMARY KEY,
    name VARCHAR UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS document_types (
    id SERIAL PRIMARY KEY,
    name VARCHAR UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS embedding_models (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL
);
```

Seed with values from Python enums. Add FK constraints:

```sql
ALTER TABLE web_documents
    ADD CONSTRAINT fk_document_type
    FOREIGN KEY (document_type) REFERENCES document_types(name);

ALTER TABLE web_documents
    ADD CONSTRAINT fk_document_state
    FOREIGN KEY (document_state) REFERENCES document_status_types(name);

ALTER TABLE web_documents
    ADD CONSTRAINT fk_document_state_error
    FOREIGN KEY (document_state_error) REFERENCES document_status_error_types(name);

ALTER TABLE websites_embeddings
    ADD CONSTRAINT model_fk
    FOREIGN KEY (model) REFERENCES embedding_models(name) ON UPDATE CASCADE ON DELETE CASCADE;
```

**Phase 2 — ORM model updates:**

Update SQLAlchemy models to reflect FK relationships. Replace `SAEnum(..., native_enum=False)` with `String` + `ForeignKey` + `relationship()`.

**Phase 3 — Sync mechanism:**

Add a startup check or Alembic migration that inserts missing enum values into lookup tables, ensuring Python enums and database stay in sync.

### Consequences

- **Positive:** Database enforces valid values — impossible to insert invalid states, types, or models.
- **Positive:** Docker and AWS schemas converge — reduces environment-specific bugs.
- **Positive:** Lookup tables serve as queryable documentation of valid values.
- **Positive:** Enables future features like status/type metadata (descriptions, display order, active/deprecated flags).
- **Negative:** Adding a new enum value now requires both a code change and a database migration (INSERT into lookup table).
- **Negative:** FK constraints may complicate bulk data imports if values are inserted before lookup tables are populated.
- **Trade-off:** FK references `name` (not `id`) — more readable in raw SQL but slightly less efficient for joins. Acceptable for the table sizes involved (< 20 rows each).

### Why Python Enums Are Kept Alongside DB FK Constraints (B-96)

After completing Phase 2 (ORM model updates with `String` + `ForeignKey`), the question arose: why keep Python enums (`StalkerDocumentType`, `StalkerDocumentStatus`, `StalkerDocumentStatusError`) if the database already enforces valid values via FK constraints?

**Decision:** Keep Python enums as the source of truth. Reasons:

1. **Early validation.** Setter methods (`set_document_type()`, `set_document_state()`, `set_document_state_error()`) raise `ValueError` immediately when called with invalid input. Without enums, the error would only surface at `session.commit()` as an `IntegrityError` — harder to debug and further from the source of the bug.

2. **Input aliases.** Setters accept aliases like `"website"` → `"webpage"`, `"sms"` → `"text_message"`, `"ERROR_DOWNLOAD"` → `"ERROR"`. The database FK cannot handle this mapping — it only validates exact values.

3. **IDE autocomplete.** `StalkerDocumentStatus.EMBEDDING_EXIST` provides autocomplete and typo detection in editors. Raw strings like `"EMBEDDING_EXIST"` do not.

4. **Two-layer defense.** Python enums catch bugs at application level; FK constraints catch bugs at data level (manual SQL, import scripts, other clients). Neither layer alone covers all cases.

The ORM columns store the enum `.name` string (e.g., `StalkerDocumentStatus.ERROR.name` → `"ERROR"`). This keeps the database portable and human-readable while maintaining Python-level type safety.

### Related Artifacts

- `backend/library/models/stalker_document_status.py` — 16 document states
- `backend/library/models/stalker_document_status_error.py` — 17 error types
- `backend/library/models/stalker_document_type.py` — 6 document types
- `backend/library/db/models.py` — SQLAlchemy ORM models with `String` + `ForeignKey` (B-96)
- `backend/database/init/03-create-table.sql` — `web_documents` table (no FK constraints)
- `backend/database/init/04-create-table.sql` — `websites_embeddings` table (no FK constraints)
- `backend/tmp/sql_data/lenie_aws-2026_01_23_05_00_40-dump.sql` — AWS dump with lookup tables and FK constraints
- [ADR-004a](adr-004a-sqlalchemy-orm-migration.md) — SQLAlchemy ORM migration
- [B-92](#b-92-migrate-database-layer-to-sqlalchemy-orm--pydantic-schemas) — ORM migration backlog item
