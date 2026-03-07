# Technology Choices & Rationale

> Living document describing the tools and technologies used in Project Lenie, with rationale for each choice.
>
> For deep architectural decisions with full context/consequences analysis, see [Architecture Decisions (ADR)](./architecture-decisions.md).

## Language Runtimes

### Python 3.11

- **Used in:** Backend API, Lambda functions, batch scripts, IaC tooling
- **Why 3.11 (not 3.12+):** AWS Lambda layers and runtime were built on Python 3.11. Upgrading requires rebuilding all Lambda layers, updating CloudFormation templates, and re-testing the serverless stack.
- **Why Python:** Primary language of the project owner; rich ecosystem for AI/LLM, web scraping, and AWS integrations.

**Upgrade plan ([B-68](backlog-reference.md)):** Migrate to Python 3.12 or 3.13. Python 3.11 EOL: October 2027. The upgrade is straightforward thanks to the SSM parameter `/${ProjectCode}/${Environment}/python/lambda-runtime-version` — update one parameter, rebuild Lambda layer, update Powertools layer ARN variant, update Docker base image (`python:3.11-slim` → `3.12-slim`), verify dependency compatibility. No blockers — can start anytime.

### Node.js

- **Used in:** Frontend build (Vite/React), landing page (Next.js)
- **Versions:** Docker builds: **24 LTS** (`web_interface_react/Dockerfile`, `web_interface_app2/Dockerfile`). Local developer requirement: **>= 18** (outdated — should be >= 20).
- **Why:** Standard runtime for React tooling. No custom Node.js backend code — used only for build and dev server.

**Upgrade plan ([B-75](backlog-reference.md)):** Standardize on Node.js 24 LTS across all environments. Docker images already use `node:24`. Remaining work: update `docs/development-guide.md` prerequisite (>= 18 → >= 22), verify `web_landing_page/` builds on Node.js 24, update any CI configs. Node.js 18 is already EOL (Apr 2025), Node.js 20 EOL Apr 2026.

## Package Managers

### uv (Python)

- **Used in:** Dependency management (`pyproject.toml` + `uv.lock`), Docker builds, Makefile targets
- **Why not pip/poetry:**
  - 10-100x faster than pip for dependency resolution and installation
  - Single tool replaces pip + pip-tools + virtualenv
  - Lock file (`uv.lock`) ensures reproducible builds
  - Built-in `uvx` runner for one-off tool execution (semgrep, bandit, etc.) without polluting the project venv
  - Excellent Docker integration (`--frozen` flag for deterministic builds)
- **Config:** `backend/pyproject.toml` with optional dependency groups (`docker`, `markdown`, `vault`, `all`)

### npm (JavaScript)

- **Used in:** Frontend dependencies (`web_interface_react/`, `web_interface_app2/`, `web_landing_page/`)
- **Why not yarn/pnpm:** Standard choice, no specific need for alternatives in this project.

## Backend Framework

### Flask

- **Used in:** `backend/server.py` — 19 REST API endpoints
- **Why Flask (not FastAPI/Django):**
  - Lightweight — minimal overhead for a REST API that delegates to library functions
  - Familiar to the project owner
  - Easy to split into Lambda handlers — Flask routes map 1:1 to Lambda event handlers
  - No need for Django's ORM, admin panel, or middleware ecosystem
  - No need for FastAPI's async — all operations are synchronous (DB queries, HTTP calls to LLM APIs)
- **Extensions:** flask-cors (CORS for browser clients)

## Database

### PostgreSQL 18 + pgvector

- **Used in:** Document storage, vector similarity search
- **Versions:** AWS RDS: **18.1**. Docker/NAS: **18.3** (upgraded Mar 2026, [B-69](backlog-reference.md) DONE). pgvector: **0.8.2**.
- **Why PostgreSQL:**
  - Mature, reliable RDBMS with excellent tooling
  - pgvector extension enables vector similarity search (cosine distance with HNSW partial indexes) in the same database as document metadata — no separate vector DB needed
  - AWS RDS support for managed hosting
  - Dimensionless `vector` column supports multiple embedding models with different dimensions (1024–4096)
- **Why not a dedicated vector DB (Pinecone, Weaviate, Qdrant):** Single-database simplicity. The dataset size (~thousands of documents) doesn't require a specialized vector store. pgvector performs well at this scale.
- **Embedding architecture:** See [docs/embeddings.md](./embeddings.md) for supported models, indexing strategy, and multi-model design.

### psycopg2 (raw SQL, no ORM)

