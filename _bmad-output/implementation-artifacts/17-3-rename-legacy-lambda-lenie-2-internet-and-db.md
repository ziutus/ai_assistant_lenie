# Story 17.3: Rename Legacy Lambda lenie_2_internet and lenie_2_db

Status: ready-for-dev

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

- [ ] Task 1: Create new Lambda functions with correct names in AWS (AC: #1, #2)
  - [ ] Create `lenie-dev-app-server-db` as copy of `lenie_2_db` (same config, layers, VPC, env vars)
  - [ ] Create `lenie-dev-app-server-internet` as copy of `lenie_2_internet`
  - [ ] Deploy latest code to new functions via `zip_to_s3.sh`
  - [ ] Verify new functions work (test invoke)
- [ ] Task 2: Update `api-gw-app.yaml` to use parameterized names (AC: #3, #4, #6)
  - [ ] Replace all 8 `lenie_2_db` URIs with `${ProjectCode}-${Environment}-app-server-db`
  - [ ] Replace all 2 `lenie_2_internet` URIs with `${ProjectCode}-${Environment}-app-server-internet`
  - [ ] Update or add Lambda invoke permissions for new function names
  - [ ] Run cfn-lint validation
- [ ] Task 3: Update deployment scripts (AC: #5)
  - [ ] Update `lambdas/app-server-db/lambda_update.sh` line 11
  - [ ] Update `lambdas/app-server-internet/lambda_update.sh` line 9
- [ ] Task 4: Deploy and verify (AC: #8)
  - [ ] Deploy updated `api-gw-app.yaml` via `deploy.sh`
  - [ ] Verify all 11 endpoints respond correctly
  - [ ] Delete old Lambda functions `lenie_2_db` and `lenie_2_internet` from AWS
- [ ] Task 5: Update documentation (AC: #7)
  - [ ] Update `docs/infrastructure-metrics.md` — Lambda names in tables
  - [ ] Update `infra/aws/CLAUDE.md` — references to non-CF Lambdas
  - [ ] Update `infra/aws/serverless/CLAUDE.md` — function details
  - [ ] Update `infra/aws/cloudformation/CLAUDE.md` — api-gw-app description
  - [ ] Update `scripts/verify-documentation-metrics.sh` if needed

## Dev Notes

### Current State — Hardcoded Lambda Names in api-gw-app.yaml

10 endpoints use hardcoded names (lines from api-gw-app.yaml):
- `lenie_2_db` — 8 endpoints (lines 51, 102, 153, 204, 224, 275, 326, 377, 428)
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

### Debug Log References

### Completion Notes List

### File List
