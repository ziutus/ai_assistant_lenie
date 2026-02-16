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
# All tests with HTML report
pytest --self-contained-html --html=pytest-results/

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
pre-commit run      # Run pre-commit hooks (includes TruffleHog secret detection)
```

## Architecture

### Backend (`backend/`)
Flask application (`server.py`) exposing REST API with 18 endpoints. Python 3.11, dependencies managed via uv, Docker build with `python:3.11-slim`. All routes (except health checks) require `x-api-key` header.

Key subdirectories: `library/` (core logic & integrations), `database/` (PostgreSQL schema), `imports/` (bulk import scripts), `data/` (site cleanup rules), `tests/` (unit + integration), `test_code/` (experimental scripts). Each has its own `CLAUDE.md`.

See `backend/CLAUDE.md` for full details including endpoints, dependencies, Docker build, and batch processing scripts.

### Frontend (`web_interface_react/`)
React 18 SPA (Create React App) for document management and AI processing. 7 pages: document list with filtering, vector similarity search, and per-type editors (link, webpage, youtube, movie) with AI tools (translate, split for embedding, clean text). Formik for form state, axios for API calls, React Router v6. Supports two backend modes: AWS Serverless (Lambda) and Docker (Flask). Includes infrastructure controls (start/stop RDS, VPN, SQS queue status).

See `web_interface_react/CLAUDE.md` for details.

### Add URL App (`web_add_url_react/`)
Minimal single-page React app for submitting new URLs via `POST /url_add`. No routing, no document browsing — just a form with URL, type, source, language, note, and text fields. API key can be pre-populated from `?apikey=` query parameter. Docker build serves static files via nginx:alpine on port 80.

See `web_add_url_react/CLAUDE.md` for details.

### Browser Extension (`web_chrome_extension/`)
Chrome/Kiwi browser extension (Manifest v3) for capturing webpages and sending them to the backend. Auto-extracts page title, description, language, and full content (text + HTML). Supports content types: webpage, link, youtube, movie. Calls `POST /url_add` with `x-api-key` auth. No build step — load unpacked from folder.

See `web_chrome_extension/CLAUDE.md` for details.

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
- **`app-server-internet`** - endpoints requiring internet access (runs outside VPC): `/translate`, `/website_download_text_content`, `/ai_embedding_get`
- **`sqs-weblink-put-into`** - handles `/url_add` functionality via SQS+DynamoDB+S3 instead of direct DB write

Some endpoints exist only in `server.py` (not in Lambda): `/url_add` (replaced by SQS flow), `/website_text_remove_not_needed`, health checks (`/healthz`, `/startup`, `/readiness`, `/liveness`), `/version`, `/metrics`.
The `/translate` endpoint exists only in the Lambda Internet version.

See `infra/aws/serverless/CLAUDE.md` for detailed comparison and known differences.

### CI/CD
- CircleCI (`.circleci/config.yml`) - EC2-based testing
- GitLab CI (`.gitlab-ci.yml`) - Qodana security scanning
- Jenkins (`Jenkinsfile`) - AWS EC2 orchestration, Semgrep security

## Environment Variables

Key variables (see `.env_example` for full list):
- `ENV_DATA` - Environment identifier
- `POSTGRESQL_HOST/DATABASE/USER/PASSWORD/PORT` - Database connection
- `LLM_PROVIDER` - LLM backend (openai, bedrock, vertex)
- `OPENAI_API_KEY`, `OPENAI_ORGANIZATION` - OpenAI credentials
- `EMBEDDING_MODEL` - Model for vector embeddings
- `STALKER_API_KEY` - API authentication key
- `PORT` - Server port

## Database

PostgreSQL 17 with pgvector extension for vector similarity search. Schema defined in `backend/database/init/` (see `backend/database/CLAUDE.md` for full details).

Two tables:
- **`web_documents`** (28 columns) — documents with content, metadata, processing state, and multilingual fields
- **`websites_embeddings`** — vector embeddings (1536 dimensions) with IVFFlat cosine similarity index

Document processing states: `URL_ADDED` → `DOCUMENT_INTO_DATABASE` → ... → `EMBEDDING_EXIST` (15 states total, see `backend/library/models/stalker_document_status.py`).

Access layer: raw `psycopg2` queries (no ORM). Connection via `POSTGRESQL_HOST/DATABASE/USER/PASSWORD/PORT` env vars.

## External Services

- **AI/LLM**: OpenAI, AWS Bedrock, Google Vertex AI, CloudFerro Bielik
- **Content extraction**: Beautiful Soup, Markdownify, Firecrawl, YouTube Transcript API
- **Speech-to-text**: AssemblyAI ($0.12/hour)
- **PDF processing**: AWS Textract, pypdf
- **Secrets**: HashiCorp Vault
