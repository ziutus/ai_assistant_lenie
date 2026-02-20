# Story 15.1: Merge /url_add Endpoint into api-gw-app.yaml

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **developer**,
I want to add the `/url_add` endpoint (POST + OPTIONS with CORS) and its Lambda permission into `api-gw-app.yaml`,
so that all application endpoints are served by a single API Gateway.

## Acceptance Criteria

1. **Given** `api-gw-url-add.yaml` defines a `/url_add` POST endpoint with Lambda proxy integration, **When** the developer adds the `/url_add` POST path to the OpenAPI Body in `api-gw-app.yaml`, **Then** the endpoint uses `!Sub` with `${ProjectCode}-${Environment}-url-add` for the Lambda integration URI, **And** the endpoint includes `security: [{api_key: []}]` (same as all other endpoints), **And** the timeout is set to 29000ms (matching current api-gw-url-add.yaml), **And** the path is added at the end of the paths section (after `/ai_embedding_get`).

2. **Given** the `/url_add` POST endpoint needs CORS support, **When** the developer adds the `/url_add` OPTIONS method, **Then** the OPTIONS method uses mock integration with CORS response headers (`Access-Control-Allow-Origin`, `Access-Control-Allow-Methods`, `Access-Control-Allow-Headers`), **And** the pattern matches existing OPTIONS methods in api-gw-app.yaml.

3. **Given** the url-add Lambda function needs invoke permission, **When** the developer adds `UrlAddLambdaInvokePermission` (AWS::Lambda::Permission) resource, **Then** `FunctionName` uses `!Sub '${ProjectCode}-${Environment}-url-add'`, **And** `SourceArn` is scoped to `/*/*/url_add` (not wildcard), **And** the resource is placed after the SSM Parameter resources (since no other Lambda permissions exist in this template).

4. **Given** all changes are applied to `api-gw-app.yaml`, **When** the developer checks the template file size, **Then** the template remains under the 51200 byte CloudFormation inline limit (current: ~9,589 bytes + ~3,000 bytes addition ≈ ~12,600 bytes — well within limit).

5. **Given** the modified template, **When** the developer runs cfn-lint validation, **Then** the template passes with zero errors.

6. **Given** existing endpoints in `api-gw-app.yaml`, **When** the developer reviews them, **Then** no existing endpoint definitions were modified during the merge.

## Tasks / Subtasks

