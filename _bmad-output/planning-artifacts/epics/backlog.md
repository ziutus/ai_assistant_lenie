## Sprint 6: Security Verification

### B-64: Verify Pre-Commit Secret Detection

As a **developer**,
I want to verify that pre-commit hooks correctly block commits containing secrets,
so that I have confidence the defense-in-depth secret detection actually works end-to-end.

**Origin:** Epic 19 retrospective — a real API key was committed (478b62c) because pre-commit hooks were misconfigured at the time. Since fixed, but never verified.

**Current setup (`.pre-commit-config.yaml`):**
- **Gitleaks v8.30.0** — regex-based offline detection (fast)
- **TruffleHog v3.93.4** — online verification of detected secrets

**Acceptance Criteria:**

**Given** pre-commit hooks are installed (`pre-commit install`)
**When** the developer attempts to commit a file containing a fake AWS access key (e.g., `AKIAIOSFODNN7EXAMPLE`)
**Then** at least one of the two tools (Gitleaks or TruffleHog) blocks the commit
**And** the error message clearly identifies the detected secret

**Given** the developer attempts to commit a fake OpenAI API key (e.g., `sk-proj-fake1234567890abcdefg`)
**When** the pre-commit hooks run
**Then** at least one tool blocks the commit

**Given** the developer attempts to commit a fake generic password in a config file (e.g., `PASSWORD=SuperSecret123!`)
**When** the pre-commit hooks run
**Then** at least one tool blocks the commit

**Given** all secret types are tested
**When** the developer documents the results
**Then** a test report is created documenting: which tools caught which secret types, any false negatives, and recommendations for `.gitleaks.toml` tuning if needed

**Given** a file contains no secrets (normal code)
**When** the developer commits it
**Then** both tools pass without blocking

**Technical notes:**
- Create temporary test files with fake secrets — do NOT use real credentials
- Remove test files after verification (do not commit them)
- Document results in `docs/security/pre-commit-verification.md`
- If either tool has blind spots, consider adding custom rules to `.gitleaks.toml`
- Test both `pre-commit` and `pre-push` stages

**Status:** backlog

---

## Backlog: Frontend Architecture & API Contract

### Overview

Work completed and planned to address frontend-backend type drift and shared code infrastructure. The `shared/` TypeScript package was extracted (B-49) and a strategy document for full API type synchronization was written (`docs/api-type-sync-strategy.md`). The main backlog item (B-50) covers the multi-phase implementation of Pydantic → OpenAPI → generated TypeScript types.

### Completed Work (Non-Sprint)

**B-49: Extract Shared TypeScript Types to shared/ Package** — DONE (2026-02-25)
- Created `shared/` package with domain types: `WebDocument`, `ApiType`, `SearchResult`, `ListItem`
- Added constants (`DEFAULT_API_URLS`) and factory values (`emptyDocument`)
- Both frontends (`web_interface_react/`, `web_interface_app2/`) reference via `@lenie/shared` alias (tsconfig paths + Vite resolve.alias)
- No build step — Vite transpiles directly via esbuild
- Commit: 64e3213

**B-51: Frontend Deployment Scripts with SSM** — DONE (2026-02-25)
- Created `deploy.sh` for `web_interface_react/` and `web_interface_app2/`
- Scripts resolve S3 bucket name and CloudFront distribution ID from SSM Parameter Store
- Support `--skip-build` and `--skip-invalidation` flags
- Commit: f2432ce

### B-50: API Type Synchronization Pipeline (Pydantic → OpenAPI → TypeScript)

**Problem:** Frontend (`shared/types/`) and backend (`backend/library/`) define the same data structures independently, leading to drift. Known issues documented in `docs/api-type-sync-strategy.md`:

| Issue | Detail |
|-------|--------|
| `id` type mismatch | TS: `string`, Python: `int` (serial PK) |
| `WebDocument` missing fields | Backend returns 13 fields not in TS interface |
| `ListItem` field count | TS: 5 fields, backend: 10 |
| `SearchResult` field count | TS: 5 fields, backend: 12 |
| Enums as plain strings | Backend has typed enums, frontend treats as `string` |
| No contract | No OpenAPI, JSON Schema, or Pydantic — backend uses custom classes + raw dicts |

**Chosen approach:** Python Pydantic models (source of truth) → OpenAPI schema (generated) → TypeScript types (generated)

**Implementation phases (from `docs/api-type-sync-strategy.md`):**

