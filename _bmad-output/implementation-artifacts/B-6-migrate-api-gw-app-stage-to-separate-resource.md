# Story B.6: Migrate API GW App Stage to Separate CloudFormation Resource

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **developer**,
I want to migrate the `v1` stage from the inline `StageName` property on `ApiDeployment` to a separate `AWS::ApiGateway::Stage` resource in `api-gw-app.yaml`,
so that stage configuration (logging, tracing, throttling) can be managed independently of deployments, matching the pattern already used in `api-gw-infra.yaml`.

## Acceptance Criteria

1. **AC1 — Separate Stage resource exists:** `api-gw-app.yaml` contains a new `AWS::ApiGateway::Stage` resource (`ApiStage`) with `StageName: v1`, `DeploymentId: !Ref ApiDeployment`, and `RestApiId: !Ref LenieApi`. The `ApiDeployment` resource no longer has `StageDescription` properties. *(Deviation: `StageName: v1` is retained on `ApiDeployment` because CloudFormation does not support removing it from an existing resource — see Debug Log.)*

2. **AC2 — Stage logging/tracing preserved:** The new `ApiStage` resource includes all current `StageDescription` settings migrated to Stage-level properties: `TracingEnabled: true`, `MethodSettings` with `LoggingLevel: INFO`, `MetricsEnabled: true`, `DataTraceEnabled: true` for all methods/resources (`HttpMethod: '*'`, `ResourcePath: '/*'`).

3. **AC3 — CloudFormation resource import succeeds:** The existing `v1` stage in AWS is imported into CloudFormation state as the `ApiStage` logical resource (not created as new). The import uses `aws cloudformation create-change-set --change-set-type IMPORT` with `ResourceIdentifier` specifying `RestApiId` and `StageName`.

4. **AC4 — Zero downtime:** The `v1` stage continues serving API requests throughout the migration. The custom domain `api.dev.lenie-ai.eu` base path mapping (`Stage: v1` in `api-gw-custom-domain.yaml`) works without modification.

5. **AC5 — cfn-lint validation passes:** The modified template passes `cfn-lint` with zero errors.

6. **AC6 — deploy.sh auto-redeploy still works:** The auto-redeployment hook in `deploy.sh` (line 122) continues to function correctly. The hook creates deployments via `aws apigateway create-deployment --stage-name v1` which targets the stage by name, not by CF resource — no script changes needed.

7. **AC7 — Template comments updated:** The B-6 backlog reference comment (line 629-631) is removed and replaced with a brief note confirming the stage is now a separate resource.

## Tasks / Subtasks

