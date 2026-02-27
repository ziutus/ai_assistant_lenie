# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Project Lenie is a personal AI assistant for collecting, managing, and searching data using LLMs. Named after the protagonist from Peter Watts' novel "Starfish," it helps users collect links/references, download and store webpage content, transcribe YouTube videos, and assess information reliability.

**Current version**: 0.3.13.0 | **Status**: Active development

## Common Commands

### Development (Docker Compose)
```bash
make build          # Build docker containers
make dev            # Run backend and frontend (docker compose up -d)
make down           # Stop and remove containers
```

### Running the Backend Directly
```bash
cd backend
python server.py    # Requires .env file with all environment variables
```

### Dependencies (uv)
```bash
# Install base dependencies
make install         # or: cd backend && uv sync

# Install all dependencies (including optional)
make install-all     # or: cd backend && uv sync --all-extras

# Install specific extras
make install-docker  # or: cd backend && uv sync --extra docker
make install-markdown # or: cd backend && uv sync --extra markdown

# Update lock file after changing pyproject.toml
make lock            # or: cd backend && uv lock
```

### Testing
```bash
# All tests
pytest

# Unit tests only
pytest backend/tests/unit/

# Integration tests (requires database)
pytest backend/tests/integration/

# Single test file
pytest backend/tests/unit/test_split_for_embedding.py
```

### Code Quality
```bash
ruff check backend/ # Linting (line-length=120)
make lint           # Run ruff linter (via Makefile)
make lint-fix       # Run ruff with auto-fix
make format         # Format code with ruff
make format-check   # Check formatting (for CI)
pre-commit run      # Run pre-commit hooks (includes TruffleHog secret detection)
make security-all   # Run all security checks (semgrep, pip-audit, bandit, safety)
```

## Architecture

### Backend (`backend/`)
Flask application (`server.py`) exposing REST API with 19 endpoints (see `docs/infrastructure-metrics.md` for full inventory). Python 3.11, dependencies managed via uv, Docker build with `python:3.11-slim`. All routes (except health checks) require `x-api-key` header.

Key subdirectories: `library/` (core logic & integrations), `database/` (PostgreSQL schema), `imports/` (bulk import scripts), `data/` (site cleanup rules), `tests/` (unit + integration), `test_code/` (experimental scripts). Each has its own `CLAUDE.md`.

See `backend/CLAUDE.md` for full details including endpoints, dependencies, Docker build, and batch processing scripts.

### Shared Types (`shared/`)
Shared TypeScript type definitions used by both frontend applications. Contains domain types (`WebDocument`, `ApiType`, `SearchResult`, `ListItem`), constants (`DEFAULT_API_URLS`), and factory values (`emptyDocument`). No build step — Vite transpiles directly via esbuild. Both frontends reference it through `@lenie/shared` alias (tsconfig `paths` + Vite `resolve.alias`). See `docs/shared-types.md` for details.

### Frontend (`web_interface_react/`)
React 18 SPA (Vite) for document management and AI processing. 7 pages: document list with filtering, vector similarity search, and per-type editors (link, webpage, youtube, movie) with AI tools (split for embedding, clean text). Formik for form state, axios for API calls, React Router v6. Supports two backend modes: AWS Serverless (Lambda) and Docker (Flask). Includes infrastructure controls (start/stop RDS, VPN, SQS queue status). Domain types imported from `shared/` via `@lenie/shared` alias.

See `web_interface_react/CLAUDE.md` for details.

### Browser Extension (`web_chrome_extension/`)
Chrome/Kiwi browser extension (Manifest v3) for capturing webpages and sending them to the backend. Auto-extracts page title, description, language, and full content (text + HTML). Supports content types: webpage, link, youtube, movie. Calls `POST /url_add` with `x-api-key` auth. No build step — load unpacked from folder.

See `web_chrome_extension/CLAUDE.md` for details.

### Landing Page (`web_landing_page/`)
Next.js 14.2 static export with React 18 + Tailwind 3.4 + TypeScript. Deployed at `www.lenie-ai.eu` via S3 + CloudFront. 25 static pages.

### Admin Panel (`web_interface_app2/`)
Vite 6 + React 18 + TypeScript admin panel at `app2.dev.lenie-ai.eu`. Uses React Bootstrap, React Router v6. Domain types imported from `shared/` via `@lenie/shared` alias.

See `web_interface_app2/CLAUDE.md` for details.

## Infrastructure

### Docker Stack (`infra/docker/compose.yaml`)
- `lenie-ai-server` (port 5000) - Flask backend
- `lenie-ai-db` (port 5433) - PostgreSQL with pgvector extension
- `lenie-ai-frontend` (port 3000) - React frontend

### Kubernetes (`infra/kubernetes/kustomize/`)
Kustomize-based deployment with base configurations and GKE dev overlay.

### AWS (`infra/aws/`)
- CloudFormation templates for DynamoDB, RDS, SQS, Lambda, API Gateway
- Serverless Lambda functions

**Architecture overview**: AWS API Gateway serves as the managed, secure entry point — access is controlled via API keys, eliminating the need to maintain and patch internet-facing services. Incoming documents flow through SQS for asynchronous processing (the database runs only when needed to optimize costs). DynamoDB provides always-available metadata storage, enabling synchronization between cloud (receiving data from mobile devices) and local environments.

