# Backend Database — CLAUDE.md

PostgreSQL database schema for Project Lenie. Init scripts are executed automatically by the `postgres` Docker image on first container startup (when the data volume is empty).

## Directory Structure

```
database/
└── init/                                        # Docker entrypoint init scripts (run in alphabetical order)
    ├── 01-create-database.sql                    # Creates the "lenie-ai" database
    ├── 02-create-extension.sql                   # Installs pgvector extension
    ├── 03-create-table.sql                       # Creates web_documents table + indexes
    ├── 04-create-table.sql                       # Creates websites_embeddings table + indexes
    ├── 05-migrate-ready-for-translation.sql
    ├── 06-drop-english-columns.sql
    ├── 07-add-transcript-needed.sql
    ├── 08-fix-language-typo.sql                  # websites_embeddings.langauge → language
    ├── 09-create-lookup-tables.sql
    ├── 10-add-foreign-keys.sql
    ├── 11-create-transcription-log.sql
    ├── 12-add-video-description.sql
    ├── 13-create-analysis-tables.sql             # document_analysis_runs, document_chunks, document_topic_sections
    ├── 14-add-speakers-to-analysis-runs.sql
    ├── 15-add-analysis-run-workflow-columns.sql  # mode, status, scope on document_analysis_runs
    ├── 16-add-chunk-id-to-embeddings.sql         # websites_embeddings.chunk_id FK
    ├── 17-add-text-extracted-to-web-documents.sql
    ├── 18-create-document-removed-lines.sql
    ├── 19-create-reader-user-tables.sql          # users, user_reading_progress, user_document_notes
    ├── 20-create-api-keys.sql                    # api_keys
    └── 21-create-document-entities.sql           # document_entities (raw NER persons/places)
```

## How Init Scripts Are Used

The scripts in `init/` are copied into `/docker-entrypoint-initdb.d` inside the PostgreSQL container (see `infra/docker/Postgresql/Dockerfile`). PostgreSQL's official Docker image executes all `.sql` files in that directory **once** — only when the data directory is empty (first run). Re-running the container with an existing volume will **not** re-execute the scripts.

To re-initialize the database, delete the named volume (`lenie-ai-db-data-3`) and restart the container.

## Database: `lenie-ai`

PostgreSQL 18 with the **pgvector** extension for vector similarity search.

### Table: `public.web_documents`

Main document storage. Each row represents a collected web resource (article, video, transcript, etc.).

| Column | Type | Description |
|--------|------|-------------|
| `id` | `serial PK` | Auto-incrementing primary key |
| `url` | `text NOT NULL` | Source URL |
| `document_type` | `varchar(50) NOT NULL` | One of: movie, youtube, link, webpage, text_message, text |
| `document_state` | `varchar(50) NOT NULL` | Processing state (default: `URL_ADDED`) |
| `document_state_error` | `text` | Error details when `document_state = ERROR` |
| `title` | `text` | Original title |
| `title_english` | `text` | English translation of title |
| `text` | `text` | Cleaned text content |
| `text_raw` | `text` | Raw extracted text before cleanup |
| `text_english` | `text` | English translation of text |
| `text_md` | `text` | Markdown version of text |
| `text_extracted` | `text` | Raw LLM article extraction output (pre `clean_article_text()`), diagnostic only — not exposed via API |
| `summary` | `text` | AI-generated summary |
| `summary_english` | `text` | English translation of summary |
| `language` | `varchar(10)` | Detected language code |
| `tags` | `text` | Comma-separated tags |
| `source` | `text` | Content source identifier |
| `author` | `text` | Document author |
| `note` | `text` | User notes |
| `paywall` | `boolean` | Whether content is behind a paywall (default: false) |
| `date_from` | `date` | Publication date |
| `created_at` | `timestamp` | Row creation timestamp |
| `document_length` | `integer` | Text length in characters |
| `chapter_list` | `text` | Chapter/section list (for videos/transcripts) |
| `original_id` | `text` | External identifier (e.g. YouTube video ID) |
| `transcript_job_id` | `text` | Transcription service job ID |
| `ai_summary_needed` | `boolean` | Flag: needs AI summary (default: false) |
| `uuid` | `varchar(100) NOT NULL DEFAULT gen_random_uuid()` | Global document identifier (ADR-015), UNIQUE |
| `project` | `varchar(100)` | Project/collection grouping |

