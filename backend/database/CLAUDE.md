# Backend Database — CLAUDE.md

PostgreSQL database schema for Project Lenie. Init scripts are executed automatically by the `postgres` Docker image on first container startup (when the data volume is empty).

## Directory Structure

```
database/
└── init/                          # Docker entrypoint init scripts (run in alphabetical order)
    ├── 01-create-database.sql     # Creates the "lenie-ai" database
    ├── 02-create-extension.sql    # Installs pgvector extension
    ├── 03-create-table.sql        # Creates web_documents table + indexes
    └── 04-create-table.sql        # Creates websites_embeddings table + indexes
```

## How Init Scripts Are Used

The scripts in `init/` are copied into `/docker-entrypoint-initdb.d` inside the PostgreSQL container (see `infra/docker/Postgresql/Dockerfile`). PostgreSQL's official Docker image executes all `.sql` files in that directory **once** — only when the data directory is empty (first run). Re-running the container with an existing volume will **not** re-execute the scripts.

To re-initialize the database, delete the named volume (`lenie-ai-db-data-3`) and restart the container.

## Database: `lenie-ai`

PostgreSQL 17 with the **pgvector** extension for vector similarity search.

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
| `s3_uuid` | `varchar(100)` | S3 object key for stored content |
| `project` | `varchar(100)` | Project/collection grouping |

**Indexes:** `document_type`, `document_state`, `created_at`, `url`, `project`, `source`, `date_from`, `paywall`, `ai_summary_needed`.

### Table: `public.websites_embeddings`

Vector embeddings for document chunks used in similarity search.

| Column | Type | Description |
|--------|------|-------------|
| `id` | `serial PK` | Auto-incrementing primary key |
| `website_id` | `integer NOT NULL` | FK → `web_documents.id` (CASCADE delete) |
| `langauge` | `varchar(10)` | Language of the embedded text (note: intentional typo kept for compatibility) |
| `text` | `text` | Translated/processed text that was embedded |
| `text_original` | `text` | Original text before translation |
| `embedding` | `vector(1536)` | Vector embedding (1536 dimensions — OpenAI ada-002 format) |
| `model` | `varchar(100) NOT NULL` | Embedding model used |
| `created_at` | `timestamp` | Row creation timestamp |

**Indexes:** `website_id`, `model`, IVFFlat index on `embedding` (cosine similarity).

## Document Processing States

The `document_state` column tracks a document through its processing pipeline (defined in `backend/library/models/stalker_document_status.py`):

```
URL_ADDED → DOCUMENT_INTO_DATABASE → NEED_CLEAN_TEXT → NEED_CLEAN_MD → TEXT_TO_MD_DONE
    → MD_SIMPLIFIED → READY_FOR_TRANSLATION → READY_FOR_EMBEDDING → EMBEDDING_EXIST
```

Special states:
- `NEED_TRANSCRIPTION` / `TRANSCRIPTION_IN_PROGRESS` / `TRANSCRIPTION_DONE` — for audio/video content
- `NEED_MANUAL_REVIEW` — requires human review
- `ERROR` — processing failed (details in `document_state_error`)

## Document Types

The `document_type` column (defined in `backend/library/models/stalker_document_type.py`):
- `movie` — video content
- `youtube` — YouTube video
- `link` — bookmark/reference link
- `webpage` — full webpage content
- `text_message` — plain text input
- `text` — generic text document

## Docker Setup

**Image:** Custom image built from `postgres:17-bookworm` with `postgresql-17-pgvector` package installed (see `infra/docker/Postgresql/Dockerfile`).

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

The backend accesses the database via `psycopg2` (no ORM). Key files:
- `backend/library/stalker_web_documents_db_postgresql.py` — query layer (list, search, vector similarity)
- `backend/library/stalker_web_document_db.py` — single document CRUD operations

Connection configured via environment variables: `POSTGRESQL_HOST`, `POSTGRESQL_DATABASE`, `POSTGRESQL_USER`, `POSTGRESQL_PASSWORD`, `POSTGRESQL_PORT`.

## Known Issues

- The `langauge` column in `websites_embeddings` has a typo (should be `language`). Kept for backward compatibility.
- The `embedding` column is fixed at 1536 dimensions, matching OpenAI's `text-embedding-ada-002`. Other models with different dimensions (e.g. Titan, Bielik) may require schema changes.
- The IVFFlat index on embeddings requires the table to have existing rows before it can be used effectively. For small datasets, consider switching to HNSW index type.
