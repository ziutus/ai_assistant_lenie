# Backend — CLAUDE.md

Flask REST API backend for Project Lenie. Provides document management, AI/LLM operations, vector similarity search, and content processing endpoints.

## Directory Structure

```
backend/
├── server.py                              # Main Flask application (23 endpoints)
├── pyproject.toml                         # Dependencies, build config, tool settings
├── uv.lock                                # Frozen dependency lock file
├── Dockerfile                             # Multi-stage Docker build (Python 3.11-slim + uv)
├── .safety-project.ini                    # Safety vulnerability scanner config
├── README.md                              # Brief pointer to root CLAUDE.md
│
├── library/                               # Core business logic & external integrations
│   └── CLAUDE.md                          # ↳ Detailed docs
├── database/                              # PostgreSQL schema & initialization
│   └── CLAUDE.md                          # ↳ Detailed docs
├── imports/                               # CLI tools & import scripts (bypass REST API)
│   └── CLAUDE.md                          # ↳ Detailed docs
├── data/                                  # Site-specific cleanup rules & regex patterns
│   └── CLAUDE.md                          # ↳ Detailed docs
├── tests/                                 # Pytest suite (unit + integration)
│   └── CLAUDE.md                          # ↳ Detailed docs
├── test_code/                             # Experimental/prototype scripts
│   └── CLAUDE.md                          # ↳ Detailed docs
│
├── documents_pipeline.py   # Batch: download, transcribe, embed documents
├── documents_fix_missing_markdown.py # Batch: fix documents with missing markdown
├── document_md_decode.py              # Batch: markdown decoding & link processing
├── document_prepare_regexp_by_ai.py   # AI-driven regex pattern generation
│
└── tmp/                                   # Runtime temp data (sql_data/, youtube_to_text/)
```

## Main Application (`server.py`)

Flask + Flask-CORS application exposing 23 REST API endpoints. **Version**: 0.3.14.0.

### API Endpoints

