# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Project Lenie is a personal AI assistant for collecting, managing, and searching data using LLMs. Named after the protagonist from Peter Watts' novel "Starfish," it helps users collect links/references, download and store webpage content, transcribe YouTube videos, and assess information reliability.

**Current version**: 0.3.14.0 | **Status**: Active development | **License**: [BSL 1.1](LICENSE) (converts to Apache 2.0 on 2030-03-12)

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

Pytest configuration lives in `backend/pyproject.toml` — run tests from `backend/` with `PYTHONPATH=.` (some tests resolve paths relative to cwd):

```bash
cd backend

# Unit tests (full suite needs the project venv, not uvx)
PYTHONPATH=. .venv/Scripts/python -m pytest tests/unit/ -q

# Integration tests (requires PostgreSQL + .env)
PYTHONPATH=. .venv/Scripts/python -m pytest tests/integration/ -q

# Single test file
PYTHONPATH=. .venv/Scripts/python -m pytest tests/unit/test_split_for_embedding.py -v
```

### Code Quality
```bash
ruff check backend/ # Linting (line-length=120)
make lint           # Run ruff linter (via Makefile)
make lint-fix       # Run ruff with auto-fix
make format         # Format code with ruff
make format-check   # Check formatting (for CI)
pre-commit run      # Pre-commit hooks: Gitleaks + TruffleHog on staged changes; a pre-push hook additionally scans unpushed commit history for secrets
make security-all   # Runs semgrep, pip-audit, bandit, safety and prints their output — tool failures are ignored (`-` prefix in Makefile), so it aggregates results but is NOT a pass/fail quality gate
```

## WSL Linux Environment (`backend/.venv_wsl`)

The developer works on Windows with a WSL (Ubuntu 24.04) environment for running Linux-specific scripts (imports, deploy scripts, shell scripts). Two separate venvs exist in `backend/`:

- **`.venv`** — Windows environment (default `uv sync` target when run from Windows)
- **`.venv_wsl`** — Linux/WSL environment

**When modifying Python dependencies** (adding/removing packages in `pyproject.toml`, adding path dependencies like `shared_python/`), you MUST also sync `.venv_wsl`:

```bash
# Sync .venv_wsl after dependency changes (path dep only)
wsl bash -c "export PATH=\"\$HOME/.local/bin:\$PATH\" && cd /mnt/c/Users/ziutus/git/_lenie-all/lenie-server-2025/backend && uv pip install -e ../shared_python/unified-config-loader/ --python .venv_wsl/bin/python"

# Or full sync from lock file — UV_PROJECT_ENVIRONMENT is REQUIRED
wsl bash -c "export PATH=\"\$HOME/.local/bin:\$PATH\" && cd /mnt/c/Users/ziutus/git/_lenie-all/lenie-server-2025/backend && UV_PROJECT_ENVIRONMENT=.venv_wsl uv sync"
```

**WARNING**: Never run plain `uv sync` (or `uv sync --python .venv_wsl/bin/python --active`) from WSL — both target the default `.venv` and will overwrite the Windows environment with a Linux one (this happened 2026-07-03). `--python` selects the interpreter, not the target venv; `--active` needs `VIRTUAL_ENV` set. Only `UV_PROJECT_ENVIRONMENT=.venv_wsl` reliably targets `.venv_wsl`.

**Checklist for dependency changes:**
1. Update `pyproject.toml` and run `uv lock`
2. Verify Windows tests pass (uvx pytest)
3. Sync `.venv_wsl` in WSL
4. Verify import works: `wsl bash -c "cd .../backend && .venv_wsl/bin/python -c 'import <new_package>'"`

See [`docs/development-guide.md`](docs/development-guide.md) for full WSL setup instructions.

## Architecture

### Backend (`backend/`)
Flask application (`server.py`) exposing REST API with 23 endpoints (see `docs/infrastructure-metrics.md` for full inventory). Python 3.11, dependencies managed via uv, Docker build with `python:3.11-slim`. All routes (except health checks) require `x-api-key` header.

Key subdirectories: `library/` (core logic & integrations), `database/` (PostgreSQL schema), `imports/` (bulk import scripts), `data/` (site cleanup rules), `tests/` (unit + integration), `test_code/` (experimental scripts). Each has its own `CLAUDE.md`.

