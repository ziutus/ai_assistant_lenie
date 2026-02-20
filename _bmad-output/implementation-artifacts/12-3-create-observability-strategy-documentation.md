# Story 12.3: Create Observability Strategy Documentation

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **developer**,
I want to create a `docs/observability.md` document describing the project's logging, tracing, and monitoring strategy,
So that the observability approach is documented, consistent across environments (AWS, Kubernetes, GCloud), and serves as a standard for future development.

## Acceptance Criteria

1. **AC1 — Create `docs/observability.md`:** Document covers all five required sections:
   - Current state — what logging/tracing exists today per environment (AWS Lambda CloudWatch JSON logs, API Gateway logging/X-Ray, Flask basic Python logging, frontend monitoring status)
   - Logging standards — log levels convention (when to use DEBUG/INFO/WARN/ERROR), structured logging format (JSON), required fields per log entry (timestamp, request_id, user_id, action)
   - Per-environment configuration — AWS (CloudWatch, X-Ray), Docker/local (stdout/stderr), Kubernetes (future: stdout to aggregator), GCloud (future: Cloud Logging)
   - Tools inventory — installed but unused tools (X-Ray SDK, Langfuse, Prometheus `/metrics` endpoint) with activation plan or removal decision
   - Request audit trail — strategy for logging user actions (API requests with method, path, status, response time, API key identity)

2. **AC2 — Link in documentation index:** `docs/index.md` includes a reference to the new `observability.md` document in the appropriate section.

## Tasks / Subtasks

