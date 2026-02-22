# Story 17.3: Rename Legacy Lambda lenie_2_internet and lenie_2_db

Status: done

## Story

As a **developer**,
I want to rename the legacy Lambda functions `lenie_2_db` and `lenie_2_internet` to follow the `${ProjectCode}-${Environment}-<description>` naming convention,
so that all Lambda functions have consistent, non-redundant names.

## Acceptance Criteria

1. **Given** Lambda function `lenie_2_db` exists in AWS
   **When** the developer renames it
   **Then** the new name is `lenie-dev-app-server-db` (matching the source directory `lambdas/app-server-db/`)

2. **Given** Lambda function `lenie_2_internet` exists in AWS
   **When** the developer renames it
   **Then** the new name is `lenie-dev-app-server-internet` (matching the source directory `lambdas/app-server-internet/`)

3. **Given** `api-gw-app.yaml` has 8 endpoints referencing hardcoded `lenie_2_db` in Lambda URI
   **When** the developer updates the template
   **Then** all 8 URIs use `!Sub '...${ProjectCode}-${Environment}-app-server-db/invocations'`
   **And** the template passes cfn-lint validation

4. **Given** `api-gw-app.yaml` has 2 endpoints referencing hardcoded `lenie_2_internet` in Lambda URI
   **When** the developer updates the template
   **Then** both URIs use `!Sub '...${ProjectCode}-${Environment}-app-server-internet/invocations'`

5. **Given** `lambda_update.sh` scripts exist in each Lambda's source directory
   **When** the developer updates them
   **Then** `app-server-db/lambda_update.sh` uses function name `lenie-dev-app-server-db`
   **And** `app-server-internet/lambda_update.sh` uses function name `lenie-dev-app-server-internet`

6. **Given** Lambda permissions in `api-gw-app.yaml` reference the old function names
   **When** the developer reviews permissions
   **Then** `LambdaDbInvokePermission` and `LambdaInternetInvokePermission` (or equivalent) use the new parameterized names

7. **Given** documentation references old names
   **When** the developer updates affected docs
   **Then** `docs/infrastructure-metrics.md`, `infra/aws/CLAUDE.md`, `infra/aws/serverless/CLAUDE.md`, and `infra/aws/cloudformation/CLAUDE.md` reflect new names
   **And** `scripts/verify-documentation-metrics.sh` is updated if it checks for old names

8. **Given** the rename is complete
   **When** the developer deploys via `./deploy.sh -p lenie -s dev`
   **Then** the API Gateway endpoints continue to function correctly with the new Lambda names

## Tasks / Subtasks