See `backend/CLAUDE.md` for full details including endpoints, dependencies, Docker build, and batch processing scripts.

### Shared Python Package (`shared_python/unified-config-loader/`)
Reusable Python package providing a unified configuration loader with pluggable backends (env/vault/aws). Used by both `backend/` and `slack_bot/` as a path dependency. The package is published as `unified-config-loader` with import `from unified_config_loader import load_config`. Both consumers re-export from `unified_config_loader` for backward compatibility (`library.config_loader` and `src.config`).

See [`shared_python/unified-config-loader/README.md`](shared_python/unified-config-loader/README.md) for details.

### Shared Types (`shared/`)
Shared TypeScript type definitions used by both frontend applications. Contains domain types (`WebDocument`, `ApiType`, `SearchResult`, `ListItem`), constants (`DEFAULT_API_URLS`), and factory values (`emptyDocument`). No build step — Vite transpiles directly via esbuild. Both frontends reference it through `@lenie/shared` alias (tsconfig `paths` + Vite `resolve.alias`). See `docs/shared-types.md` for details.

### Frontend (`web_interface_react/`)
React 18 SPA (Vite) for document management and AI processing. Pages: document list with filtering, vector similarity search, chunk review (`/chunks/:id`), and per-type editors (link, webpage, youtube, movie) with AI tools (split for embedding, clean text). Formik for form state, axios for API calls, React Router v6. Single backend mode: Docker (Flask) — the AWS Serverless mode was removed entirely 2026-07-04 (Lambdas decommissioned 2026-07-02). Domain types imported from `shared/` via `@lenie/shared` alias.

See `web_interface_react/CLAUDE.md` for details.

### Browser Extension (`web_chrome_extension/`)
Chrome/Kiwi browser extension (Manifest v3) for capturing webpages and sending them to the backend. Auto-extracts page title, description, language, and full content (text + HTML). Supports content types: webpage, link, youtube, movie. Calls `POST /url_add` with `x-api-key` auth. No build step — load unpacked from folder.

See `web_chrome_extension/CLAUDE.md` for details.

### Landing Page (`web_landing_page/`)
Next.js 15 static export with React 19 + Tailwind 3.4 + TypeScript (exact versions: `web_landing_page/package.json`). Deployed at `www.lenie-ai.eu` via S3 + CloudFront. 25 static pages.

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
- CloudFormation templates for DynamoDB, Lambda, API Gateway
- Serverless Lambda functions

**Architecture overview**: AWS API Gateway serves as the managed, secure entry point — access is controlled via API keys, eliminating the need to maintain and patch internet-facing services. Incoming documents land in DynamoDB (metadata) and S3 (content); DynamoDB provides always-available storage, enabling synchronization between cloud (receiving data from mobile devices) and local environments via `imports/dynamodb_sync.py`. The SQS pipeline and AWS RDS were decommissioned 2026-07-02 (see [docs/aws-serverless-restoration.md](docs/aws-serverless-restoration.md)).

**Flask server vs Lambda split**: The Flask `server.py` is the unified backend used in Docker/K8s deployments. For AWS serverless, the same logic is split into two Lambda functions due to VPC networking constraints (no NAT Gateway to save costs):
- **`app-server-db`** - endpoints requiring PostgreSQL (runs inside VPC): `/website_list`, `/website_get`, `/website_save`, `/website_delete`, `/website_is_paid`, `/website_get_next_to_correct`, `/website_similar`, `/website_split_for_embedding`
- **`app-server-internet`** - endpoints requiring internet access (runs outside VPC): `/website_download_text_content`, `/ai_embedding_get`
- **`url-add`** - handles `/url_add` functionality via DynamoDB+S3 instead of direct DB write (source in `infra/aws/serverless/lambdas/url-add/`; the SQS send was removed 2026-07-02)

Some endpoints exist only in `server.py` (not in Lambda): `/url_add` (replaced by the DynamoDB flow), `/website_text_remove_not_needed`, health checks (`/healthz`, `/startup`, `/readiness`, `/liveness`), `/version`, `/metrics`.