- [x] **Task 1: Create `docs/observability.md`** (AC: #1)
  - [x] 1.1 Write "Current State" section — inventory all existing logging/tracing per environment
  - [x] 1.2 Write "Logging Standards" section — define log level conventions and structured format
  - [x] 1.3 Write "Per-Environment Configuration" section — document each environment's observability stack
  - [x] 1.4 Write "Tools Inventory" section — catalog installed-but-unused tools with decisions
  - [x] 1.5 Write "Request Audit Trail" section — define strategy for API request logging
- [x] **Task 2: Update `docs/index.md`** (AC: #2)
  - [x] 2.1 Add `observability.md` link in the Operations section of the documentation index

## Dev Notes

### This is a Documentation-Only Story

No code changes are required. The deliverable is a markdown document (`docs/observability.md`) describing the current state and desired standard. Implementation of missing observability features (X-Ray instrumentation, structured Flask logging, Prometheus metrics) would be separate stories in a future sprint.

### Current Observability State — Comprehensive Inventory

The project has **minimal and fragmented observability**. Below is the complete inventory that the document must accurately describe.

#### Backend Logging (`backend/`)

| Component | File | Log Level | Format | Structured? |
|-----------|------|-----------|--------|-------------|
| Flask server | `server.py:7,18` | INFO | Default Python (`logging.basicConfig`) | No |
| YouTube processing | `library/youtube_processing.py:5,23` | N/A (module logger) | Default Python | No |
| Language detection | `library/text_detect_language.py:5` | N/A (module logger) | Default Python | No |
| YouTube file | `library/stalker_youtube_file.py:11` | N/A (module logger) | Default Python | No |
| Batch: youtube_add | `youtube_add.py:37` | Configurable | `%(asctime)s %(levelname)s %(name)s: %(message)s` | No |
| Batch: do_the_needful | `web_documents_do_the_needful_new.py:22` | INFO | Default Python | No |
| Batch: md_decode | `webdocument_md_decode.py:20-21` | DEBUG | Default Python | No |
| Batch: regexp_by_ai | `webdocument_prepare_regexp_by_ai.py:21-22` | DEBUG | Default Python | No |

**Key finding:** No structured logging (JSON), no request ID tracking, no correlation IDs anywhere in the backend.

#### Lambda Function Logging

| Lambda | File | Logging? | Format | Notes |
|--------|------|----------|--------|-------|
| sqs-weblink-put-into | `lambdas/sqs-weblink-put-into/lambda_function.py:7-10` | YES | Python + `extra` dict | Best practice — partial structured logging via `extra` parameter |
| sqs-into-rds | `lambdas/sqs-into-rds/lambda_function.py:3,5-6` | YES | Python logger | Basic info messages |
| app-server-db | `lambdas/app-server-db/lambda_function.py:2,13` | YES | Python basicConfig(DEBUG) | Extensive but unstructured |
| app-server-internet | `lambdas/app-server-internet/lambda_function.py:4,11` | YES | Python basicConfig(DEBUG) | Basic debug/error |
| rds-start/stop/status | `lambdas/rds-*/lambda_function.py` | **NO** | N/A | No logging at all |
| ec2-start/stop/status | `lambdas/ec2-*/lambda_function.py` | **NO** | N/A | No logging at all |
| sqs-size | `lambdas/sqs-size/lambda_function.py` | **NO** | N/A | No logging at all |

**Key finding:** 7 infrastructure Lambdas have ZERO logging. Document processing Lambdas have basic logging.

#### CloudFormation-Level Observability

| Resource | Template | Configuration | Status |
|----------|----------|--------------|--------|
| API Gateway app stage | `api-gw-app.yaml:589-598` | TracingEnabled: true, LoggingLevel: INFO, MetricsEnabled: true, DataTraceEnabled: true | Active (codified in Story 11-10) |
| API Gateway infra Lambdas | `api-gw-infra.yaml:54-56,81-84,...` | LoggingConfig: JSON format, INFO level | Active — 7 Lambda LoggingConfig blocks |
| API Gateway infra stage | `api-gw-infra.yaml` | No StageDescription logging | **Not configured** |
| API Gateway url-add | `api-gw-url-add.yaml` | No stage logging/tracing | **Not configured** |
| Step Function | `sqs-to-rds-step-function.yaml` | CloudWatch execution monitoring | Active |

#### Installed-But-Unused Tools

| Tool | Location | Status | Decision Needed |
|------|----------|--------|-----------------|
| **aws-xray-sdk** | `pyproject.toml:63` (docker extra) | Dependency installed, **NOT used** in any application code | Activate or remove? |
| **Langfuse** | `pyproject.toml:32` (base dep), `library/api/openai/openai_my.py:5` (commented import) | Dependency installed, **import commented out** | Activate for LLM tracing or remove? |
| **Prometheus `/metrics`** | `server.py:695-697` | Endpoint exists but implementation is `pass` (stub) | Implement with prometheus_client or remove stub? |
| **AWS RUM** | Removed in Story 5-2 | **Completely removed** | No action needed — document removal for posterity |

#### Environments Summary

| Environment | Logging | Tracing | Metrics | Monitoring |
|-------------|---------|---------|---------|------------|
| **AWS Lambda** | CloudWatch (JSON for infra Lambdas, basic for app Lambdas) | X-Ray on API GW app only | CloudWatch built-in | CloudWatch alarms (none configured) |
| **Docker/local** | stdout/stderr (Python logging) | None | `/metrics` stub | None |
| **Kubernetes** | stdout/stderr (Python logging) | None | `/metrics` stub, health probes (`/startup`, `/readiness`, `/liveness`) | None |
| **GCloud** | Future: Cloud Logging | Future | Future | Future |

### Previous Story Intelligence (from Story 12-2)

- Story 12-2 verified all documentation is accurate post-Sprint 3
- cfn-lint passes with zero errors on all templates
- Story 11-10 codified API Gateway stage logging and tracing in CloudFormation (TracingEnabled, MetricsEnabled, LoggingLevel: INFO, DataTraceEnabled)
- **Warning from 12-2:** `DataTraceEnabled: true` logs full request/response bodies — review for production appropriateness

### Git Intelligence

Recent commits (relevant to observability context):
- `134d03a` — dependency updates (may affect observability tool versions)
- `fec7c1e` — closed epic 10 and 11 (cleanup and CF improvements complete)
- `0cf41b6` — consolidated API Gateway architecture (affects logging surface)
- Story 11-10 added `StageDescription` with `TracingEnabled`, `MetricsEnabled`, `LoggingLevel: INFO` to `api-gw-app.yaml`

### Architecture Compliance

This is a documentation-only story — no architecture compliance constraints apply to the document content itself. However, the document MUST accurately reflect:
- The Gen 2+ canonical template pattern (CloudFormation)
- SSM Parameter Store conventions
- The 8-layer deployment model
- Per-environment deployment differences (Docker, Kubernetes, AWS Lambda)

### Library/Framework Requirements

No libraries or frameworks are needed for this documentation story. The document should reference current versions of:
- Python 3.11 built-in `logging` module
- Flask (no specific version constraint for logging)
- aws-xray-sdk (installed in docker/all extras)
- langfuse (installed in base dependencies)
- prometheus_client (NOT installed — would need to be added if `/metrics` is implemented)

### File Structure Requirements

**Files to create:**
- `docs/observability.md` — new document (the primary deliverable)

**Files to modify:**
- `docs/index.md` — add link to new document in Operations section (after "Code Quality" line ~103)

**No files to delete.**

### Testing Requirements

No automated tests apply to documentation. Manual review:
- Verify all file paths and line numbers referenced in the document are accurate
- Verify all tool names and version references are current
- Verify the document renders correctly in GitHub markdown

### Project Structure Notes

- Document location: `docs/observability.md` — consistent with existing docs pattern (`docs/CI_CD.md`, `docs/Code_Quality.md`, etc.)
- Index update: `docs/index.md` Operations section — follows existing alphabetical/topical ordering

### References

- [Source: `backend/server.py`:7,18,695-697] — Flask logging setup and `/metrics` stub
- [Source: `backend/pyproject.toml`:32,63] — Langfuse and X-Ray SDK dependencies
- [Source: `backend/library/api/openai/openai_my.py`:5] — Commented Langfuse import
- [Source: `infra/aws/cloudformation/templates/api-gw-app.yaml`:589-598] — API Gateway stage logging/tracing
- [Source: `infra/aws/cloudformation/templates/api-gw-infra.yaml`:54-56] — Lambda JSON LoggingConfig
- [Source: `infra/aws/serverless/lambdas/sqs-weblink-put-into/lambda_function.py`:7-10] — Best-practice Lambda logging with `extra` dict
- [Source: `_bmad-output/implementation-artifacts/12-2-cloudformation-validation-and-documentation-update.md`] — Previous story learnings
- [Source: `_bmad-output/implementation-artifacts/11-10-codify-api-gateway-stage-logging-and-tracing.md`] — Story that added API GW observability
- [Source: `_bmad-output/implementation-artifacts/5-2-remove-dead-frontend-monitoring-code.md`] — AWS RUM removal
- [Source: `_bmad-output/planning-artifacts/epics.md`:626-649] — Story 12.3 acceptance criteria
- [Source: `docs/index.md`:98-104] — Operations section where link will be added

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6 (claude-opus-4-6)

### Debug Log References

No debug issues encountered — documentation-only story.

### Completion Notes List

- Created comprehensive `docs/observability.md` covering all 5 required sections (Current State, Logging Standards, Per-Environment Configuration, Tools Inventory, Request Audit Trail)
- All source file references verified against actual codebase before writing (Lambda functions, CloudFormation templates, backend logging, Kubernetes configs)
- Verified 7 infrastructure Lambdas use `print()` statements (not zero output as initially described — they have print-based output but no Python logging module)
- Documented Kubernetes health probe configuration (Helm + Kustomize) which was not explicitly mentioned in Dev Notes but verified during implementation
- Added link to `docs/index.md` Operations section at line 104 (between Code Quality and Python Dependencies)
- Document follows existing docs naming and structure conventions

### Change Log

- 2026-02-18: Created `docs/observability.md` with all 5 AC1 sections; updated `docs/index.md` with link (AC2)
- 2026-02-18: Code review — fixed 6 issues (3 Medium, 3 Low): added Frontend Monitoring subsection (M1), added user_id field to logging standards (M2), corrected /metrics endpoint behavior description (M3), added version note for line numbers (L1), documented /healthz endpoint in Docker section (L2), clarified infra Lambda logging in summary table (L3)

### File List

- `docs/observability.md` — **NEW** — Observability strategy document (primary deliverable)
- `docs/index.md` — **MODIFIED** — Added observability.md link in Operations section (line 104)

## Senior Developer Review (AI)

**Review Date:** 2026-02-18
**Reviewer:** Claude Opus 4.6 (code-review workflow)
**Review Outcome:** Approve (after fixes)

### Summary

Documentation-only story executed accurately. All source file references were verified against the codebase. The dev agent correctly identified and corrected a Dev Notes error (regexp_by_ai log level was DEBUG in notes but INFO in code). Git vs Story File List had zero discrepancies.

### Action Items

- [x] [Medium] M1: Add Frontend Monitoring subsection to Current State (AC1 required "frontend monitoring status")
- [x] [Medium] M2: Add `user_id` field to structured logging format (AC1 required "user_id" in field list)
- [x] [Medium] M3: Correct `/metrics` endpoint description — returns 500 error, not empty response
- [x] [Low] L1: Add version note for line number references
- [x] [Low] L2: Document `/healthz` endpoint in Docker section
- [x] [Low] L3: Clarify infra Lambda logging in Environments Summary table (CF LoggingConfig vs code)
