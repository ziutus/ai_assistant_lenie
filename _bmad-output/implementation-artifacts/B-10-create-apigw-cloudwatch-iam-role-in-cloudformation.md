# Story B-10: Create API Gateway CloudWatch IAM Role in CloudFormation

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **developer**,
I want to manage the API Gateway CloudWatch IAM role and Account resource via CloudFormation,
so that CloudWatch logging for API Gateway is fully codified in IaC and not dependent on a manually-created Terraform role.

## Acceptance Criteria

1. **AC1 — IAM Role created in CloudFormation:** A new CloudFormation template creates an IAM Role with the `AmazonAPIGatewayPushToCloudWatchLogs` AWS managed policy attached, following the project naming convention `${ProjectCode}-${Environment}-apigw-cloudwatch-role`.

2. **AC2 — API Gateway Account resource configured:** The template includes an `AWS::ApiGateway::Account` resource that sets the `CloudWatchRoleArn` to the newly created IAM role, enabling CloudWatch logging for all API Gateways in the account/region.

3. **AC3 — Template registered in deploy.ini:** The new template is added to `deploy.ini` in the `[dev]` section, positioned before `api-gw-infra.yaml` (first entry in Layer 6: API) so that the Account resource exists before any API Gateway templates that depend on logging.

4. **AC4 — cfn-lint passes:** The new template passes cfn-lint validation with zero errors.

5. **AC5 — SSM export (optional):** The IAM Role ARN is exported to SSM Parameter Store at `/${ProjectCode}/${Environment}/apigw/cloudwatch-role-arn` for cross-stack reference if needed.

6. **AC6 — Documentation updated:** `infra/aws/cloudformation/CLAUDE.md` is updated to document the new template and remove the note about verifying `cloudwatchRoleArn` manually. `docs/infrastructure-metrics.md` template count is updated.

7. **AC7 — Existing logging continues to work:** After deployment, `api-gw-app.yaml` stage logging (LoggingLevel: INFO, MetricsEnabled: true, TracingEnabled: true) continues to function correctly with the new CloudFormation-managed role replacing the Terraform-created role.

## Tasks / Subtasks