**Indexes:** `document_type`, `document_state`, `created_at`, `url`, `project`, `source`, `date_from`, `paywall`, `ai_summary_needed`.

### Table: `public.websites_embeddings`

Vector embeddings for document chunks used in similarity search.

| Column | Type | Description |
|--------|------|-------------|
| `id` | `serial PK` | Auto-incrementing primary key |
| `website_id` | `integer NOT NULL` | FK → `web_documents.id` (CASCADE delete) |
| `language` | `varchar(10)` | Language of the embedded text |
| `text` | `text` | Translated/processed text that was embedded |
| `text_original` | `text` | Original text before translation |
| `embedding` | `vector` | Vector embedding (dimensionless — supports multiple models with different dimensions) |
| `model` | `varchar(100) NOT NULL` | Embedding model used |
| `chunk_id` | `integer` | FK → `document_chunks.id` (`ON DELETE SET NULL`), NULL for embeddings generated directly from the document (fallback path when no reviewed chunk run exists) |
| `created_at` | `timestamp` | Row creation timestamp |

**Indexes:** `website_id`, `model`, HNSW partial indexes on `embedding` per model (cosine similarity). Each embedding model has its own partial index to support different vector dimensions.

### Table: `public.document_analysis_runs`

One row per chunk-analysis pass over a document (`library/document_analysis_service.py`, `POST /document/<id>/analyze_chunks`). A document can have several runs — e.g. a book typically has one `split_only` run over the whole text plus one `article` run per chapter.

| Column | Type | Description |
|--------|------|-------------|
| `id` | `serial PK` | Auto-incrementing primary key |
| `document_id` | `integer NOT NULL` | FK → `web_documents.id` (CASCADE delete) |
| `model` | `varchar(100) NOT NULL` | LLM model used for the analysis |
| `chunk_size` | `integer NOT NULL DEFAULT 5000` | Target chunk size in characters |
| `synthesis` | `text` | LLM-generated overview of the whole run (shown as a collapsible "Synteza" panel in `/chunks/:id`) |
| `speakers` | `jsonb NOT NULL DEFAULT '[]'` | Detected speaker list, `mode=transcript` only |
| `mode` | `varchar(20) NOT NULL DEFAULT 'transcript'` | `transcript` (YouTube/movie STT — LLM rewrite + speaker labeling, split by sentence) or `article` (webpage/link/text/book chapters — no rewrite, source markdown already clean so every chunk's `corrected_text` is `NULL` by design; split by markdown headings) |
| `status` | `varchar(20) NOT NULL DEFAULT 'created'` | Run review workflow: `created` → `in_review` → `reviewed` |
| `scope` | `varchar(200)` | Human-readable analysed range (e.g. a book chapter title); `NULL` = whole document |
| `created_at` | `timestamp` | Row creation timestamp |

### Table: `public.document_chunks`

One row per chunk produced by a run.

| Column | Type | Description |
|--------|------|-------------|
| `id` | `serial PK` | Auto-incrementing primary key |
| `run_id` | `integer NOT NULL` | FK → `document_analysis_runs.id` (CASCADE delete) |
| `document_id` | `integer NOT NULL` | FK → `web_documents.id` (CASCADE delete) |
| `position` | `smallint NOT NULL` | 1-based order within the run |
| `type` | `varchar(20) NOT NULL` | `TEMAT` (on-topic) / `REKLAMA` (sponsored) / `SZUM` (extraction junk — portal nav, cookie banners; auto-approved, excluded from note-writing) |
| `topic` | `varchar(500)` | Short topic label |
| `original_text` | `text NOT NULL` | Source text of the chunk |
| `corrected_text` | `text` | LLM-rewritten text — populated only for `mode=transcript`; always `NULL` for `mode=article` (no rewrite step, not a data quality issue) |
| `summary` | `text` | 2-3 sentence LLM summary |
| `seg_start` / `seg_end` | `integer` | Segment index range within the transcript (`mode=transcript` only) |
| `rewrite_ratio` | `smallint` | STT rewrite change ratio (`mode=transcript` only) |
| `status` | `varchar(30) NOT NULL DEFAULT 'pending'` | `pending` / `approved` / `needs_reanalysis` / `split_requested` / `split` / `skipped` |
| `split_at_seg` | `integer` | Segment offset for a pending manual split |
| `split_first_type` / `split_second_type` | `varchar(20)` | Resulting types after executing a split |
| `created_at` / `updated_at` | `timestamp` | Row timestamps |
| `obsidian_note_paths` | `text[] NOT NULL DEFAULT '{}'` | Vault-relative paths of notes written from this chunk (populated by the `/obsidian-note` skill) |

### Table: `public.document_topic_sections`

LLM-synthesized grouping of a run's chunks by topic — drives the book/chapter drill-down accordion in `/chunks/:id` (used once a run exceeds the UI's `SECTION_VIEW_THRESHOLD`). Coverage of a run's chunks is partial by design — LLM synthesis doesn't always assign every chunk to a section.

