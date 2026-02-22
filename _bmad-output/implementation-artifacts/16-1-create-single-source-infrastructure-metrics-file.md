# Story 16.1: Create Single-Source Infrastructure Metrics File

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **developer**,
I want to create a single authoritative metrics file and fix all discrepancies across documentation,
So that infrastructure counts (endpoints, templates, Lambda functions) are accurate and consistent everywhere.

## Acceptance Criteria

1. **Given** infrastructure metrics are duplicated across 7+ files with known discrepancies, **When** the developer creates `docs/infrastructure-metrics.md`, **Then** the file contains authoritative counts organized by deployment perspective:
   - Flask Server (Docker/Kubernetes): endpoint count and list
   - AWS Serverless (Lambda + API Gateway): endpoints per gateway (api-gw-app: 11, api-gw-infra: 7, url-add: 1), Lambda function count and list
   - CloudFormation: template count in deploy.ini, total template file count

2. **Given** the metrics file is created with post-consolidation values (2 API Gateway templates + url-add.yaml with own REST API = 3 REST APIs total, /url_add in api-gw-app), **When** the developer reviews each of the 7+ documentation files, **Then** all discrepancies are fixed in: `CLAUDE.md`, `README.md`, `backend/CLAUDE.md`, `docs/index.md`, `docs/api-contracts-backend.md`, `infra/aws/CLAUDE.md`, `infra/aws/cloudformation/CLAUDE.md` **And** each file either references `docs/infrastructure-metrics.md` as the source of truth or uses consistent correct values

3. **Given** all files are updated, **When** the developer compares documented counts against actual infrastructure, **Then** zero discrepancies exist between any documentation file and the actual state

## Tasks / Subtasks