- [x] **Task 1: Create CloudFormation template `api-gw-account.yaml`** (AC: #1, #2, #5)
  - [x] 1.1 Create `infra/aws/cloudformation/templates/api-gw-account.yaml` with parameters: `ProjectCode`, `Environment`
  - [x] 1.2 Add IAM Role resource (`ApiGatewayCloudWatchRole`) with:
    - AssumeRolePolicyDocument allowing `apigateway.amazonaws.com` to assume the role
    - ManagedPolicyArns: `arn:aws:iam::aws:policy/service-role/AmazonAPIGatewayPushToCloudWatchLogs`
    - RoleName: `!Sub "${ProjectCode}-${Environment}-apigw-cloudwatch-role"`
    - Tags: Project, Environment
  - [x] 1.3 Add `AWS::ApiGateway::Account` resource (`ApiGatewayAccount`) with:
    - `CloudWatchRoleArn: !GetAtt ApiGatewayCloudWatchRole.Arn`
    - DependsOn: ApiGatewayCloudWatchRole
  - [x] 1.4 Add SSM Parameter export: `/${ProjectCode}/${Environment}/apigw/cloudwatch-role-arn`
  - [x] 1.5 Add Outputs section with role ARN

- [x] **Task 2: Create parameter file** (AC: #3)
  - [x] 2.1 Create `infra/aws/cloudformation/parameters/dev/api-gw-account.json` with `ProjectCode: lenie`, `Environment: dev`

- [x] **Task 3: Register in deploy.ini** (AC: #3)
  - [x] 3.1 Add `templates/api-gw-account.yaml` as the FIRST entry in Layer 6 (API), before `templates/api-gw-infra.yaml`
  - [x] 3.2 Add comment explaining this is an account-level prerequisite for API Gateway CloudWatch logging

- [x] **Task 4: Validate template** (AC: #4)
  - [x] 4.1 Run `cfn-lint infra/aws/cloudformation/templates/api-gw-account.yaml` — zero errors expected

- [x] **Task 5: Update documentation** (AC: #6)
  - [x] 5.1 Update `infra/aws/cloudformation/CLAUDE.md`:
    - Add `api-gw-account.yaml` entry to the API Gateway templates table
    - Update the Layer 6 deployment order section
    - Remove/update the note about manually verifying `cloudwatchRoleArn` via `aws apigateway get-account`
  - [x] 5.2 Update `docs/infrastructure-metrics.md` with the new template count
  - [x] 5.3 Update `docs/observability.md` if it references the manual CloudWatch role

## Dev Notes

### Critical Architecture Context

**Current state:** The API Gateway CloudWatch IAM role exists in AWS as `arn:aws:iam::008971653395:role/cw-ho-tf-dev-apigw` — this was created by Terraform (the `cw-ho-tf-` prefix indicates it). It is NOT managed by CloudFormation. The `AWS::ApiGateway::Account` resource does not exist in any CF template.

**Why this matters:** If this Terraform role is ever deleted, API Gateway CloudWatch logging will silently fail across ALL API Gateways in the account/region, even though `api-gw-app.yaml` has `LoggingLevel: INFO` configured. Moving this to CloudFormation ensures it's tracked, versioned, and deployed alongside other infrastructure.

**`AWS::ApiGateway::Account` is a singleton resource** — only one exists per AWS account per region. CloudFormation will update the existing account settings, replacing the Terraform role ARN with the new CF-managed role ARN.

### Template Design

The template should follow existing project patterns (Gen 2+ standards from architecture.md):

```yaml
AWSTemplateFormatVersion: '2010-09-09'
Description: >
  API Gateway account-level CloudWatch IAM role.
  Enables CloudWatch logging for all API Gateways in this account/region.

Parameters:
  ProjectCode:
    Type: String
  Environment:
    Type: String

Resources:
  ApiGatewayCloudWatchRole:
    Type: 'AWS::IAM::Role'
    Properties:
      RoleName: !Sub '${ProjectCode}-${Environment}-apigw-cloudwatch-role'
      AssumeRolePolicyDocument:
        Version: '2012-10-17'
        Statement:
          - Effect: Allow
            Principal:
              Service: apigateway.amazonaws.com
            Action: 'sts:AssumeRole'
      ManagedPolicyArns:
        - 'arn:aws:iam::aws:policy/service-role/AmazonAPIGatewayPushToCloudWatchLogs'
      Tags:
        - Key: Project
          Value: !Ref ProjectCode
        - Key: Environment
          Value: !Ref Environment

  ApiGatewayAccount:
    Type: 'AWS::ApiGateway::Account'
    DependsOn: ApiGatewayCloudWatchRole
    Properties:
      CloudWatchRoleArn: !GetAtt ApiGatewayCloudWatchRole.Arn

  CloudWatchRoleArnParameter:
    Type: 'AWS::SSM::Parameter'
    Properties:
      Name: !Sub '/${ProjectCode}/${Environment}/apigw/cloudwatch-role-arn'
      Type: String
      Value: !GetAtt ApiGatewayCloudWatchRole.Arn
      Description: 'API Gateway CloudWatch IAM Role ARN'

Outputs:
  CloudWatchRoleArn:
    Description: 'API Gateway CloudWatch IAM Role ARN'
    Value: !GetAtt ApiGatewayCloudWatchRole.Arn
```

### Parameter File Design

```json
[
  { "ParameterKey": "ProjectCode", "ParameterValue": "lenie" },
  { "ParameterKey": "Environment", "ParameterValue": "dev" }
]
```

### Deployment Considerations

1. **deploy.ini placement:** The `AWS::ApiGateway::Account` resource must exist before API Gateway stages with logging are deployed. Place as first item in Layer 6, before `api-gw-infra.yaml`.

2. **Stack name:** Following convention: `lenie-dev-api-gw-account`

3. **Role replacement:** When this CF stack is deployed, the `AWS::ApiGateway::Account` resource will update the account's `cloudwatchRoleArn` from the Terraform role (`cw-ho-tf-dev-apigw`) to the new CF-managed role. This is seamless — logging continues without interruption.

4. **Terraform role cleanup:** After verifying the CF deployment works, the old Terraform role `cw-ho-tf-dev-apigw` can be manually deleted from IAM (it will no longer be referenced). This is OUT OF SCOPE for this story.

5. **CAPABILITY_NAMED_IAM:** Required for stack creation (already the default in `deploy.sh`).

### deploy.ini Change

```ini
; --- Layer 6: API ---
templates/api-gw-account.yaml     ; Account-level CloudWatch IAM role (prerequisite for API GW logging)
templates/api-gw-infra.yaml
templates/api-gw-app.yaml
templates/api-gw-custom-domain.yaml
```

### What NOT to Do

- Do NOT delete the existing Terraform role `cw-ho-tf-dev-apigw` — let it remain until manually cleaned up
- Do NOT modify `api-gw-app.yaml` or `api-gw-infra.yaml` — this story only creates the Account resource
- Do NOT add stage logging to `api-gw-infra.yaml` — that's a separate task (noted in observability.md as a gap)
- Do NOT hardcode ARNs — use `!GetAtt` and SSM parameters

### Project Structure Notes

- New template follows `api-gw-*` naming pattern matching existing API Gateway templates
- Placed in `infra/aws/cloudformation/templates/` alongside all other templates
- Parameter file in `infra/aws/cloudformation/parameters/dev/`
- SSM export follows existing pattern: `/${ProjectCode}/${Environment}/<service>/<resource>`

### References

- [Source: _bmad-output/implementation-artifacts/11-10-codify-api-gateway-stage-logging-and-tracing.md:92-98] — CloudWatch IAM role prerequisite documentation
- [Source: _bmad-output/implementation-artifacts/11-10-codify-api-gateway-stage-logging-and-tracing.md:204] — Role verified as `arn:aws:iam::008971653395:role/cw-ho-tf-dev-apigw`
- [Source: infra/aws/cloudformation/CLAUDE.md:184] — Note about verifying `cloudwatchRoleArn` manually
- [Source: docs/observability.md] — Gap: api-gw-infra stage lacks logging
- [Source: infra/aws/cloudformation/deploy.ini:45-48] — Layer 6 API section
- [Source: infra/aws/cloudformation/templates/sqs-to-rds-step-function.yaml:37-100] — Reference pattern for CloudWatch IAM role (Step Function)

### Previous Story Intelligence

**From Story 11-10 (done) — Codify API Gateway Stage Logging and Tracing:**
- Verified that `cloudwatchRoleArn` is already set to `arn:aws:iam::008971653395:role/cw-ho-tf-dev-apigw`
- B-10 was explicitly created as a backlog item from that story
- `StageDescription` with `LoggingLevel: INFO`, `MetricsEnabled: true`, `DataTraceEnabled: true`, `TracingEnabled: true` was added to `api-gw-app.yaml`
- cfn-lint validation confirmed the template is valid

**From Story B-21 (done) — Split Shared Lambda Execution Role into Per-Function Roles:**
- IAM roles should be least-privilege and per-function/service
- Tags (Project, Environment) should be on all IAM resources
- Role naming convention: `${ProjectCode}-${Environment}-<description>`

**From Story B-6 (done) — Migrate API GW App Stage to Separate Resource:**
- `api-gw-app.yaml` now has a separate `ApiStage` resource
- Stage settings (logging, tracing, metrics) are on the `ApiStage` resource
- DeletionPolicy: Retain added to ApiStage

### Git Intelligence

**Recent commit patterns:**
```
a0cf648 fix(security): migrate web_interface_target from CRA to Vite
cd77619 chore(B-6): finalize API GW stage migration
2c269f1 feat(B-8): manage ACM certificates via CloudFormation and SSM
eb34305 feat(B-9): organize S3 CloudFormation bucket
```
- Commit prefix: `feat(B-N):` for backlog item implementations
- All deliverables committed together (template + parameters + deploy.ini + docs + story file)

### Files to Create/Modify (Scope)

| Action | File |
|--------|------|
| Create | `infra/aws/cloudformation/templates/api-gw-account.yaml` |
| Create | `infra/aws/cloudformation/parameters/dev/api-gw-account.json` |
| Modify | `infra/aws/cloudformation/deploy.ini` |
| Modify | `infra/aws/cloudformation/CLAUDE.md` |
| Modify | `docs/infrastructure-metrics.md` |
| Modify | `docs/observability.md` (if references manual role) |
| Modify | `_bmad-output/implementation-artifacts/sprint-status.yaml` |

**Files NOT to touch:**
```
infra/aws/cloudformation/templates/api-gw-app.yaml        [NO CHANGE] Logging already configured
infra/aws/cloudformation/templates/api-gw-infra.yaml       [NO CHANGE] Adding logging is separate task
infra/aws/cloudformation/templates/api-gw-custom-domain.yaml [NO CHANGE]
infra/aws/cloudformation/deploy.sh                          [NO CHANGE]
```

### Library / Framework Requirements

No new libraries or dependencies. Pure CloudFormation template creation.

### Testing Requirements

**Validation (before commit):**
```bash
cfn-lint infra/aws/cloudformation/templates/api-gw-account.yaml
```

**Post-deployment verification (after AWS deploy):**
```bash
# Verify the Account resource is configured with new role
aws apigateway get-account

# Expected: cloudwatchRoleArn points to lenie-dev-apigw-cloudwatch-role (not cw-ho-tf-dev-apigw)

# Verify API Gateway app stage logging still works
aws apigateway get-stage --rest-api-id <app-api-id> --stage-name v1
```

**No unit or integration tests needed** — this is a pure infrastructure template and documentation change.

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

- cfn-lint initial run returned W3005 warning for redundant `DependsOn` (already enforced by `!GetAtt`). Removed `DependsOn: ApiGatewayCloudWatchRole` from `ApiGatewayAccount` resource. Re-run passed with zero errors/warnings.
- `docs/observability.md` checked for manual CloudWatch role references — none found, no changes needed (Task 5.3 N/A).

### Completion Notes List

- Created `api-gw-account.yaml` CloudFormation template with IAM Role (`AmazonAPIGatewayPushToCloudWatchLogs`), `AWS::ApiGateway::Account` singleton, SSM Parameter export, and Outputs section.
- Created parameter file `api-gw-account.json` for dev environment.
- Registered template in `deploy.ini` as first entry in Layer 6 (API), before `api-gw-infra.yaml`.
- cfn-lint validation passes with zero errors and zero warnings.
- Updated `infra/aws/cloudformation/CLAUDE.md`: added template to API Gateway table, updated Layer 6 deployment order, replaced manual `cloudwatchRoleArn` verification note with reference to `api-gw-account.yaml`.
- Updated `docs/infrastructure-metrics.md`: deploy.ini [dev] count 29→30, Layer 6 count 3→4, total .yaml 39→40.
- Updated `infra/aws/CLAUDE.md`: total .yaml files 38→40.
- AC7 (existing logging continues) is an operational verification — no code changes to `api-gw-app.yaml` needed; the `AWS::ApiGateway::Account` resource seamlessly replaces the Terraform role ARN.

### Change Log

- 2026-02-25: Story B-10 implemented — API Gateway CloudWatch IAM role codified in CloudFormation

### File List

- `infra/aws/cloudformation/templates/api-gw-account.yaml` (created)
- `infra/aws/cloudformation/parameters/dev/api-gw-account.json` (created)
- `infra/aws/cloudformation/deploy.ini` (modified)
- `infra/aws/cloudformation/CLAUDE.md` (modified)
- `infra/aws/CLAUDE.md` (modified)
- `docs/infrastructure-metrics.md` (modified)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (modified)
- `_bmad-output/implementation-artifacts/B-10-create-apigw-cloudwatch-iam-role-in-cloudformation.md` (modified)
