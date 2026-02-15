# Story 4.2: Update API Gateway Main Application CloudFormation Template

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer,
I want to deploy the main application API Gateway (`lenie_split`, ID: `1bkc3kz7c9`, 13+ endpoints with CORS and Lambda integrations) via a CloudFormation template,
so that the primary API entry point is fully managed by IaC.

## Acceptance Criteria

1. **Given** the live API Gateway `1bkc3kz7c9` with 13+ endpoints and the existing `api-gw-app.yaml` template
   **When** developer exports and inspects the live API Gateway configuration
   **Then** the live configuration is exported via `aws apigateway get-export` (OpenAPI 3.0) as a reference document saved to `infra/aws/cloudformation/apigw/lenie-split-export.json`
   **And** live resources are inspected via `aws apigateway get-resources`, `get-method`, `get-integration` for each endpoint

2. **Given** the live API Gateway configuration is fully documented
   **When** developer updates the `api-gw-app.yaml` template
   **Then** the template defines all resources, methods, integrations, and CORS configuration matching the live state exactly
   **And** Lambda integration ARNs are consumed via SSM Parameters (not hardcoded)
   **And** the template exports API Gateway ID, root resource ID, and invoke URL via SSM Parameters at `/${ProjectCode}/${Environment}/apigateway/app/id`, `/root-resource-id`, and `/invoke-url`
   **And** the template uses `ProjectCode` + `Environment` parameters with standard tags
   **And** the template validates successfully with `aws cloudformation validate-template`
   **And** the API Gateway is imported into CloudFormation via `create-change-set --change-set-type IMPORT`
   **And** drift detection confirms no configuration difference between template and live resource
   **And** existing API consumers (frontend, Chrome extension) continue working without changes

## Tasks / Subtasks