| Column | Type | Description |
|--------|------|-------------|
| `id` | `serial PK` | Auto-incrementing primary key |
| `run_id` | `integer NOT NULL` | FK → `document_analysis_runs.id` (CASCADE delete) |
| `document_id` | `integer NOT NULL` | FK → `web_documents.id` (CASCADE delete) |
| `position` | `smallint NOT NULL` | Order within the run |
| `type` | `varchar(20) NOT NULL` | `TEMAT` / `REKLAMA` / `SZUM` |
| `title` | `varchar(500)` | Section title (editable via `PATCH /topic_section/<id>`) |
| `summary` | `text` | LLM summary of the section |
| `chunk_positions` | `integer[] NOT NULL` | Positions of the `document_chunks` rows belonging to this section |
| `created_at` / `updated_at` | `timestamp` | Row timestamps |

### Table: `public.document_removed_lines`

Training data for `article_cleaner.py`: lines a human manually removed from a chunk or document during review. Survives run/chunk deletion (`run_id`/`chunk_id` are `SET NULL`, not `CASCADE`) so aggregate queries (e.g. most-removed lines per portal, joined on `web_documents.url`) keep working after runs are re-created.

| Column | Type | Description |
|--------|------|-------------|
| `id` | `serial PK` | Auto-incrementing primary key |
| `document_id` | `integer NOT NULL` | FK → `web_documents.id` (CASCADE delete) |
| `run_id` | `integer` | FK → `document_analysis_runs.id` (`SET NULL` on delete) |
| `chunk_id` | `integer` | FK → `document_chunks.id` (`SET NULL` on delete) |
| `source` | `varchar(20) NOT NULL` | `manual` (removed in chunk-review UI) or `szum_chunk` (whole SZUM/REKLAMA chunk dropped by "Wyczyść dokument") |
| `line_text` | `text NOT NULL` | The removed line/block |
| `created_at` | `timestamp` | Row creation timestamp |

### Table: `public.document_entities`

Raw NER entities (person/place mentions) per document — MVP of [`docs/ner-integration-plan.md`](../../docs/ner-integration-plan.md). Populated by `library/entity_service.py` from the NER microservice (`ner_service/`, via `library/ner_client.py`). Rows are derived data: a refresh **replaces** the document's rows (unlike `tags`, which accumulates). Deliberately no disambiguation columns — persons get dedicated tables in a later stage ([`docs/person-ner-plan.md`](../../docs/person-ner-plan.md)), places get verification + tags ([`docs/geo-place-ner-plan.md`](../../docs/geo-place-ner-plan.md)).

| Column | Type | Description |
|--------|------|-------------|
| `id` | `serial PK` | Auto-incrementing primary key |
| `document_id` | `integer NOT NULL` | FK → `web_documents.id` (CASCADE delete) |
| `entity_type` | `varchar(20) NOT NULL` | `persName` / `geogName` / `placeName` (spaCy `pl_core_news_lg` labels) |
| `entity_text` | `text NOT NULL` | Base form of the mention (lemma when available — inflected variants aggregate into one row) |
| `mention_count` | `integer NOT NULL DEFAULT 1` | Number of mentions aggregated into this row |
| `created_at` | `timestamp` | Row creation timestamp |