- [x] **Task 1: Prepare import template** (AC: #1, #2, #3)
  - [x] 1.1 Create a temporary version of `api-gw-app.yaml` that adds `ApiStage` resource WITHOUT removing `StageName` from `ApiDeployment` (both must coexist during import)
  - [x] 1.2 `ApiStage` resource must include: `RestApiId: !Ref LenieApi`, `DeploymentId: !Ref ApiDeployment`, `StageName: v1`, `DeletionPolicy: Retain`, `UpdateReplacePolicy: Retain`, `TracingEnabled: true`, and `MethodSettings` matching current `StageDescription`
  - [x] 1.3 Validate with cfn-lint

- [x] **Task 2: Execute CloudFormation resource import** (AC: #3, #4)
  - [x] 2.1 Get the REST API ID from SSM: `aws ssm get-parameter --name /lenie/dev/apigateway/app/id --query 'Parameter.Value' --output text`
  - [x] 2.2 Create import change set:
    ```bash
    aws cloudformation create-change-set \
      --stack-name lenie-dev-api-gw-app \
      --change-set-name import-api-stage \
      --change-set-type IMPORT \
      --template-body file://templates/api-gw-app.yaml \
      --parameters file://parameters/dev/api-gw-app.json \
      --capabilities CAPABILITY_NAMED_IAM \
      --resources-to-import '[{"ResourceType":"AWS::ApiGateway::Stage","LogicalResourceId":"ApiStage","ResourceIdentifier":{"RestApiId":"<API_ID>","StageName":"v1"}}]'
    ```
  - [x] 2.3 Review the change set: `aws cloudformation describe-change-set --stack-name lenie-dev-api-gw-app --change-set-name import-api-stage`
  - [x] 2.4 Execute the import: `aws cloudformation execute-change-set --stack-name lenie-dev-api-gw-app --change-set-name import-api-stage`
  - [x] 2.5 Wait for completion: `aws cloudformation wait stack-import-complete --stack-name lenie-dev-api-gw-app`
  - [x] 2.6 Verify stage is imported: `aws cloudformation describe-stack-resources --stack-name lenie-dev-api-gw-app --logical-resource-id ApiStage`

- [x] **Task 3: Finalize template — remove inline stage** (AC: #1, #2, #7)
  - [x] 3.1 ~~Remove `StageName: v1` from `ApiDeployment` Properties~~ — Retained: CloudFormation does not support removing `StageName` from an existing Deployment resource (UPDATE_ROLLBACK_FAILED). Stage is now managed by `ApiStage`; the property on `ApiDeployment` is inert.
  - [x] 3.2 Remove `Description: 'CF-managed deployment'` from `ApiDeployment` (optional cleanup) or keep
  - [x] 3.3 Remove entire `StageDescription` block from `ApiDeployment`
  - [x] 3.4 Remove the B-6 backlog reference comment (lines 629-631) and replace with note: `# Stage managed by separate ApiStage resource (migrated from inline StageName)`
  - [x] 3.5 Validate with cfn-lint

- [x] **Task 4: Deploy finalized template** (AC: #4, #5, #6)
  - [x] 4.1 Deploy via deploy.sh (or manual `aws cloudformation update-stack`) — this removes the inline stage from the deployment and lets the imported `ApiStage` resource own the stage
  - [x] 4.2 Verify auto-redeployment hook fires after stack update
  - [x] 4.3 Verify API responds: `curl -s -H "x-api-key: <KEY>" https://api.dev.lenie-ai.eu/website_list | head -c 200`
  - [x] 4.4 Verify stage settings preserved: `aws apigateway get-stage --rest-api-id <API_ID> --stage-name v1 | jq '{tracingEnabled, methodSettings}'`

- [x] **Task 5: Update documentation** (AC: #7)
  - [x] 5.1 Update `infra/aws/cloudformation/CLAUDE.md` — remove note about StageName on Deployment, confirm ApiStage is separate
  - [x] 5.2 Update `docs/infrastructure-metrics.md` if any counts changed (likely none — same number of resources conceptually)

## Dev Notes

### The Problem

In `api-gw-app.yaml`, the `v1` stage is defined inline on the `ApiDeployment` resource via `StageName: v1` and `StageDescription` properties. This couples stage lifecycle to deployment lifecycle:
- Stage settings (logging, tracing, throttling) can only be changed by modifying the Deployment resource
- `AWS::ApiGateway::Deployment` is immutable — changes to the RestApi Body don't propagate without a new deployment
- The `deploy.sh` auto-redeployment hook (story 11-3) works around this, but the template structure is non-standard

The `api-gw-infra.yaml` template already uses the correct pattern: separate `ApiStage` resource (line 582) with `ApiDeployment` having no `StageName` (line 589).

### Why CloudFormation Resource Import Is Required

The `v1` stage already exists in AWS, created by the `ApiDeployment` resource. Simply adding a new `ApiStage` resource would cause CloudFormation to CREATE a new `v1` stage, which FAILS because the name is already taken. Resource import tells CloudFormation to adopt the existing AWS resource into its state management.

### Historical Context

- **Story 11-3** originally separated the stage in the template, but **story 11-10** added `StageDescription` (logging/tracing) which requires `StageName` on the Deployment. The separation was reverted and B-6 was created as a dedicated backlog item.
- The current comment at line 629-630 explains: "StageName kept in Deployment for backward compatibility with existing v1 stage. Separating into ApiStage requires CF resource import (not creation)."

### Current Template Structure (pre-migration, historical reference)

```yaml
# NOTE: StageName kept in Deployment for backward compatibility with existing v1 stage.
# Separating into ApiStage requires CF resource import (not creation). See backlog (Story B.6).
# Stage logging, metrics, and X-Ray tracing are codified in StageDescription below.
ApiDeployment:
  Type: 'AWS::ApiGateway::Deployment'
  DeletionPolicy: Retain
  UpdateReplacePolicy: Retain
  Properties:
    RestApiId: !Ref LenieApi
    StageName: v1
    Description: 'CF-managed deployment'
    StageDescription:
      TracingEnabled: true
      MethodSettings:
        - HttpMethod: '*'
          ResourcePath: '/*'
          LoggingLevel: INFO
          MetricsEnabled: true
          DataTraceEnabled: true
```

### Target Template Structure

*(Updated to reflect actual implementation — `StageName: 'v1'` retained on `ApiDeployment` due to CF limitation.)*

```yaml
# Stage managed by separate ApiStage resource
ApiStage:
  Type: 'AWS::ApiGateway::Stage'
  DeletionPolicy: Retain
  UpdateReplacePolicy: Retain
  Properties:
    RestApiId: !Ref LenieApi
    DeploymentId: !Ref ApiDeployment
    StageName: 'v1'
    Description: 'CF-managed v1 stage'
    TracingEnabled: true
    MethodSettings:
      - HttpMethod: '*'
        ResourcePath: '/*'
        LoggingLevel: INFO
        MetricsEnabled: true
        DataTraceEnabled: true

# StageName kept on Deployment (CloudFormation does not support removing it from an existing resource)
ApiDeployment:
  Type: 'AWS::ApiGateway::Deployment'
  DeletionPolicy: Retain
  UpdateReplacePolicy: Retain
  Properties:
    RestApiId: !Ref LenieApi
    StageName: 'v1'
```

### Placement in Template

Insert `ApiStage` between `ApiDeployment` and the SSM Parameter exports section (`ApiGatewayIdParameter`). This follows the pattern in `api-gw-infra.yaml` (lines 582-595).

### Impact on Other Resources

- **`api-gw-custom-domain.yaml`** — `AppBasePathMapping` references `Stage: v1` as a string, not as `!Ref ApiStage`. No changes needed.
- **`deploy.sh`** — Auto-redeployment hook uses `aws apigateway create-deployment --stage-name v1` (string name, not CF ref). No changes needed.
- **SSM parameters** — `ApiGatewayInvokeUrlParameter` hardcodes `/v1` in the URL. No changes needed.
- **`deploy.ini`** — No template additions or removals. Same stack name.

### Three-Step Migration Process (CRITICAL)

**Step A: Import** — Add `ApiStage` to template while keeping `StageName` on `ApiDeployment`. Use `--change-set-type IMPORT` to import the existing `v1` stage. After this step, CloudFormation knows about `ApiStage` and it points to the existing AWS stage.

**Step B: Update** — Remove `StageName` and `StageDescription` from `ApiDeployment`. Run a normal stack update. CloudFormation now manages the stage entirely through `ApiStage`.

**Step C: Verify** — Confirm stage settings, API responses, and auto-redeployment all work.

**WARNING:** Steps A and B are separate CloudFormation operations. Do NOT combine them. The import must complete before the cleanup update.

### Rollback Plan

If the import fails or causes issues:
1. Delete the import change set: `aws cloudformation delete-change-set --stack-name lenie-dev-api-gw-app --change-set-name import-api-stage`
2. Revert `api-gw-app.yaml` to the current version (git checkout)
3. The `v1` stage is protected by `DeletionPolicy: Retain` on the original `ApiDeployment`
4. No data loss — the stage is just a configuration pointer

### Anti-Patterns to Avoid

- Do NOT try to create `ApiStage` with a normal stack update — it will fail with "Stage already exists"
- Do NOT delete the existing stage before import — this causes downtime and breaks the custom domain
- Do NOT use `aws apigateway delete-stage` as a workaround — the stage is in active use
- Do NOT modify `api-gw-custom-domain.yaml` — it uses stage name strings, not CF references
- Do NOT skip `DeletionPolicy: Retain` on `ApiStage` — protects against accidental stage deletion

### Architecture Compliance

- **Gen 2+ canonical pattern:** Parameters → Resources (SSM exports last) — maintained
- **`AWS::ApiGateway::Stage` is NOT taggable** in CloudFormation (confirmed in story 11-1) — no Tags property needed
- **Consistent with `api-gw-infra.yaml`** — same pattern (separate `ApiStage` + `ApiDeployment` without `StageName`)

### File Structure Notes

**Files to modify:**
- `infra/aws/cloudformation/templates/api-gw-app.yaml` — add `ApiStage`, remove inline stage from `ApiDeployment`
- `infra/aws/cloudformation/CLAUDE.md` — update api-gw-app entry to reflect separate stage

**No other files changed.** No parameter file changes. No deploy.ini changes. No deploy.sh changes.

### Testing Requirements

- **cfn-lint validation** on modified `api-gw-app.yaml` — zero errors required: `uvx cfn-lint infra/aws/cloudformation/templates/api-gw-app.yaml`
- **Import change set review** — verify the change set only imports `ApiStage`, no unexpected changes
- **API response test** — `curl` to `https://api.dev.lenie-ai.eu/website_list` with API key after migration
- **Stage settings verification** — `aws apigateway get-stage` confirms TracingEnabled, MethodSettings preserved
- **Auto-redeploy test** — modify a comment in the OpenAPI Body, run `deploy.sh`, verify auto-redeployment fires

### References

- [Source: infra/aws/cloudformation/templates/api-gw-app.yaml:628-649] — Current ApiDeployment with inline StageName and StageDescription
- [Source: infra/aws/cloudformation/templates/api-gw-infra.yaml:582-595] — Target pattern (separate ApiStage + ApiDeployment)
- [Source: infra/aws/cloudformation/templates/api-gw-custom-domain.yaml:69-83] — BasePathMappings reference Stage: v1 as string
- [Source: infra/aws/cloudformation/deploy.sh:116-139] — Auto-redeployment hook (uses stage name string)
- [Source: _bmad-output/implementation-artifacts/11-3-fix-apideployment-pattern-for-automatic-redeployment.md] — Original stage separation attempt + deploy.sh hook implementation
- [Source: _bmad-output/planning-artifacts/architecture.md:880] — B-6 listed as deferred decision
- [Source: infra/aws/cloudformation/CLAUDE.md#api-gw-app] — Stage configuration documentation, non-taggable resource note

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

- Initial attempt to remove `StageName` from `ApiDeployment` failed with `UPDATE_ROLLBACK_FAILED` — CloudFormation does not support removing `StageName` from an existing `AWS::ApiGateway::Deployment` resource. Fixed via `continue-update-rollback --resources-to-skip ApiDeployment`, then kept `StageName: v1` on deployment.
- After CF resource import, `MethodSettings` were empty on the stage. CF imported the resource as-is without applying template properties. Fixed by adding `Description` to `ApiStage` to force a CF update, which then applied all `MethodSettings`.

### Completion Notes List

- Migrated `v1` stage from inline `StageDescription` on `ApiDeployment` to separate `ApiStage` resource
- `StageName: v1` retained on `ApiDeployment` (CF limitation — cannot be removed from existing resource)
- Stage settings (TracingEnabled, MethodSettings with LoggingLevel, MetricsEnabled, DataTraceEnabled) now managed by `ApiStage`
- CF resource import executed successfully, stage adopted into CloudFormation management
- Verified: tracing enabled, method settings applied, API responding via custom domain, auto-redeploy works
- Pattern now consistent with `api-gw-infra.yaml` (separate `ApiStage` + `ApiDeployment`), with added `DeletionPolicy: Retain` and `UpdateReplacePolicy: Retain` on `ApiStage` for production safety (not present on infra template)

### Change Log

- 2026-02-24: Migrated API Gateway v1 stage to separate ApiStage CloudFormation resource (B-6)
- 2026-02-24: Code review fixes — updated AC1 deviation note, Task 3.1 CF limitation, DataTraceEnabled warning comment in template, Completion Notes clarification
- 2026-02-24: Code review #2 — fixed StageName quoting inconsistency (v1 → 'v1' on ApiDeployment), updated Target Template Structure to reflect CF limitation deviation, corrected sprint-status.yaml description in File List, reordered ApiStage before ApiDeployment (consistent with api-gw-infra.yaml), added DeletionPolicy/UpdateReplacePolicy to api-gw-infra.yaml ApiStage, fixed stale line references in Dev Notes

### File List

- `infra/aws/cloudformation/templates/api-gw-app.yaml` — Added `ApiStage` resource, removed `StageDescription` from `ApiDeployment`, updated comments
- `infra/aws/cloudformation/CLAUDE.md` — Updated api-gw-app documentation to reflect separate stage resource
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — Status updated: backlog → done
- `_bmad-output/implementation-artifacts/B-6-migrate-api-gw-app-stage-to-separate-resource.md` — Story file updated
