# Story 26.2: ORM Models — WebDocument (STI) & WebsiteEmbedding

Status: done

## Story

As a **developer**,
I want `WebDocument` and `WebsiteEmbedding` defined as SQLAlchemy 2.x ORM models in `library/db/models.py`,
So that database schema is defined once in Python and I can add columns/tables with a single-file change.

## Acceptance Criteria

1. **Given** `library/db/models.py` exists
   **When** `WebDocument` model is inspected
   **Then** it maps all 26 columns from `web_documents` table with exact column names and types matching DDL (`03-create-table.sql`)

2. **Given** `WebDocument` has STI configured
   **When** `__mapper_args__` is inspected
   **Then** `document_type` is the polymorphic discriminator

3. **Given** `WebDocument` has domain methods
   **When** `set_document_type()`, `set_document_state()`, `validate()`, `dict()` are called
   **Then** they behave identically to current `StalkerWebDocumentDB` methods

4. **Given** `dict()` is called on a `WebDocument` instance
   **When** the result is inspected
   **Then** dates are formatted as `"YYYY-MM-DD HH:MM:SS"`, enums as `.name`, all existing keys preserved

5. **Given** `WebsiteEmbedding` model exists
   **When** inspected
   **Then** it has dimensionless `Vector()` column, `website_id` FK, `language`, `model`, `text` columns matching DDL (`04-create-table.sql`)

6. **Given** `WebDocument` has a relationship to `WebsiteEmbedding`
   **When** relationship is inspected
   **Then** `cascade="all, delete-orphan"` is configured

7. **Given** enums are needed by ORM model
   **When** imports are inspected
   **Then** enums are imported from `library.models.stalker_document_status` (original location, not moved)

8. **Given** all ORM model columns use type hints
   **When** code is inspected
   **Then** all columns use `Mapped[type]` with `mapped_column()` (not older `Column()` style)

9. **Given** navigation fields exist
   **When** `next_id`, `next_type`, `previous_id`, `previous_type` are inspected
   **Then** they are plain Python class attributes (`= None`), NOT `mapped_column()`

## Tasks / Subtasks

