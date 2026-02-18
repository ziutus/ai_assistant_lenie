# Story 11.10: Codify API Gateway Stage Logging and Tracing in CloudFormation

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **developer**,
I want to add `StageDescription` with `MethodSettings` and `TracingEnabled` to the `ApiDeployment` resource in `api-gw-app.yaml`,
so that the API Gateway stage logging, metrics, and X-Ray tracing configuration is managed by CloudFormation instead of being manually configured in the AWS console.

## Acceptance Criteria

1. **AC1 — MethodSettings codified:** The `ApiDeployment` resource in `api-gw-app.yaml` includes a `StageDescription` with `MethodSettings` matching the current console configuration:
   - `LoggingLevel: INFO` (error and info logs)
   - `MetricsEnabled: true` (detailed CloudWatch metrics)
   - `DataTraceEnabled: true` (data tracing)
   - `HttpMethod: '*'` and `ResourcePath: '/*'` (applies to all methods/resources)

2. **AC2 — X-Ray tracing codified:** The `StageDescription` includes `TracingEnabled: true` for X-Ray tracing.

3. **AC3 — cfn-lint passes:** `api-gw-app.yaml` passes cfn-lint validation with zero errors after changes.

4. **AC4 — CloudFormation CLAUDE.md updated:** The manual stage configuration note in `infra/aws/cloudformation/CLAUDE.md` is updated to reflect that logging/tracing settings are now managed by CloudFormation via `StageDescription` on `ApiDeployment`.

5. **AC5 — DataTraceEnabled production consideration documented:** A comment in the template notes that `DataTraceEnabled: true` logs full request/response bodies and should be reviewed before enabling in production environments.

## Tasks / Subtasks

