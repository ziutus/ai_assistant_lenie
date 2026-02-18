# Story 11.3: Fix ApiDeployment Pattern for Automatic Redeployment

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **developer**,
I want to fix the `ApiDeployment` resource in `api-gw-app.yaml` to force redeployment when RestApi Body changes,
So that API Gateway redeploys automatically without requiring manual `aws apigateway create-deployment`.

## Acceptance Criteria

1. **AC1 — Separate Stage from Deployment:** The `ApiDeployment` resource no longer contains `StageName`. A new `AWS::ApiGateway::Stage` resource (`ApiStage`) is created with `StageName: v1` and `DeploymentId` pointing to the deployment resource. The existing `v1` stage continues to function after the stack update.

2. **AC2 — Automatic redeployment mechanism:** The `deploy.sh` script automatically triggers a new API Gateway deployment after updating the `api-gw-app` stack. When a developer modifies the RestApi Body and runs `deploy.sh`, the API Gateway reflects the changes without any manual `aws apigateway create-deployment` command.

3. **AC3 — cfn-lint validation passes:** The modified template passes cfn-lint validation with zero errors.

## Tasks / Subtasks

- [x] **Task 1: Separate Stage from Deployment resource** (AC: #1)
  - [x] 1.1 Remove `StageName: v1` from `ApiDeployment` resource
  - [x] 1.2 Create `ApiStage` resource (`AWS::ApiGateway::Stage`) with `StageName: v1`, `DeploymentId: !Ref ApiDeployment`, `RestApiId: !Ref LenieApi`
  - [x] 1.3 Update `ApiGatewayInvokeUrlParameter` SSM if it references the stage name (verify `/v1` path is still correct)
  - [x] 1.4 Verify the template passes cfn-lint with zero errors

- [x] **Task 2: Add auto-redeployment to deploy.sh** (AC: #2)
  - [x] 2.1 Read current `deploy.sh` to understand the stack processing loop and identify the insertion point
  - [x] 2.2 After `create-stack` or `update-stack` completes for `api-gw-app`, call `aws apigateway create-deployment --rest-api-id <id> --stage-name v1`
  - [x] 2.3 Retrieve the REST API ID from SSM parameter (`/${ProjectCode}/${Environment}/apigateway/app/id`) or stack output
  - [x] 2.4 Add error handling: if the `create-deployment` call fails, print a warning but do not abort the script
  - [x] 2.5 Test by running `deploy.sh` with change-set mode (`-t`) to verify the hook logic (dry run)

- [x] **Task 3: Validate and verify** (AC: #3)
  - [x] 3.1 Run cfn-lint on modified `api-gw-app.yaml` — zero errors required
  - [x] 3.2 Verify template structure follows canonical pattern (Parameters → Resources with SSM exports last)
  - [x] 3.3 Document the deployment behavior change in `infra/aws/cloudformation/CLAUDE.md` (one sentence about auto-redeployment)

## Dev Notes

### The Problem

`AWS::ApiGateway::Deployment` creates an **immutable snapshot** of the API configuration. When the `LenieApi` Body (OpenAPI spec) changes, CloudFormation updates the RestApi resource but does NOT create a new deployment — the existing `ApiDeployment` still points to the old snapshot. This is a known CloudFormation limitation: deployment resources are immutable and only a new physical resource (new logical ID) captures Body changes.

**Current template structure (`api-gw-app.yaml` lines 984-991):**
```yaml
ApiDeployment:
  Type: 'AWS::ApiGateway::Deployment'
  DeletionPolicy: Retain
  UpdateReplacePolicy: Retain
  Properties:
    RestApiId: !Ref LenieApi
    StageName: v1
    Description: 'CF-managed deployment'
```

**Why this fails:** Changing the Body of `LenieApi` and running a stack update causes CloudFormation to update the RestApi but skip the Deployment — its logical ID (`ApiDeployment`) and properties haven't changed, so CF sees no reason to recreate it. The stage `v1` continues serving the old API configuration.

### Solution Design

Two complementary changes:

**1. Template change — Separate Stage from Deployment (best practice):**
- Remove `StageName` from `ApiDeployment`
- Create a new `ApiStage` (`AWS::ApiGateway::Stage`) resource
- This is the AWS-recommended pattern for managing API Gateway in CloudFormation — it separates the immutable deployment snapshot from the mutable stage configuration

**2. Script change — Auto-redeployment in `deploy.sh`:**
- After `deploy.sh` creates/updates the `api-gw-app` stack, automatically call `aws apigateway create-deployment`
- This creates a NEW deployment snapshot capturing the current Body state and points the stage to it
- The REST API ID is available from SSM: `/${ProjectCode}/${Environment}/apigateway/app/id`

**Why both changes:** The template change establishes correct CloudFormation structure. The script change provides the actual automation — pure CloudFormation cannot auto-redeploy REST APIs (only API Gateway V2 HTTP APIs support `AutoDeploy`).

### Important: Stage Migration During First Deployment

**CRITICAL:** The current template has `StageName: v1` on the `ApiDeployment` resource. This means CloudFormation manages the stage as part of the deployment. When we remove `StageName` from `ApiDeployment` and add a separate `ApiStage` resource, CloudFormation may try to create a NEW stage `v1` while the old one still exists (owned by the deployment).

**Migration approach:**
- The existing `v1` stage was created by the `ApiDeployment` resource with `StageName: v1`
- Removing `StageName` from `ApiDeployment` will cause CF to "disassociate" the stage from the deployment
- Adding `ApiStage` with `StageName: v1` should adopt the existing stage
- If CloudFormation reports a conflict (stage already exists), the developer may need to:
  1. First deploy with `StageName` removed from `ApiDeployment` but WITHOUT `ApiStage` yet
  2. Then deploy again with `ApiStage` added
- **Test with change-set mode first** (`deploy.sh -t`) to preview what CloudFormation will do

**Alternative if migration is problematic:** Keep `StageName: v1` on `ApiDeployment` (skip Task 1) and ONLY implement the `deploy.sh` auto-redeployment (Task 2). The auto-redeployment solves the actual problem regardless of template structure.

### Technical Requirements

**Scope: 2 files modified (1 template, 1 script), optionally 1 documentation update.**

#### Template Change: `infra/aws/cloudformation/templates/api-gw-app.yaml`

**Current `ApiDeployment` (lines 984-991):**
```yaml
ApiDeployment:
  Type: 'AWS::ApiGateway::Deployment'
  DeletionPolicy: Retain
  UpdateReplacePolicy: Retain
  Properties:
    RestApiId: !Ref LenieApi
    StageName: v1
    Description: 'CF-managed deployment'
```

**Target — Remove StageName, add separate Stage resource:**
```yaml
ApiDeployment:
  Type: 'AWS::ApiGateway::Deployment'
  DeletionPolicy: Retain
  UpdateReplacePolicy: Retain
  Properties:
    RestApiId: !Ref LenieApi
    Description: 'CF-managed deployment'

ApiStage:
  Type: 'AWS::ApiGateway::Stage'
  Properties:
    RestApiId: !Ref LenieApi
    DeploymentId: !Ref ApiDeployment
    StageName: v1
    Description: 'Main application API stage'
```

**Placement:** Insert `ApiStage` between `ApiDeployment` and the SSM Parameter exports section (before `ApiGatewayIdParameter`).

**SSM invoke URL (line 1021):** Currently uses `!Sub 'https://${LenieApi}.execute-api.${AWS::Region}.amazonaws.com/v1'` — this hardcodes `/v1` and does NOT reference `ApiDeployment.StageName`. No change needed.

#### Script Change: `infra/aws/cloudformation/deploy.sh`

**Current flow in `create_update_stack` function (lines 82-113):**
```bash
for template in "${templates[@]}"
do
  # ... get stack_name, determine cf_action ...
  cf_execute "${cf_action}" "${stack_name}" "${template}"
done
```

**Target — Add post-deploy hook after `cf_execute` in the loop:**
```bash
cf_execute "${cf_action}" "${stack_name}" "${template}"

# Auto-redeploy API Gateway after api-gw-app stack update
local file_name
file_name=$(get_file_name "${template}")
if [ "${file_name}" == "api-gw-app" ]; then
  log "Auto-redeploying API Gateway for ${stack_name}..."
  local api_id
  api_id=$(aws --region "${REGION}" ssm get-parameter \
    --name "/${PROJECT_CODE}/${STAGE}/apigateway/app/id" \
    --query 'Parameter.Value' --output text 2>/dev/null) || true
  if [ -n "${api_id}" ]; then
    if aws --region "${REGION}" apigateway create-deployment \
      --rest-api-id "${api_id}" --stage-name v1 \
      --description "Auto-deploy after CF stack update ${DATE}" 2>/dev/null; then
      log "API Gateway redeployed successfully (API ID: ${api_id})"
    else
      log "WARNING: API Gateway auto-redeploy failed. Run manually: aws apigateway create-deployment --rest-api-id ${api_id} --stage-name v1"
    fi
  else
    log "WARNING: Could not retrieve API Gateway ID from SSM. Auto-redeploy skipped."
  fi
fi
```

**Key considerations for deploy.sh modification:**
- Use `get_file_name` (already exists, line 122) to extract template name without path/extension
- Retrieve REST API ID from SSM parameter `/${PROJECT_CODE}/${STAGE}/apigateway/app/id` (created by the same template)
- Stage name `v1` is hardcoded (matches the template)
- `|| true` after `aws ssm get-parameter` prevents `set -e` from aborting on failure
- Error handling: log a warning but never abort — the stack update itself succeeded
- The `${DATE}` variable (line 10) is already available globally for the description
- **Change-set mode (`-t`):** The auto-redeploy should ONLY run after actual execution, not after change-set creation. Check: in change-set mode, `cf_execute` doesn't wait for stack update, so `create_update_stack` flow is different. The hook should be gated on `"${CHANGE_SET}" != true`

**deploy.sh architecture (relevant functions):**
- `parse_config` (line 61) — reads `deploy.ini`, populates `TEMPLATES[]`
- `create_update_stack` (line 82) — iterates templates, calls `cf_execute` per template
- `cf_execute` (line 179) — handles create/update/changeset, waits for completion
- `get_file_name` (line 122) — extracts filename without path and extension
- `get_stack_name` (line 115) — builds `${PROJECT_CODE}-${STAGE}-<filename>`
- Timestamp update (line 198) — auto-updates `timestamp` parameter in JSON files
- Script uses `set -eu` (line 2) — errors abort immediately, so `|| true` is essential for non-critical calls

### Architecture Compliance

**Gen 2+ canonical pattern:**
- Parameters → Resources (SSM exports last) — maintained
- `AWS::ApiGateway::Stage` is NOT taggable in CloudFormation (no Tags property)
- `AWS::ApiGateway::Deployment` is NOT taggable (confirmed in Story 11.1)
- No new SSM Parameters needed — existing exports still valid
- No new parameters needed in the template

**Anti-patterns to avoid:**
- Do NOT add `Outputs` section (use SSM Parameters — project standard)
- Do NOT hardcode the REST API ID in `deploy.sh` — always resolve from SSM
- Do NOT skip error handling in the script hook — `set -e` will kill the script

### Library / Framework Requirements

- **cfn-lint**: `uvx cfn-lint infra/aws/cloudformation/templates/api-gw-app.yaml`
- **aws CLI**: Required for `apigateway create-deployment` and `ssm get-parameter`
- No new libraries or dependencies

### File Structure Notes

**Files to modify:**
- `infra/aws/cloudformation/templates/api-gw-app.yaml` — separate Stage from Deployment
- `infra/aws/cloudformation/deploy.sh` — add auto-redeployment hook

**Optional documentation update:**
- `infra/aws/cloudformation/CLAUDE.md` — mention auto-redeployment behavior in `api-gw-app.yaml` entry

**No other files changed.** No parameter file changes needed (no new parameters).

### Testing Requirements

- **cfn-lint validation** on modified `api-gw-app.yaml` — zero errors required
- **No unit tests** — CloudFormation + shell script changes, no backend/frontend code
- **Change-set preview:** Run `deploy.sh -p lenie -s dev -t` to preview CloudFormation changes before actual deployment
- **Script verification:** After modifying `deploy.sh`, run with `bash -n deploy.sh` to check for syntax errors
- **Regression check:** Verify the SSM parameter `/${ProjectCode}/${Environment}/apigateway/app/id` exists and resolves to the correct REST API ID before testing the hook

### Project Structure Notes

- All changes are within `infra/aws/cloudformation/` directory
- No backend, frontend, or Lambda code changes
- `deploy.ini` does NOT need changes (no new templates added or removed)
- Parameter file `parameters/dev/api-gw-app.json` does NOT need changes (no new parameters)

### Previous Story Intelligence

**From Story 11.2 (done):**
- Modified `sqs-to-rds-step-function.yaml` — replaced `{{resolve:ssm:...}}` with `AWS::SSM::Parameter::Value<String>` and parameterized Lambda name via `DefinitionSubstitutions`
- cfn-lint v1.44.0 used — zero errors
- Commit prefix: `chore:` for cleanup/maintenance work
- Lambda name mismatch confirmed: deployed `lenie-sqs-to-db` vs CF-defined `lenie-dev-sqs-to-rds-lambda` — this story doesn't need to touch the step function template
- Code review applied: parameter ordering fix (SSM params before String params, after foundation params)

**From Story 11.1 (done):**
- `api-gw-app.yaml` was modified: added `qa2`, `qa3` to AllowedValues, added tags to RestApi, SSM Params already tagged
- Story 10-3 (review) previously modified `api-gw-app.yaml` — removed `/infra/ip-allow` endpoint from the Body. Working tree may have uncommitted changes from 10-3 — **verify git status before making changes**
- Non-taggable resources documented: `AWS::ApiGateway::Deployment` and `AWS::ApiGateway::Stage` do NOT support Tags in CloudFormation
- Parameter files follow standard format: `[{"ParameterKey": "ProjectCode", "ParameterValue": "lenie"}, ...]`

**From Epic 10 stories:**
- Story 10-3 is in "review" status — it modified `api-gw-app.yaml` (removed `/infra/ip-allow`). The current working tree has `infra/aws/cloudformation/apigw/lenie-split-export.json` as modified. Ensure Story 11.3 changes build on top of the 10-3 changes.

### Git Intelligence

**Recent commits (most recent first):**
```
4e790af chore: add __pycache__/ to .gitignore
4a11307 chore: replace resolve:ssm with SSM Parameter types and parameterize Lambda name in step function
21391f3 docs: update story 11.1 with code review round 2 results and cfn-lint verification
2005495 chore: parameterize hardcoded values in sqs-application-errors, budget, and secrets templates
f2fc017 chore: add parameter files and fix hardcoded S3 reference in lambda-weblink-put-into-sqs
```

**Patterns:**
- Commit prefix: `chore:` for infrastructure cleanup/maintenance
- This story fits the `chore:` category
- `deploy.sh` has NOT been modified in recent commits — changes will be the first script modification in Sprint 3

**Working tree status (at conversation start):**
- `M .claude/settings.local.json`
- `M infra/aws/cloudformation/apigw/lenie-split-export.json` (from Story 10-3)
- `?? _bmad-output/implementation-artifacts/10-3-remove-infra-ip-allow-endpoint.md` (untracked)

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 11.3] — Original story definition with ACs (FR22, FR23)
- [Source: _bmad-output/planning-artifacts/architecture.md#Starter Template Evaluation] — Gen 2+ canonical template pattern
- [Source: _bmad-output/planning-artifacts/architecture.md#Implementation Patterns & Consistency Rules] — Enforcement guidelines, anti-patterns
- [Source: infra/aws/cloudformation/CLAUDE.md] — Template overview, deploy.sh usage, deployment order documentation
- [Source: infra/aws/cloudformation/deploy.sh:82-113] — `create_update_stack` function (insertion point for auto-redeploy hook)
- [Source: infra/aws/cloudformation/deploy.sh:122-128] — `get_file_name` helper function
- [Source: infra/aws/cloudformation/deploy.sh:179-235] — `cf_execute` function (create/update/changeset logic)
- [Source: infra/aws/cloudformation/templates/api-gw-app.yaml:984-991] — Current `ApiDeployment` resource
- [Source: infra/aws/cloudformation/templates/api-gw-app.yaml:994-1026] — SSM Parameter exports
- [Source: _bmad-output/implementation-artifacts/11-2-*.md#Completion Notes] — Previous story learnings
- [Source: _bmad-output/implementation-artifacts/11-1-*.md#Completion Notes] — Tagging story learnings, non-taggable resources list

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

- cfn-lint validation: zero errors on `api-gw-app.yaml` (cfn-lint v1.44.0)
- bash -n syntax check: zero errors on `deploy.sh`

### Completion Notes List

- **Task 1**: Separated `ApiStage` from `ApiDeployment` in `api-gw-app.yaml`. Removed `StageName: v1` from `ApiDeployment`, created new `AWS::ApiGateway::Stage` resource (`ApiStage`) with `StageName: v1`, `DeploymentId: !Ref ApiDeployment`, and `RestApiId: !Ref LenieApi`. Verified SSM invoke URL hardcodes `/v1` and requires no changes.
- **Task 2**: Added auto-redeployment hook in `deploy.sh` `create_update_stack` function. After `cf_execute` completes for `api-gw-app`, the script retrieves the REST API ID from SSM (`/${PROJECT_CODE}/${STAGE}/apigateway/app/id`) and calls `aws apigateway create-deployment --stage-name v1`. Error handling: SSM lookup failure and create-deployment failure both log warnings without aborting. Hook is gated on `CHANGE_SET != true` to avoid running during change-set preview mode.
- **Task 3**: cfn-lint passes with zero errors. Template structure verified (Parameters → Resources with SSM exports last). Documented auto-redeployment behavior in `infra/aws/cloudformation/CLAUDE.md`.
- **Code Review Fixes**: Added `STACK_UPDATED` flag to prevent unnecessary API Gateway redeployment when stack has no updates. Captured stderr from `create-deployment` for proper error diagnostics (replaced `2>/dev/null` with `2>&1`). Added `DeletionPolicy: Retain` and `UpdateReplacePolicy: Retain` to `ApiStage` for consistency with `ApiDeployment`. Documented changeset-mode auto-redeploy limitation as a known gap. Fixed glob pattern for "No updates are to be performed" AWS CLI error matching.

### Change Log

- 2026-02-17: Story created by create-story workflow — comprehensive developer guide with template change pattern, deploy.sh auto-redeploy hook, and stage migration strategy
- 2026-02-17: Implementation complete — separated ApiStage from ApiDeployment, added auto-redeployment hook to deploy.sh, documented behavior change in CLAUDE.md
- 2026-02-17: Code review (adversarial) — 5 issues found (3 MEDIUM, 2 LOW). All fixed: (1) STACK_UPDATED flag prevents unnecessary redeploy on "no updates", (2) stderr captured in create-deployment for proper error diagnostics, (3) changeset limitation documented as known gap, (4) DeletionPolicy/UpdateReplacePolicy: Retain added to ApiStage for consistency, (5) sprint-status.yaml added to File List. Also fixed glob pattern for "No updates are to be performed" string matching.

### File List

- `infra/aws/cloudformation/templates/api-gw-app.yaml` — modified (removed StageName from ApiDeployment, added ApiStage resource with DeletionPolicy/UpdateReplacePolicy: Retain)
- `infra/aws/cloudformation/deploy.sh` — modified (added auto-redeployment hook with STACK_UPDATED guard, proper error capture, changeset limitation documented)
- `infra/aws/cloudformation/CLAUDE.md` — modified (documented auto-redeployment behavior)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — modified (11-3: backlog → review)