- [x] Task 1: Create WebDocument ORM model (AC: #1, #2, #7, #8)
  - [x]1.1: Create `backend/library/db/models.py` with imports (Base from engine.py, enums from library.models.*)
  - [x]1.2: Define `WebDocument` class inheriting from `Base` with `__tablename__ = "web_documents"`
  - [x]1.3: Map all 26 columns with exact DDL names, types, nullability, and server_default values
  - [x]1.4: Configure STI: `__mapper_args__ = {"polymorphic_on": "document_type"}`
  - [x]1.5: Use `Enum(StalkerDocumentType, native_enum=False, values_callable=...)` for enum-as-varchar mapping (same for Status and StatusError)
- [x] Task 2: Define STI subclasses for each document type (AC: #2)
  - [x]2.1: Create `LinkDocument(WebDocument)` with `polymorphic_identity = "link"`
  - [x]2.2: Create `YouTubeDocument(WebDocument)` with `polymorphic_identity = "youtube"`
  - [x]2.3: Create `MovieDocument(WebDocument)` with `polymorphic_identity = "movie"`
  - [x]2.4: Create `WebpageDocument(WebDocument)` with `polymorphic_identity = "webpage"`
  - [x]2.5: Create `TextMessageDocument(WebDocument)` with `polymorphic_identity = "text_message"`
  - [x]2.6: Create `TextDocument(WebDocument)` with `polymorphic_identity = "text"`
- [x] Task 3: Add domain methods to WebDocument (AC: #3, #4)
  - [x]3.1: Migrate `set_document_type(str)` from `stalker_web_document.py`
  - [x]3.2: Migrate `set_document_state(str)` from `stalker_web_document.py`
  - [x]3.3: Migrate `set_document_state_error(str)` from `stalker_web_document.py`
  - [x]3.4: Migrate `validate()` from `stalker_web_document.py`
  - [x]3.5: Migrate `analyze()` from `stalker_web_document.py`
  - [x]3.6: Implement `dict()` matching exact output format of `StalkerWebDocumentDB.dict()` (see Dev Notes for required format)
  - [x]3.7: Add navigation attributes as plain class attributes: `next_id = None`, `next_type = None`, `previous_id = None`, `previous_type = None` (AC: #9)
- [x] Task 4: Create WebsiteEmbedding ORM model (AC: #5, #6)
  - [x]4.1: Define `WebsiteEmbedding` class with `__tablename__ = "websites_embeddings"`
  - [x]4.2: Map all 8 columns with exact DDL names and types, including dimensionless `Vector()` column
  - [x]4.3: Define `website_id` FK: `ForeignKey("web_documents.id", ondelete="CASCADE")`
  - [x]4.4: Add relationship on `WebDocument`: `embeddings: Mapped[list["WebsiteEmbedding"]]` with `cascade="all, delete-orphan"`, `passive_deletes=True`
  - [x]4.5: Add back_populates relationship on `WebsiteEmbedding`: `document: Mapped["WebDocument"]`
- [x] Task 5: Write unit tests (AC: all)
  - [x]5.1: Test WebDocument model has all 26 column attributes (inspect mapper columns)
  - [x]5.2: Test column types match DDL (String(50), Text, Boolean, Integer, Date, DateTime)
  - [x]5.3: Test STI configuration: `polymorphic_on` is `document_type`
  - [x]5.4: Test all 6 STI subclasses have correct `polymorphic_identity`
  - [x]5.5: Test `set_document_type()` sets enum correctly (e.g., 'link' → StalkerDocumentType.link)
  - [x]5.6: Test `set_document_state()` sets enum correctly
  - [x]5.7: Test `validate()` sets NEED_MANUAL_REVIEW for missing title
  - [x]5.8: Test `dict()` output keys match expected set (31 keys including navigation fields)
  - [x]5.9: Test `dict()` formats `created_at` as `"YYYY-MM-DD HH:MM:SS"` string
  - [x]5.10: Test `dict()` returns `.name` for document_type and document_state enums
  - [x]5.11: Test WebsiteEmbedding has all 8 columns
  - [x]5.12: Test WebsiteEmbedding.website_id FK target is `web_documents.id`
  - [x]5.13: Test WebDocument.embeddings relationship exists with correct cascade
  - [x]5.14: Test navigation fields (next_id, next_type, etc.) are NOT in mapper columns
  - [x]5.15: Test enums imported from original `library.models.*` locations
  - [x]5.16: Test Base is imported from `library.db.engine` (not redefined)
- [x] Task 6: Quality checks (AC: all)
  - [x]6.1: Run `ruff check backend/` — zero warnings for new files
  - [x]6.2: Run existing unit tests — no regressions
  - [x] 6.3: Sync `.venv_wsl` and verify import: `from library.db.models import WebDocument, WebsiteEmbedding`

## Dev Notes

### Architecture Requirements

This story implements **Phase B (Models)** of the 9-phase SQLAlchemy ORM migration sequence. It depends on Story 26.1 (engine, Base, session factories) which is DONE. All subsequent stories (26.3 Alembic, Epic 27-29) depend on this.

**Key architectural decisions (from PRD and epics):**

1. **Single File:** All models in `backend/library/db/models.py` — one file for all ORM models.
2. **STI on `web_documents`:** `document_type` column is the polymorphic discriminator. 6 subclasses (one per document type). Subclasses have NO extra columns — only `polymorphic_identity`.
3. **Enum-as-VARCHAR:** Database stores enum names as plain strings (NOT PostgreSQL ENUM types). ORM must map between Python Enum and DB string. Use `sqlalchemy.Enum(EnumClass, native_enum=False, values_callable=lambda x: [e.name for e in x])`.
4. **Navigation Fields:** `next_id`, `next_type`, `previous_id`, `previous_type` are transient — populated by repository's `load_neighbors()` method (Story 27.2). They are plain Python class attributes (`= None`), NOT mapped columns.
5. **Enums Stay in Place:** Import from `library.models.stalker_document_status`, `library.models.stalker_document_type`, `library.models.stalker_document_status_error`. DO NOT move or copy enum classes.
6. **pgvector HNSW Indexes:** NOT defined in ORM model. Managed by Alembic migrations only (Story 26.3).
7. **`passive_deletes=True`:** On the embeddings relationship. DB has `ON DELETE CASCADE` — let PostgreSQL handle cascading, don't load all children in Python.
8. **`dict()` Backward Compatibility:** Output must EXACTLY match `StalkerWebDocumentDB.dict()` — same keys, same types, same date formatting. This is critical for API response stability.

### Current Code to Replace (reference only — do NOT modify these files in this story)

**`stalker_web_document.py`** (domain model, 228 lines):
- 26 instance attributes in `__init__`
- Domain methods: `set_document_type(str)`, `set_document_state(str)`, `set_document_state_error(str)`, `validate()`, `analyze()`
- Enums stored as Python Enum members (e.g., `self.document_type = StalkerDocumentType.link`)

**`stalker_web_document_db.py`** (persistence wrapper, 280 lines):
- Inherits StalkerWebDocument, adds psycopg2 DB access
- `dict()` method — the EXACT format to replicate
- `save()`, `delete()` — NOT part of this story (Story 27.1)
- `embedding_add()`, `embedding_delete()`, `embedding_add_simple()` — NOT part of this story (Story 28.1)
- Navigation fields: `next_id`, `next_type`, `previous_id`, `previous_type`

### Database Schema — `web_documents` (26 columns)

```sql
create table web_documents (
    id                   serial primary key,          -- Mapped[int], primary_key=True
    summary              text,                        -- Mapped[str | None], Text
    url                  text not null,               -- Mapped[str], Text, nullable=False
    language             varchar(10),                 -- Mapped[str | None], String(10)
    tags                 text,                        -- Mapped[str | None], Text
    text                 text,                        -- Mapped[str | None], Text
    paywall              boolean default false,       -- Mapped[bool | None], Boolean, server_default=text('false')
    title                text,                        -- Mapped[str | None], Text
    created_at           timestamp default CURRENT_TIMESTAMP, -- Mapped[datetime | None], DateTime, server_default=func.now()
    document_type        varchar(50) not null,        -- Mapped[StalkerDocumentType], Enum(..., native_enum=False), nullable=False
    source               text,                        -- Mapped[str | None], Text
    date_from            date,                        -- Mapped[date | None], Date
    original_id          text,                        -- Mapped[str | None], Text
    document_length      integer,                     -- Mapped[int | None], Integer
    chapter_list         text,                        -- Mapped[str | None], Text
    document_state       varchar(50) default 'URL_ADDED' not null, -- Mapped[StalkerDocumentStatus], Enum(...), nullable=False, server_default='URL_ADDED'
    document_state_error text,                        -- Mapped[str | None] OR Mapped[StalkerDocumentStatusError | None]
    text_raw             text,                        -- Mapped[str | None], Text
    transcript_job_id    text,                        -- Mapped[str | None], Text
    ai_summary_needed    boolean default false,       -- Mapped[bool | None], Boolean, server_default=text('false')
    author               text,                        -- Mapped[str | None], Text
    note                 text,                        -- Mapped[str | None], Text
    s3_uuid              varchar(100),                -- Mapped[str | None], String(100)
    project              varchar(100),                -- Mapped[str | None], String(100)
    text_md              text,                        -- Mapped[str | None], Text
    transcript_needed    boolean default false         -- Mapped[bool | None], Boolean, server_default=text('false')
);
```

**Indexes** (9 indexes on web_documents — reference only, NOT defined in ORM model):
`document_type`, `document_state`, `created_at`, `url`, `project`, `source`, `date_from`, `paywall`, `ai_summary_needed`

### Database Schema — `websites_embeddings` (8 columns)

```sql
CREATE TABLE websites_embeddings (
    id           SERIAL PRIMARY KEY,               -- Mapped[int], primary_key=True
    website_id   INTEGER NOT NULL,                  -- Mapped[int], ForeignKey("web_documents.id", ondelete="CASCADE")
    language     VARCHAR(10),                       -- Mapped[str | None], String(10)
    text         TEXT,                              -- Mapped[str | None], Text
    text_original TEXT,                             -- Mapped[str | None], Text
    embedding    vector,                            -- Mapped[Vector | None], Vector() (dimensionless!)
    model        VARCHAR(100) NOT NULL,             -- Mapped[str], String(100), nullable=False
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP -- Mapped[datetime | None], DateTime, server_default=func.now()
);
```

**HNSW partial indexes** (5 per-model indexes — NOT in ORM model, managed by Alembic):
`idx_emb_ada002`, `idx_emb_titan_v1`, `idx_emb_titan_v2`, `idx_emb_stella_en`, `idx_emb_bge_m3`

### Enum-as-VARCHAR Mapping Strategy

The DB stores enum values as plain strings (e.g., `'link'`, `'URL_ADDED'`, `'NONE'`). The Python code uses Enum classes. Use SQLAlchemy's `Enum` type with `native_enum=False`:

```python
from sqlalchemy import Enum as SAEnum

document_type: Mapped[StalkerDocumentType] = mapped_column(
    SAEnum(
        StalkerDocumentType,
        values_callable=lambda x: [e.name for e in x],
        native_enum=False,
        length=50,
    ),
    nullable=False,
)
```

This ensures:
- DB column remains VARCHAR (no PostgreSQL ENUM type created)
- Python attribute is a `StalkerDocumentType` enum member
- `.name` works for `dict()` serialization
- `set_document_type()` method still works (sets enum member)

Apply the same pattern to `document_state` (StalkerDocumentStatus) and `document_state_error` (StalkerDocumentStatusError).

**Note on `document_state_error`:** The DDL type is `text` (not `varchar(50)`) and is nullable. The current code sometimes stores `None` and sometimes the enum `.name`. When loaded, `set_document_state_error(None)` sets it to `StalkerDocumentStatusError.NONE`. For the ORM, either:
- Use `SAEnum(StalkerDocumentStatusError, native_enum=False)` with `nullable=True`
- OR use `Mapped[str | None]` and handle conversion in methods

The first approach is cleaner and maintains backward compatibility.

### `dict()` Method — Exact Required Output Format

```python
def dict(self):
    return {
        "id": self.id,
        "next_id": self.next_id,          # transient, populated by load_neighbors()
        "next_type": self.next_type,       # transient
        "previous_id": self.previous_id,   # transient
        "previous_type": self.previous_type, # transient
        "summary": self.summary,
        "url": self.url,
        "language": self.language,
        "tags": self.tags,
        "text": self.text,
        "paywall": self.paywall,
        "title": self.title,
        "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S"),  # MUST format
        "document_type": self.document_type.name,    # enum → string
        "source": self.source,
        "date_from": self.date_from,        # date object, NOT formatted
        "original_id": self.original_id,
        "document_length": self.document_length,
        "chapter_list": self.chapter_list,
        "document_state": self.document_state.name,  # enum → string
        "document_state_error": self.document_state_error.name,  # enum → string
        "text_raw": self.text_raw,
        "transcript_job_id": self.transcript_job_id,
        "ai_summary_needed": self.ai_summary_needed,
        "author": self.author,
        "note": self.note,
        "s3_uuid": self.s3_uuid,
        "project": self.project,
        "text_md": self.text_md,
        "transcript_needed": self.transcript_needed,
    }
```

**31 keys total** (26 DB columns + 4 navigation + `id` which is a DB column). Handle `created_at is None` edge case (new unsaved document).

### Domain Methods to Migrate

Copy these methods from `stalker_web_document.py` (lines 99-227) into the ORM model:

1. **`set_document_type(document_type: str) -> None`** — Maps string ('movie', 'youtube', 'link', 'webpage', 'website', 'sms', 'text_message', 'text') to enum. Raises ValueError for unknown types.
2. **`set_document_state(document_state: str) -> None`** — Maps string to StalkerDocumentStatus enum. Note: 'ERROR_DOWNLOAD' and 'ERROR' both map to ERROR. 'TEXT_TO_MD_DONE' maps to NEED_CLEAN_MD (appears to be intentional).
3. **`set_document_state_error(document_state_error: str) -> None`** — Maps string or None to StalkerDocumentStatusError. `None` and `"NONE"` both map to `.NONE`.
4. **`validate() -> None`** — Resets error to NONE, checks title length ≥3, checks summary for links, checks text for webpages.
5. **`analyze() -> None`** — Sets text_raw from text, clears text for links. Skips if EMBEDDING_EXIST.

### SQLAlchemy 2.x API Reference (verified March 2026)

**STI pattern:**
```python
class WebDocument(Base):
    __tablename__ = "web_documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    document_type: Mapped[StalkerDocumentType] = mapped_column(
        SAEnum(StalkerDocumentType, values_callable=lambda x: [e.name for e in x],
               native_enum=False, length=50),
        nullable=False,
    )
    __mapper_args__ = {"polymorphic_on": "document_type"}

class LinkDocument(WebDocument):
    __mapper_args__ = {"polymorphic_identity": StalkerDocumentType.link}
```

**Dimensionless Vector (pgvector-python):**
```python
from pgvector.sqlalchemy import Vector

embedding: Mapped[list | None] = mapped_column(Vector(), nullable=True)
```
Note: `Vector()` without argument = dimensionless (supports multiple embedding models with different dimensions).

**Relationship with cascade:**
```python
embeddings: Mapped[list["WebsiteEmbedding"]] = relationship(
    back_populates="document",
    cascade="all, delete-orphan",
    passive_deletes=True,
)
```

### Testing Strategy

**Unit tests only** (no database required):

- Use `inspect(WebDocument)` to verify mapper columns, relationships, and STI configuration
- Instantiate models directly to test domain methods (set_*, validate, dict)
- Test enum mapping via direct attribute access
- Test navigation fields are NOT in `inspect(WebDocument).mapper.columns`

**Test location:** `backend/tests/unit/test_db_models.py`

**Test framework:** pytest (`cd backend && PYTHONPATH=. uvx pytest tests/unit/ -v`)

**Note from Story 26.1:** `uvx pytest` may not find `sqlalchemy`/`pgvector` because uvx creates an isolated env. If so, use `.venv/Scripts/python -m pytest` instead.

### Existing Enum Values (reference)

**StalkerDocumentType** (6 values): `movie=1, youtube=2, link=3, webpage=4, text_message=5, text=6`

**StalkerDocumentStatus** (15 values): `ERROR=1, URL_ADDED=2, NEED_TRANSCRIPTION=3, TRANSCRIPTION_IN_PROGRESS=4, TRANSCRIPTION_DONE=5, TRANSCRIPTION_DONE_AND_SPLIT_BY_CHAPTERS=6, NEED_MANUAL_REVIEW=7, READY_FOR_TRANSLATION=8, READY_FOR_EMBEDDING=9, EMBEDDING_EXIST=10, DOCUMENT_INTO_DATABASE=11, NEED_CLEAN_TEXT=12, NEED_CLEAN_MD=13, TEXT_TO_MD_DONE=14, MD_SIMPLIFIED=15`

**StalkerDocumentStatusError** (14 values): `NONE=1, ERROR_DOWNLOAD=2, LINK_SUMMARY_MISSING=3, TITLE_MISSING=4, TITLE_TRANSLATION_ERROR=5, TEXT_MISSING=6, TEXT_TRANSLATION_ERROR=7, SUMMARY_TRANSLATION_ERROR=8, NO_URL_ERROR=9, EMBEDDING_ERROR=10, MISSING_TRANSLATION=11, TRANSLATION_ERROR=12, REGEX_ERROR=13, TEXT_TO_MD_ERROR=14`

### Project Structure Notes

- `backend/library/db/models.py` is a NEW file in the `backend/library/db/` package created in Story 26.1
- Base is imported from `library.db.engine` (already exists)
- Follows existing pattern: one models file per package (`library/models/` has individual files per enum, but the ORM models consolidate into one file per architecture decision)
- No conflicts with existing files or modules

### Critical Anti-Patterns

- **DO NOT** create PostgreSQL ENUM types — use `native_enum=False`
- **DO NOT** define HNSW indexes in the ORM model — they are managed by Alembic
- **DO NOT** move or copy enum classes — import from original locations
- **DO NOT** add `__tablename__` to STI subclasses — they share the parent's table
- **DO NOT** use `Column()` style — use `Mapped[type]` + `mapped_column()`
- **DO NOT** add `default=` to boolean columns — use `server_default=text('false')` to match DDL
- **DO NOT** modify `stalker_web_document.py`, `stalker_web_document_db.py`, or any existing file — this story only ADDS new files
- **DO NOT** add `__init__` override — let SQLAlchemy generate it from mapped columns

### WSL Sync Command

After verifying tests pass:
```bash
wsl bash -c "export PATH=\"\$HOME/.local/bin:\$PATH\" && cd /mnt/c/Users/ziutus/git/_lenie-all/lenie-server-2025/backend && .venv_wsl/bin/python -c 'from library.db.models import WebDocument, WebsiteEmbedding; print(\"OK\")'"
```

### References

- [Source: _bmad-output/planning-artifacts/prd.md — Target Architecture, Session Management, Key Technology Decisions, Implementation Considerations]
- [Source: _bmad-output/planning-artifacts/epics.md — Epic 26, Story 26.2]
- [Source: _bmad-output/implementation-artifacts/26-1-dependencies-engine-session-factories.md — Previous story learnings, engine.py API]
- [Source: backend/library/stalker_web_document.py — Domain model, 26 attributes, domain methods]
- [Source: backend/library/stalker_web_document_db.py — dict() format, navigation fields, embedding methods]
- [Source: backend/database/init/03-create-table.sql — web_documents DDL (26 columns)]
- [Source: backend/database/init/04-create-table.sql — websites_embeddings DDL (8 columns)]
- [Source: backend/library/models/stalker_document_status.py — 15 status enum values]
- [Source: backend/library/models/stalker_document_type.py — 6 type enum values]
- [Source: backend/library/models/stalker_document_status_error.py — 14 error enum values]
- [Source: backend/library/db/engine.py — Base (DeclarativeBase), get_engine(), session factories]
- [Source: SQLAlchemy 2.1 docs — Mapped, mapped_column, DeclarativeBase, relationship, Enum, STI]
- [Source: pgvector-python docs — Vector(), cosine_distance(), dimensionless column]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6 (claude-opus-4-6)

### Debug Log References

None

### Completion Notes List

- Story document incorrectly stated 31 dict() keys — actual count is 30 (26 DB columns + 4 navigation fields, id is already one of the 26 columns)
- `polymorphic_map` has 6 entries (one per subclass), not 7 — base class without `polymorphic_identity` is not included in the map
- SQLAlchemy's `cascade="all, delete-orphan"` expands "all" to individual cascade values (save-update, merge, refresh-expire, expunge, delete) — cannot check `"all" in rel.cascade` directly
- `sa_text` alias used for `sqlalchemy.text` to avoid naming conflict with `text` column attribute
- 4 pre-existing test failures in `test_metrics_endpoint.py` (x-api-key header issue) — unrelated to this story
- Task 6.3 (WSL sync) not executed in this session — requires WSL environment
- Code review fixes applied: M3 (type hint `str | None` on set_document_state_error), M4 (removed length=50 from document_state_error SAEnum — DDL is TEXT not VARCHAR), L1 (stronger test for STI __tablename__), L2 (simplified Base issubclass check), M1 (added TestSetDocumentStateError with 16 parametrized tests), M2 (added TestAnalyze with 5 tests), H1 (unmarked Task 6.3)
- Code review #2 fixes applied (2026-03-08): H1 (added pytest.importorskip("sqlalchemy") — uvx pytest no longer crashes), M2 (added 8 missing parametrized test cases for set_document_state covering all 14 handled states), M3 (replaced print() with logging.info() in analyze()), L2 (WSL sync verified — import OK)

### File List

- `backend/library/db/models.py` — NEW: WebDocument (26 columns, STI, domain methods, dict()), 6 STI subclasses, WebsiteEmbedding (8 columns, Vector, relationship)
- `backend/tests/unit/test_db_models.py` — NEW: 104 unit tests (18 test classes covering all acceptance criteria)