**Flask server vs Lambda split**: The Flask `server.py` is the unified backend used in Docker/K8s deployments. For AWS serverless, the same logic is split into two Lambda functions due to VPC networking constraints (no NAT Gateway to save costs):
- **`app-server-db`** - endpoints requiring PostgreSQL (runs inside VPC): `/website_list`, `/website_get`, `/website_save`, `/website_delete`, `/website_is_paid`, `/website_get_next_to_correct`, `/website_similar`, `/website_split_for_embedding`
- **`app-server-internet`** - endpoints requiring internet access (runs outside VPC): `/website_download_text_content`, `/ai_embedding_get`
- **`sqs-weblink-put-into`** - handles `/url_add` functionality via SQS+DynamoDB+S3 instead of direct DB write

Some endpoints exist only in `server.py` (not in Lambda): `/url_add` (replaced by SQS flow), `/website_text_remove_not_needed`, health checks (`/healthz`, `/startup`, `/readiness`, `/liveness`), `/version`, `/metrics`.

See `infra/aws/serverless/CLAUDE.md` for detailed comparison and known differences.

### Frontend Deployment (AWS)

All three frontends are deployed to S3 + CloudFront. Deploy scripts resolve bucket names and distribution IDs from SSM Parameter Store (exported by CloudFormation). See `docs/frontend-deployment.md` for full details.

```bash
# React app (app.dev.lenie-ai.eu)
cd web_interface_react && ./deploy.sh

# Admin panel (app2.dev.lenie-ai.eu)
cd web_interface_app2 && ./deploy.sh

# Common options
./deploy.sh --skip-build         # Deploy existing build/ only
./deploy.sh --skip-invalidation  # Skip CloudFront cache invalidation
```

### CI/CD
**Currently inactive** — all deployments are manual from the developer's machine. Configuration files from previous experimental setups remain in the repository:
- CircleCI (`.circleci/config.yml`), GitLab CI (`.gitlab-ci.yml`), Jenkins (`Jenkinsfile`)

Restoration tracked in backlog: B-70 (prerequisites), B-71–B-74 (per-tool pipelines). See `docs/technology-choices.md` for details.

## Security — Secrets Handling

**NEVER commit files containing real secrets** (API keys, passwords, tokens, credentials) to the repository. This is a hard rule — no exceptions.

- Always create `.example` files with placeholders (e.g., `nas.env.example` with `<your-api-key>`) and commit those instead
- Add files with real secrets to `.gitignore` BEFORE creating them
- When creating new env/config files: first add the filename to `.gitignore`, then create the `.example` template, then create the real file locally
- Files that must never be committed: `.env`, `nas.env`, `credentials.json`, `token.json`, any file containing API keys or passwords
- If in doubt whether a file contains secrets, do NOT stage or commit it — ask first

## Environment Variables

Key variables (see `.env_example` for full list):
- `SECRETS_BACKEND` - Secret backend to use: `env` (default, reads `.env`), `vault` (HashiCorp Vault), `aws` (SSM Parameter Store)
- `SECRETS_ENV` - Environment name for secret paths (`dev`, `prod`, `qa`). Falls back to `VAULT_ENV` if not set. Default: `dev`
- `PROJECT_CODE` - Project code used in secret paths. Default: `lenie`
- `ENV_DATA` - Date of last configuration data update (e.g., `2025.10.02`), logged at startup to verify the application loaded fresh config
- `POSTGRESQL_HOST/DATABASE/USER/PASSWORD/PORT` - Database connection
- `POSTGRESQL_SSLMODE` - SSL mode for PostgreSQL (set to `require` for AWS RDS)
- `LLM_PROVIDER` - LLM backend (openai, bedrock, vertex)
- `OPENAI_API_KEY`, `OPENAI_ORGANIZATION` - OpenAI credentials
- `EMBEDDING_MODEL` - Model for vector embeddings
- `STALKER_API_KEY` - API authentication key
- `PORT` - Server port

## Database

PostgreSQL 18 with pgvector extension for vector similarity search (RDS: 18.1, Docker/NAS: 17 — pending upgrade via B-69). Schema defined in `backend/database/init/` (see `backend/database/CLAUDE.md` for full details).

Two tables:
- **`web_documents`** (28 columns) — documents with content, metadata, processing state, and multilingual fields
- **`websites_embeddings`** — vector embeddings (1536 dimensions) with IVFFlat cosine similarity index

Document processing states: `URL_ADDED` → `DOCUMENT_INTO_DATABASE` → ... → `EMBEDDING_EXIST` (15 states total, see `backend/library/models/stalker_document_status.py`).

Access layer: raw `psycopg2` queries (no ORM). Connection via `POSTGRESQL_HOST/DATABASE/USER/PASSWORD/PORT` env vars.

## File Export Convention

When saving text files (chat exports, notes, analysis results) during a conversation, **always save them to `.claude/exports/`** instead of the project root. Create the directory if it doesn't exist. This keeps the project root clean and the directory is already in `.gitignore`.

## External Services

- **AI/LLM**: OpenAI, AWS Bedrock, Google Vertex AI, CloudFerro Bielik
- **Content extraction**: Beautiful Soup, Markdownify, Firecrawl, YouTube Transcript API
- **Speech-to-text**: AssemblyAI ($0.12/hour)
- **PDF processing**: AWS Textract, pypdf
- **Secrets**: HashiCorp Vault