- [x] Task 1: Add `/url_add` POST endpoint to OpenAPI Body (AC: #1)
  - [x] Read `api-gw-url-add.yaml` for exact POST endpoint definition
  - [x] Add `/url_add` POST path at end of paths section (after `/ai_embedding_get`)
  - [x] Use `!Sub` with `${ProjectCode}-${Environment}-url-add` for Lambda URI (NOT hardcoded, NOT `!Ref`)
  - [x] Include `security: [{api_key: []}]`
  - [x] Set timeout to 29000ms
  - [x] Set `contentHandling: "CONVERT_TO_TEXT"` and `passthroughBehavior: "when_no_match"`
- [x] Task 2: Add `/url_add` OPTIONS method for CORS (AC: #2)
  - [x] Copy mock integration pattern from any existing OPTIONS method in api-gw-app.yaml
  - [x] Include all three CORS response headers
  - [x] Verify headers match exactly: `Access-Control-Allow-Methods: 'DELETE,GET,HEAD,OPTIONS,PATCH,POST,PUT'`, `Access-Control-Allow-Headers: 'Content-Type,Authorization,X-Amz-Date,X-Api-Key,X-Amz-Security-Token'`, `Access-Control-Allow-Origin: '*'`
- [x] Task 3: Add `UrlAddLambdaInvokePermission` resource (AC: #3)
  - [x] Add `AWS::Lambda::Permission` resource after SSM Parameter resources
  - [x] `FunctionName: !Sub '${ProjectCode}-${Environment}-url-add'`
  - [x] `SourceArn: !Sub 'arn:aws:execute-api:${AWS::Region}:${AWS::AccountId}:${LenieApi}/*/*/url_add'`
  - [x] `Action: lambda:InvokeFunction`, `Principal: apigateway.amazonaws.com`
- [x] Task 4: Verify template file size (AC: #4)
  - [x] Check file size is under 51200 bytes — 29,647 bytes (58% of 51,200 limit)
  - [x] If exceeded (extremely unlikely at ~12.6 KB), document fallback to `aws cloudformation package`
- [x] Task 5: Run cfn-lint validation (AC: #5)
  - [x] Run `cfn-lint infra/aws/cloudformation/templates/api-gw-app.yaml` — zero errors
- [x] Task 6: Verify no existing endpoints modified (AC: #6)
  - [x] Review diff to confirm only additions, no modifications to existing paths or resources

## Dev Notes

### Architecture Compliance

**OpenAPI Merge Pattern (from Sprint 4 Architecture):**
- The `/url_add` endpoint must follow the exact same structure as existing endpoints in the OpenAPI Body
- This is the ONLY endpoint in api-gw-app.yaml that uses a parameterized Lambda name (`${ProjectCode}-${Environment}-url-add`)
- All other endpoints use hardcoded names (`lenie_2_db`, `lenie_2_internet`) — intentional, deferred to B-3
- Architecture explicitly calls this a "hybrid naming approach"

**Lambda Permission Pattern (from Architecture):**
```yaml
UrlAddLambdaInvokePermission:
  Type: AWS::Lambda::Permission
  Properties:
    FunctionName: !Sub '${ProjectCode}-${Environment}-url-add'
    Action: lambda:InvokeFunction
    Principal: apigateway.amazonaws.com
    SourceArn: !Sub 'arn:aws:execute-api:${AWS::Region}:${AWS::AccountId}:${LenieApi}/*/*/url_add'
```

**Anti-patterns (NEVER do):**
- Using `!Ref` or `Fn::GetAtt` for Lambda ARN instead of `!Sub` inline
- Changing existing endpoint definitions while adding /url_add
- Adding request/response models not present in existing endpoints
- Modifying the security scheme definition
- Using wildcard `/*/*` in SourceArn (must scope to `/url_add`)
- Migrating ApiKey/UsagePlan/UsagePlanKey resources from api-gw-url-add.yaml (use existing api-gw-app API key)

### Critical Technical Context

**Pre-implementation api-gw-app.yaml Structure (633 lines, ~9,589 bytes; post-implementation: 693 lines, 29,647 bytes, 11 endpoints):**
```
Parameters:
  ProjectCode (default: lenie)
  Environment (default: dev, AllowedValues: [dev])
Resources:
  LenieApi (AWS::ApiGateway::RestApi)
    Body: OpenAPI 3.0.1 spec with 10 endpoints
      paths:
        /website_list (GET+OPTIONS)
        /website_get (GET+OPTIONS)
        /website_save (POST+OPTIONS)
        /website_delete (GET+POST+OPTIONS)
        /website_is_paid (POST+OPTIONS)
        /website_get_next_to_correct (GET+OPTIONS)
        /website_similar (POST+OPTIONS)
        /website_split_for_embedding (POST+OPTIONS)
        /website_download_text_content (POST+OPTIONS)
        /ai_embedding_get (POST+OPTIONS)
      components:
        schemas: Empty
        securitySchemes: api_key (x-api-key header)
  ApiDeployment (AWS::ApiGateway::Deployment)
    StageName: v1
    Logging, metrics, X-Ray tracing enabled
  ApiGatewayIdParameter (SSM)
  ApiGatewayRootResourceIdParameter (SSM)
  ApiGatewayInvokeUrlParameter (SSM)
```

**Lambda Integration URI Pattern to use for /url_add:**
```yaml
uri: !Sub "arn:aws:apigateway:${AWS::Region}:lambda:path/2015-03-31/functions/arn:aws:lambda:${AWS::Region}:${AWS::AccountId}:function:${ProjectCode}-${Environment}-url-add/invocations"
```
Note: existing endpoints use hardcoded function names like `lenie_2_db` instead of `${ProjectCode}-${Environment}` — this is intentional hybrid state per architecture.

**Lambda Functions used in api-gw-app.yaml:**
| Lambda | Endpoints | Naming |
|--------|-----------|--------|
| `lenie_2_db` | website_list, website_get, website_save, website_delete, website_is_paid, website_get_next_to_correct, website_similar, website_split_for_embedding | Hardcoded (legacy, B-3) |
| `lenie_2_internet` | website_download_text_content, ai_embedding_get | Hardcoded (legacy, B-3) |
| `${ProjectCode}-${Environment}-url-add` | url_add (NEW) | Parameterized `!Sub` |

**CORS OPTIONS Mock Integration Pattern (copy from existing):**
```yaml
options:
  responses:
    "200":
      description: "200 response"
      headers:
        Access-Control-Allow-Origin:
          schema:
            type: "string"
        Access-Control-Allow-Methods:
          schema:
            type: "string"
        Access-Control-Allow-Headers:
          schema:
            type: "string"
      content: {}
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
      application/json: '{"statusCode": 200}'
    passthroughBehavior: "when_no_match"
```

**What NOT to change:**
- Do NOT modify any existing endpoint definitions in api-gw-app.yaml
- Do NOT migrate ApiKey, UsagePlan, or UsagePlanKey resources from api-gw-url-add.yaml
- Do NOT change the security scheme definition
- Do NOT change ApiDeployment or SSM Parameter resources
- Do NOT modify `deploy.ini` (api-gw-url-add.yaml is already commented out — removal is Story 15.3)
- Do NOT remove `api-gw-url-add.yaml` template file (that's Story 15.3)
- Do NOT update client application URLs (that's Story 15.2)

**What NOT to migrate from api-gw-url-add.yaml:**
- `LenieApiKey` (AWS::ApiGateway::ApiKey) — use existing api-gw-app API key
- `LenieUsagePlan` (AWS::ApiGateway::UsagePlan) — not needed
- `LenieUsagePlanKey` — not needed
- Outputs section — api-gw-app.yaml already has SSM Parameters

**deploy.ini Current State:**
```ini
; --- Layer 6: API ---
templates/api-gw-infra.yaml
templates/api-gw-app.yaml
; templates/api-gw-url-add.yaml  ; UNUSED duplicate
```
The `api-gw-url-add.yaml` is already commented out — no deploy.ini changes needed for this story.

### File Structure

Only one file modified:

| File | Action | Description |
|------|--------|-------------|
| `infra/aws/cloudformation/templates/api-gw-app.yaml` | MOD | Add `/url_add` POST+OPTIONS paths + `UrlAddLambdaInvokePermission` resource |

Verification-only files (read, no changes):

| File | Verification |
|------|-------------|
| `infra/aws/cloudformation/templates/api-gw-url-add.yaml` | Reference for /url_add endpoint definition |
| `infra/aws/cloudformation/deploy.ini` | Confirm api-gw-url-add.yaml already commented out |

### Testing Requirements

1. **cfn-lint validation:** `cfn-lint infra/aws/cloudformation/templates/api-gw-app.yaml` — zero errors
2. **Template validation:** `aws cloudformation validate-template --template-body file://infra/aws/cloudformation/templates/api-gw-app.yaml` — valid
3. **File size check:** Verify < 51200 bytes (expected ~12.6 KB)
4. **Diff review:** Confirm only additions, no modifications to existing content

### Previous Story Intelligence

**From Story 14.2 (Fix Redundant Lambda FunctionName):**
- CRITICAL lesson: Always check for naming conflicts before assuming a simple rename — Story 14.2 discovered that `api-gw-infra.yaml` already created the target Lambda function name, leading to a different resolution path
- cfn-lint validation as standard quality gate
- Minimal change approach: only modify what the AC specifies
- Commit message pattern: `fix:` prefix with story reference

**From Story 14.1 (Remove Elastic IP):**
- Clean removal pattern: no remnants, no placeholder comments
- Verification-driven tasks work well for confirming existing behavior
- Code review caught stale documentation references — remember to verify related docs

**Key learnings applicable to 15.1:**
- The `api-gw-app.yaml` template has `DeletionPolicy: Retain` on the main API resource — safe to modify
- No Lambda permission resources currently exist in api-gw-app.yaml — the new `UrlAddLambdaInvokePermission` will be the first one
- The existing 10 endpoints all use the same CORS OPTIONS pattern — copy exactly
- api-gw-url-add.yaml is already commented out in deploy.ini from previous work

**From Sprint 4 Git History (last 15 commits):**
- `4ec15ca` — Merge remote-tracking branch into bmad-method
- `1a0fb83` — fix: upgrade flask+werkzeug (security)
- `00069d5` — fix: remove stale EIP references (Story 14-1 review)
- `2518e2d` — fix: add missing EC2/SQS IAM permissions (Story 14-2 review)
- `edc94c6` — fix: consolidate rds-start Lambda (Story 14-2)
- Pattern: conventional commits (fix:, feat:, docs:) with story references

### Project Structure Notes

- `api-gw-app.yaml` is in Layer 6 (API) of deploy.ini
- Story 15.1 is the first story in Epic 15 (API Gateway Consolidation)
- Sprint 4 architecture specifies: B-14 (this story's parent backlog item) is the most architecturally complex story in the sprint
- Implementation sequence: B-5 (done) → B-14 (this) → B-19 (documentation)
- After this story: Story 15.2 updates client app URLs, Story 15.3 removes old template and CF stack

### References

- [Source: _bmad-output/planning-artifacts/epics.md — Epic 15, Story 15.1]
- [Source: _bmad-output/planning-artifacts/architecture.md — Sprint 4, API Gateway Consolidation Strategy]
- [Source: _bmad-output/planning-artifacts/architecture.md — Sprint 4, OpenAPI Merge Pattern (B-14)]
- [Source: _bmad-output/planning-artifacts/architecture.md — Sprint 4, Lambda Permission Resource Pattern (B-14)]
- [Source: _bmad-output/planning-artifacts/architecture.md — Sprint 4, Enforcement Guidelines]
- [Source: infra/aws/cloudformation/templates/api-gw-app.yaml — LenieApi OpenAPI Body, 10 endpoints]
- [Source: infra/aws/cloudformation/templates/api-gw-url-add.yaml — /url_add POST+OPTIONS definition, LambdaInvokePermission]
- [Source: infra/aws/cloudformation/deploy.ini — api-gw-url-add.yaml already commented out]
- [Source: _bmad-output/implementation-artifacts/14-2-fix-redundant-lambda-function-name-in-lambda-rds-start.md — Previous story learnings]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

No issues encountered during implementation.

### Completion Notes List

- Added `/url_add` POST endpoint to api-gw-app.yaml OpenAPI Body (after `/ai_embedding_get`)
- Lambda integration URI uses parameterized `!Sub` with `${ProjectCode}-${Environment}-url-add` (hybrid naming approach per architecture)
- Added `/url_add` OPTIONS method with mock CORS integration (identical pattern to all 10 existing endpoints)
- Added `UrlAddLambdaInvokePermission` (AWS::Lambda::Permission) scoped to `/*/*/url_add` path
- Template size: 29,647 bytes (58% of 51,200 byte limit) — well within bounds
- cfn-lint validation: zero errors
- git diff confirms only additions, zero modifications to existing endpoints or resources
- api-gw-app.yaml now has 11 endpoints (was 10): website_list, website_get, website_save, website_delete, website_is_paid, website_get_next_to_correct, website_similar, website_split_for_embedding, website_download_text_content, ai_embedding_get, url_add

### File List

| File | Action | Description |
|------|--------|-------------|
| `infra/aws/cloudformation/templates/api-gw-app.yaml` | MOD | Added /url_add POST+OPTIONS paths (lines 567-617) and UrlAddLambdaInvokePermission resource (lines 685-692) |
| `infra/aws/cloudformation/parameters/dev/url-add.json` | MOD | Timestamp auto-update during deployment |

## Change Log

| Date | Change | Story |
|------|--------|-------|
| 2026-02-20 | Merged /url_add endpoint (POST+OPTIONS with CORS) and Lambda permission into api-gw-app.yaml; template now serves 11 application endpoints via single API Gateway | 15-1 |
| 2026-02-20 | Code review: fixed 4 issues (stale endpoint/Lambda counts in 4 doc files, undocumented file in File List, story reference in CF comment, clarified Dev Notes pre/post state). 2 LOW issues deferred (cfn-lint independent verification, deploy.ini comment cleanup for Story 15.3). | 15-1 review |
