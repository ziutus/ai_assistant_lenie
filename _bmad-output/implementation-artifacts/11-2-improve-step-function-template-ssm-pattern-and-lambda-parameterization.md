# Story 11.2: Improve Step Function Template — SSM Pattern and Lambda Parameterization

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **developer**,
I want to replace `{{resolve:ssm:...}}` with `AWS::SSM::Parameter::Value<String>` and parameterize the hardcoded Lambda name in `sqs-to-rds-step-function.yaml`,
So that the template follows consistent SSM and parameterization patterns established in Sprint 1.

## Acceptance Criteria

1. **AC1 — SSM pattern standardized:** All `{{resolve:ssm:...}}` dynamic references in `sqs-to-rds-step-function.yaml` are replaced with `AWS::SSM::Parameter::Value<String>` parameter types. SSM values are resolved at deploy time via CloudFormation parameters, and the template follows the project-standard SSM consumption pattern established in the architecture document.

2. **AC2 — Lambda function name parameterized:** The hardcoded Lambda function name `lenie-sqs-to-db` in `DefinitionSubstitutions` (Step Function definition) and IAM policy is replaced with a configurable parameter. The Step Function definition resolves the parameterized name correctly at deploy time.

3. **AC3 — cfn-lint validation passes:** The modified template passes cfn-lint validation with zero errors.

## Tasks / Subtasks