- [x] **Task 1: Verify CloudWatch IAM role prerequisite** (AC: #1)
  - [x] 1.1 Run `aws apigateway get-account` and confirm `cloudwatchRoleArn` is set. If not set, logging will silently fail — document the finding.
  - [x] 1.2 If `cloudwatchRoleArn` is NOT set, create the IAM role and configure it via `aws apigateway update-account` before proceeding. (If already set, skip.)

- [x] **Task 2: Add StageDescription to ApiDeployment** (AC: #1, #2, #5)
  - [x] 2.1 Add `StageDescription` property to `ApiDeployment` resource in `api-gw-app.yaml` (after `Description: 'CF-managed deployment'`, line 993)
  - [x] 2.2 Add `MethodSettings` list with a single wildcard entry: `HttpMethod: '*'`, `ResourcePath: '/*'`, `LoggingLevel: INFO`, `MetricsEnabled: true`, `DataTraceEnabled: true`
  - [x] 2.3 Add `TracingEnabled: true` to `StageDescription`
  - [x] 2.4 Add comment above `DataTraceEnabled` noting production consideration (logs full request/response bodies)

- [x] **Task 3: Update template comment** (AC: #1)
  - [x] 3.1 Update the existing comment block above `ApiDeployment` (lines 983-985) to reflect that stage logging/tracing is now codified in `StageDescription`

- [x] **Task 4: Update CloudFormation CLAUDE.md** (AC: #4)
  - [x] 4.1 Replace the manual stage configuration note in `infra/aws/cloudformation/CLAUDE.md` (`api-gw-app` stage configuration section) to state that logging/tracing settings are now managed via `StageDescription` in the CloudFormation template

- [x] **Task 5: Validate** (AC: #3)
  - [x] 5.1 Run `cfn-lint infra/aws/cloudformation/templates/api-gw-app.yaml` — zero errors expected
  - [x] 5.2 Verify `StageDescription` YAML structure is valid (correct indentation under `Properties`)

## Dev Notes

### Critical Architecture Context

**There is NO separate `ApiStage` resource in `api-gw-app.yaml`.** The `StageName: v1` is embedded directly in the `ApiDeployment` resource (line 992). This is different from `api-gw-infra.yaml` and `url-add.yaml` which have separate `AWS::ApiGateway::Stage` resources.

The comment at lines 983-985 explains why:
```
# NOTE: StageName kept in Deployment for backward compatibility with existing v1 stage.
# Separating into ApiStage requires CF resource import (not creation). See backlog.
```

Migrating to a separate `ApiStage` resource is tracked as **Story B.6** in the backlog. For THIS story, use `StageDescription` on the existing `ApiDeployment` resource instead.

### Implementation Approach: StageDescription on ApiDeployment

The `AWS::ApiGateway::Deployment` resource supports a `StageDescription` property that configures the stage created by the deployment. This is the correct approach given the current template structure.

**Target YAML structure** (add to `ApiDeployment.Properties`):

```yaml
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
            # DataTraceEnabled logs full request/response bodies.
            # Review before enabling in production environments.
            DataTraceEnabled: true
```

### CloudWatch IAM Role Prerequisite

API Gateway CloudWatch logging requires an IAM role at the **account level** (not per-API). Verify with:
```bash
aws apigateway get-account
```
The response must include a `cloudwatchRoleArn`. If absent, CloudWatch logging will silently fail even with `LoggingLevel: INFO` configured. This role must have the `AmazonAPIGatewayPushToCloudWatchLogs` managed policy.

### StageDescription vs Separate ApiStage Resource

| Aspect | StageDescription (this story) | Separate ApiStage (Story B.6) |
|--------|-------------------------------|-------------------------------|
| Requires CF resource import | No | Yes |
| Risk level | Low | Medium (immutable StageName) |
| Settings scope | MethodSettings, TracingEnabled | Full stage config + access logs |
| Long-term recommendation | Interim solution | Proper solution |

`StageDescription` is sufficient for codifying the current manual settings. When Story B.6 migrates to a separate `ApiStage` resource, the settings will move from `StageDescription` to the `ApiStage` resource properties.

### deploy.sh Interaction

After deploying `api-gw-app`, `deploy.sh` automatically runs `aws apigateway create-deployment` to apply RestApi Body changes. This creates a new deployment pointing to the existing `v1` stage. The `StageDescription` settings are applied by CloudFormation when it manages the `ApiDeployment` resource — the post-deploy script does not override them.

### Project Structure Notes

- `api-gw-app.yaml` is in Layer 6 (API) in `deploy.ini`
- No other templates need to be modified for this story
- The only documentation change is in `infra/aws/cloudformation/CLAUDE.md`

### References

- [Source: infra/aws/cloudformation/templates/api-gw-app.yaml:983-993] — Current ApiDeployment with StageName and comment
- [Source: infra/aws/cloudformation/CLAUDE.md] — Manual stage configuration note to be updated
- [Source: _bmad-output/planning-artifacts/epics.md#Story 11.10] — Story definition with acceptance criteria
- [Source: _bmad-output/planning-artifacts/architecture.md#Implementation Patterns] — Gen 2+ template standards
- [Source: infra/aws/cloudformation/templates/api-gw-infra.yaml:583-587] — Reference pattern: separate ApiStage resource
- [Source: infra/aws/cloudformation/templates/url-add.yaml:238-242] — Reference pattern: separate ApiStage resource

### Previous Story Intelligence

**From Story 11.9 (review) — Reconcile Lambda Function Name Mismatch:**
- Option B chosen: align all consumers to CF-defined name `lenie-dev-sqs-to-rds-lambda`
- Neither Lambda existed in AWS — clean-slate scenario
- Commit prefix: `chore:` for infrastructure template changes
- cfn-lint validation before commit
- All story deliverables committed together

**From Story 11.3 (done) — Fix ApiDeployment Pattern:**
- deploy.sh handles auto-redeployment after api-gw-app deploy
- ApiDeployment logical ID remains static (no hash technique)
- `DeletionPolicy: Retain` and `UpdateReplacePolicy: Retain` on ApiDeployment

### Git Intelligence

**Recent commits (pattern to follow):**
```
03725eb chore: add B-9 backlog item for S3 bucket directory structure
ae1cfff chore: reconcile Lambda function name mismatch (Story 11-9)
d587b98 chore: add SSM Parameter for DLQ ARN and commit Story 11-8 deliverables
7f82301 chore: complete stories 10-3 and 11-3 with code review fixes
```
- Commit prefix: `chore:` for infrastructure template changes
- Commit all story deliverables together (template + CLAUDE.md + story file)

### Files to Modify (Scope)

| File | Change |
|------|--------|
| `infra/aws/cloudformation/templates/api-gw-app.yaml` | Add `StageDescription` to `ApiDeployment` with MethodSettings and TracingEnabled |
| `infra/aws/cloudformation/CLAUDE.md` | Update manual stage configuration note |

**Files NOT to touch:**
```
infra/aws/cloudformation/parameters/dev/api-gw-app.json    [NO CHANGE] No new parameters
infra/aws/cloudformation/deploy.ini                         [NO CHANGE] Template already registered
infra/aws/cloudformation/deploy.sh                          [NO CHANGE]
infra/aws/cloudformation/templates/api-gw-infra.yaml        [NO CHANGE] Different API
infra/aws/cloudformation/templates/url-add.yaml             [NO CHANGE] Different API
```

### Library / Framework Requirements

No new libraries or dependencies. Pure CloudFormation template modification.

### Testing Requirements

**Validation (before commit):**
```bash
cfn-lint infra/aws/cloudformation/templates/api-gw-app.yaml
```

**Post-deployment verification (optional, after AWS deploy):**
```bash
# Verify stage settings applied
aws apigateway get-stage --rest-api-id <api-id> --stage-name v1

# Verify CloudWatch IAM role exists
aws apigateway get-account
```

**No unit or integration tests needed** — this is a pure infrastructure template and documentation change.

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6 (claude-opus-4-6)

### Debug Log References

### Completion Notes List

- ✅ Task 1: CloudWatch IAM role verified — `cloudwatchRoleArn` is set to `arn:aws:iam::008971653395:role/cw-ho-tf-dev-apigw`. Subtask 1.2 skipped (role already configured).
- ✅ Task 2: Added `StageDescription` to `ApiDeployment` in `api-gw-app.yaml` with `TracingEnabled: true`, wildcard `MethodSettings` (LoggingLevel: INFO, MetricsEnabled: true, DataTraceEnabled: true), and production consideration comment.
- ✅ Task 3: Updated comment block above `ApiDeployment` to reflect stage logging/tracing codification and reference Story B.6.
- ✅ Task 4: Replaced manual stage configuration note in `infra/aws/cloudformation/CLAUDE.md` with CloudFormation-managed description.
- ✅ Task 5: cfn-lint validation passed with zero errors. YAML structure verified.

### Change Log

- 2026-02-18: Codified API Gateway stage logging, metrics, and X-Ray tracing in CloudFormation `StageDescription` on `ApiDeployment` resource. Updated CLAUDE.md documentation. Added B-10 backlog item for CloudWatch IAM role CloudFormation template. Added B-11 backlog item for adding AWS account info to zip_to_s3.sh script.

### File List

| Action | File |
|--------|------|
| Modified | `infra/aws/cloudformation/templates/api-gw-app.yaml` |
| Modified | `infra/aws/cloudformation/CLAUDE.md` |
| Modified | `_bmad-output/implementation-artifacts/sprint-status.yaml` |
| Modified | `_bmad-output/implementation-artifacts/11-10-codify-api-gateway-stage-logging-and-tracing.md` |