1. **Phase 1: Pydantic Response Models** — Create Pydantic v2 models in `backend/library/models/schemas/` for all API response shapes (WebDocumentResponse, WebDocumentListItem, SearchResultItem, ListResponse, SearchResponse, ErrorResponse)
2. **Phase 2: Use Models in Flask Routes** — Replace raw dict returns with Pydantic model serialization in `server.py` and Lambda handlers
3. **Phase 3: Generate OpenAPI Schema** — Manual export script or flask-smorest integration to produce `docs/openapi.json`
4. **Phase 4: Generate TypeScript from OpenAPI** — Use `openapi-typescript` to generate `shared/types/generated.ts` from OpenAPI schema
5. **Phase 5: CI Integration** — Add generation + diff check to CI pipeline to prevent future drift

**Migration path:** Incremental, one endpoint at a time. Start with `/website_get`, then `/website_list`, `/website_similar`. Hand-written `shared/types/` coexists with generated types during migration.

**Status:** backlog
**Strategy document:** `docs/api-type-sync-strategy.md`
**Depends on:** B-49 (shared types package) — DONE

---

## Backlog: Architecture Decisions

### B-67: Choose Compute Model for Serverless YouTube Processing

As an **architect**,
I want to decide how to run YouTube processing (pytubefix) in the AWS serverless architecture,
so that future features requiring YouTube metadata/download can be implemented without Lambda layer size constraints.

**Origin:** Lambda layer rebuild (Story 20-4, 2026-02). `pytubefix` depends on `nodejs-wheel-binaries` (~60 MB), which exceeds the Lambda layer ZIP limit (50 MB). YouTube processing is currently available only in Docker/K8s and batch scripts, not in any Lambda function.

**Constraint:** Lambda layers: 50 MB zipped / 250 MB unzipped. No NAT Gateway (budget $8/month).

**Options to evaluate:**

| Option | Pros | Cons |
|--------|------|------|
| ECS Fargate task (on-demand) | Pay only when running, full dependency support, no size limits | Fargate pricing (~$0.04/vCPU-hr), cold start ~30-60s, needs task definition + ECR |
| ECS Fargate task + Step Functions | Clean orchestration (Lambda → ECS task → Lambda), cost protection via timeout | More infrastructure to manage, Step Functions pricing |
| Lambda container image (up to 10 GB) | Stays in Lambda ecosystem, familiar API | Longer cold starts (~5-10s), need Docker build pipeline, still limited to 15 min |
| EKS job (existing cluster) | Reuses existing EKS infra | EKS cluster cost, over-engineered for single task |

**Acceptance Criteria:**
- Option chosen and documented in `docs/architecture-decisions/` (ADR format)
- Cost estimate for chosen option at expected usage (~10-50 YouTube videos/month)
- Proof of concept with `pytubefix` running in chosen compute model
- Integration path defined (how to trigger from SQS/API Gateway/Step Functions)

**Status:** backlog

---

## Backlog: Config Loader Improvements

### B-65: Handle Empty String Values in Config.require()

As a **developer**,
I want `Config.require()` to handle empty string values deliberately,
so that missing-but-set configuration variables (e.g., `OPENAI_API_KEY=""`) don't silently pass validation and cause cryptic runtime errors later.

**Origin:** Code review of Story 20-1 (config_loader module).

**Current behavior:**
`cfg.require("OPENAI_API_KEY")` on `Config({"OPENAI_API_KEY": ""})` returns `""` without any warning. For API keys, passwords, and database hosts, an empty string is effectively the same as a missing value.

**Challenge:** Some variables are legitimately empty (e.g., `DEBUG=""`, `POSTGRESQL_SSLMODE=""`). A blanket rejection of empty strings would break existing behavior.

**Possible approaches (to be decided):**
1. Add a `allow_empty=False` parameter to `require()` — raises/warns when value is `""`
2. Maintain a list of "critical" keys that must be non-empty
3. Add a separate `require_non_empty()` method
4. Log a warning for empty values but still return them (least disruptive)

**Acceptance Criteria:**
- Empty string handling strategy is chosen and documented
- `require()` behavior is updated accordingly
- Existing tests pass, new tests cover the empty string scenario
- No breaking changes to current callers

**Status:** backlog

---

### B-66: Add Tests for env_to_vault.py Script

As a **developer**,
I want `scripts/env_to_vault.py` to have unit tests,
so that changes to secret management CLI operations can be verified without requiring live Vault or AWS SSM connections.

**Origin:** Code review of Story 20-3 (AWS SSM Parameter Store backend).

