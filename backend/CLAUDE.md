# Backend — CLAUDE.md

Flask REST API backend for Project Lenie. Provides document management, AI/LLM operations, vector similarity search, and content processing endpoints.

## Directory Structure

```
backend/
├── server.py                              # Main Flask application (19 endpoints)
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
├── imports/                               # Bulk data import scripts
│   └── CLAUDE.md                          # ↳ Detailed docs
├── data/                                  # Site-specific cleanup rules & regex patterns
│   └── CLAUDE.md                          # ↳ Detailed docs
├── tests/                                 # Pytest suite (unit + integration)
│   └── CLAUDE.md                          # ↳ Detailed docs
├── test_code/                             # Experimental/prototype scripts
│   └── CLAUDE.md                          # ↳ Detailed docs
│
├── markdown_to_embedding.py              # Batch: markdown files → embeddings
├── web_documents_do_the_needful_new.py   # Batch: download, transcribe, embed documents
├── webdocument_md_decode.py              # Batch: markdown decoding & link processing
├── webdocument_prepare_regexp_by_ai.py   # AI-driven regex pattern generation
│
└── tmp/                                   # Runtime temp data (sql_data/, youtube_to_text/)
```

## Main Application (`server.py`)

Flask + Flask-CORS application exposing 19 REST API endpoints. **Version**: 0.3.13.0.

### API Endpoints

| Category | Endpoints |
|----------|----------|
| **Document CRUD** | `/url_add`, `/website_list`, `/website_get`, `/website_save`, `/website_delete` |
| **AI Operations** | `/ai_get_embedding`, `/website_similar` |
| **Content Processing** | `/website_download_text_content`, `/website_text_remove_not_needed`, `/website_split_for_embedding` |
| **Metadata** | `/website_is_paid`, `/website_get_next_to_correct` |
| **Health & Info** | `/` (root), `/healthz`, `/startup`, `/readiness`, `/liveness`, `/version`, `/metrics` |

All routes (except health checks) require `x-api-key` header validated against `STALKER_API_KEY` env var.

### Storage

- **Primary**: PostgreSQL via `WebsitesDBPostgreSQL`
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
| **dev** group | pytest, pytest-html, pre-commit, ruff | Included by default |

### Key Dependencies

- **Web**: flask, flask-cors, requests
- **Database**: psycopg2-binary, neo4j
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
| `web_documents_do_the_needful_new.py` | Full pipeline: download webpage content, transcribe YouTube videos (AssemblyAI/AWS Transcribe), detect language, generate embeddings, store to PostgreSQL + S3 | **Yes** |
| `webdocument_md_decode.py` | Markdown decoding, link extraction and correction, prepare content for embedding | **Yes** |
| `webdocument_prepare_regexp_by_ai.py` | Generate site-specific regex patterns for article extraction using LLM | **Yes** |
| `markdown_to_embedding.py` | Convert markdown files from `tmp/markdown_output/` into embeddings. Supports manual corrections via `{id}_manual.md` files | No |

### Database connectivity requirement

Scripts marked **Yes** use `WebsitesDBPostgreSQL` (direct `psycopg2` connection). The same applies to `imports/unknown_news_import.py`.

- **Local/Docker**: Connect to local PostgreSQL (`lenie-ai-db` on port 5433) — works out of the box.
- **AWS RDS**: The database runs inside a private VPC and is not publicly accessible. To connect from a local machine, start the OpenVPN EC2 instance first:
  ```bash
  make aws-start-openvpn   # Start OpenVPN EC2 and update Route53 DNS
  ```
  Then connect to OpenVPN before running the scripts. The `.env` file must contain the RDS endpoint as `POSTGRESQL_HOST`.

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
pytest --self-contained-html --html=pytest-results/  # Full suite with report
```

## Code Quality

```bash
ruff check backend/    # Linting (line-length=120)
pre-commit run         # Pre-commit hooks (includes TruffleHog secret detection)
```

Tool config in `pyproject.toml`: ruff line-length=120, excludes `.git`, `__pycache__`, `venv`, `node_modules`.

## Subdirectory Documentation

Each subdirectory has its own `CLAUDE.md` with detailed documentation:

| Directory | CLAUDE.md | Covers |
|-----------|-----------|--------|
| `library/` | [library/CLAUDE.md](library/CLAUDE.md) | Domain models, LLM abstraction, embedding generation, text processing, external API integrations |
| `database/` | [database/CLAUDE.md](database/CLAUDE.md) | PostgreSQL schema, pgvector setup, `web_documents` and `websites_embeddings` tables, 15 processing states |
| `imports/` | [imports/CLAUDE.md](imports/CLAUDE.md) | Bulk import scripts (unknow.news), direct DB access pattern |
| `data/` | [data/CLAUDE.md](data/CLAUDE.md) | Site-specific cleanup rules (`site_rules.json`), regex patterns for Polish news portals |
| `tests/` | [tests/CLAUDE.md](tests/CLAUDE.md) | Unit tests (9 files: markdown, text, paywall) and integration tests (5 files: REST API endpoints) |
| `test_code/` | [test_code/CLAUDE.md](test_code/CLAUDE.md) | Experimental scripts: RAG pipeline, LLM provider testing, Bielik text processing, cloud migrations |