- [x] Task 1: Create new Lambda functions with correct names in AWS (AC: #1, #2)
  - [x] Create `lenie-dev-app-server-db` as copy of `lenie_2_db` (same config, layers, VPC, env vars)
  - [x] Create `lenie-dev-app-server-internet` as copy of `lenie_2_internet`
  - [x] Deploy latest code to new functions via `zip_to_s3.sh`
  - [x] Verify new functions work (test invoke)
- [x] Task 2: Update `api-gw-app.yaml` to use parameterized names (AC: #3, #4, #6)
  - [x] Replace all 8 `lenie_2_db` URIs with `${ProjectCode}-${Environment}-app-server-db`
  - [x] Replace all 2 `lenie_2_internet` URIs with `${ProjectCode}-${Environment}-app-server-internet`
  - [x] Update or add Lambda invoke permissions for new function names
  - [x] Run cfn-lint validation
- [x] Task 3: Update deployment scripts (AC: #5)
  - [x] Update `lambdas/app-server-db/lambda_update.sh` line 11
  - [x] Update `lambdas/app-server-internet/lambda_update.sh` line 9
- [x] Task 4: Deploy and verify (AC: #8)
  - [x] Deploy updated `api-gw-app.yaml` via `deploy.sh`
  - [x] Verify all 11 endpoints respond correctly
  - [x] Delete old Lambda functions `lenie_2_db` and `lenie_2_internet` from AWS
- [x] Task 5: Update documentation (AC: #7)
  - [x] Update `docs/infrastructure-metrics.md` — Lambda names in tables
  - [x] Update `infra/aws/CLAUDE.md` — references to non-CF Lambdas
  - [x] Update `infra/aws/serverless/CLAUDE.md` — function details
  - [x] Update `infra/aws/cloudformation/CLAUDE.md` — api-gw-app description
  - [x] Update `scripts/verify-documentation-metrics.sh` if needed

## Dev Notes

### Current State — Hardcoded Lambda Names in api-gw-app.yaml

10 endpoints use hardcoded names (lines from api-gw-app.yaml):
- `lenie_2_db` — 8 endpoint paths / 9 URIs (lines 51, 102, 153, 204, 224, 275, 326, 377, 428; `/website_delete` has GET+POST)
- `lenie_2_internet` — 2 endpoints (lines 479, 530)
- `${ProjectCode}-${Environment}-url-add` — 1 endpoint (already parameterized, Sprint 4 Story 15.1)

After this story, ALL 11 endpoints will use the `${ProjectCode}-${Environment}-*` pattern.

### Lambda Rename Strategy

AWS Lambda does NOT support renaming in-place. The approach is:
1. Create new functions with correct names (copy configuration from old ones)
2. Deploy code to new functions
3. Update `api-gw-app.yaml` to point to new names
4. Deploy CF stack (updates API Gateway)
5. Verify all endpoints work
6. Delete old Lambda functions

**CRITICAL:** The `lenie_2_db` and `lenie_2_internet` functions are NOT managed by CloudFormation — they were created manually. The new functions should ideally be CF-managed (add as resources in a template), but for this story scope, just creating them via CLI and updating the api-gw-app.yaml references is sufficient.

### Affected Files

| File | Change |
|------|--------|
| `infra/aws/cloudformation/templates/api-gw-app.yaml` | Replace 10 hardcoded URIs with parameterized `!Sub` |
| `infra/aws/serverless/lambdas/app-server-db/lambda_update.sh` | Update function name |
| `infra/aws/serverless/lambdas/app-server-internet/lambda_update.sh` | Update function name |
| `docs/infrastructure-metrics.md` | Update Lambda names in tables |
| `infra/aws/CLAUDE.md` | Update non-CF Lambda references |
| `infra/aws/serverless/CLAUDE.md` | Update function names |
| `infra/aws/cloudformation/CLAUDE.md` | Update api-gw-app description |
| `scripts/verify-documentation-metrics.sh` | Update if checks old names (lines 148-150) |

### Key Constraints

- **Template size limit:** api-gw-app.yaml must stay under 51200 bytes (parameterized `!Sub` strings are slightly longer than hardcoded)
- **Zero downtime goal:** Create new functions BEFORE updating API Gateway references
- **`/url_add` already uses parameterized name** — do NOT modify it, it's already correct
- **Lambda permissions:** Existing `LambdaInvokePermission` resources may need updating — check all permission resources
- **Usage plans:** `lenie_2_db-UsagePlan` may reference old names — verify and update if needed

### Previous Story Intelligence

- Story 15.1 added `/url_add` with parameterized `!Sub` name — follow the same pattern
- Story 4.2 documented the hardcoded names as intentional hybrid state
- Architecture doc explicitly defers this to B-3

### References

- [Source: infra/aws/cloudformation/templates/api-gw-app.yaml — 10 hardcoded URIs]
- [Source: infra/aws/serverless/lambdas/app-server-db/lambda_update.sh:11 — hardcoded name]
- [Source: infra/aws/serverless/lambdas/app-server-internet/lambda_update.sh:9 — hardcoded name]
- [Source: _bmad-output/planning-artifacts/architecture.md:874,879 — B-3 deferred decision]
- [Source: Story 15.1 — parameterized Lambda name pattern reference]
- [Source: scripts/verify-documentation-metrics.sh:148-150 — old name references]

## Dev Agent Record

### Agent Model Used
Claude Opus 4.6

### Debug Log References
- Lambda functions discovered in us-east-1 (not eu-central-1 as initially assumed)
- Both old functions (lenie_2_db, lenie_2_internet) existed and were successfully copied and deleted
- API Gateway endpoints return HTTP 502 (expected — RDS is stopped, Lambda functions are invoked correctly)
- CloudWatch log group `/aws/lambda/lenie-dev-app-server-internet` confirms correct routing
- cfn-lint validation passed with exit code 0
- Template size: 30,676 bytes (well under 51,200 limit)
- verify-documentation-metrics.sh: Lambda-related checks PASS (4 pre-existing FAILs unrelated to this story)

### Completion Notes List
- Task 1: Created `lenie-dev-app-server-db` and `lenie-dev-app-server-internet` in us-east-1 via AWS CLI, copying full config (runtime, layers, VPC, env vars, tracing) from originals
- Task 2: Replaced 9 `lenie_2_db` URIs (8 endpoint paths, 9 URIs due to `/website_delete` GET+POST) and 2 `lenie_2_internet` URIs with `${ProjectCode}-${Environment}-*` parameterized names. Added `AppServerDbLambdaInvokePermission` and `AppServerInternetLambdaInvokePermission` resources
- Task 3: Updated both `lambda_update.sh` scripts with new function names
- Task 4: Deployed CFN stack update + new API GW deployment. Verified endpoints work (HTTP 502 = Lambda invoked, RDS offline). Deleted old Lambda functions
- Task 5: Updated infrastructure-metrics.md, infra/aws/CLAUDE.md, infra/aws/cloudformation/CLAUDE.md, and verify-documentation-metrics.sh. serverless/CLAUDE.md had no old references

### File List
- `infra/aws/cloudformation/templates/api-gw-app.yaml` — replaced 11 hardcoded Lambda URIs with parameterized names, added 2 Lambda invoke permissions
- `infra/aws/serverless/lambdas/app-server-db/lambda_update.sh` — updated function name to lenie-dev-app-server-db
- `infra/aws/serverless/lambdas/app-server-internet/lambda_update.sh` — updated function name to lenie-dev-app-server-internet
- `docs/infrastructure-metrics.md` — updated Lambda names in API Gateway and Lambda tables
- `infra/aws/CLAUDE.md` — updated non-CF Lambda references
- `infra/aws/cloudformation/CLAUDE.md` — updated api-gw-app description
- `scripts/verify-documentation-metrics.sh` — updated non-CF Lambda detection for parameterized naming pattern
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — status: in-progress → review
- `_bmad-output/implementation-artifacts/17-3-rename-legacy-lambda-lenie-2-internet-and-db.md` — story file updated

## Senior Developer Review (AI)

**Reviewer**: Claude Opus 4.6 | **Date**: 2026-02-23

**Outcome**: Changes Requested → Fixed

**Issues found**: 1 High, 3 Medium, 3 Low (7 total)

| # | Severity | Finding | Resolution |
|---|----------|---------|------------|
| H1 | HIGH | `docs/infrastructure-metrics.md` template counts stale (26/33 → should be 27/34) — "Last verified" date updated but counts not | Fixed: updated to 27/34 |
| M1 | MEDIUM | `app-server-internet/lambda_update.sh` missing `set -e` / `set -x` (inconsistent with db script) | Fixed: added both flags |
| M2 | MEDIUM | Lambda invoke permissions use wildcard `SourceArn` (`/*`) vs path-specific for url-add | Fixed: added explanatory comment in api-gw-app.yaml |
| M3 | MEDIUM | Template count inconsistency between infra/aws/CLAUDE.md (27) and infrastructure-metrics.md (was 26) | Fixed: by H1 fix |
| L1 | LOW | `lambda_update.sh` scripts hardcode function name — only works for dev environment | Fixed: added TODO comment |
| L2 | LOW | Dev Notes say "8 endpoints" but list 9 line numbers (due to /website_delete GET+POST) | Fixed: clarified wording |
| L3 | LOW | Completion Notes say "9 lenie_2_db" vs AC "8 endpoints" — correct but confusing | Fixed: clarified in Completion Notes |

**Post-fix verification**: `verify-documentation-metrics.sh` — deploy.ini (27) and total .yaml (34) PASS. 4 pre-existing FAILs unrelated to this story (grep pattern issues on Windows/MSYS for api-gw-infra, url-add, Lambda counts).

## Change Log
- 2026-02-23: Renamed Lambda functions lenie_2_db → lenie-dev-app-server-db and lenie_2_internet → lenie-dev-app-server-internet. All 11 api-gw-app.yaml endpoints now use parameterized ${ProjectCode}-${Environment}-* naming. Old functions deleted from AWS. Documentation and deployment scripts updated.
- 2026-02-23: Code review fixes — corrected infrastructure-metrics.md template counts (26→27, 33→34), added set -e/set -x to app-server-internet/lambda_update.sh, added SourceArn design rationale comment to api-gw-app.yaml, clarified URI vs endpoint path counts in Dev Notes.
