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

**Migration path:** Incremental, one endpoint at a time. Start with `/ai_parse_intent` (simplest, already used as AI structured output in slack_bot), then `/website_get`, `/website_list`, `/website_similar`. Hand-written `shared/types/` coexists with generated types during migration.

**Additional benefit:** Pydantic schemas double as `response_format` for LLM structured outputs (OpenAI, Bedrock, Vertex AI). The `/ai_parse_intent` endpoint is a natural first candidate — its Pydantic schema (`ParsedIntent`) can serve as both the API response model and the LLM structured output format, replacing manual JSON parsing in `ai_intent_parser.py`.

**Status:** backlog
**Strategy document:** `docs/api-type-sync-strategy.md`
**Depends on:** B-49 (shared types package) — DONE, [B-92](#b-92-migrate-database-layer-to-sqlalchemy-orm--pydantic-schemas) (Pydantic dependency)

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

## Backlog: Infrastructure — Vault

### B-78: Vault Auto-Unseal via AWS KMS for NAS Deployment

As a **developer**,
I want HashiCorp Vault on NAS to automatically unseal using AWS KMS,
so that Vault restarts (planned or unplanned) don't require manual unseal intervention.

**Origin:** Sprint 6 (Epic 20) — while integrating config_loader (Story 20-4), the NAS Vault deployment needed production-grade reliability. Manual unseal after every container restart was operationally unacceptable for a secrets backend.

**What was implemented (commit 60eddb3):**
1. **CloudFormation template** (`infra/aws/cloudformation/templates/vault-kms-unseal.yaml`) — KMS key + IAM user dedicated to Vault auto-unseal, deployed on personal AWS account (`ziutus-Administrator` profile, eu-central-1)
2. **NAS Compose improvements** (`infra/docker/compose.nas.yaml`) — Vault pinned to 1.21.3, added `env_file` for AWS credentials, healthcheck (30s interval, 5s timeout)
3. **Configuration templates** — `vault.env.example` with AWS KMS credential placeholders
4. **Documentation** — expanded `docs/CICD/Vault_Setup.md` (auto-unseal section + migration steps) and `docs/CICD/NAS_Deployment.md`

**Acceptance Criteria:**
- ✅ Vault container auto-unseals on restart without manual intervention
- ✅ KMS key and IAM user provisioned via CloudFormation (IaC, not manual)
- ✅ AWS credentials passed via env_file (not hardcoded in compose)
- ✅ No AWS account numbers committed to repository
- ✅ Documentation covers setup, migration from Shamir to transit seal, and troubleshooting

**Status:** done (2026-02-27)
**Related:** Story 20-2 (Vault backend), Story 20-4 (config_loader integration)

---


### B-79: Migrate Standalone Scripts to config_loader

As a **developer**,
I want all standalone scripts to use config_loader instead of `load_dotenv()`,
so that they work correctly when `.env` contains only bootstrap variables (Vault/AWS mode).

**Origin:** Epic 20 retrospective (2026-02-27) — discovered that import scripts and batch processing scripts still use `load_dotenv()` directly instead of config_loader. They will fail when `.env` contains only bootstrap variables.

**Scope (original 6 scripts + 4 bonus):**
1. `imports/unknown_news_import.py` — already migrated before B-79 branch (uses `load_config()` since creation)
2. `imports/dynamodb_sync.py` — already migrated before B-79 branch; fixed remaining `os.getenv()` → `cfg.get()` for display vars (2026-03-03)
3. `web_documents_do_the_needful_new.py` — migrated (commit 119fd42)
4. `webdocument_md_decode.py` — migrated (commit 119fd42)
5. `markdown_to_embedding.py` — **N/A**: script does not use any configuration (reads local files only, no env vars)
6. `webdocument_prepare_regexp_by_ai.py` — migrated + unused imports cleaned (commit 119fd42)
7. `youtube_add.py` — migrated (commit 119fd42, bonus)
8. `test_code/embeddings_search.py` — migrated (commit 119fd42, bonus)
9. `test_code/gcloud_firestore_example.py` — migrated (commit 119fd42, bonus)
10. `test_code/vault_tests.py` — migrated (commit 119fd42, bonus)

**Additional fix (commit eb2653e):**
- `library/lenie_markdown.py` — `re.sub()` keyword args to silence DeprecationWarning
- `library/text_transcript.py` — `split_text_and_time()` returns `{}` instead of `None` for safer API contract

**Acceptance Criteria:**
- ✅ All scripts use `load_config()` from `library.config_loader`
- ✅ Scripts work with `SECRETS_BACKEND=vault` (NAS) and `SECRETS_BACKEND=aws`
- ⚠️ `load_dotenv()` calls remain in `test_code/` (11 scripts) and `library/api/cloudferro/sherlock/` (2 files) — tracked in [B-85](#b-85-migrate-remaining-test_code-and-library-scripts-to-config_loader)
- ✅ Existing behavior preserved for `SECRETS_BACKEND=env`

**Priority:** HIGH — blocks Vault-only deployments for batch processing
**Status:** done (2026-03-03)
**Related:** Epic 20 retrospective action item #3, [B-85](#b-85-migrate-remaining-test_code-and-library-scripts-to-config_loader)

---

## Backlog: Docker Build Optimization

### B-80: Optimize Docker Build Context with .dockerignore

As a **developer**,
I want Docker build context to exclude unnecessary files,
so that builds are faster and don't send unnecessary data to the Docker daemon.

**Origin:** Code review of Story 21-1 (Slack bot). Found that `slack_bot/` had no `.dockerignore` (fixed in review). Investigation showed other directories have the same issue.

**Implementation note:** All compose builds use project root as build context (`context: ../..`), so per-directory `.dockerignore` files are NOT needed — only the **root `.dockerignore`** matters. The original plan to add per-directory files was based on incorrect assumptions.

**What was done (2026-03-04):**
- Rewrote root `.dockerignore` with proper `**` glob patterns (Docker matching: patterns without `**` only match root level)
- Added project-specific exclusions: `_bmad/`, `_bmad-output/`, `.claude/`, `docs/`, `scripts/`, `web_landing_page/`, `web_chrome_extension/`, `infra/`
- Added backend dev exclusions: `backend/tests/`, `backend/test_code/`, `backend/tmp/`, `backend/imports/`, `backend/data/`
- Added `**/*.md` exclusion with `!slack_bot/README.md` exception (required by hatchling build in slack_bot Dockerfile)
- Added `backend/.venv_wsl/` exclusion (WSL venv)
- Verified all COPY sources in all 5 Dockerfiles remain accessible

**Previous state:** Generic `.dockerignore` with patterns like `tests/`, `tmp/` that only matched root level (ineffective for `backend/tests/` etc.)

**Acceptance Criteria:**
- ✅ Docker builds exclude dev dependencies, tests, caches, and temp files at all directory levels
- ✅ No change in runtime behavior — only build context optimization
- ✅ All Dockerfile COPY commands verified against exclusion rules

**Priority:** LOW — optimization, not blocking
**Status:** done (2026-03-04)

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

**Status:** subsumed by Story 20-6 (Task 10 in tech spec covers all test scope + 30 additional tests for new commands)

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

**Status:** done (2026-03-07)

---

### B-70: Restore CI/CD — Common Prerequisites

As a **developer**,
I want all prerequisites for CI/CD pipelines to be met,
so that any of the CI/CD tools (B-71 through B-74) can be configured and activated.

**Origin:** CI/CD tools were previously configured and tested but are not currently active. All deployments happen manually from the developer's machine.

**Current state:**
- No active CI/CD pipeline — all deploys are manual
- Configuration files remain in the repository as reference: `.circleci/config.yml`, `.gitlab-ci.yml`, `Jenkinsfile`
- Previous setup used three tools experimentally

**Scope:**
1. All infrastructure deployable via IaC (CloudFormation `deploy.sh`, Docker `compose.yaml`)
2. All secrets accessible from CI environment (SSM, Vault, or CI-native secrets)
3. All deploy scripts tested and idempotent (`infra/aws/cloudformation/deploy.sh`, frontend `deploy.sh`)
4. Integration tests runnable against a CI database (Docker Compose or test RDS)
5. Define common pipeline stages that all tools must implement:
   - **Lint & format check** — `ruff check`, `ruff format --check`
   - **Unit tests** — `pytest backend/tests/unit/`
   - **Security scan** — pre-commit hooks (gitleaks, TruffleHog), semgrep, pip-audit
   - **Build** — Docker image build, frontend build
   - **Deploy to dev** — CloudFormation stacks, Lambda layers, frontend to S3+CloudFront

**Acceptance Criteria:**
- All deploy scripts execute successfully from a clean environment (no local state dependencies)
- Secrets access pattern documented for CI environments
- Common pipeline stage definitions documented in `docs/CICD/CI_CD.md`

**Status:** backlog
**Blocks:** B-71, B-72, B-73, B-74

---

### B-71: CI/CD — GitHub Actions Pipeline

As a **developer**,
I want a CI/CD pipeline using GitHub Actions,
so that CI runs natively in the repository host without external services.

**Origin:** Repository is hosted on GitHub. GitHub Actions is the native CI/CD solution — no external account or runner setup needed.

**Existing config:** None (new).

**Pros:**
- Native to GitHub — no external service, no separate account
- Free tier: 2,000 minutes/month for private repos
- Direct integration with PR checks, branch protection, deployments
- Large marketplace of reusable actions (AWS deploy, Docker build, etc.)

**Cons:**
- No existing configuration to build on
- GitHub-hosted runners have limited compute (2 vCPU, 7 GB RAM)
- Vendor lock-in to GitHub ecosystem

**Scope:**
1. Create `.github/workflows/ci.yml` — lint + unit tests + security scan on push/PR
2. Create `.github/workflows/deploy.yml` — build + deploy on merge to main (manual trigger)
3. Configure GitHub secrets for AWS credentials and API keys
4. Set up branch protection rules requiring CI pass before merge

**Acceptance Criteria:**
- PR checks run lint + unit tests + security scan
- Deploy workflow available as manual dispatch or on merge to main
- Pipeline completes in < 10 minutes for CI checks
- Documentation in `docs/CICD/GitHub_Actions.md`

**Depends on:** B-70
**Status:** backlog

---

### B-72: CI/CD — CircleCI Pipeline

As a **developer**,
I want a CI/CD pipeline using CircleCI,
so that CI runs on dedicated EC2 runners with full AWS access.

**Origin:** CircleCI was previously configured (`.circleci/config.yml` exists) for EC2-based testing.

**Existing config:** `.circleci/config.yml` — needs update to current project structure.

**Pros:**
- Existing configuration as starting point
- EC2-based runners — can have VPC access for integration tests against RDS
- Good parallelism and caching support
- Free tier: 6,000 build minutes/month

**Cons:**
- External service — requires CircleCI account
- Previous config is outdated and needs significant rework
- Self-hosted runner setup needed for VPC access

**Scope:**
1. Update `.circleci/config.yml` to current project structure
2. Configure CircleCI context with AWS credentials
3. Set up EC2 runner if VPC access needed for integration tests
4. GitHub integration for PR status checks

**Acceptance Criteria:**
- PR checks run lint + unit tests + security scan
- Deploy workflow available on merge to main
- Pipeline completes in < 10 minutes for CI checks
- Documentation updated in `docs/CICD/CircleCI.md`

**Depends on:** B-70
**Status:** backlog

---

### B-73: CI/CD — GitLab CI Pipeline

As a **developer**,
I want a CI/CD pipeline using GitLab CI,
so that CI runs with Qodana security scanning and GitLab-native features.

**Origin:** GitLab CI was previously configured (`.gitlab-ci.yml` exists) for Qodana security scanning.

**Existing config:** `.gitlab-ci.yml` — Qodana-focused, needs expansion to full pipeline.

**Pros:**
- Existing configuration as starting point
- Qodana integration for deep code quality analysis
- Built-in container registry, environments, and review apps
- Free tier: 400 compute minutes/month on gitlab.com

**Cons:**
- Requires GitLab mirror or separate GitLab repository (primary repo is on GitHub)
- Lower free tier than alternatives
- Previous config is narrow (Qodana only, not full pipeline)

**Scope:**
1. Update `.gitlab-ci.yml` to full pipeline (lint, test, security, build, deploy)
2. Configure GitLab CI/CD variables for AWS credentials
3. Set up GitHub → GitLab mirroring if needed
4. Integrate Qodana as a pipeline stage

**Acceptance Criteria:**
- Full pipeline runs on push (lint + test + security + Qodana)
- Deploy stage available on main branch
- Pipeline completes in < 10 minutes for CI checks (excluding Qodana)
- Documentation updated in `docs/CICD/GitLabCI.md`

**Depends on:** B-70
**Status:** backlog

---

### B-74: CI/CD — Jenkins Pipeline

As a **developer**,
I want a CI/CD pipeline using Jenkins,
so that CI runs on a self-managed AWS EC2 instance with full control over the environment.

**Origin:** Jenkins was previously configured (`Jenkinsfile` exists) for AWS EC2 orchestration and Semgrep security scanning.

**Existing config:** `Jenkinsfile` — needs update to current project structure.

**Pros:**
- Existing configuration as starting point
- Full control over runner environment (EC2 instance)
- Direct AWS access from EC2 — IAM role, VPC, no credential passing needed
- Unlimited builds (self-hosted, pay only for EC2)

**Cons:**
- Self-managed infrastructure — EC2 instance maintenance, Jenkins updates, plugin management
- EC2 cost even when idle (unless using spot/on-demand scheduling)
- Most complex setup and maintenance of all options

**Scope:**
1. Update `Jenkinsfile` to current project structure
2. Set up Jenkins EC2 instance (or reuse existing AMI from `docs/CICD/EC2_AMI_Backup_Pipeline.md`)
3. Configure IAM role for Jenkins EC2 with deploy permissions
4. Integrate Semgrep as a pipeline stage
5. GitHub webhook for PR triggers

**Acceptance Criteria:**
- PR checks run lint + unit tests + security scan + Semgrep
- Deploy stage available on main branch
- Pipeline completes in < 10 minutes for CI checks
- Documentation updated in `docs/CICD/Jenkins.md`

**Depends on:** B-70
**Status:** backlog

---

### B-75: Standardize Node.js Version to 24 LTS

As a **developer**,
I want all environments to use Node.js 24 LTS consistently,
so that frontends build on a supported, up-to-date runtime with the same behavior everywhere.

**Origin:** Docker builds already use `node:24` (`web_interface_react/Dockerfile`, `web_interface_app2/Dockerfile`), but documentation still stated `>= 18`. Node.js 18 reached EOL in April 2025. Node.js 20 EOL is April 2026. The project should standardize on Node.js 24 LTS (active LTS, supported until April 2028).

**Current state:**
- Docker builds: `node:24` (already up to date)
- `docs/development-guide.md`: lists `>= 22` as prerequisite (updated from `>= 18`)
- `web_landing_page/`: Next.js 14.2, built locally — not verified against Node.js 24
- No `.nvmrc` or `engines` field in `package.json` to enforce version

**Scope:**
1. Verify `web_landing_page/` builds correctly on Node.js 24 (Next.js 14.2 compatibility)
2. Add `engines` field to all `package.json` files: `"node": ">=22"`
3. Add `.nvmrc` file to project root: `24` (for developers using nvm)
4. Update `docs/development-guide.md` prerequisite to `>= 22 (recommended: 24 LTS)`
5. Verify all npm scripts work on Node.js 24 (`npm install`, `npm run build`, `npm test`)
6. Update CI configs (when restored) to use Node.js 24

**Acceptance Criteria:**
- All three frontends build successfully on Node.js 24
- `package.json` files have `engines` field enforcing `>= 22`
- `.nvmrc` present in project root
- No deprecation warnings from Node.js 24 during builds
- Documentation reflects Node.js 24 as the standard

**Status:** backlog

---

### B-76: Restore pytest-html for CI/CD Test Reports

As a **developer**,
I want pytest-html restored when CI/CD pipelines are active,
so that test results are available as visual HTML reports in CI artifacts.

**Origin:** pytest-html was removed from dependencies (Feb 2026) because no CI/CD pipeline is active to consume the reports. It was previously used to generate HTML test reports (`pytest --self-contained-html --html=pytest-results/`) as CI build artifacts.

**Scope:**
1. Add `pytest-html` back to `[dependency-groups] dev` in `backend/pyproject.toml`
2. Update `uv.lock`
3. Restore `pytest --self-contained-html --html=pytest-results/` commands in documentation (`CLAUDE.md`, `backend/CLAUDE.md`, `backend/tests/CLAUDE.md`, `docs/development-guide.md`)
4. Configure CI pipeline to archive `pytest-results/` as build artifacts
5. Update `docs/technology-choices.md` status

**Acceptance Criteria:**
- pytest-html is in dev dependencies
- CI pipeline archives HTML test reports as artifacts
- Reports are accessible from CI build page

**Depends on:** B-70 (CI/CD prerequisites)
**Status:** backlog

---

### B-77: Upgrade React to 19 and Vite to 7 in Main Frontends

As a **developer**,
I want all frontends to use React 19 and the latest build tools,
so that the project benefits from new React features, performance improvements, and security patches.

**Origin:** Main frontend (`web_interface_react/`) and admin panel (`web_interface_app2/`) use React 18.3.1 + Vite 6.0.7. Landing page already uses React 19. React 19 has been stable since Dec 2024 (current: 19.2.x). Vite 7 is current stable (7.3.x).

**Current state:**

| App | React | Vite/Next.js | Target |
|-----|-------|-------------|--------|
| `web_interface_react/` | 18.3.1 | Vite 6.0.7 | React 19 + Vite 7 |
| `web_interface_app2/` | 18.3.1 | Vite 6.0.7 | React 19 + Vite 7 |
| `web_landing_page/` | 19.0.0 | Next.js 15.5.10 | Next.js 16 |

**Scope:**
1. **React 19 migration** (`web_interface_react/`, `web_interface_app2/`):
   - Update `react` and `react-dom` to `^19.0.0`
   - Review breaking changes: `forwardRef` removal, `ref` as prop, `Context` as provider, `use()` hook
   - Update `react-router-dom`, `formik`, `react-bootstrap` to React 19-compatible versions
   - Verify shared types (`@lenie/shared`) work with React 19
2. **Vite 7 upgrade** (`web_interface_react/`, `web_interface_app2/`):
   - Update `vite` to `^7.0.0`
   - Review Vite 7 migration guide for config changes
   - Verify build output and dev server functionality
3. **Next.js 16 upgrade** (`web_landing_page/`):
   - Update `next` to `^16.0.0`
   - Review Next.js 16 migration guide
   - Verify static export still works (`output: 'export'`)
   - Verify S3 + CloudFront deployment
4. **Testing:**
   - Verify all pages load correctly
   - Test document CRUD operations
   - Test vector similarity search
   - Verify Chrome extension compatibility (API calls unchanged)

**Acceptance Criteria:**
- All three frontends build successfully with updated dependencies
- No runtime errors on any page
- All existing functionality works (document list, edit, search, AI tools)
- Docker builds work with updated dependencies
- `npm run build` produces valid output for S3 deployment

**Status:** backlog

---

## Backlog: Code Quality

### B-81: Expand Code Duplication Control

As a **developer**,
I want comprehensive code duplication detection across the entire project (Python + TypeScript),
so that duplicated code blocks are identified early and can be refactored into shared modules.

**Origin:** Extraction of `shared_python/unified-config-loader/` (commit 7d11b12) eliminated ~300 lines of duplicated config code. Initial `pylint --duplicate-code` check added to Makefile (`make duplicate-check`). Further expansion needed for cross-language coverage and CI integration.

**Current state:**
- `make duplicate-check` — pylint `duplicate-code` checker for Python (`backend/library/`), min 6 lines
- Known duplicates detected: DB connection kwargs block (2 files), document serialization block (2 files)
- No TypeScript duplication check
- Not integrated into CI pipeline

**Scope:**
1. **Fix known Python duplicates** — extract `connect_kwargs` builder and shared serialization into helpers
2. **Add jscpd** for cross-language detection (Python + TypeScript): `npx jscpd --min-lines 5 --ignore "**/node_modules/**,**/.venv/**,**/dist/**"`
3. **Expand pylint scope** — include `shared_python/`, `slack_bot/src/`, `scripts/` (not just `backend/library/`)
4. **CI integration** — add duplication check to CI pipeline stages (depends on [B-70](./backlog.md))
5. **Set thresholds** — define acceptable duplication percentage, fail CI if exceeded

**Acceptance Criteria:**
- Python duplication check covers all Python source directories
- TypeScript duplication check covers `web_interface_react/src/`, `web_interface_app2/src/`, `shared/`
- Known duplicates from initial scan are resolved or documented as accepted
- CI pipeline includes duplication check (when B-70 is done)
- Documentation updated in [`docs/Code_Quality.md`](../../docs/Code_Quality.md)

**Priority:** LOW — quality improvement, not blocking
**Status:** backlog
**Related:** B-70 (CI/CD prerequisites)

---

## Backlog: Infrastructure — Storage

### B-82: Add MinIO as S3-Compatible Local Storage for NAS Development

As a **developer**,
I want a local S3-compatible storage (MinIO) running on NAS alongside the application,
so that development uses the same S3 API as production (AWS) and future Kubernetes deployments — eliminating environment-specific file storage code paths.

**Origin:** `dynamodb_sync.py` downloads S3 files to a local `data/` directory, creating a divergence between dev (filesystem) and prod (S3). With NAS as the primary development environment, a unified storage interface prevents future rewrites.

**Current state:**
- **Production (AWS):** S3 buckets for webpage content (`{uuid}.txt`, `{uuid}.html`)
- **Development (NAS/Docker):** local `data/` directory via filesystem I/O
- **Backend code:** `server.py` uses boto3 S3 client; `dynamodb_sync.py` downloads to local dir; batch scripts mix S3 and local paths

**Why MinIO:**
- S3-compatible API — same boto3 code, only `endpoint_url` changes
- Single Docker container, single-node — no cluster complexity
- Web console for browsing stored objects (port 9001)
- Smooth migration path to Kubernetes (MinIO has a K8s operator)
- Data stored as plain files on NAS disk — easy to backup

**Scope:**
1. Add MinIO service to `infra/docker/compose.nas.yaml` (port 9000 for S3 API, 9001 for console)
2. Add `MINIO_*` env vars to config_loader: `S3_ENDPOINT_URL`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`
3. Update boto3 S3 client initialization in backend to use `endpoint_url` when configured (transparent — if `S3_ENDPOINT_URL` is not set, defaults to AWS S3)
4. Create initial buckets (e.g., `website-content`) via MinIO client or startup script
5. Update `dynamodb_sync.py` to upload downloaded S3 files to local MinIO instead of (or in addition to) saving to `data/`
6. Update `vars-classification.yaml` with new S3/MinIO variables
7. Add MinIO credentials to Vault (NAS deployment)
8. Documentation: update `docs/CICD/NAS_Deployment.md`, `CLAUDE.md`

**Acceptance Criteria:**
- MinIO runs as a Docker container on NAS alongside PostgreSQL and the backend
- Backend can read/write objects via boto3 using `S3_ENDPOINT_URL` pointing to MinIO
- Same backend code works against both MinIO (dev) and AWS S3 (prod) without changes
- `dynamodb_sync.py` stores downloaded content in MinIO
- MinIO web console accessible for debugging/browsing stored objects
- Vault stores MinIO credentials (NAS deployment)

**Technical notes:**
- MinIO single-node config: `minio server /data --console-address ":9001"` — that's it
- boto3 integration: `boto3.client("s3", endpoint_url="http://minio:9000")` — no other code changes
- Data lives in a Docker volume mapped to NAS disk — survives container restarts
- Consider `mc` (MinIO client CLI) for bucket creation in entrypoint/init script

**Priority:** MEDIUM — enables consistent NAS development, prevents future rewrites
**Status:** backlog

### B-84: Add CONTENT_NEEDED Document Status for Slack Bot URL Additions

As a **developer**,
I want a new document processing status `CONTENT_NEEDED` that signals the backend to fetch page content automatically,
so that URLs added via Slack Bot (which cannot send page HTML/text like the Chrome extension) still get their content downloaded and processed.

**Origin:** Story 22.1 verification — `/lenie-add` works but adding `webpage` type via Slack is incomplete because the Chrome extension sends full HTML/text content with the request, while Slack Bot can only send the URL. Without content, the document sits in the database with no text to process.

**Context — how different sources add documents:**
- **Chrome extension** (`/url_add`): sends URL + type + full HTML + extracted text + title + language → document is immediately ready for processing
- **Slack Bot** (`/lenie-add`): can only send URL + type → no content available at submission time
- **YouTube**: content is fetched automatically via YouTube Transcript API — works fine from Slack
- **link**: only URL and description matter — works fine from Slack
- **webpage**: needs HTML/text content that Slack cannot provide → this is the gap

**Proposed solution:**
1. Add `CONTENT_NEEDED` status to `StalkerDocumentStatus` enum (in `backend/library/models/stalker_document_status.py`)
2. When `/url_add` receives a `webpage` without `text`/`html` fields, set status to `CONTENT_NEEDED` instead of the default flow
3. Backend batch processing script (`web_documents_do_the_needful_new.py`) picks up `CONTENT_NEEDED` documents and downloads content using existing tools (BeautifulSoup, Firecrawl, Markdownify)
4. After content is fetched, status transitions to `DOCUMENT_INTO_DATABASE` and normal processing continues

**Scope:**
1. Add `CONTENT_NEEDED` to `StalkerDocumentStatus` enum and database `document_types` table
2. Modify `/url_add` endpoint to detect missing content and set appropriate status
3. Extend `web_documents_do_the_needful_new.py` to handle `CONTENT_NEEDED` → download content → update status
4. Update Slack Bot `/lenie-add` response to inform user that content will be fetched automatically

**Acceptance Criteria:**
- `/lenie-add https://example.com webpage` via Slack → document created with status `CONTENT_NEEDED`
- Batch processing script picks up `CONTENT_NEEDED` documents and downloads their content
- After content fetch, document transitions to normal processing pipeline
- Chrome extension workflow unchanged (still sends content directly)

**Priority:** MEDIUM — improves Slack Bot usefulness for webpage additions
**Status:** backlog

---

## Backlog: Code Quality — Config Migration

### B-85: Migrate Remaining test_code/ and Library Scripts to config_loader

As a **developer**,
I want all remaining scripts using `load_dotenv()` to be migrated to `config_loader`,
so that the acceptance criterion from [B-79](#b-79-migrate-standalone-scripts-to-config_loader) ("no `load_dotenv()` calls remain outside of `config_loader.py`") is fully met.

**Origin:** B-79 completion review (2026-03-03) — discovered 13 files still using `load_dotenv()` directly.

**Scope:**

**Library code (priority — used in production):**
1. `library/api/cloudferro/sherlock/sherlock_embedding.py`
2. `library/api/cloudferro/sherlock/sherlock.py`

**Experimental scripts (`test_code/` — lower priority):**
3. `test_code/webdocument_bielik_popraw_2.py`
4. `test_code/webdocument_bielik_popraw.py`
5. `test_code/webdocument_bielik_analizuj.py`
6. `test_code/serper_dev.py`
7. `test_code/openroute.py`
8. `test_code/models_list.py`
9. `test_code/gcloud_firestore.py`
10. `test_code/firecrawl.py`
11. `test_code/embedding_search_2.py`
12. `test_code/describe_image.py`
13. `test_code/cloudferro_embeddings.py`
14. `test_code/cloudferro_ark_labs_models.py`

**Acceptance Criteria:**
- No `load_dotenv()` calls remain in `backend/` outside of `config_loader.py` itself and test mocks
- All migrated scripts use `load_config()` from `library.config_loader`
- `test_code/CLAUDE.md` updated to reflect new pattern

**Priority:** LOW — `test_code/` scripts are experimental; sherlock library files are medium priority
**Status:** backlog
**Related:** [B-79](#b-79-migrate-standalone-scripts-to-config_loader)

---

## Backlog: Security — CodeQL & SAST Findings

### B-86: Triage CodeQL Clear-Text Logging Alerts (12 HIGH)

As a **developer**,
I want to review and resolve CodeQL "clear-text logging of sensitive data" alerts,
so that actual credential leaks are fixed and false positives are properly suppressed.

**Origin:** First CodeQL scan (2026-03-05) — 12 HIGH alerts of rule `py/clear-text-logging-sensitive-data`.

**Alerts to review (12):**

| # | File | Line | Assessment |
|---|------|------|------------|
| 3,4,5 | `shared_python/unified-config-loader/.../aws.py` | 30, 48, 52 | Logs SSM parameter **names** (paths like `/lenie/dev/db_host`), not values. **Likely false positive** — but verify each `logging.info()` call. |
| 6,7 | `shared_python/unified-config-loader/.../config.py` | 62, 101 | Logs config key names being loaded. **Likely false positive.** |
| 10 | `shared_python/unified-config-loader/.../vault.py` | 44 | Logs Vault path. **Verify** — could log secret value if variable naming is ambiguous. |
| 8 | `scripts/gitguardian_manage_incidents.py` | 203 | **Verify** — script handles incident data, may log token/secret info. |
| 9 | `backend/scripts/notion_changelog.py` | 141 | **Verify** — may log Notion API token. |
| 11,12,13 | `backend/imports/unknown_news_import.py` | 77, 90, 95 | **Verify** — import script, check what is logged. |
| 14 | `backend/test_code/vault_tests.py` | 80 | Logs Vault secret values for debugging. **True positive** in test code — low risk but should be suppressed or removed. |

**How to suppress false positives in CodeQL:**

1. **Per-alert dismissal** (recommended for individual false positives):
   ```bash
   gh api repos/{owner}/{repo}/code-scanning/alerts/{alert_number} \
     -X PATCH -f state=dismissed -f dismissed_reason="false_positive" \
     -f dismissed_comment="Logs parameter name/path, not secret value"
   ```

2. **CodeQL config file** (recommended for excluding paths like `test_code/`):
   Create `.github/codeql/codeql-config.yml`:
   ```yaml
   paths-ignore:
     - backend/test_code
   ```
   Then reference it in `.github/workflows/codeql.yml`:
   ```yaml
   - name: Initialize CodeQL
     uses: github/codeql-action/init@v3
     with:
       languages: ${{ matrix.language }}
       config-file: .github/codeql/codeql-config.yml
   ```

3. **Disable specific rule globally** (NOT recommended — rule catches real issues):
   ```yaml
   # in codeql-config.yml
   query-filters:
     - exclude:
         id: py/clear-text-logging-sensitive-data
   ```

**Acceptance Criteria:**
- Each of the 12 alerts is reviewed and categorized as true positive or false positive
- True positives are fixed (remove secret logging or mask values)
- False positives are dismissed via GitHub API with explanation
- `test_code/` path excluded from CodeQL scanning via config file

**Priority:** MEDIUM — no actual secrets are being leaked (initial assessment), but alerts should be triaged
**Status:** backlog

---

### B-87: Fix Stack Trace Exposure in server.py Error Handlers (7 MEDIUM)

As a **developer**,
I want error handlers in `server.py` to return generic error messages instead of raw exception details,
so that stack traces and internal implementation details are not exposed to API consumers.

**Origin:** CodeQL scan (2026-03-05) — 7 MEDIUM alerts of rule `py/stack-trace-exposure`.

**Affected lines in `backend/server.py`:** 189, 204, 222, 237, 277, 285, 682

**Current pattern:**
```python
except Exception as e:
    return jsonify({"error": str(e)}), 500
```

**Proposed fix:**
```python
except Exception as e:
    logging.exception("Error in endpoint_name")
    return jsonify({"error": "Internal server error"}), 500
```

For development, keep detailed errors behind a `DEBUG` flag:
```python
except Exception as e:
    logging.exception("Error in endpoint_name")
    if cfg.require("DEBUG", "false").lower() == "true":
        return jsonify({"error": str(e)}), 500
    return jsonify({"error": "Internal server error"}), 500
```

**Acceptance Criteria:**
- All `except` blocks in `server.py` return generic error messages in production
- Full exception details are logged server-side via `logging.exception()`
- DEBUG mode still returns detailed errors for development
- CodeQL alerts resolve after fix

**Priority:** MEDIUM — API is behind `x-api-key` auth, but good practice
**Status:** backlog

---

### B-88: Review Reflected XSS Alerts in server.py (8 MEDIUM)

As a **developer**,
I want to verify that Flask endpoints in `server.py` are not vulnerable to reflected XSS,
so that CodeQL alerts are resolved — either by fixing real issues or dismissing false positives.

**Origin:** CodeQL scan (2026-03-05) — 8 MEDIUM alerts of rule `py/reflective-xss`.

**Affected lines in `backend/server.py`:** 364, 428, 462, 467, 519, 569, 603, 674

**Assessment needed:**
- All endpoints return `jsonify()` responses (Content-Type: `application/json`)
- JSON responses are generally not vulnerable to reflected XSS because browsers don't render them as HTML
- If all responses use `jsonify()`, these are **likely false positives**
- However, verify that no endpoint returns raw `str` or `make_response()` with HTML content-type

**How to suppress if confirmed false positive:**
```bash
# Per-alert dismissal
gh api repos/{owner}/{repo}/code-scanning/alerts/{alert_number} \
  -X PATCH -f state=dismissed -f dismissed_reason="false_positive" \
  -f dismissed_comment="Endpoint returns application/json via jsonify(), not rendered as HTML"
```

**Acceptance Criteria:**
- Each of the 8 alerts is reviewed — verify response Content-Type
- True positives fixed (add escaping or ensure JSON response)
- False positives dismissed with explanation

**Priority:** MEDIUM — API returns JSON, likely false positives, but should be verified
**Status:** backlog

---

### B-89: Fix ReDoS Vulnerability in webdocument_prepare_regexp_by_ai.py

As a **developer**,
I want to fix the regular expression with exponential backtracking risk,
so that the application is not vulnerable to ReDoS (Regular Expression Denial of Service).

**Origin:** CodeQL scan (2026-03-05) — 1 HIGH alert of rule `py/redos` at line 36.

**Details:** The regex pattern may cause exponential backtracking on strings starting with `\n` and containing many repetitions of `\n`.

**Acceptance Criteria:**
- Regex is rewritten to avoid catastrophic backtracking
- Unit test added to verify regex works on edge cases (long strings with many newlines)
- CodeQL alert resolves after fix

**Priority:** HIGH — ReDoS can cause application hangs with crafted input
**Status:** backlog

---

### B-90: Add Timeout to All requests Calls (6 locations)

As a **developer**,
I want all `requests.get()` and `requests.post()` calls to include a `timeout` parameter,
so that the application does not hang indefinitely on unresponsive external services.

**Origin:** Bandit scan (2026-03-05) — 6 MEDIUM alerts of rule B113.

**Affected files:**
1. `backend/library/api/cloudferro/sherlock/sherlock_embedding.py:40` — `requests.post()` (production)
2. `backend/library/website/website_download_context.py:18` — `requests.get()` (production)
3. `backend/library/youtube_processing.py:272` — `requests.get()` (production)
4. `backend/imports/unknown_news_import.py:44` — `requests.get()` (import script)
5. `backend/test_code/cloudferro_ark_labs_models.py:30,52` — `requests.get()` (test code)
6. `backend/test_code/cloudferro_embeddings.py:38` — `requests.post()` (test code)

**Fix:** Add `timeout=30` (or appropriate value) to each call.

**Acceptance Criteria:**
- All `requests` calls in `backend/` have explicit `timeout=` parameter
- No new Bandit B113 alerts

**Priority:** MEDIUM — production code (items 1-3) should be fixed soon; test code is lower priority
**Status:** backlog

---

### B-91: Migrate SQL F-Strings to Parameterized Queries

As a **developer**,
I want SQL queries in `stalker_web_documents_db_postgresql.py` to use parameterized queries instead of f-strings,
so that the code follows security best practices and SAST tools stop flagging SQL injection risks.

**Origin:** Semgrep (22 findings) + Bandit (11 findings) + CodeQL scan (2026-03-05). All three tools flag the same pattern.

**Risk assessment:**
- Most f-strings interpolate Python enum `.name` attributes (e.g., `StalkerDocumentStatus.URL_ADDED.name`) — these are **not user-controlled** and are safe
- However, some queries interpolate function parameters: `embedding`, `model`, `url`, `min` — these could be risky if upstream validation is missing
- **Highest risk locations:** lines 358-363 (`min` param), 387-392 (`url` param)

**Scope:**
1. `backend/library/stalker_web_documents_db_postgresql.py` — ~15 queries
2. `backend/library/stalker_web_document_db.py` — 1 query
3. `backend/imports/dynamodb_sync.py` — 1 query

**Acceptance Criteria:**
- All SQL queries use `%s` placeholders with parameter tuples
- Semgrep/Bandit/CodeQL scans show 0 SQL injection alerts
- All existing unit tests pass
- Integration tests pass against test database

**Priority:** LOW — enum `.name` interpolation is safe in practice; parameterized queries are better practice but not urgent
**Status:** superseded by [B-92](#b-92-migrate-database-layer-to-sqlalchemy-orm--pydantic-schemas) — SQLAlchemy uses parameterized queries by default
**Related:** [B-85](#b-85-migrate-remaining-test_code-and-library-scripts-to-config_loader)

---

### B-92: Migrate Database Layer to SQLAlchemy ORM + Pydantic Schemas

As a **developer**,
I want the database layer to use SQLAlchemy ORM instead of raw psycopg2,
so that adding a column requires only one field definition instead of manual changes in 5+ places (SELECT, INSERT, UPDATE, dict, clean, model).

**Origin:** Repeated pain of manual SQL maintenance. Adding `transcript_needed` column required edits in `stalker_web_document.py`, `stalker_web_document_db.py` (SELECT, INSERT, UPDATE, dict, clean), `03-create-table.sql`, and a migration script. See [ADR-004a](../../docs/architecture-decisions.md#adr-004a-migrate-to-sqlalchemy-orm--pydantic-schemas).

**Architecture:**

Two-layer design:
1. **SQLAlchemy 2.x ORM models** (`backend/library/db/models.py`) — `WebDocument`, `WebsiteEmbedding`. Define schema once, SQLAlchemy generates all SQL.
2. **Pydantic v2 schemas** (`backend/library/models/schemas/`) — API response serialization, OpenAPI generation, structured AI outputs. Separate from ORM models.

**Dependencies to add:** `sqlalchemy>=2.0`, `pgvector>=0.3.0`, `alembic>=1.13`

**Scope:**

| File | Change |
|------|--------|
| `backend/library/db/__init__.py` | NEW — package |
| `backend/library/db/engine.py` | NEW — engine, session factory, Base |
| `backend/library/db/models.py` | NEW — WebDocument, WebsiteEmbedding ORM models |
| `backend/library/stalker_web_document.py` | REWRITE — re-export from new model |
| `backend/library/stalker_web_document_db.py` | REWRITE — thin wrapper delegating to WebDocument ORM |
| `backend/library/stalker_web_documents_db_postgresql.py` | REWRITE — SQLAlchemy session queries |
| `backend/server.py` | UPDATE — add session teardown |
| `backend/alembic.ini` | NEW — Alembic config |
| `backend/alembic/env.py` | NEW — Alembic environment |
| `backend/pyproject.toml` | UPDATE — new dependencies |

Consumers (no API changes needed — wrappers preserve signatures):
- `backend/web_documents_do_the_needful_new.py`
- `backend/youtube_add.py`
- `backend/imports/unknown_news_import.py`
- `backend/imports/dynamodb_sync.py`
- `infra/aws/serverless/lambdas/app-server-db/lambda_function.py`
- `infra/aws/serverless/lambdas/sqs-into-rds/lambda_function.py`

**Acceptance Criteria:**
- All existing unit tests pass
- All existing integration tests pass
- Adding a new column requires only one field in ORM model + `alembic revision --autogenerate`
- `dict()` serialization produces identical output to current implementation
- pgvector similarity search (`get_similar()`) works unchanged
- `.venv_wsl` synced with new dependencies

**Supersedes:** [B-91](#b-91-migrate-sql-f-strings-to-parameterized-queries) — SQLAlchemy uses parameterized queries by default
**Enables:** [B-50](#b-50-api-type-synchronization-pipeline-pydantic--openapi--typescript) Phase 1 (Pydantic schemas)
**Priority:** MEDIUM
**Status:** backlog
**Plan:** [`.claude/exports/plan-sqlalchemy-migration.md`](../../.claude/exports/plan-sqlalchemy-migration.md)

---

## Epic 30: Database Lookup Tables & Search Extensions

Introduce database-level enum enforcement via lookup tables with FK constraints (matching AWS production schema), and add PostgreSQL search extensions (`unaccent`, `pg_trgm`) for Polish name/city search. Prepares the database for personal CRM capabilities.

**Related ADRs:** [ADR-009](../../docs/architecture-decisions.md#adr-009-postgresql-search-strategy--unaccent--pg_trgm-for-structured-fields-embeddings-for-content), [ADR-010](../../docs/architecture-decisions.md#adr-010-database-lookup-tables-with-foreign-keys-for-enum-like-fields)

### B-94: Create Lookup Tables and Seed Data

As a **developer**,
I want lookup tables (`document_status_types`, `document_status_error_types`, `document_types`, `embedding_models`) created in the database with seed data from Python enums,
so that valid values are defined at the database level, not just in application code.

**Origin:** AWS production database already has these tables (visible in dump from 2026-01-23). Docker init scripts do not create them, causing schema divergence. See [ADR-010](../../docs/architecture-decisions.md#adr-010-database-lookup-tables-with-foreign-keys-for-enum-like-fields).

**Scope:**
- Add new init script (e.g., `backend/database/init/09-create-lookup-tables.sql`) creating 4 lookup tables
- Seed with values from `StalkerDocumentStatus` (16), `StalkerDocumentStatusError` (17), `StalkerDocumentType` (6)
- Seed `embedding_models` with currently used models (ada-002, titan-v1, titan-v2, stella, bge-m3, bge-gemma2, e5-mistral)
- Create Alembic migration for existing databases

**Acceptance Criteria:**
- All 4 lookup tables exist after `docker compose up` (fresh volume)
- `SELECT count(*) FROM document_status_types` returns 16
- `SELECT count(*) FROM document_types` returns 6
- Alembic migration applies cleanly to existing Docker database
- Alembic migration applies cleanly to AWS RDS (via VPN)

**Priority:** MEDIUM
**Status:** backlog

### B-95: Add Foreign Key Constraints to web_documents and websites_embeddings

As a **developer**,
I want FK constraints on `document_state`, `document_state_error`, `document_type`, and `embedding model` columns,
so that the database rejects invalid values and matches the AWS production schema.

**Origin:** [ADR-010](../../docs/architecture-decisions.md#adr-010-database-lookup-tables-with-foreign-keys-for-enum-like-fields). Depends on [B-94](#b-94-create-lookup-tables-and-seed-data).

**Scope:**
- Add FK constraints in init script (e.g., `backend/database/init/10-add-foreign-keys.sql`)
- Create Alembic migration for existing databases
- Verify no orphaned values exist before adding constraints (clean up if needed)

**Acceptance Criteria:**
- `INSERT INTO web_documents (..., document_state, ...) VALUES (..., 'INVALID_STATE', ...)` fails with FK violation
- `INSERT INTO web_documents (..., document_type, ...) VALUES (..., 'podcast', ...)` fails with FK violation
- All existing data passes FK validation (no orphaned values)
- All unit and integration tests pass

**Depends on:** [B-94](#b-94-create-lookup-tables-and-seed-data)
**Priority:** MEDIUM
**Status:** backlog

### B-96: Update SQLAlchemy ORM Models for Lookup Table Relationships

As a **developer**,
I want the SQLAlchemy ORM models to use `ForeignKey` + `relationship()` for enum-like fields instead of `SAEnum(..., native_enum=False)`,
so that the ORM reflects the actual database schema and enables JOIN queries on lookup tables.

**Origin:** [ADR-010](../../docs/architecture-decisions.md#adr-010-database-lookup-tables-with-foreign-keys-for-enum-like-fields). Depends on [B-95](#b-95-add-foreign-key-constraints-to-web_documents-and-websites_embeddings).

**Scope:**
- Create SQLAlchemy ORM models for 4 lookup tables (`DocumentStatusType`, `DocumentStatusErrorType`, `DocumentType`, `EmbeddingModel`)
- Update `WebDocument` model: replace `SAEnum` columns with `String` + `ForeignKey('document_types.name')`
- Update `WebsiteEmbedding` model: add `ForeignKey('embedding_models.name')` to `model` column
- Add startup sync: on app start, verify Python enum values match lookup table rows (log warnings for mismatches)

**Acceptance Criteria:**
- `WebDocument.document_type` has FK relationship to `DocumentType` model
- `session.query(DocumentStatusType).all()` returns all 16 states
- All existing unit and integration tests pass
- Adding a new enum value + Alembic migration seeds it into lookup table

**Depends on:** [B-95](#b-95-add-foreign-key-constraints-to-web_documents-and-websites_embeddings)
**Priority:** MEDIUM
**Status:** backlog

### B-97: Install unaccent and pg_trgm Extensions on Existing Databases

As a **developer**,
I want `unaccent` and `pg_trgm` PostgreSQL extensions installed on all database environments (Docker, NAS, AWS RDS),
so that diacritic-insensitive and fuzzy search is available for future CRM features.

**Origin:** [ADR-009](../../docs/architecture-decisions.md#adr-009-postgresql-search-strategy--unaccent--pg_trgm-for-structured-fields-embeddings-for-content). Init scripts already updated (`02-create-extension.sql`), but existing databases need manual migration.

**Scope:**
- Run `CREATE EXTENSION IF NOT EXISTS unaccent; CREATE EXTENSION IF NOT EXISTS pg_trgm;` on:
  - Docker local database (port 5433)
  - NAS Docker database
  - AWS RDS (via VPN)
- Verify extensions are installed: `SELECT extname FROM pg_extension;`

**Acceptance Criteria:**
- `SELECT unaccent('Łódź')` returns `Lodz` on all three environments
- `SELECT similarity('Warszawa', 'Warszawie')` returns a value > 0.3 on all three environments
- No errors in application logs after extension installation

**Priority:** MEDIUM
**Status:** backlog

---

### B-93: Synchronize Document States from Backend to Frontend

As a **developer**,
I want the list of document states in the frontend to be fetched from the backend API instead of hardcoded,
so that adding a new state (like `TEMPORARY_ERROR`) doesn't require manual frontend updates and rebuilds.

**Origin:** Frontend `list.tsx` had a hardcoded subset of 5 document states (out of 16). Adding `TEMPORARY_ERROR` required a manual edit. Same applies to `document_type` and `document_state_error` enums.

**Current state:** `StalkerDocumentStatus` enum is defined in `backend/library/models/stalker_document_status.py` (16 values). Frontend `list.tsx` duplicates a subset as `<option>` elements.

**Proposed solution:**

1. Add `GET /document_states` endpoint in `server.py` returning `{"states": ["ERROR", "TEMPORARY_ERROR", ...], "types": ["webpage", "link", ...]}` from the Python enums
2. Frontend fetches available states on mount and populates `<select>` dynamically
3. Optionally cache in `localStorage` to avoid extra request on every page load

**Acceptance Criteria:**
- `GET /document_states` returns all values from `StalkerDocumentStatus` and `StalkerDocumentType`
- Frontend `list.tsx` populates state and type dropdowns from API response
- Adding a new enum value in backend automatically appears in frontend without code change
- Existing filter behavior unchanged

**Priority:** LOW
**Status:** backlog