**Constraints/indexes:** UNIQUE `(document_id, entity_type, entity_text)`; indexes on `document_id` and `entity_type`.

Reader identity and API key tables (`users`, `user_reading_progress`, `user_document_notes`, `api_keys` — init scripts 19-20) are out of scope for this section; see `library/reader_routes.py`, `library/auth.py` and `library/db/models.py` for their definitions.

## Document Processing States

The `document_state` column tracks a document through its processing pipeline (defined in `backend/library/models/stalker_document_status.py`):

```
URL_ADDED → DOCUMENT_INTO_DATABASE → NEED_CLEAN_TEXT → NEED_CLEAN_MD → TEXT_TO_MD_DONE
    → MD_SIMPLIFIED → READY_FOR_TRANSLATION → READY_FOR_EMBEDDING → EMBEDDING_EXIST
```

Special states:
- `NEED_TRANSCRIPTION` / `TRANSCRIPTION_IN_PROGRESS` / `TRANSCRIPTION_DONE` — for audio/video content
- `NEED_MANUAL_REVIEW` — automatic text cleanup failed; needs manual removal of ads, comments, and spam
- `ERROR` / `TEMPORARY_ERROR` — processing failed (details in `document_state_error`)

**Invariant — `document_state_error` must be reset on every successful transition.** The field only means something while the document is in an error state (`ERROR`/`TEMPORARY_ERROR`); once a retry succeeds and `document_state` moves on, any code that sets `document_state_error` on failure MUST also clear it (`StalkerDocumentStatusError.NONE.name`) on the corresponding success path in the same function. Otherwise the error becomes sticky forever — a later retry that succeeds leaves the stale value in place because nothing overwrites it. `WebDocument.validate()` in `db/models.py` follows this correctly (resets to `NONE` at the top before re-evaluating). `library/youtube_processing.py` did **not** follow it for `CAPTIONS_FETCH_ERROR`/transcription errors until this was fixed (2026-07-04) — a retry that fetched captions successfully left `CAPTIONS_FETCH_ERROR` from an earlier failed attempt in place indefinitely. When adding a new failure/retry branch to any pipeline step, always pair the error-setting line with a reset on the success path.

## Document Types

The `document_type` column (defined in `backend/library/models/stalker_document_type.py`):
- `movie` — video content
- `youtube` — YouTube video
- `link` — bookmark/reference link
- `webpage` — full webpage content
- `text_message` — plain text input
- `text` — generic text document

## Docker Setup

**Image:** Custom image built from `postgres:18-bookworm` with `postgresql-18-pgvector` package installed (see `infra/docker/Postgresql/Dockerfile`).

**Compose service** (`infra/docker/compose.yaml`):
- Image: `lenie-ai-db:latest` (must be built locally first)
- Port mapping: `5433:5432` (host:container)
- Volume: `lenie-ai-db-data-3` for persistent storage
- Default password: `postgres` (development only)

Build the database image:
```bash
docker build -f infra/docker/Postgresql/Dockerfile -t lenie-ai-db:latest .
```

## Application Access

The backend accesses the database via SQLAlchemy ORM. Key files:
- `backend/library/db/models.py` — ORM models (`WebDocument`, `WebsiteEmbedding`, lookup table models)
- `backend/library/db/engine.py` — engine & session factories (`get_session`, `get_scoped_session`)
- `backend/library/stalker_web_documents_db_postgresql.py` — query layer (list, search, vector similarity)

Connection configured via environment variables: `POSTGRESQL_HOST`, `POSTGRESQL_DATABASE`, `POSTGRESQL_USER`, `POSTGRESQL_PASSWORD`, `POSTGRESQL_PORT`.

## Known Issues

- The `langauge` typo in `websites_embeddings` was fixed — column renamed to `language` (migration: `08-fix-language-typo.sql`).
- The `embedding` column uses dimensionless `vector` type to support multiple embedding models with different dimensions (e.g. OpenAI ada-002: 1536, Titan v2: 1024, BAAI/bge-multilingual-gemma2: 3584). Each model has a dedicated HNSW partial index. When adding a new embedding model, create a new partial index in `04-create-table.sql`.