- [x] **Task 1: Replace `{{resolve:ssm:...}}` with `AWS::SSM::Parameter::Value<String>` parameters** (AC: #1)
  - [x] 1.1 Add `SqsDocumentsQueueUrl` parameter (Type: `AWS::SSM::Parameter::Value<String>`, Default: `/lenie/dev/sqs/documents/url`)
  - [x] 1.2 Add `DatabaseInstanceName` parameter (Type: `AWS::SSM::Parameter::Value<String>`, Default: `/lenie/dev/database/name`)
  - [x] 1.3 Update EventBridge Scheduler `Input` to use `!Sub` with `${SqsDocumentsQueueUrl}` and `${DatabaseInstanceName}` instead of `{{resolve:ssm:...}}`
  - [x] 1.4 Update parameter file `parameters/dev/sqs-to-rds-step-function.json` with new SSM path parameter values

- [x] **Task 2: Parameterize hardcoded Lambda function name** (AC: #2)
  - [x] 2.1 Verify actual Lambda function name deployed in AWS (see Dev Notes — Name Mismatch Investigation)
  - [x] 2.2 Add `SqsToRdsLambdaFunctionName` parameter (Type: `String`, Default: verified function name)
  - [x] 2.3 Add `DefinitionSubstitutions` property to `MyStateMachine` resource, mapping `SqsToRdsLambdaFunctionName` to `!Ref SqsToRdsLambdaFunctionName`
  - [x] 2.4 Replace hardcoded `"FunctionName": "lenie-sqs-to-db"` in DefinitionString with `"FunctionName": "${SqsToRdsLambdaFunctionName}"`
  - [x] 2.5 Update IAM policy `StateMachinePolicy` Lambda invoke Resource from `function:lenie-sqs-to-db` to `!Sub` with `${SqsToRdsLambdaFunctionName}`
  - [x] 2.6 Update parameter file with `SqsToRdsLambdaFunctionName` value

- [x] **Task 3: Validate template** (AC: #3)
  - [x] 3.1 Run cfn-lint on modified `sqs-to-rds-step-function.yaml` — zero errors required
  - [x] 3.2 Verify template structure follows canonical pattern (Parameters → Resources, SSM params first in Parameters)

## Dev Notes

### Technical Requirements

**Scope: Single template file with two focused changes.**

This story modifies `infra/aws/cloudformation/templates/sqs-to-rds-step-function.yaml` to:
1. Replace `{{resolve:ssm:...}}` dynamic references with `AWS::SSM::Parameter::Value<String>` parameter type (project standard from architecture.md)
2. Parameterize hardcoded Lambda function name `lenie-sqs-to-db` using `DefinitionSubstitutions`

**Current SSM pattern (lines 405-410):**
```yaml
Input: !Sub |
  {
    "QueueUrl": "{{resolve:ssm:/${ProjectCode}/${Environment}/sqs/documents/url}}",
    "DbInstanceIdentifier": "{{resolve:ssm:/${ProjectCode}/${Environment}/database/name}}",
    "StopDatabase": "yes"
  }
```

**Target SSM pattern:**
```yaml
Parameters:
  SqsDocumentsQueueUrl:
    Type: AWS::SSM::Parameter::Value<String>
    Default: '/lenie/dev/sqs/documents/url'
    Description: SQS documents queue URL (resolved from SSM)
  DatabaseInstanceName:
    Type: AWS::SSM::Parameter::Value<String>
    Default: '/lenie/dev/database/name'
    Description: RDS database instance identifier (resolved from SSM)
```
Then in EventBridge Input:
```yaml
Input: !Sub |
  {
    "QueueUrl": "${SqsDocumentsQueueUrl}",
    "DbInstanceIdentifier": "${DatabaseInstanceName}",
    "StopDatabase": "yes"
  }
```

**Current Lambda name (hardcoded in 2 places):**
- Line 58 (IAM policy): `Resource: !Sub "arn:aws:lambda:${AWS::Region}:${AWS::AccountId}:function:lenie-sqs-to-db"`
- Line 262 (DefinitionString): `"FunctionName": "lenie-sqs-to-db"`

**Target Lambda parameterization:**
```yaml
Parameters:
  SqsToRdsLambdaFunctionName:
    Type: String
    Default: <verified-actual-function-name>
    Description: Name of the Lambda function that processes SQS messages into RDS
```
In the StateMachine resource, add:
```yaml
DefinitionSubstitutions:
  SqsToRdsLambdaFunctionName: !Ref SqsToRdsLambdaFunctionName
```
In DefinitionString, replace:
```json
"FunctionName": "${SqsToRdsLambdaFunctionName}"
```
In IAM policy, replace:
```yaml
Resource: !Sub "arn:aws:lambda:${AWS::Region}:${AWS::AccountId}:function:${SqsToRdsLambdaFunctionName}"
```

### Lambda Function Name Mismatch Investigation

**CRITICAL: The developer MUST verify the actual Lambda function name before parameterizing.**

There is a known mismatch between the step function reference and the Lambda CF template:
- Step function references: `lenie-sqs-to-db`
- `sqs-to-rds-lambda.yaml` defines FunctionName: `!Sub '${ProjectCode}-${Environment}-sqs-to-rds-lambda'` → `lenie-dev-sqs-to-rds-lambda`
- `sqs-to-rds-lambda.yaml` S3Key: `!Sub '${ProjectCode}-${Environment}-sqs-to-db.zip'` → `lenie-dev-sqs-to-db.zip`

The deployed Lambda may have EITHER name depending on how it was created (manual vs CF). The parameter default MUST match the actual deployed function name.

**How to verify:** Run `aws lambda get-function --function-name lenie-sqs-to-db` and `aws lambda get-function --function-name lenie-dev-sqs-to-rds-lambda` — one should succeed, the other should return ResourceNotFoundException.

**Note:** If the actual name differs from the CF template `sqs-to-rds-lambda.yaml` FunctionName, that's a separate issue to track (not in this story's scope). This story only parameterizes the reference in the step function template.

### Architecture Compliance

**Gen 2+ canonical pattern requirements:**
- Parameters section order: `ProjectCode`, `Environment` first, then resource-specific params
- SSM consumption: Use `AWS::SSM::Parameter::Value<String>` parameter type, NOT `{{resolve:ssm:...}}`
- Tags: Already present on all taggable resources (done in Story 11.1)
- Template structure: Parameters → Resources (no Outputs section — use SSM Parameters)

**`DefinitionSubstitutions` safety:**
- `DefinitionSubstitutions` resolves ONLY `${key_name}` patterns (with curly braces)
- Step Functions JSONPath expressions use bare `$` without curly braces: `$QueueUrl`, `$.Messages`, `$StopDatabase`, `$waitSeconds`, `$.Attributes...`, `$.DbInstances...`, `$.Payload.body`
- NO conflict between `DefinitionSubstitutions` and Step Functions JSONPath expressions
- The existing `>` YAML folded block scalar for DefinitionString is compatible with `DefinitionSubstitutions`

### Library / Framework Requirements

- **cfn-lint**: Use for template validation. Run: `uvx cfn-lint infra/aws/cloudformation/templates/sqs-to-rds-step-function.yaml`
- No new libraries or dependencies needed — purely CloudFormation template editing

### File Structure Notes

**Files to modify:**
- `infra/aws/cloudformation/templates/sqs-to-rds-step-function.yaml` — main template changes
- `infra/aws/cloudformation/parameters/dev/sqs-to-rds-step-function.json` — add new parameter values

**No other files changed.** This story does NOT modify `sqs-to-rds-lambda.yaml` or any other template.

### Testing Requirements

- **cfn-lint validation** on modified template — zero errors required
- **No unit tests** — this story is CloudFormation-only, no backend/frontend code changes
- **No integration tests** — template deployment is verified via cfn-lint; actual deployment is a separate step
- **Regression check:** Verify that existing parameters (`ProjectCode`, `Environment`, `ScheduleExpression`) still work correctly after adding new parameters

### Out of Scope

The following issues exist in this template but are NOT addressed by this story:
- **SQS queue `lenie_websites` hardcoded** (line 48 in IAM policy) — covered by Story 11.7
- **`Fn::ImportValue` for DLQ ARN** (line 404) — kept as-is; the ImportValue was already parameterized in Story 11.1
- **SSM Parameter exports** — this template does not export any values via SSM (no changes needed)
- **Lambda name mismatch** between step function and `sqs-to-rds-lambda.yaml` FunctionName — this story parameterizes the reference, but does not reconcile the naming discrepancy

### Previous Story Intelligence

**From Story 11.1 (done):**
- All tags and parameter standardization completed successfully
- `sqs-to-rds-step-function.yaml` was modified: renamed `ProjectName` → `ProjectCode`, added AllowedValues to Environment
- Code review identified pre-existing debt in this template (items 8.f-g in Completion Notes):
  - `sqs-to-rds-step-function.yaml:51` — SQS ARN with hardcoded `lenie_websites` queue name (→ Story 11.7)
  - `sqs-to-rds-step-function.yaml:61` — Lambda function ARN `lenie-sqs-to-db` (name mismatch with actual FunctionName) (→ THIS story)
- Code review also parameterized EventBridge Scheduler Input from hardcoded values to `{{resolve:ssm:...}}` (the pattern this story now replaces)
- SSM paths were parameterized: `/lenie/` → `/${ProjectCode}/` in the EventBridge Input
- ImportValue was parameterized: `!ImportValue lenie-problems-dlq-arn` → `Fn::ImportValue: !Sub '${ProjectCode}-${Environment}-problems-dlq-arn'`
- cfn-lint version used: v1.44.0

**Commit message convention:** `chore:` prefix for cleanup/maintenance work.

### Git Intelligence

**Recent relevant commits:**
```
21391f3 docs: update story 11.1 with code review round 2 results and cfn-lint verification
2005495 chore: parameterize hardcoded values in sqs-application-errors, budget, and secrets templates
f2fc017 chore: add parameter files and fix hardcoded S3 reference in lambda-weblink-put-into-sqs
d2b3992 chore: unify environment definitions — keep only dev, remove unused environments
```

These commits show the parameterization pattern used in Sprint 3. This story follows the same approach.

### Project Structure Notes

- All changes are within `infra/aws/cloudformation/` directory
- No backend, frontend, or Lambda code changes
- No documentation updates needed
- `deploy.ini` does NOT need changes (template already registered)

### References

- [Source: _bmad-output/planning-artifacts/architecture.md#SSM Parameter Consumption] — `AWS::SSM::Parameter::Value<String>` pattern specification
- [Source: _bmad-output/planning-artifacts/architecture.md#Implementation Patterns & Consistency Rules] — Enforcement guidelines, anti-patterns for `{{resolve:ssm:...}}`
- [Source: _bmad-output/planning-artifacts/epics.md#Story 11.2] — Original story definition with ACs and FRs (FR18-FR21)
- [Source: _bmad-output/implementation-artifacts/11-1-*.md#Completion Notes] — Pre-existing debt items identified during code review
- [Source: infra/aws/cloudformation/CLAUDE.md] — Template overview, deployment documentation, deploy.sh usage
- [Source: infra/aws/cloudformation/templates/sqs-to-rds-lambda.yaml:20] — Lambda FunctionName: `${ProjectCode}-${Environment}-sqs-to-rds-lambda`

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6 (claude-opus-4-6)

### Debug Log References

- Lambda name verification: `aws lambda get-function --function-name lenie-sqs-to-db` → exists; `aws lambda get-function --function-name lenie-dev-sqs-to-rds-lambda` → ResourceNotFoundException. Confirmed actual deployed name is `lenie-sqs-to-db`.
- cfn-lint validation: zero errors on modified template

### Completion Notes List

1. **SSM pattern migration (AC1):** Replaced two `{{resolve:ssm:...}}` dynamic references in EventBridge Scheduler Input with `AWS::SSM::Parameter::Value<String>` parameter types (`SqsDocumentsQueueUrl`, `DatabaseInstanceName`). SSM values are now resolved at deploy time via CloudFormation parameters, following the project-standard pattern from architecture.md.
2. **Lambda name parameterization (AC2):** Verified actual deployed Lambda name is `lenie-sqs-to-db` (not `lenie-dev-sqs-to-rds-lambda` as the CF template `sqs-to-rds-lambda.yaml` would produce). Added `SqsToRdsLambdaFunctionName` parameter with default `lenie-sqs-to-db`. Used `DefinitionSubstitutions` to inject the value into the Step Function DefinitionString. Updated IAM policy to use the parameter. No conflict with JSONPath expressions (bare `$` vs `${...}` with braces).
3. **Lambda name mismatch note:** The deployed function `lenie-sqs-to-db` does not match the CF template `sqs-to-rds-lambda.yaml` which defines `lenie-dev-sqs-to-rds-lambda`. This is a pre-existing issue outside this story's scope — the step function now correctly references the actual deployed name via a configurable parameter.
4. **cfn-lint validation (AC3):** Template passes cfn-lint with zero errors.
5. **Parameter file updated:** Added `SqsDocumentsQueueUrl`, `DatabaseInstanceName`, and `SqsToRdsLambdaFunctionName` entries to `parameters/dev/sqs-to-rds-step-function.json`.
6. **Existing parameters preserved:** `ProjectCode`, `Environment`, `ScheduleExpression` remain unchanged and functional.

### File List

- `infra/aws/cloudformation/templates/sqs-to-rds-step-function.yaml` — modified (SSM params, Lambda parameterization, DefinitionSubstitutions)
- `infra/aws/cloudformation/parameters/dev/sqs-to-rds-step-function.json` — modified (added 3 new parameter entries)

## Senior Developer Review (AI)

**Reviewer:** Claude Opus 4.6 (code-review workflow)
**Date:** 2026-02-17

### AC Validation

| AC | Status | Evidence |
|----|--------|----------|
| AC1 — SSM pattern | IMPLEMENTED | Zero `{{resolve:ssm:` remaining. Two `AWS::SSM::Parameter::Value<String>` params added. |
| AC2 — Lambda parameterized | IMPLEMENTED | `SqsToRdsLambdaFunctionName` param + `DefinitionSubstitutions` + IAM policy updated. Deployed name verified via AWS CLI. |
| AC3 — cfn-lint | IMPLEMENTED | cfn-lint ran with zero errors/warnings (verified independently by reviewer). |

### Task Audit

All 12 subtasks (1.1–1.4, 2.1–2.6, 3.1–3.2) verified as genuinely completed. Zero false `[x]` claims.

### Findings (0 High, 1 Medium, 5 Low)

**MEDIUM:**
1. **IAM SQS policy may not match SSM-resolved queue (pre-existing, risk elevated)** — `sqs-to-rds-step-function.yaml:60` grants SQS access to hardcoded `lenie_websites` queue, but `SqsDocumentsQueueUrl` SSM may resolve to a different queue. Out of scope (Story 11.7) but runtime risk is real.

**LOW:**
2. SSM parameter defaults hardcode `/lenie/dev/...` paths — acceptable for single-env, needs parameter file override for multi-env.
3. Parameter ordering: `ScheduleExpression` before SSM params — **FIXED by reviewer** (reordered SSM params before String params).
4. `Fn::ImportValue` for DLQ ARN (line 418) — architecture anti-pattern, out of scope.
5. Unrelated `lenie-split-export.json` change in git working directory from story 10-3 — exclude from commit.
6. Lambda naming mismatch (`lenie-sqs-to-db` vs CF-defined `lenie-dev-sqs-to-rds-lambda`) perpetuated in default — pre-existing, correctly uses actual deployed name.

### Fixes Applied

1. Reordered Parameters section: SSM-type params (`SqsDocumentsQueueUrl`, `DatabaseInstanceName`) moved before String-type params (`ScheduleExpression`, `SqsToRdsLambdaFunctionName`), after foundation params (`ProjectCode`, `Environment`). Parameter file reordered to match.
2. cfn-lint re-verified after fix: zero errors.

### Outcome

**APPROVED** — All ACs implemented correctly. One cosmetic fix applied. Pre-existing issues documented for future stories (11.7).

## Change Log

- 2026-02-17: Replaced `{{resolve:ssm:...}}` with `AWS::SSM::Parameter::Value<String>` parameters and parameterized hardcoded Lambda function name `lenie-sqs-to-db` via `DefinitionSubstitutions` in `sqs-to-rds-step-function.yaml`
- 2026-02-17: Code review — approved with 1 fix (parameter ordering). Status → done.