See `infra/aws/serverless/CLAUDE.md` for detailed comparison and known differences.

### Frontend Deployment (AWS)

**Only the landing page** (`www.lenie-ai.eu`) is hosted on AWS (S3 + CloudFront). The `app.dev.lenie-ai.eu` and `app2.dev.lenie-ai.eu` hosting stacks were deleted 2026-07-02 — those frontends required the AWS document API (`app-server-db`), which was decommissioned; they now run only against the Docker/NAS backend (local dev or NAS deployment). Restoration: [docs/aws-serverless-restoration.md](docs/aws-serverless-restoration.md). See `docs/frontend-deployment.md` for landing page deployment details.

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

Configuration is managed by the **config_loader** module (`backend/library/config_loader.py`) with three backends: `env` (default), `vault` (HashiCorp Vault), `aws` (AWS SSM). See [`docs/security/secrets-management.md`](docs/security/secrets-management.md) for full architecture, setup instructions, and troubleshooting.

Bootstrap variables (always in `.env`, regardless of backend):
- `SECRETS_BACKEND` - Secret backend to use: `env`, `vault`, `aws`. Default: `env`
- `SECRETS_ENV` - Environment name for secret paths (`dev`, `prod`, `qa`). Default: `dev`
- `PROJECT_CODE` - Project code used in secret paths. Default: `lenie`
- `ENV_DATA` - Date of last configuration data update (e.g., `2025.10.02`), logged at startup
- `VAULT_ADDR`, `VAULT_TOKEN` - Required when `SECRETS_BACKEND=vault`
- `AWS_REGION` - Required when `SECRETS_BACKEND=aws`. Default: `eu-central-1`

All application variables (database, LLM, API keys, etc.) are defined in [`scripts/vars-classification.yaml`](scripts/vars-classification.yaml). To generate a backend-specific `.env` file: `python scripts/env_to_vault.py generate env-example --backend <env|vault|aws>`

## Database

PostgreSQL 18 with pgvector extension for vector similarity search. Schema defined in `backend/database/init/` (see `backend/database/CLAUDE.md` for full details).

Core tables:
- **`web_documents`** — documents with content, metadata, processing state, and multilingual fields
- **`websites_embeddings`** — vector embeddings (dimensionless column, per-model HNSW partial indexes) with cosine similarity search

The full model is much larger (chunk analysis runs/chunks/topic sections, NER entities/persons/exclusions, geocode and infrastructure caches, document references, reader progress/notes, users and API keys, import logs) — the authoritative inventory is [`backend/database/CLAUDE.md`](backend/database/CLAUDE.md); schema migrations live in `backend/alembic/`.

Document processing states: `URL_ADDED` → `DOCUMENT_INTO_DATABASE` → ... → `EMBEDDING_EXIST` (15 states total, see `backend/library/models/stalker_document_status.py`).

Access layer: SQLAlchemy 2.0 ORM (`backend/library/db/models.py`, `backend/library/db/engine.py`). Connection via `POSTGRESQL_HOST/DATABASE/USER/PASSWORD/PORT` env vars.

## File Export Convention

When saving text files (chat exports, notes, analysis results) during a conversation, **always save them to `.claude/exports/`** instead of the project root. Create the directory if it doesn't exist. This keeps the project root clean and the directory is already in `.gitignore`.

## Git Commit Authorship

When creating git commits, always use the `--author` flag to attribute the code to Claude Code:

```bash
git commit --author="Claude Code <noreply@anthropic.com>" -m "commit message"
```

This ensures the commit history correctly shows **Claude Code as the author** (who wrote the code) and the repository owner as the **committer** (who approved and committed it). Do NOT add the `Co-Authored-By` trailer when using `--author` — the authorship is already set.

## External Services

- **AI/LLM**: OpenAI, AWS Bedrock, Google Vertex AI, CloudFerro Bielik
- **Content extraction**: Beautiful Soup, Markdownify, Firecrawl, YouTube Transcript API
- **Speech-to-text**: AssemblyAI ($0.12/hour)
- **PDF processing**: AWS Textract, pypdf
- **Secrets**: HashiCorp Vault