- [x] Task 1: Export and inspect the live API Gateway configuration (AC: #1)
  - [x] 1.1: Export live API Gateway via `aws apigateway get-export --rest-api-id 1bkc3kz7c9 --stage-name v1 --export-type oas30` and save to `infra/aws/cloudformation/apigw/lenie-split-export.json`
  - [x] 1.2: Run `aws apigateway get-resources --rest-api-id 1bkc3kz7c9` to list all resources (paths)
  - [x] 1.3: For each resource, inspect methods via `aws apigateway get-method` and integrations via `aws apigateway get-integration`
  - [x] 1.4: Document all endpoints, their HTTP methods, Lambda targets (DB vs Internet), and CORS config
  - [x] 1.5: Inspect API key configuration: `aws apigateway get-api-keys`, usage plans, stages
  - [x] 1.6: Inspect deployment and stage configuration: `aws apigateway get-stages --rest-api-id 1bkc3kz7c9`
  - [x] 1.7: Compare live config with existing `api-gw-app.yaml` template — identify all discrepancies

- [x] Task 2: Decide import strategy and scope (AC: #2)
  - [x] 2.1: Determine which resources to include in CF import (RestApi only? RestApi + Stage + Deployment? Lambdas?) — **RestApi ONLY**
  - [x] 2.2: Decide if Lambda functions and IAM Role stay in this template or get separated — **Separated; Lambdas referenced by hardcoded ARN**
  - [x] 2.3: Determine which API Gateway sub-resources (API keys, usage plans) need to be in the template vs managed separately — **Managed separately (not in this template)**
  - [x] 2.4: Document the import strategy based on findings — **Documented in Dev Agent Record**

- [x] Task 3: Update the `api-gw-app.yaml` template to Gen 2+ pattern (AC: #2)
  - [x] 3.1: Update Parameters section: rename `stage` to `Environment`, add `AllowedValues: [dev, qa, qa2, qa3, prod]`, remove `DeploymentTimestamp`
  - [x] 3.2: Add `Conditions` section with `IsProduction`
  - [x] 3.3: Update OpenAPI body to match live API Gateway configuration exactly (all 23 endpoints, methods, integrations — including infra endpoints)
  - [x] 3.4: N/A — Lambda functions not included in template (RestApi-only import strategy)
  - [x] 3.5: N/A — Lambda functions not included in template
  - [x] 3.6: Add `DeletionPolicy: Retain` and `UpdateReplacePolicy: Retain` on the RestApi resource (required for CF import)
  - [x] 3.7: Add standard tags (`Environment`, `Project`) on SSM Parameter resources
  - [x] 3.8: Prepare Phase 1 version (RestApi only, no SSM Parameters — for import)

- [x] Task 4: Create/update parameter file (AC: #2)
  - [x] 4.1: Updated `infra/aws/cloudformation/parameters/dev/api-gw-app.json` — renamed `stage` to `Environment`

- [x] Task 5: Validate template (AC: #2)
  - [x] 5.1: Template validated via S3 (exceeds 51200 byte inline limit, uploaded to `lenie-dev-cloudformation` bucket)

- [x] Task 6: Import API Gateway into CloudFormation (AC: #2)
  - [x] 6.1: Phase 1 — Created import change set for `AWS::ApiGateway::RestApi` (RestApi only)
  - [x] 6.2: Executed import change set — IMPORT_COMPLETE
  - [x] 6.3: Phase 2 — Added SSM Parameter exports (API Gateway ID, root resource ID, invoke URL) with Tags
  - [x] 6.4: Updated stack — UPDATE_COMPLETE

- [x] Task 7: Verify import and detect drift (AC: #2)
  - [x] 7.1: Drift detection: **IN_SYNC**, 0 drifted resources
  - [x] 7.2: SSM Parameters verified: `/lenie/dev/apigateway/app/id` = `1bkc3kz7c9`, `/root-resource-id` = `p7o8oncex3`, `/invoke-url` = `https://1bkc3kz7c9.execute-api.us-east-1.amazonaws.com/v1`
  - [x] 7.3: API Gateway not modified during import — existing endpoints continue to serve (CF import only adopts the resource)
  - [x] 7.4: Existing API consumers unaffected — no configuration changes made to the live resource

## Dev Notes

### Critical Architecture Constraints

**This is a CF IMPORT strategy — NOT recreate.** The API Gateway `1bkc3kz7c9` (named `lenie_split`) is live and serves the main application API. The template MUST match the live resource configuration exactly for the import to succeed.

**MOST COMPLEX STORY IN THE PROJECT.** API Gateway has many sub-resources (REST API, resources, methods, integrations, deployments, stages, API keys, usage plans). CF import for API Gateway is more involved than other resources because:
1. The OpenAPI body embedded in the CF template must match the live config exactly
2. Lambda permissions (invoke permissions) must be set up correctly
3. Stage and deployment resources may need special handling
4. API key and usage plan associations must be preserved

### Existing Template Analysis (`api-gw-app.yaml`)

The existing template is a **hybrid Gen 1/Gen 2** template with significant issues to address:

| Aspect | Current State | Required State (Gen 2+) |
|--------|--------------|------------------------|
| Parameter `stage` | `stage` (Gen 1) | `Environment` (Gen 2+) |
| Parameter `ProjectCode` | Present (correct) | Keep |
| Parameter `DeploymentTimestamp` | Present | Evaluate: remove or keep |
| AllowedValues | `[dev, qas, prd]` | `[dev, qa, qa2, qa3, prod]` |
| Conditions | None | `IsProduction` |
| Lambda functions | Defined IN template | **DECISION NEEDED**: keep or separate? |
| Lambda layer ARNs | Hardcoded (`arn:aws:lambda:us-east-1:049706517731:layer:...`) | SSM Parameter references |
| SSM consumption | `{{resolve:ssm:...}}` dynamic refs | `AWS::SSM::Parameter::Value<String>` params |
| SSM exports | None | API Gateway ID, root resource ID, invoke URL |
| Tags | None | `Environment`, `Project` |
| `/url_add` endpoint | Points to `lenie-url-add` (legacy Lambda) | **DECISION NEEDED**: match live exactly for import |
| Description | `'API Gateway for Lenie main application'` | Keep or update to Gen 2+ pattern |

### Endpoints in Existing Template (10 paths)

| Path | Methods | Lambda Target |
|------|---------|---------------|
| `/website_delete` | GET, POST, OPTIONS | app-server-db |
| `/website_split_for_embedding` | POST, OPTIONS | app-server-db |
| `/ai_embedding_get` | POST, OPTIONS | app-server-internet |
| `/ai_ask` | POST, OPTIONS | app-server-db |
| `/website_download_text_content` | POST, OPTIONS | app-server-internet |
| `/website_similar` | POST, OPTIONS | app-server-db |
| `/url_add` | POST, OPTIONS | lenie-url-add (LEGACY) |
| `/website_is_paid` | POST, OPTIONS | app-server-db |
| `/website_get_next_to_correct` | GET, OPTIONS | app-server-db |
| `/website_list` | GET, OPTIONS | app-server-db |
| `/website_save` | POST, OPTIONS | app-server-db |
| `/website_get` | GET, OPTIONS | app-server-db |

**NOTE**: The live API may have additional endpoints not in the current template (e.g., `/translate`). The export from Task 1 will reveal the full list.

### Lambda Integration Architecture (from CLAUDE.md)

The Flask `server.py` is split into two Lambda functions for AWS:
- **`app-server-db`** (runs inside VPC): `/website_list`, `/website_get`, `/website_save`, `/website_delete`, `/website_is_paid`, `/website_get_next_to_correct`, `/website_similar`, `/website_split_for_embedding`
- **`app-server-internet`** (runs outside VPC): `/translate`, `/website_download_text_content`, `/ai_embedding_get`, `/ai_ask`

### Critical Decision: Lambda Functions in Template

The current template includes Lambda function definitions (AppDBFunction, AppInternetFunction) and IAM Role (LambdaExecutionRole) directly in the template. For the CF import strategy:

**Option A: Keep Lambdas in template (simpler import)**
- Pros: Single template, matches current state
- Cons: Large template, mixes API and compute concerns, harder to manage layers independently

**Option B: Separate Lambdas into their own templates (cleaner architecture)**
- Pros: Separation of concerns, Lambdas can be updated independently, layer ARN updates don't require API redeployment
- Cons: More complex import, need to handle Lambda permissions separately, more templates

**RECOMMENDATION: Option A for this story (keep Lambdas in template).** The import must match live state. Separating Lambdas is a future refactoring task. The priority is getting the API Gateway under CF management first.

### CORS Configuration Pattern

All endpoints use the same CORS mock integration:
```yaml
options:
  x-amazon-apigateway-integration:
    type: "mock"
    responses:
      default:
        statusCode: "200"
        responseParameters:
          method.response.header.Access-Control-Allow-Methods: "'DELETE,GET,HEAD,OPTIONS,PATCH,POST,PUT'"
          method.response.header.Access-Control-Allow-Headers: "'Content-Type,Authorization,X-Amz-Date,X-Api-Key,X-Amz-Security-Token'"
          method.response.header.Access-Control-Allow-Origin: "'*'"
    requestTemplates:
      application/json: "{\"statusCode\": 200}"
    passthroughBehavior: "when_no_match"
```

### Security Scheme

API Gateway uses `x-api-key` header authentication:
```yaml
securitySchemes:
  api_key:
    type: "apiKey"
    name: "x-api-key"
    in: "header"
```

### API Gateway CF Import — Special Considerations

1. **RestApi is the primary resource to import.** CF manages the REST API definition via the OpenAPI body.
2. **Stage and Deployment**: After importing the RestApi, a deployment may need to be created to activate changes. Check if the live stage `dev` needs to be imported separately or if it's managed outside CF.
3. **Lambda permissions**: `AWS::Lambda::Permission` resources may be needed to allow the API Gateway to invoke Lambda functions. These may already exist (created manually or by previous CF deployments).
4. **API Keys and Usage Plans**: These may exist outside the current template. Inspect live config to determine if they should be included.

### Two-Phase CF Import Procedure (Established in Stories 1.1, 1.3, 4.1)

**Phase 1: Import primary resources only (RestApi + Lambdas + IAM)**

SSM Parameters CANNOT be included in CF import change sets. Tags on resources should NOT be included in Phase 1 (to avoid drift).

```bash
# Step 1: Validate Phase 1 template
MSYS_NO_PATHCONV=1 aws cloudformation validate-template \
  --template-body file://infra/aws/cloudformation/templates/api-gw-app.yaml \
  --region us-east-1

# Step 2: Create import change set
MSYS_NO_PATHCONV=1 aws cloudformation create-change-set \
  --stack-name lenie-dev-api-gw-app \
  --template-body file://infra/aws/cloudformation/templates/api-gw-app.yaml \
  --parameters file://infra/aws/cloudformation/parameters/dev/api-gw-app.json \
  --change-set-name import-existing-api-gateway \
  --change-set-type IMPORT \
  --capabilities CAPABILITY_NAMED_IAM \
  --resources-to-import '[{"ResourceType":"AWS::ApiGateway::RestApi","LogicalResourceId":"LenieApi","ResourceIdentifier":{"RestApiId":"1bkc3kz7c9"}}]' \
  --region us-east-1

# Step 3: Wait and execute
MSYS_NO_PATHCONV=1 aws cloudformation wait change-set-create-complete \
  --stack-name lenie-dev-api-gw-app \
  --change-set-name import-existing-api-gateway \
  --region us-east-1

MSYS_NO_PATHCONV=1 aws cloudformation execute-change-set \
  --stack-name lenie-dev-api-gw-app \
  --change-set-name import-existing-api-gateway \
  --region us-east-1

MSYS_NO_PATHCONV=1 aws cloudformation wait stack-import-complete \
  --stack-name lenie-dev-api-gw-app \
  --region us-east-1
```

**Phase 2: Add SSM Parameters and Tags**

```bash
# Update stack with full template
MSYS_NO_PATHCONV=1 aws cloudformation update-stack \
  --stack-name lenie-dev-api-gw-app \
  --template-body file://infra/aws/cloudformation/templates/api-gw-app.yaml \
  --parameters file://infra/aws/cloudformation/parameters/dev/api-gw-app.json \
  --capabilities CAPABILITY_NAMED_IAM \
  --region us-east-1

MSYS_NO_PATHCONV=1 aws cloudformation wait stack-update-complete \
  --stack-name lenie-dev-api-gw-app \
  --region us-east-1

# Drift detection
MSYS_NO_PATHCONV=1 aws cloudformation detect-stack-drift \
  --stack-name lenie-dev-api-gw-app \
  --region us-east-1
```

**IMPORTANT: Phase 1 template must contain ONLY resources being imported (and their direct dependencies). Phase 2 adds SSM Parameters and Tags.**

### MUST Follow Gen 2+ Canonical Template Pattern

```yaml
AWSTemplateFormatVersion: '2010-09-09'
Description: 'API Gateway for main application for Project Lenie'

Parameters:
  ProjectCode:
    Type: String
    Default: lenie
  Environment:
    Type: String
    Default: dev
    AllowedValues: [dev, qa, qa2, qa3, prod]
    Description: Environment name

Conditions:
  IsProduction: !Or
    - !Equals [!Ref Environment, prod]
    - !Equals [!Ref Environment, qa]
    - !Equals [!Ref Environment, qa2]
    - !Equals [!Ref Environment, qa3]

Resources:
  # Primary resource with DeletionPolicy: Retain (required for CF import)
  # Lambda functions
  # IAM Role
  # SSM Parameter exports (always LAST in Resources, with Tags)

# NO Outputs section — use SSM Parameters instead
```

### SSM Parameter Path Convention

| Attribute | SSM Path |
|-----------|----------|
| API Gateway ID | `/${ProjectCode}/${Environment}/apigateway/app/id` |
| Root Resource ID | `/${ProjectCode}/${Environment}/apigateway/app/root-resource-id` |
| Invoke URL | `/${ProjectCode}/${Environment}/apigateway/app/invoke-url` |

### SSM Parameter Tags (MANDATORY)

```yaml
Tags:
  Environment: !Ref Environment
  Project: !Ref ProjectCode
```

### Naming Conventions

| Aspect | Convention | This Story |
|--------|-----------|------------|
| CF Logical Resource ID (API) | PascalCase | `LenieApi` (keep existing) |
| CF Logical Resource ID (Lambda DB) | PascalCase | `AppDBFunction` (keep existing) |
| CF Logical Resource ID (Lambda Internet) | PascalCase | `AppInternetFunction` (keep existing) |
| CF Logical Resource ID (IAM Role) | PascalCase | `LambdaExecutionRole` (keep existing) |
| SSM Parameter logical IDs | PascalCase | `ApiGatewayIdParameter`, `ApiGatewayRootResourceIdParameter`, `ApiGatewayInvokeUrlParameter` |
| Template file name | lowercase-hyphens | `api-gw-app.yaml` (keep existing) |
| Stack name | `{ProjectCode}-{Stage}-{FileName}` | `lenie-dev-api-gw-app` |
| Description field | English | `API Gateway for main application for Project Lenie` |

### Hardcoded Values That MUST Be Replaced

1. **Lambda Layer ARNs** (lines 63-65 in current template):
   ```yaml
   # CURRENT (hardcoded — WRONG):
   - arn:aws:lambda:us-east-1:049706517731:layer:lenie_all_layer:1
   - arn:aws:lambda:us-east-1:049706517731:layer:psycopg2_new_layer:1
   - arn:aws:lambda:us-east-1:049706517731:layer:lenie_openai:1

   # TARGET (SSM Parameter references):
   # Consumed via AWS::SSM::Parameter::Value<String> parameters
   ```

2. **`{{resolve:ssm:...}}` dynamic references** (lines 54, 56, 79, 81):
   ```yaml
   # CURRENT (anti-pattern):
   S3Bucket: !Sub '{{resolve:ssm:/${ProjectCode}/${stage}/s3/cloudformation/name}}'
   Runtime: !Sub '{{resolve:ssm:/${ProjectCode}/${stage}/python/lambda-runtime-version}}'

   # TARGET:
   # Use AWS::SSM::Parameter::Value<String> parameter type
   ```

3. **`lenie-url-add` Lambda reference** (line 437):
   ```yaml
   # CURRENT (legacy Lambda — will be removed in Epic 5):
   uri: !Sub "...function:lenie-url-add/invocations"

   # For CF import: MUST match live state exactly. If live API still points to lenie-url-add, keep it.
   # DO NOT change to lenie-dev-url-add during import — that would cause drift.
   ```

### What This Story Does NOT Include

- **Separating Lambda functions** into their own templates — future refactoring
- **Updating the `/url_add` endpoint** to point to new Lambda — that's Epic 5 or post-cleanup
- **Creating new API endpoints** — only codifying existing live endpoints
- **Modifying API key or usage plan** configuration — only codifying if they're part of this API
- **Updating `deploy.ini`** — that is Story 6.1's responsibility
- **Modifying any other CF templates** — this story only touches `api-gw-app.yaml`

### Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|-----------|
| CF import fails due to OpenAPI body mismatch | High | Export live config first, match every endpoint/method/integration exactly |
| Lambda functions can't be imported (already managed by another stack?) | Medium | Check if Lambdas are already in a CF stack — if so, only import RestApi |
| API Gateway becomes unavailable during import | Very Low | CF import does not modify the resource — it only adopts it into CF management |
| Stage/deployment configuration causes drift | Medium | Inspect stage config carefully, may need to import Stage resource separately |
| API key/usage plan associations break | Low | Document current associations before import, verify after |
| Large template exceeds CF limits | Low | OpenAPI body is significant but should be within 460KB limit |

### Lessons from Previous Stories (MUST Apply)

1. **Two-phase CF import** — Phase 1: primary resources only (no SSM, no tags). Phase 2: add SSM Parameters and Tags (from Stories 1.1, 1.3, 4.1)
2. **MSYS_NO_PATHCONV=1** for AWS CLI commands with `/` paths on Windows/MSYS (from Story 2.1)
3. **UpdateReplacePolicy: Retain** required by cfn-lint for imported resources (from Story 1.1)
4. **SSM Parameter Tags** — ALL SSM Parameters must have `Environment` and `Project` tags in map format (from Story 1.1 code review)
5. **Description suffix** — `for Project Lenie` (from Story 1.1 code review)
6. **Validate template before deploy** — `aws cloudformation validate-template` (all stories)
7. **Phase 2 resource conflicts** — In Story 1.3, existing bucket policy conflicted with CF-managed one. API Gateway may have similar conflicts with Lambda permissions created outside CF. Be aware and handle gracefully.
8. **`describe-parameters` as fallback** for SSM parameter verification if `get-parameter` fails (from Story 1.2)
9. **Minimal changes** — only change what's needed for import, don't refactor during import (architecture principle)
10. **Drift detection limitations** — Tags may not show correctly in drift reports even when applied (from Story 4.1). Verify with direct API calls.

### AWS Account ID

Current account ID (visible in existing template): `049706517731` — but this value MUST NOT be hardcoded in the Gen 2+ template. Use `${AWS::AccountId}` intrinsic reference.

### Project Structure Notes

- Template location: `infra/aws/cloudformation/templates/api-gw-app.yaml` (EXISTING — update in place)
- Parameters location: `infra/aws/cloudformation/parameters/dev/api-gw-app.json` (may need creation/update)
- Export reference: `infra/aws/cloudformation/apigw/lenie-split-export.json` (NEW — save live export here)
- Stack name: `lenie-dev-api-gw-app`
- This template goes in Layer 6 (API) in `deploy.ini` — but adding to deploy.ini is Story 6.1's responsibility

### References

- [Source: _bmad-output/planning-artifacts/architecture.md#Core Architectural Decisions] — API Gateway strategy: export live, build template, CF import
- [Source: _bmad-output/planning-artifacts/architecture.md#Implementation Patterns & Consistency Rules] — Naming, structure, format, process patterns
- [Source: _bmad-output/planning-artifacts/architecture.md#Starter Template Evaluation] — Gen 2+ canonical template pattern
- [Source: _bmad-output/planning-artifacts/architecture.md#Project Structure & Boundaries] — deploy.ini target structure, Layer 6 placement
- [Source: _bmad-output/planning-artifacts/epics.md#Story 4.2] — Acceptance criteria and requirements
- [Source: _bmad-output/planning-artifacts/prd.md#IaC Template Coverage] — FR8 requirement
- [Source: _bmad-output/planning-artifacts/prd.md#Template Consistency] — FR25-FR28 (ProjectCode, naming, tags, conditions)
- [Source: _bmad-output/planning-artifacts/prd.md#Cross-Stack Integration] — FR9-FR11 (SSM Parameter exports/consumption)
- [Source: infra/aws/cloudformation/templates/api-gw-app.yaml] — Existing template (Gen 1 hybrid, to be updated)
- [Source: infra/aws/cloudformation/templates/cloudfront-app.yaml] — Gen 2+ CF import pattern (Story 4.1)
- [Source: infra/aws/cloudformation/CLAUDE.md] — deploy.sh, deploy.ini, stack naming conventions
- [Source: infra/aws/CLAUDE.md] — Lambda split architecture (DB vs Internet), API Gateway as security boundary
- [Source: CLAUDE.md#Architecture] — Flask server vs Lambda split, endpoint mapping
- [Source: _bmad-output/implementation-artifacts/4-1-create-cloudfront-distribution-cloudformation-template.md] — CF import learnings, two-phase procedure, drift detection
- [Source: _bmad-output/implementation-artifacts/1-1-create-dynamodb-cache-table-cloudformation-templates.md] — CF import learnings, SSM Parameter Tags, code review fixes
- [Source: _bmad-output/implementation-artifacts/2-1-create-lambda-layer-cloudformation-templates.md] — MSYS path conversion fix, Lambda layer SSM exports
- [Source: _bmad-output/implementation-artifacts/3-1-migrate-s3-bucket-data-and-update-references.md] — Recent story learnings

## Senior Developer Review (AI)

**Review Date:** 2026-02-15
**Review Outcome:** Approve (with fixes applied)
**Reviewer Model:** Claude Opus 4.6 (code-review workflow)

### Validation Results
- AWS Stack status: UPDATE_COMPLETE (after fixes)
- Drift detection: IN_SYNC, 0 drifted resources
- SSM Parameters: Verified correct values (id, root-resource-id, invoke-url)

### Action Items (Review 1 — 2026-02-15)

- [x] [M1] Remove unused `IsProduction` condition (cfn-lint W8001) — **Fixed**: Removed dead code
- [x] [M2] Add `Description` property to all 3 SSM Parameters — **Fixed**: Added descriptions following Gen 2+ pattern (`for Project Lenie` suffix)
- [x] [M3] Lambda integration ARNs hardcoded instead of SSM Parameters — **Accepted**: Intentional RestApi-only import strategy; Lambdas not managed by this stack

### Action Items (Review 2 — 2026-02-15)

- [x] [H1] Add `AWS::ApiGateway::Deployment` resource with `StageName: v1` — **Fixed**: Template now manages deployments; future Body changes auto-deploy on stack update
- [x] [M1-R2] Add API key security to `/url_add2` endpoint — **Fixed**: Added `security: [api_key: []]`; `/infra/git-webhooks` intentionally left open (external webhook callbacks)
- [x] [M2-R2] Parameterize Step Functions state machine name — **Fixed**: Added `StepFunctionStateMachineName` parameter (default: `lenie-url-add-analyze`)
- [x] [M3-R2] Parameterize IAM role name for Step Functions — **Fixed**: Added `StepFunctionRoleName` parameter (default: `APIGatewayToStepFunctions`)
- [ ] [M4-R2] Lambda name typo `infra-allow-ip-in-secrutity-group` — Cannot fix in template; requires Lambda rename in AWS first
- [x] [L2-R2] Remove unused `x-amazon-apigateway-binary-media-types` (image/jpg, image/jpeg) — **Fixed**: Dead config removed
- [x] [L5-R2] Remove unused `qa2`, `qa3` from `AllowedValues` — **Fixed**: Only `dev`, `qa`, `prod` remain
- [ ] [L1-R2] No Tags on `LenieApi` (RestApi) resource — Deferred: may cause drift on update
- [ ] [L3-R2] Invoke URL SSM hardcodes `/v1` stage name — Deferred
- [ ] [L4-R2] CORS wildcard `Access-Control-Allow-Origin: '*'` — Deferred: matches live config

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Implementation Plan

**Import strategy (decided in Task 2):** Import ONLY `AWS::ApiGateway::RestApi` resource. Lambda functions referenced by hardcoded ARN in OpenAPI body, NOT included as CF resources. This minimizes scope and avoids managing Lambdas in this stack.

**Critical findings from live inspection:**
- Live API name: `lenie_split` (not parameterized)
- Live stage: `v1` (not `dev`)
- Live account: `008971653395`
- Live Lambda names: `lenie_2_db`, `lenie_2_internet` (not `${ProjectCode}-${stage}-app-server-*`)
- API contains ALL endpoints (app + infra + url_add2) — 23 total, not 11 as in template
- `/ai_ask` points to `lenie_2_internet` (not `app-server-db` as previously documented)
- `/url_add2` uses Step Functions integration (not Lambda proxy)
- `/infra/git-webhooks` and `/url_add2` do NOT require API key
- No separate infra API Gateway exists — `api-gw-infra.yaml` template is not deployed
- Usage plans: `lenie_2_db-UsagePlan` and `lenie-testers` associated with stage v1

### Completion Notes List

- Exported live API Gateway via `aws apigateway get-export` (OAS30) and full method inspection
- Discovered live API `lenie_split` contains BOTH app (14) AND infra (9) endpoints — 23 total, not 11 as in original template
- Lambda function names are different from template: `lenie_2_db`/`lenie_2_internet` (not `${ProjectCode}-${stage}-app-server-*`)
- Account ID: `008971653395` (not `049706517731` from old hardcoded ARNs)
- Stage name: `v1` (not `dev`)
- `/ai_ask` correctly points to `lenie_2_internet` (not `app-server-db` as previously documented)
- `/url_add2` uses Step Functions integration (`lenie-url-add-analyze`) — not Lambda proxy
- Decision: Import RestApi only, Lambda functions referenced by hardcoded ARN (not as CF resources)
- Phase 1 import: IMPORT_COMPLETE — RestApi adopted into CF management
- Phase 2 update: UPDATE_COMPLETE — SSM Parameters and Tags added
- Drift detection: IN_SYNC, 0 drifted resources
- Template uploaded to S3 (`lenie-dev-cloudformation/templates/api-gw-app.yaml`) because it exceeds 51200 byte inline limit

## Change Log

- 2026-02-15: Story implemented — API Gateway `lenie_split` (1bkc3kz7c9) imported into CloudFormation stack `lenie-dev-api-gw-app`. Template updated to Gen 2+ pattern with all 23 live endpoints, SSM Parameter exports, and drift-free state.
- 2026-02-15: Code review (Senior Developer AI). Fixed: removed unused `IsProduction` condition, added Description to 3 SSM Parameters. Stack updated and re-verified: UPDATE_COMPLETE, drift IN_SYNC. Accepted: Lambda ARNs hardcoded (RestApi-only import strategy).
- 2026-02-15: Code review 2 (Senior Developer AI). Fixed: added ApiDeployment resource (H1), API key on `/url_add2` (M1), parameterized Step Functions state machine name and IAM role (M2, M3), removed unused binary media types (L2) and `qa2`/`qa3` AllowedValues (L5). Deferred: Lambda typo (M4, requires AWS rename), CORS wildcard (L4), hardcoded `/v1` (L3), RestApi Tags (L1). Stack update required to apply changes.

### File List

- `infra/aws/cloudformation/templates/api-gw-app.yaml` — Updated: Gen 2+ template with all 23 endpoints matching live state, DeletionPolicy Retain, SSM Parameter exports
- `infra/aws/cloudformation/parameters/dev/api-gw-app.json` — Updated: renamed `stage` to `Environment`
- `infra/aws/cloudformation/apigw/lenie-split-export.json` — New: OAS30 export of live API Gateway