- **Used in:** All database access (`backend/library/stalker_web_document_db.py`, `backend/library/stalker_web_documents_db_postgresql.py`)
- **Why:** See [ADR-004](./architecture-decisions.md#adr-004-raw-psycopg2-instead-of-orm). Full control over pgvector-specific queries (cosine similarity search), simpler dependency tree, no ORM abstraction overhead.
- **Trade-off:** Manual SQL construction, no migration framework.
- **Status: maintenance-only upstream.** psycopg2 is no longer actively developed — new features go into psycopg3 (psycopg).

**Upgrade plan:** Migrate to **psycopg3** (`psycopg`). Key benefits:
- **Server-side parameter binding** — eliminates SQL f-string injection risk ([B-91](backlog-reference.md))
- **Native async support** (`AsyncConnection`) — useful if Flask is replaced with an async framework
- **Built-in connection pooling** (`ConnectionPool`)
- **Better pgvector integration** with `pgvector-python` library
- **3x faster** for large result sets (~500k rows/s vs ~150k rows/s)
- **Breaking change:** `with conn` closes the connection (not just the transaction) — requires code review

**Evolution plan ([B-50](backlog-reference.md)):** The API response layer will migrate from raw dicts to **Pydantic v2 models** ([api-type-sync-strategy.md](./api-type-sync-strategy.md)). psycopg2 SQL queries remain — Pydantic replaces only the serialization layer (custom `.dict()` methods → Pydantic `BaseModel`), enabling automatic OpenAPI schema generation and TypeScript type generation. This is not an ORM migration — database access stays raw SQL.

### DynamoDB

- **Used in:** Cloud-local synchronization buffer for incoming documents
- **Why:** See [ADR-003](./architecture-decisions.md#adr-003-dynamodb-as-cloud-local-synchronization-buffer). Always-available (PAY_PER_REQUEST), buffers documents when RDS is stopped for cost savings.

## AI / LLM

### Multi-provider abstraction

- **Providers:** OpenAI (GPT-4o), AWS Bedrock (Titan, Nova), Google Vertex AI (Gemini), CloudFerro (Bielik)
- **Used in:** `backend/library/ai.py` — LLM calls; `backend/library/embedding.py` — vector embeddings
- **Why multi-provider:** No vendor lock-in. Ability to compare quality/cost across providers. Polish-language support (Bielik) not available from all providers.
- **Embedding models:** OpenAI `text-embedding-ada-002`, AWS Titan Embed v2, BAAI/bge-multilingual-gemma2 (Polish-native). See [ADR-001](./architecture-decisions.md#adr-001-remove-translate-endpoint-and-use-native-language-embeddings) for the native-language embedding decision.

### openai (Python SDK)

- **Used in:** OpenAI API calls (chat completions, embeddings)
- **Why:** Official SDK, also used as the client for OpenAI-compatible APIs.

## Content Processing

### BeautifulSoup4

- **Used in:** HTML parsing, webpage content extraction, text cleanup
- **Why:** De-facto standard for Python HTML parsing. Tolerant of malformed HTML (common in scraped web pages).

### Markdownify

- **Used in:** HTML-to-Markdown conversion for cleaner text storage
- **Why:** Lightweight, produces clean Markdown from HTML. Used in the content processing pipeline.

### Firecrawl

- **Used in:** Advanced webpage content extraction (alternative to BeautifulSoup for complex sites)
- **Why:** Handles JavaScript-rendered content, provides cleaner extraction for modern SPAs.

### pytubefix

- **Used in:** YouTube video metadata extraction, video download
- **Why:** Maintained fork of `pytube` (abandoned). Cannot run in Lambda due to `nodejs-wheel-binaries` dependency (~60 MB). See [ADR-007](./architecture-decisions.md#adr-007-pytubefix-excluded-from-lambda--serverless-youtube-processing-requires-alternative-compute).

**Upgrade plan ([B-67](backlog-reference.md)):** Enable in serverless path via Lambda container image (10 GB limit) or ECS Fargate task. Architecture decision pending.

### youtube-transcript-api

- **Used in:** YouTube video transcript extraction
- **Why:** Direct access to YouTube's auto-generated and manual transcripts without downloading the video.

### AssemblyAI

- **Used in:** Speech-to-text transcription for videos without transcripts
- **Why:** High accuracy for Polish language. Cost: $0.12/hour.

## YAML Processing

### ruamel.yaml

- **Used in:** `scripts/env_to_vault.py` — YAML operations on `vars-classification.yaml` (SSOT file)
- **Why:** See [ADR-008](./architecture-decisions.md#adr-008-ruamelyaml-for-round-trip-yaml-preservation-in-variable-classification-ssot). Preserves comments, key ordering, and formatting during round-trip (load → modify → dump). Critical for machine-written YAML that is also human-edited. PyYAML strips comments and reorders keys.
- **Loaded via:** Lazy import (`_require_ruamel()`) — only when YAML commands are invoked.

## Secrets Management

### Multi-backend architecture

- **Backends:** `.env` files (default), HashiCorp Vault, AWS SSM Parameter Store
- **Used in:** `backend/library/config_loader.py` — unified secrets access
- **Controlled by:** `SECRETS_BACKEND` env var (`env`, `vault`, `aws`)
- **Why multi-backend:** Different deployment modes need different secret stores — `.env` for local dev, Vault for Docker/NAS, SSM for AWS serverless.

### hvac (HashiCorp Vault client)

- **Used in:** Vault backend for secrets
- **Why:** Official Python client for HashiCorp Vault. Loaded lazily (optional dependency).

### python-dotenv

- **Used in:** `.env` file loading for local development
- **Why:** Standard approach for environment-based configuration in Python projects.

## Code Quality

### ruff

- **Used in:** Linting (`ruff check`) and formatting (`ruff format`) for all Python code
- **Config:** `backend/pyproject.toml` — line-length=120, selects E/F/W rules, ignores E501
- **Why ruff (not flake8 + black + isort):**
  - Single tool replaces three (linter + formatter + import sorter)
  - Written in Rust — 10-100x faster than flake8/black
  - Native `pyproject.toml` configuration (no separate `.flake8`, `pyproject.toml` [tool.black], etc.)
  - Growing ecosystem with expanding rule set (supports most flake8 plugins natively)
- **Makefile targets:** `make lint`, `make lint-fix`, `make format`, `make format-check`

## Testing

### pytest

- **Used in:** Unit tests (`backend/tests/unit/`), integration tests (`backend/tests/integration/`)
- **Config:** `backend/pyproject.toml` [tool.pytest.ini_options]
- **Why pytest (not unittest):**
  - Simpler test syntax (plain functions with `assert`, no class boilerplate)
  - Rich plugin ecosystem (pytest-html for reports)
  - Better fixture system for test setup/teardown
  - De-facto standard for modern Python testing

### pytest-html (removed, restore with CI/CD)

- **Previously used for:** HTML test reports in CI/CD pipelines (`pytest --self-contained-html --html=pytest-results/`)
- **Status:** Removed from dependencies — no active CI/CD pipeline to consume reports. Will be restored when CI/CD is reactivated ([B-76](backlog-reference.md)).

## Security Scanning

### Pre-commit hooks

- **Config:** `.pre-commit-config.yaml`
- **Hooks:**
  - **gitleaks** v8.30.0 — regex-based secret detection (offline, fast)
  - **TruffleHog** v3.93.4 — secret detection with online verification (checks if secrets are active)
- **Why two tools:** Gitleaks catches patterns fast (offline). TruffleHog verifies whether detected secrets are actually active/valid — reduces false positives.

### Security scanners (via `uvx`)

All run as one-off tools via `uvx` — not installed in project venv.

| Tool | Purpose | Makefile target |
|------|---------|-----------------|
| **Semgrep** | Static code analysis, security vulnerability patterns | `make security` |
| **Bandit** | Python-specific security linter (SQL injection, exec, etc.) | `make security-bandit` |
| **pip-audit** | Dependency vulnerability scanning (PyPI advisory DB) | `make security-deps` |
| **Safety** | Dependency vulnerability check (alternative DB) | `make security-safety` |

- **Why multiple tools:** Each has different strengths and vulnerability databases. Running all four (`make security-all`) provides defense in depth.

## Monitoring & Observability

### Langfuse

- **Used in:** LLM call tracing and monitoring
- **Why:** Open-source LLM observability platform. Tracks token usage, latency, and cost across all LLM providers.

### AWS X-Ray (aws-xray-sdk)

- **Used in:** Docker deployment (request tracing)
- **Why:** AWS-native distributed tracing. Included only in the `docker` dependency group.

## Frontend

### React 18 + Vite 6

- **Used in:** Main frontend (`web_interface_react/`), admin panel (`web_interface_app2/`)
- **Versions:** React **18.3.1** (current: 19.2.x), Vite **6.0.7** (current: 7.3.x). Landing page already uses React 19.
- **Why React:** Widely adopted, large ecosystem, familiar to the project owner.
- **Why Vite:** Fast dev server with HMR, fast builds via esbuild. Replaces Create React App (deprecated).

**Upgrade plan ([B-77](backlog-reference.md)):** Upgrade `web_interface_react/` and `web_interface_app2/` to React 19 + Vite 7. React 19 introduces Server Components, Actions, and improved hooks (`use`, `useFormStatus`). Vite 7 brings performance improvements. Landing page (`web_landing_page/`) already runs React 19 — confirms ecosystem compatibility.

### Key frontend libraries

| Library | Purpose | Why |
|---------|---------|-----|
| **React Router v6** | Client-side routing | Standard for React SPAs |
| **Formik** | Form state management | Declarative form handling, validation integration |
| **axios** | HTTP client | Interceptors for API key injection, better error handling than fetch |
| **React Bootstrap** | UI components (admin panel) | Quick prototyping with consistent styling |

### Next.js 15

- **Used in:** Landing page (`web_landing_page/`)
- **Version:** **15.5.10** (current: 16.1.x).
- **Why:** Static site generation for `www.lenie-ai.eu`. 25 static pages deployed to S3 + CloudFront.

**Upgrade plan ([B-77](backlog-reference.md)):** Upgrade to Next.js 16 as part of the frontend upgrade batch. Already runs React 19.

## AWS SDK

### boto3

- **Used in:** S3 (document storage), SQS (async processing), SSM Parameter Store (secrets), DynamoDB (sync buffer), RDS management (start/stop), Bedrock (LLM), CloudFormation operations
- **Why:** Official AWS SDK for Python. Required for all AWS service integrations across the entire stack.

## Infrastructure

### Docker + Docker Compose

- **Used in:** Local development stack (Flask + PostgreSQL + React)
- **Why:** Reproducible development environment. Single `make dev` command.

### AWS CloudFormation

- **Used in:** All AWS infrastructure (29 templates)
- **Why CloudFormation (not Terraform for AWS):** Native AWS service, no state file management, direct integration with AWS services. Terraform is used for GCloud resources instead.

### AWS Lambda

- **Used in:** Serverless API (split into VPC and non-VPC functions)
- **Why:** Pay-per-invocation, no server management. See [ADR-002](./architecture-decisions.md#adr-002-api-gateway-as-security-boundary-no-nat-gateway) for the VPC split rationale.

### Kubernetes (Kustomize + Helm)

- **Used in:** GKE deployment (`infra/kubernetes/`)
- **Why Kustomize:** Overlay-based configuration without templating. Base + per-environment overlays.

### Terraform

- **Used in:** GCloud infrastructure (Cloud Run)
- **Why:** Standard IaC for non-AWS clouds. Used alongside CloudFormation (AWS) for multi-cloud support.

## CI/CD

**Current state: inactive.** All deployments are performed manually from the developer's machine (CloudFormation via `deploy.sh`, frontends via `deploy.sh`, Docker images via `make docker-push`). There is no automated CI/CD pipeline running.

The following tools were **previously configured and tested** but are not currently active:

| Tool | Environment | What was tested |
|------|-------------|-----------------|
| **CircleCI** | EC2-based | Testing, linting |
| **GitLab CI** | GitLab runners | Qodana security scanning |
| **Jenkins** | AWS EC2 | AWS deployment orchestration, Semgrep security |

Configuration files (`.circleci/config.yml`, `.gitlab-ci.yml`, `Jenkinsfile`) remain in the repository as reference for future restoration.

**Restoration plan:** Prerequisites tracked in [B-70](backlog-reference.md) (IaC complete, secrets accessible, deploy scripts idempotent). Each tool has a dedicated backlog item: [B-71 GitHub Actions](backlog-reference.md), [B-72 CircleCI](backlog-reference.md), [B-73 GitLab CI](backlog-reference.md), [B-74 Jenkins](backlog-reference.md). A single consolidated pipeline is preferred over the previous multi-tool setup.

## Build System

### hatchling

- **Used in:** `backend/pyproject.toml` build system
- **Why:** PEP 517 compliant, lightweight build backend. Required by uv for dependency resolution. No custom build logic needed.

## Related Documents

- [Architecture Decisions (ADR)](./architecture-decisions.md) — Deep decision records with full context and consequences
- [Project Overview](./project-overview.md) — Executive summary with technology stack table
- [Code Quality](./Code_Quality.md) — Security scanning tool usage
- [Python Dependencies](./Python_Dependencies.md) — uv package management guide
- [Development Guide](./development-guide.md) — Setup and usage instructions