| Category | Endpoints |
|----------|----------|
| **Document CRUD** | `/url_add`, `/website_list`, `/website_get`, `/website_save`, `/website_delete` |
| **AI Operations** | `/ai_get_embedding` (legacy `/website_similar` removed in stage 12 — `POST /search` is the only search endpoint) |
| **Content Processing** | `/website_download_text_content`, `/website_text_remove_not_needed`, `/website_split_for_embedding` (**deprecated** — the `\n\n\n`-separator split predates the chunk-analysis pipeline; embeddings are now generated from approved TEMAT chunks via `POST /analysis_run/<id>/generate_embeddings`; kept in the API for compatibility, removed from the frontend 2026-07-10) |
| **Entities (NER)** | `/website_entities` (GET: stored persons/places; POST: re-run NER + verify places + resolve persons; DELETE `/website_entities/<entity_id>`: remove a stored entity + its person link), `/persons` (GET: fuzzy registry search; POST `/persons/<id>/aliases`: manually add an alias/nickname), `/person_documents` (GET: all documents mentioning a person, each with `mention_count` from `document_entities`, sorted by it), GET `/document/<id>/entity_occurrences?text=` (per-chapter occurrence counts of an entity name — the person page's "occurrences in this book" drill-down), `/persons_review` (GET: manual_review queue; PATCH `/persons_review/<link_id>`: approve/reject/merge decision), PATCH `/document_persons/<link_id>` (same actions without the manual_review gate — editor path for undoing wrong matches), `/ner_exclusions` (GET list / POST add / DELETE `/ner_exclusions/<id>`: false-positive suppression dictionary applied at entity refresh), GET `/document/<id>/chapter/<pos>/entities` (entities + kraj-* countries filtered to one reader chapter via surface-variant matching — `library/chunk_review_routes.py`) — see `library/entity_service.py`, `library/person_registry.py` |
| **Timeline** | GET `/document/<id>/events` (stored dated events discussed in the document, sorted chronologically; extraction: `imports/extract_events.py`), GET `/document/<id>/time_periods` (historical periods the content is about, per reader chapter for books; classification: `imports/extract_time_periods.py`), GET `/document/<id>/tones` (emotional tone + language register per chapter; classification: `imports/extract_tones.py`) |
| **Metadata** | `/website_is_paid`, `/website_get_next_to_correct`, `/document_states`, `/tags` (GET: distinct tags with usage counts), `/sources` (GET: lookup-table rows joined with per-source document counts, `?active=1` filters to active — editor/extension pickers; POST: add; PATCH `/sources/<id>`: edit/rename/deactivate — documents reference the row by id (`discovery_source_id`, stage 11d), so a rename only edits the lookup row; DELETE `/sources/<id>`: only when count==0, otherwise 409). Unknown source names in write paths are auto-created by `Document.set_discovery_source()`; the HTTP wire format keeps the NAME under `source` |
| **Auth & identity** | `/whoami`, `/api_keys` (GET/POST), `/api_keys/<id>` (DELETE) — see `library/api_key_routes.py` |
| **Health & Info** | `/` (root), `/healthz`, `/startup`, `/readiness`, `/liveness`, `/version`, `/metrics` |

All routes (except health checks) require an `x-api-key` header. Keys live in the `api_keys` table (`library/auth.py`: SHA-256 hash lookup with an in-process TTL cache; `kind=user` keys carry the reader identity used by `reader_routes.py`, `kind=service` keys have full access but get 403 on reader endpoints). There is no shared/legacy key fallback — every client (frontend, Chrome extension, slack-bot) authenticates with its own key. Keys are managed via `imports/api_key_admin.py` (CLI) or the `/api_keys` endpoints (service keys only); the plaintext (`lk_usr_*`/`lk_svc_*`) is shown once at creation.

### Storage

- **Primary**: PostgreSQL via `DocumentRepository`
- **Files**: S3 (boto3) with local fallback to `/app/data/`

## Dependencies (`pyproject.toml`)

Managed via **uv** package manager. Python >= 3.11, build system: hatchling.

### Dependency Groups

| Group | Purpose | Install Command |
|-------|---------|----------------|
| **base** (37 packages) | Core: Flask, psycopg2, openai, boto3, beautifulsoup4, etc. | `uv sync` |
| **docker** extra | Curated subset for Docker + aws-xray-sdk | `uv sync --extra docker` |
| **markdown** extra | MarkItDown, html2markdown, html2text | `uv sync --extra markdown` |
| **all** extra | Everything combined | `uv sync --all-extras` |
| **dev** group | pytest, pre-commit, ruff | Included by default |

### Key Dependencies

- **Web**: flask, flask-cors, requests
- **Database**: sqlalchemy, psycopg2-binary (as SQLAlchemy driver), neo4j
- **AI/LLM**: openai, boto3 (Bedrock), google-api-python-client
- **Content**: beautifulsoup4, firecrawl-py, markdownify, youtube-transcript-api
- **Speech**: assemblyai, pypdf
- **Monitoring**: langfuse, aws-xray-sdk (Docker)
- **Secrets**: hvac (HashiCorp Vault)
- **Text**: dateparser, chardet, unidecode

## Docker Build (`Dockerfile`)

```
Base: python:3.11-slim
Package manager: uv (from ghcr.io/astral-sh/uv)
Install: uv sync --frozen --extra docker --no-dev --no-install-project
User: lenie-ai-client (UID 1000)
Port: 5000
Entry: python server.py
```

Copies only `library/` and `server.py` into the image (not test files or batch scripts).

## Batch Processing Scripts

Standalone scripts for bulk document operations. Run manually, not part of the Flask API.

| Script | Purpose | DB Access |
|--------|---------|-----------|
| `documents_pipeline.py` | Full pipeline: download webpage content, transcribe YouTube videos (AssemblyAI/AWS Transcribe), detect language, generate embeddings, store to PostgreSQL + S3 | **Yes** |
| `documents_fix_missing_markdown.py` | Fix documents that are missing markdown content | **Yes** |
| `document_md_decode.py` | Markdown decoding, link extraction and correction, prepare content for embedding | **Yes** |
| `document_prepare_regexp_by_ai.py` | Generate site-specific regex patterns for article extraction using LLM | **Yes** |

Ad-hoc single-item tools and bulk import scripts live in [`imports/`](imports/CLAUDE.md): `youtube_add.py`, `youtube_batch_analyze.py`, `dynamodb_sync.py`, `feed_monitor.py`, `article_browser.py`, `freedom_house_import.py`, `control_questions.py`, `migrate_data_to_cache.py`.

### Database connectivity requirement

Scripts marked **Yes** use `DocumentRepository` with SQLAlchemy ORM session (`get_session()` from `library.db.engine`). The same applies to all scripts in `imports/`.

- **Local/Docker**: Connect to local PostgreSQL (`lenie-ai-db` on port 5433) — works out of the box.
- **AWS RDS**: decommissioned 2026-07-02 (unused since ~2026-04; document sync now goes DynamoDB → S3 → local Postgres via `imports/dynamodb_sync.py`). The OpenVPN EC2 instance that provided access to it has also been terminated.

## Running

```bash
# Direct execution (requires .env)
cd backend
python server.py

# Docker (via root Makefile)
make build && make dev

# Dependencies
uv sync                    # base
uv sync --all-extras       # all
uv lock                    # update lock file after pyproject.toml changes
```

## Testing

```bash
pytest backend/tests/unit/          # Unit tests (no dependencies)
pytest backend/tests/integration/   # Integration tests (requires PostgreSQL)
pytest                                               # Full suite
```

## Code Quality

```bash
ruff check backend/    # Linting (line-length=120)
pre-commit run         # Pre-commit hooks (includes TruffleHog secret detection)
```

Tool config in `pyproject.toml`: ruff line-length=120, excludes `.git`, `__pycache__`, `venv`, `node_modules`.

## Key Field Semantics: `source` vs `byline`

These two fields on `documents` serve distinct purposes:

- **`source`** (wire format; stored as `discovery_source_id` FK → `discovery_sources` since stage 11d) — How the user *discovered* the content: `"own"` (found it themselves), `"unknow.news"` (from unknow.news newsletter), `"friend"` (personal recommendation), etc. This enables evaluating recommendation source quality over time (e.g. "links from source X tend to be low quality").
- **`byline`** (renamed from `author` in stage 11b of the search rebuild) — Who *created* the content: YouTube channel name, article author, blog name, etc. This is content metadata, not a discovery channel. The comma-separated display cache; structured author links live in `document_persons` (role=`author`).

Example: A YouTube video by "Good Times Bad Times Polska" found via unknow.news newsletter → `source="unknow.news"`, `byline="Good Times Bad Times Polska"`.

## Subdirectory Documentation

Each subdirectory has its own `CLAUDE.md` with detailed documentation:

| Directory | CLAUDE.md | Covers |
|-----------|-----------|--------|
| `library/` | [library/CLAUDE.md](library/CLAUDE.md) | Domain models, LLM abstraction, embedding generation, text processing, external API integrations |
| `database/` | [database/CLAUDE.md](database/CLAUDE.md) | PostgreSQL schema, pgvector setup, `documents` and `document_embeddings` tables, 15 processing states |
| `imports/` | [imports/CLAUDE.md](imports/CLAUDE.md) | CLI tools & import scripts: `youtube_add.py`, `youtube_batch_analyze.py`, `dynamodb_sync.py`, `feed_monitor.py`, `article_browser.py`, `freedom_house_import.py`, `control_questions.py` |
| `data/` | [data/CLAUDE.md](data/CLAUDE.md) | Site-specific cleanup rules (`site_rules.json`), regex patterns for Polish news portals |
| `tests/` | [tests/CLAUDE.md](tests/CLAUDE.md) | Unit tests (41 files: ORM, services, Flask endpoints, batch/import scripts, article & markdown processing) and integration tests (6 files: REST API endpoints, FK constraints) |
| `test_code/` | [test_code/CLAUDE.md](test_code/CLAUDE.md) | Experimental scripts: RAG pipeline, LLM provider testing, Bielik text processing, cloud migrations |