**Current state:**
`env_to_vault.py` has ~700 lines covering: .env parsing, Vault CRUD, SSM CRUD, and backend sync — all without any tests. Refactoring (e.g., extracting `PROJECT_CODE`, renaming `SKIP_VARS`) was done without automated verification.

**Suggested test coverage:**
1. `parse_env_file()` — parsing, comments, empty lines, quoting, edge cases
2. `mask_value()` — short/long strings
3. `vault_secret_path()` / `ssm_path_prefix()` — path construction with PROJECT_CODE
4. `SKIP_VARS` filtering — ensure bootstrap vars are excluded from uploads
5. CLI argument parsing — verify subcommands and required arguments
6. Vault/SSM operations — mock `hvac` and `boto3` clients to test command logic without live connections

**Acceptance Criteria:**
- Test file created at `scripts/tests/test_env_to_vault.py` (or `backend/tests/unit/test_env_to_vault.py`)
- Pure functions tested without mocks
- Vault/SSM operations tested with mocked clients
- All tests pass in CI (no live connections required)

**Status:** backlog

---

## Backlog: Technology Upgrades

### B-68: Upgrade Python Runtime in Lambda to 3.12+

As a **developer**,
I want Lambda functions to run on the latest supported Python runtime,
so that the project benefits from performance improvements, new language features, and continued AWS security patching.

**Origin:** Technology debt — Lambda functions and layers were built on Python 3.11. AWS Lambda now supports Python 3.12 and 3.13. Python 3.11 will reach end-of-life in October 2027.

**Current state:**
- All Lambda functions use Python 3.11 (configured via SSM parameter `/${ProjectCode}/${Environment}/python/lambda-runtime-version`)
- Lambda layer `lenie_all_layer` built with Python 3.11
- AWS Lambda Powertools layer pinned to `python311-x86_64` variant
- Docker image uses `python:3.11-slim`

**Scope:**
1. Update SSM parameter for Lambda runtime version to `python3.12` (or `python3.13`)
2. Rebuild `lenie_all_layer` with the new Python version
3. Update Powertools layer ARN to matching Python version variant
4. Update `backend/Dockerfile` base image to `python:3.12-slim` (or `3.13-slim`)
5. Update `pyproject.toml` `requires-python` to `>=3.12`
6. Verify all Lambda functions work correctly (deploy to dev, run integration tests)
7. Verify Docker stack works correctly
8. Update documentation (`CLAUDE.md`, `docs/technology-choices.md`, `docs/project-overview.md`)

**Acceptance Criteria:**
- All Lambda functions run on Python 3.12+ without errors
- Lambda layer deploys successfully with new Python version
- Docker image builds and runs correctly
- All unit and integration tests pass
- No regressions in API behavior

**Technical notes:**
- SSM parameter approach makes the runtime change easy — update one parameter, redeploy stacks
- Main risk: dependency compatibility (psycopg2-binary, boto3, etc.) — test in dev first
- Consider going directly to 3.13 if all dependencies support it

**Status:** backlog

---

### B-69: Upgrade Docker/NAS PostgreSQL from 17 to 18

As a **developer**,
I want the Docker/NAS PostgreSQL image to match the RDS version (18),
so that all environments run the same database version.

**Origin:** RDS was upgraded to PostgreSQL 18.1 (Feb 2026). Docker/NAS image still uses `postgres:17-bookworm`.

**Current state:**
- AWS RDS: **PostgreSQL 18.1** (already upgraded)
- Docker/NAS: **PostgreSQL 17** (`infra/docker/Postgresql/Dockerfile` uses `postgres:17-bookworm`)
- NAS database is empty — no data migration needed, rebuild from scratch

**Scope:**
1. Update `infra/docker/Postgresql/Dockerfile`: base image `postgres:17-bookworm` → `postgres:18-bookworm`, package `postgresql-17-pgvector` → `postgresql-18-pgvector`
2. Update `infra/docker/compose.yaml` comment: `pgvector/pgvector:pg17` → `pgvector/pgvector:pg18`
3. Build and test locally: `make build && make dev`, run integration tests
4. Push updated image to NAS registry (`192.168.200.7:5005/lenie-ai-db:latest`)
5. Recreate NAS database container (empty DB — init scripts will create schema)
6. Update documentation version references

**Acceptance Criteria:**
- Docker image builds successfully with PostgreSQL 18 + pgvector
- Local integration tests pass
- NAS deployment works with new image
- Vector similarity search works correctly

**Status:** backlog