- [x] Task 1: Audit actual infrastructure counts (AC: #1)
  - [x] 1.1: Count Flask server.py endpoints (all routes including health checks)
  - [x] 1.2: Count api-gw-app.yaml endpoint paths from OpenAPI Body
  - [x] 1.3: Count api-gw-infra.yaml endpoint paths from OpenAPI Body
  - [x] 1.4: Count url-add.yaml endpoint paths
  - [x] 1.5: Count Lambda functions defined in CF templates (deployed via deploy.ini)
  - [x] 1.6: Count Lambda functions referenced but not CF-managed (lenie_2_db, lenie_2_internet)
  - [x] 1.7: Count CloudFormation templates in deploy.ini [dev] section
  - [x] 1.8: Count total .yaml template files in templates/ directory
- [x] Task 2: Create `docs/infrastructure-metrics.md` (AC: #1)
  - [x] 2.1: Write Flask Server section with endpoint count and list
  - [x] 2.2: Write AWS Serverless section with API Gateway endpoints per gateway
  - [x] 2.3: Write AWS Serverless section with Lambda function list (CF-managed + non-CF)
  - [x] 2.4: Write CloudFormation section with template counts
  - [x] 2.5: Add verification date and methodology notes
- [x] Task 3: Fix discrepancies across 7 documentation files (AC: #2)
  - [x] 3.1: Fix `CLAUDE.md` — update endpoint count (18 → 19)
  - [x] 3.2: Fix `README.md` — update endpoint count (18 → 19)
  - [x] 3.3: Fix `backend/CLAUDE.md` — update endpoint count and list
  - [x] 3.4: Fix `docs/index.md` — update endpoint count
  - [x] 3.5: Fix `docs/api-contracts-backend.md` — update endpoint count and clarify root `/`
  - [x] 3.6: Fix `infra/aws/CLAUDE.md` — update Lambda count, template count, API GW endpoint counts
  - [x] 3.7: Fix `infra/aws/cloudformation/CLAUDE.md` — update template list and counts
  - [x] 3.8: Fix `docs/source-tree-analysis.md` — update endpoint count (18 → 19)
  - [x] 3.9: Fix `docs/project-overview.md` — update endpoint count (18 → 19)
  - [x] 3.10: Fix `docs/architecture-backend.md` — update endpoint count and category count
- [x] Task 4: Verify zero discrepancies (AC: #3)
  - [x] 4.1: Cross-check all updated files against actual infrastructure counts
  - [x] 4.2: Verify consistency between docs/infrastructure-metrics.md and all other files
  - [x] 4.3: Grep verification — confirmed no remaining "18 endpoints" in active documentation

## Dev Notes

### Verified Actual Infrastructure Counts (as of 2026-02-21)

**Flask Server (`backend/server.py`):**
- **19 routes** total (including root `/` and `/version`)
- Functional endpoints: `/url_add`, `/website_list`, `/website_is_paid`, `/website_get`, `/website_get_next_to_correct`, `/ai_get_embedding`, `/website_similar`, `/website_download_text_content`, `/website_text_remove_not_needed`, `/website_split_for_embedding`, `/website_delete`, `/website_save` (12 business endpoints)
- Operational: `/` (root/info), `/healthz`, `/metrics`, `/startup`, `/readiness`, `/liveness`, `/version` (7 operational endpoints)
- All routes except health checks require `x-api-key` header
- Auth-exempt paths: `/startup`, `/readiness`, `/liveness`, `/version`

**AWS API Gateway — api-gw-app.yaml (11 unique paths):**
`/website_list` (GET), `/website_get` (GET), `/website_save` (POST), `/website_delete` (GET+POST), `/website_is_paid` (POST), `/website_get_next_to_correct` (GET), `/website_similar` (POST), `/website_split_for_embedding` (POST), `/website_download_text_content` (POST), `/ai_embedding_get` (POST), `/url_add` (POST)
- Note: `/website_delete` exposes both GET and POST methods
- Each path also has OPTIONS for CORS (not counted as functional endpoints)

**AWS API Gateway — api-gw-infra.yaml (7 unique paths):**
`/infra/sqs/size` (GET), `/infra/vpn_server/start` (POST), `/infra/vpn_server/stop` (POST), `/infra/vpn_server/status` (GET), `/infra/database/start` (POST), `/infra/database/stop` (POST), `/infra/database/status` (GET)

**AWS API Gateway — url-add.yaml (1 path):**
`/url_add` (POST) — standalone REST API (`lenie_dev_add_from_chrome_extension`)

**Lambda Functions (12 total in AWS):**
- CF-managed via deploy.ini (10):
  - `api-gw-infra.yaml`: sqs-size, rds-start, rds-stop, rds-status, ec2-status, ec2-start, ec2-stop (7)
  - `sqs-to-rds-lambda.yaml`: sqs-to-rds-lambda (1)
  - `lambda-weblink-put-into-sqs.yaml`: weblink-put-into-sqs (1)
  - `url-add.yaml`: url-add (1)
- Non-CF-managed, referenced by api-gw-app.yaml (2):
  - `lenie_2_db` — handles DB endpoints (inside VPC)
  - `lenie_2_internet` — handles internet endpoints (outside VPC)
- Not deployed (template exists but NOT in deploy.ini):
  - `lambda-rds-start.yaml` — superseded by RdsStartFunction in api-gw-infra.yaml

**CloudFormation Templates:**
- deploy.ini [dev] section: **26 templates**
- Total .yaml files in templates/ directory: **33 files** (includes 7 not in deploy.ini: identityStore, organization, 3 SCP templates, lambda-rds-start, rds)

### Known Discrepancies to Fix

| File | Current Value | Actual Value | Issue |
|------|--------------|--------------|-------|
| `CLAUDE.md` | "18 endpoints" | 19 routes | Missing `/version` endpoint |
| `README.md` | "18 endpoints" | 19 routes | Same |
| `backend/CLAUDE.md` | "18 REST API endpoints" | 19 routes | Same |
| `docs/index.md` | "18 endpoints" | 19 routes | Same |
| `docs/api-contracts-backend.md` | "18 endpoints (plus root `/`)" | 19 routes | Ambiguous wording — 18+1=19 but not clearly stated |
| `infra/aws/CLAUDE.md` | "34 templates", "11 functions" | 26 in deploy.ini / 33 total, 12 Lambda functions | Template count unclear (34 vs actual), Lambda count off by 1 |
| `infra/aws/cloudformation/CLAUDE.md` | Various counts | Various | Needs alignment with metrics file |

### Architecture Pattern (from architecture.md)

The metrics file MUST be organized by **deployment perspective**, not by resource type:
1. **Flask Server (Docker / Kubernetes)** — endpoints available in local/Docker/K8s deployment
2. **AWS Serverless (Lambda + API Gateway)** — endpoints available in AWS deployment
3. **CloudFormation** — IaC template inventory

**Key distinction:** Some Flask endpoints don't exist in AWS Lambda (e.g., `/website_text_remove_not_needed`, health checks), and all infra endpoints exist only in AWS (not in Flask). The metrics file must make this clear.

**Endpoints only in Flask server.py (not in AWS Lambda):**
`/url_add` (replaced by SQS flow), `/website_text_remove_not_needed`, `/healthz`, `/metrics`, `/startup`, `/readiness`, `/liveness`, `/version`, `/` (root)

**Endpoints only in AWS (not in Flask):**
All 7 infra endpoints (`/infra/*`)

### Documentation Update Strategy

Two options for fixing the 7+ documentation files:
- **Option A:** Each file references `docs/infrastructure-metrics.md` as the canonical source (e.g., "See [Infrastructure Metrics](docs/infrastructure-metrics.md) for current counts")
- **Option B:** Each file uses correct inline values consistent with the metrics file

**Recommended approach:** Use Option B (inline correct values) for key files like `CLAUDE.md` and `README.md` where counts appear in context, but add a note pointing to `docs/infrastructure-metrics.md` as the authoritative source. This avoids forcing readers to open another file for basic information.

### Project Structure Notes

- New file: `docs/infrastructure-metrics.md` — single source of truth
- Modified files (10): `CLAUDE.md`, `README.md`, `backend/CLAUDE.md`, `docs/index.md`, `docs/api-contracts-backend.md`, `infra/aws/CLAUDE.md`, `infra/aws/cloudformation/CLAUDE.md`, `docs/source-tree-analysis.md`, `docs/project-overview.md`, `docs/architecture-backend.md`
- `docs/` directory already exists with multiple documentation files

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Epic 16, Story 16.1]
- [Source: _bmad-output/planning-artifacts/prd.md#FR29, FR30]
- [Source: _bmad-output/planning-artifacts/architecture.md#Documentation Metrics File Pattern (B-19)]
- [Source: _bmad-output/planning-artifacts/prd.md#NFR13, NFR14, NFR15]
- [Source: _bmad-output/planning-artifacts/prd.md#API Gateway Architecture Principle]

### Git Intelligence

Recent commits (Sprint 4):
- `e72235d` feat: complete Epic 15 — API Gateway consolidation, retro, and PRD fix (Story 15-3)
- `bcee6dd` feat: update client apps to consolidated API Gateway (Story 15-2)
- `08a755b` feat: merge /url_add endpoint into api-gw-app.yaml (Story 15-1)
- `00069d5` fix: remove stale Elastic IP references from docs and template description (Story 14-1 review)
- `edc94c6` fix: consolidate rds-start Lambda and remove git-webhooks endpoint (Story 14-2)

**Key insight:** Epic 15 consolidated API Gateway — post-consolidation state is current. All infrastructure changes from Sprints 1-4 (Epics 1-15) are complete. Story 16.1 documents the final state.

## Dev Agent Record

### Agent Model Used
Claude Opus 4.6

### Debug Log References
N/A (documentation-only story, no debugging required)

### Completion Notes List
- Created `docs/infrastructure-metrics.md` as single source of truth for all infrastructure counts
- Fixed endpoint count discrepancy (18 → 19) across 10 documentation files — the root `/` endpoint was consistently excluded from prior counts
- Fixed Lambda function count (11 → 12) in `infra/aws/CLAUDE.md` — non-CF-managed functions were undercounted
- Fixed CloudFormation template count (34 → 26 in deploy.ini / 33 total) in `infra/aws/CLAUDE.md`
- Updated `api-gw-app.yaml` description in `infra/aws/cloudformation/CLAUDE.md` — clarified it defines Lambda Permissions, not Lambdas
- Added `docs/infrastructure-metrics.md` link to `docs/index.md` under new "Operations & Metrics" section
- Found and fixed 3 additional files beyond the 7 in the story scope: `docs/source-tree-analysis.md`, `docs/project-overview.md`, `docs/architecture-backend.md`
- Verified via grep: no remaining "18 endpoints" references in active documentation (remaining are in historical _bmad-output artifacts)
- Unit tests: 6 pre-existing failures (markdown/transcript tests), 16 passed — no regressions from documentation changes
- **[Code Review]** Fixed `docs/architecture-backend.md` category breakdown: removed ghost endpoint `website_exist`, corrected 5 categories (5+3+2+2+7=19), added missing `/` root and `/metrics`
- **[Code Review]** Fixed `docs/infrastructure-metrics.md` "Flask vs AWS" section: `/url_add` exists in both (different implementation), separated from Flask-only endpoints
- **[Code Review]** Fixed story Dev Notes: "Modified files (7)" → "(10)"

### File List
- `docs/infrastructure-metrics.md` (NEW) — single source of truth for infrastructure counts
- `CLAUDE.md` — updated endpoint count 18 → 19, added reference to metrics file
- `README.md` — updated endpoint count 18 → 19
- `backend/CLAUDE.md` — updated endpoint count 18 → 19, added root `/` to Health & Info table
- `docs/index.md` — updated endpoint count 18 → 19, added infrastructure-metrics.md link
- `docs/api-contracts-backend.md` — clarified "19 endpoints (including root /)"
- `infra/aws/CLAUDE.md` — updated template count, Lambda count, API GW counts
- `infra/aws/cloudformation/CLAUDE.md` — updated api-gw-app.yaml description
- `docs/source-tree-analysis.md` — updated endpoint count 18 → 19
- `docs/project-overview.md` — updated endpoint count 18 → 19
- `docs/architecture-backend.md` — updated endpoint count 18 → 19, category count 4 → 5
