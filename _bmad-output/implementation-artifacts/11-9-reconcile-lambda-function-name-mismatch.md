# Story 11.9: Reconcile Lambda Function Name Mismatch Between Step Function and Lambda Template

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **developer**,
I want to reconcile the naming mismatch between the deployed Lambda function `lenie-sqs-to-db` and the CF template `sqs-to-rds-lambda.yaml` which defines `lenie-dev-sqs-to-rds-lambda`,
so that the deployed resource name matches the CloudFormation-defined name and follows the `${ProjectCode}-${Environment}-<description>` naming convention.

## Acceptance Criteria

1. **AC1 — Mismatch origin documented:** The developer investigates whether the deployed Lambda `lenie-sqs-to-db` was manually created or deployed via a different CF stack, and documents the finding in Dev Agent Record.

2. **AC2 — Naming decision documented:** A decision is documented: either (a) update the CF Lambda template FunctionName to match the deployed `lenie-sqs-to-db`, or (b) align the deployed Lambda and all consumers to the CF-defined name `lenie-dev-sqs-to-rds-lambda`. The chosen approach and rationale are recorded in Dev Agent Record.

3. **AC3 — Step Function parameter default updated:** The `SqsToRdsLambdaFunctionName` parameter default in `sqs-to-rds-step-function.yaml` (line 29) matches the reconciled Lambda function name.

4. **AC4 — Step Function parameter file updated:** `parameters/dev/sqs-to-rds-step-function.json` entry for `SqsToRdsLambdaFunctionName` matches the reconciled Lambda function name.

5. **AC5 — Lambda template FunctionName consistent:** `sqs-to-rds-lambda.yaml` FunctionName (line 63) produces the same name that the step function references.

6. **AC6 — Lambda update script aligned:** `infra/aws/serverless/lambdas/sqs-into-rds/lambda_update` FUNCTION_NAME matches the reconciled function name.

7. **AC7 — cfn-lint validation passes:** Both `sqs-to-rds-lambda.yaml` and `sqs-to-rds-step-function.yaml` pass cfn-lint with zero errors.

8. **AC8 — Zero stale references:** `grep -r "lenie-sqs-to-db"` across the repo returns zero matches after reconciliation (all references use the reconciled name).

## Tasks / Subtasks

- [x] **Task 1: Investigate mismatch origin** (AC: #1)
  - [x] 1.1 Check AWS for deployed Lambda functions — does `lenie-sqs-to-db` exist? Does `lenie-dev-sqs-to-rds-lambda` exist? Use `aws lambda get-function --function-name <name>` or check CF stack resources
  - [x] 1.2 Check if `sqs-to-rds-lambda.yaml` was ever deployed as a CF stack (look for stack in `deploy.ini` registration and `aws cloudformation describe-stacks`)
  - [x] 1.3 Document finding in Dev Agent Record → Debug Log

- [x] **Task 2: Make and document naming decision** (AC: #2)
  - [x] 2.1 Evaluate Option A: Change CF Lambda template FunctionName to `lenie-sqs-to-db` (breaks `${ProjectCode}-${Environment}-<description>` convention but matches deployed state)
  - [x] 2.2 Evaluate Option B: Keep CF template name `lenie-dev-sqs-to-rds-lambda` and update all consumers (follows convention but requires Lambda recreation or manual rename via deploy)
  - [x] 2.3 Choose option based on: (1) project naming convention compliance, (2) deployment risk, (3) number of references to update. Document in Dev Agent Record

- [x] **Task 3: Update Lambda template FunctionName if needed** (AC: #5)
  - [x] 3.1 ~~If Option A chosen~~ N/A — Option B chosen. **[Review fix]** S3Key updated: `sqs-to-db.zip` → `sqs-into-rds.zip` to match `function_list_cf.txt` and `lambdas/sqs-into-rds/` directory name convention
  - [x] 3.2 If Option B chosen: no change needed to Lambda template (already produces `lenie-dev-sqs-to-rds-lambda`)

- [x] **Task 4: Update Step Function template and parameter file** (AC: #3, #4)
  - [x] 4.1 Update `SqsToRdsLambdaFunctionName` default in `sqs-to-rds-step-function.yaml` to the reconciled name
  - [x] 4.2 Update `SqsToRdsLambdaFunctionName` value in `parameters/dev/sqs-to-rds-step-function.json` to the reconciled name

- [x] **Task 5: Update lambda_update script** (AC: #6)
  - [x] 5.1 Update FUNCTION_NAME in `infra/aws/serverless/lambdas/sqs-into-rds/lambda_update` to the reconciled name

- [x] **Task 6: Eliminate stale references** (AC: #8)
  - [x] 6.1 Search entire repo for old name (whichever name was replaced) using `grep -r`
  - [x] 6.2 Update any remaining references in documentation (CLAUDE.md, README.md, etc.) — no references found in CLAUDE.md, README.md, or any code/infra files. Remaining references only in _bmad-output/ historical artifacts (completed stories, epics, PRD) which are not modified.

- [x] **Task 7: Validate** (AC: #7, #8)
  - [x] 7.1 Run `cfn-lint infra/aws/cloudformation/templates/sqs-to-rds-lambda.yaml` — zero errors ✅
  - [x] 7.2 Run `cfn-lint infra/aws/cloudformation/templates/sqs-to-rds-step-function.yaml` — zero errors ✅
  - [x] 7.3 Run `grep -r "lenie-sqs-to-db"` in infra/, backend/, docs/, CLAUDE.md, README.md — zero matches ✅ (remaining references only in _bmad-output/ historical artifacts)
  - [x] 7.4 Verify Lambda template FunctionName and Step Function parameter resolve to the same string — both resolve to `lenie-dev-sqs-to-rds-lambda` ✅

## Dev Notes

### The Situation

There is a naming mismatch between the Lambda function name in two CloudFormation templates:

| Component | Function Name | File:Line |
|-----------|---------------|-----------|
| Lambda template `FunctionName` | `lenie-dev-sqs-to-rds-lambda` | `sqs-to-rds-lambda.yaml:63` |
| Step Function parameter default | `lenie-sqs-to-db` | `sqs-to-rds-step-function.yaml:29` |
| Step Function parameter file | `lenie-sqs-to-db` | `parameters/dev/sqs-to-rds-step-function.json` |
| Lambda manual update script | `lenie-sqs-to-db` | `serverless/lambdas/sqs-into-rds/lambda_update:4` |

**Root cause:** The Lambda `lenie-sqs-to-db` was originally created manually. Story 11.6 created/parameterized the CloudFormation template `sqs-to-rds-lambda.yaml` using the Gen 2+ naming convention (`${ProjectCode}-${Environment}-sqs-to-rds-lambda`), which produces `lenie-dev-sqs-to-rds-lambda`. Story 11.2 parameterized the Lambda name in the Step Function template but kept `lenie-sqs-to-db` as the default to match the still-deployed manual Lambda.

**Impact:** If the Lambda template is deployed via CloudFormation, it creates a NEW function named `lenie-dev-sqs-to-rds-lambda`, but the Step Function still invokes `lenie-sqs-to-db`. The Step Function would fail if the manual Lambda is deleted without updating the reference.

### Decision Framework

**Option A — Update CF Lambda template to match deployed name:**
- Change `FunctionName` in `sqs-to-rds-lambda.yaml` from `!Sub '${ProjectCode}-${Environment}-sqs-to-rds-lambda'` to use `lenie-sqs-to-db` (or a parameter with that default)
- Pros: No AWS changes needed, zero deployment risk, matches what's actually running
- Cons: Breaks `${ProjectCode}-${Environment}-<description>` convention, not environment-agnostic

**Option B — Align everything to CF-defined name:**
- Keep `sqs-to-rds-lambda.yaml` FunctionName as `lenie-dev-sqs-to-rds-lambda`
- Update Step Function parameter to `lenie-dev-sqs-to-rds-lambda`
- Update `lambda_update` script
- Requires either: (1) deploying Lambda template first (creates new function), then updating Step Function, then deleting old `lenie-sqs-to-db`; or (2) if Lambda template is not yet deployed as a stack, importing the existing Lambda into CF management
- Pros: Follows naming convention, environment-agnostic, consistent with all other templates
- Cons: Requires careful deployment sequencing, potential brief outage during cutover

**Recommendation:** The developer MUST investigate the current AWS state (Task 1) before deciding. If the Lambda template has NOT been deployed to AWS yet (i.e., `lenie-sqs-to-db` is the only deployed function), Option A is simpler and safer for THIS story — the template FunctionName should match the deployed reality. Convention compliance can be addressed in a future story (B-3 or similar) when actually recreating the Lambda. If the Lambda template HAS been deployed (both functions exist in AWS), Option B is better — update consumers to point to the CF-managed one.

### Architecture Compliance

**Gen 2+ canonical template pattern requirements:**
- `FunctionName` should use `!Sub '${ProjectCode}-${Environment}-<description>'` pattern
- SSM path convention: `/${ProjectCode}/${Environment}/<service>/<resource-path>`
- Template section ordering: Parameters → Conditions → Resources → (SSM Parameters last)
- cfn-lint validation before commit
- All descriptions and comments in English

**Anti-patterns to avoid:**
- Do NOT hardcode AWS account IDs or ARNs
- Do NOT create inconsistency between template-defined name and what consumers reference
- Do NOT update one template without updating all consumers
- Do NOT skip `lambda_update` script — it's used for manual Lambda code deployments

### Files to Modify (Scope)

| File | Change |
|------|--------|
| `infra/aws/cloudformation/templates/sqs-to-rds-lambda.yaml` | Possibly update FunctionName (depends on decision) |
| `infra/aws/cloudformation/templates/sqs-to-rds-step-function.yaml` | Update `SqsToRdsLambdaFunctionName` default |
| `infra/aws/cloudformation/parameters/dev/sqs-to-rds-step-function.json` | Update `SqsToRdsLambdaFunctionName` value |
| `infra/aws/serverless/lambdas/sqs-into-rds/lambda_update` | Update `FUNCTION_NAME` |

**Files NOT to touch:**
```
infra/aws/cloudformation/deploy.ini                       [NO CHANGE] Both templates already registered
infra/aws/cloudformation/deploy.sh                        [NO CHANGE] Deployment script
infra/aws/cloudformation/parameters/dev/sqs-to-rds-lambda.json [NO CHANGE unless Option A adds new parameter]
infra/aws/cloudformation/templates/sqs-application-errors.yaml [NO CHANGE]
infra/aws/cloudformation/templates/sqs-documents.yaml     [NO CHANGE]
```

### Project Structure Notes

- `sqs-to-rds-lambda.yaml` is Layer 5 (Compute) in `deploy.ini`
- `sqs-to-rds-step-function.yaml` is Layer 7 (Orchestration) in `deploy.ini`
- Deployment order: Lambda template deploys before Step Function — so if Lambda name changes, Step Function will pick up the new name in the same deploy run
- `lambda_update` script in `serverless/lambdas/sqs-into-rds/` is used for manual code pushes (not CloudFormation managed)

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 11.9] — Story definition with acceptance criteria
- [Source: infra/aws/cloudformation/templates/sqs-to-rds-lambda.yaml:63] — Lambda FunctionName definition
- [Source: infra/aws/cloudformation/templates/sqs-to-rds-step-function.yaml:27-30] — SqsToRdsLambdaFunctionName parameter
- [Source: infra/aws/cloudformation/parameters/dev/sqs-to-rds-step-function.json] — Parameter file with `lenie-sqs-to-db`
- [Source: infra/aws/serverless/lambdas/sqs-into-rds/lambda_update:4] — FUNCTION_NAME="lenie-sqs-to-db"
- [Source: _bmad-output/planning-artifacts/architecture.md#Implementation Patterns] — Gen 2+ naming convention
- [Source: _bmad-output/planning-artifacts/architecture.md#Naming Patterns] — `${ProjectCode}-${Environment}-<description>` pattern
- [Source: _bmad-output/implementation-artifacts/11-8-replace-fn-importvalue-with-ssm-parameter-for-dlq-arn.md] — Previous story patterns

### Previous Story Intelligence

**From Story 11.8 (done) — Replace Fn::ImportValue with SSM Parameter for DLQ ARN:**
- Two-stack changes require deployment sequencing (producer first, then consumer)
- CF Export preserved during transition for safety
- Commit prefix: `chore:` for infrastructure template changes
- Debug Log: Documented split-commit issue — all story deliverables should be committed together

**From Story 11.6 (done) — Parameterize sqs-to-rds-lambda Infrastructure Values:**
- Parameterized the Lambda template using `!Sub '${ProjectCode}-${Environment}-sqs-to-rds-lambda'` for FunctionName
- This is where the naming convention was applied to this Lambda template
- Commit: `cda9fd9 chore: parameterize hardcoded values in sqs-to-rds-lambda template`

**From Story 11.2 (done) — Improve Step Function Template:**
- Added `SqsToRdsLambdaFunctionName` parameter with default `lenie-sqs-to-db`
- Code review flagged the mismatch as → Story 11.9
- Commit: `4a11307 chore: replace resolve:ssm with SSM Parameter types and parameterize Lambda name in step function`

### Git Intelligence

**Recent commits:**
```
d587b98 chore: add SSM Parameter for DLQ ARN and commit Story 11-8 deliverables
5a69cbe chore: parameterize legacy lenie_websites SQS queue references
cda9fd9 chore: parameterize hardcoded values in sqs-to-rds-lambda template
4a11307 chore: replace resolve:ssm with SSM Parameter types and parameterize Lambda name in step function
```

**Patterns to follow:**
- Commit prefix: `chore:` for infrastructure template changes
- cfn-lint validation before commit
- Parameter files updated alongside templates
- Commit all story deliverables together (lesson from Story 11.8 code review)

### Library / Framework Requirements

No new libraries or dependencies. Pure CloudFormation template and script modifications.

### Testing Requirements

**Validation (before commit):**
```bash
cfn-lint infra/aws/cloudformation/templates/sqs-to-rds-lambda.yaml
cfn-lint infra/aws/cloudformation/templates/sqs-to-rds-step-function.yaml
```

**Verification (grep checks):**
```bash
# Verify old name is fully eliminated (adjust based on decision)
grep -rn "lenie-sqs-to-db" infra/ backend/ web_interface_react/ web_add_url_react/ docs/ CLAUDE.md README.md
# Expected: zero matches

# Verify consistent Lambda name across templates
grep -n "FunctionName" infra/aws/cloudformation/templates/sqs-to-rds-lambda.yaml
grep -n "SqsToRdsLambdaFunctionName" infra/aws/cloudformation/templates/sqs-to-rds-step-function.yaml
grep -n "SqsToRdsLambdaFunctionName" infra/aws/cloudformation/parameters/dev/sqs-to-rds-step-function.json
grep -n "FUNCTION_NAME" infra/aws/serverless/lambdas/sqs-into-rds/lambda_update
```

**No unit or integration tests needed** — this is a pure infrastructure template and script change.

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

#### Task 1 — Mismatch Origin Investigation (2026-02-17)

**AWS Investigation Results:**
- `aws lambda get-function --function-name lenie-sqs-to-db` → ResourceNotFoundException (function does NOT exist)
- `aws lambda get-function --function-name lenie-dev-sqs-to-rds-lambda` → ResourceNotFoundException (function does NOT exist)
- `aws cloudformation list-stacks` filtered for "sqs-to-rds" → empty (no CF stacks deployed)
- `aws lambda list-functions` filtered for "sqs" or "rds" → empty (no related Lambda functions at all)
- `deploy.ini` line 38: `sqs-to-rds-lambda.yaml` IS registered (not commented out) but was never deployed

**Root Cause Analysis:**
The original Lambda `lenie-sqs-to-db` was manually created in an earlier phase but has since been deleted (or existed in the old AWS account `008971653395`). The CF template `sqs-to-rds-lambda.yaml` was created by Story 11.6 using the Gen 2+ naming convention but was never deployed to AWS. Neither Lambda exists — this is a clean-slate scenario.

#### Task 2 — Naming Decision (2026-02-17)

**Decision: Option B — Align everything to CF-defined name `lenie-dev-sqs-to-rds-lambda`**

**Rationale:**
1. Neither Lambda exists in AWS → zero deployment risk, no migration needed
2. CF template already uses correct `${ProjectCode}-${Environment}-sqs-to-rds-lambda` convention
3. Follows Gen 2+ naming pattern consistent with all other templates
4. Environment-agnostic — works for future `prod`/`qa` environments
5. Only 3 consumer files need updating (Step Function template, parameter file, lambda_update script)

**Files to update:**
- `sqs-to-rds-step-function.yaml` line 29: default `lenie-sqs-to-db` → `lenie-dev-sqs-to-rds-lambda`
- `parameters/dev/sqs-to-rds-step-function.json`: value `lenie-sqs-to-db` → `lenie-dev-sqs-to-rds-lambda`
- `serverless/lambdas/sqs-into-rds/lambda_update` line 5: `lenie-sqs-to-db` → `lenie-dev-sqs-to-rds-lambda`

### Completion Notes List

1. **Investigation (AC1):** Neither `lenie-sqs-to-db` nor `lenie-dev-sqs-to-rds-lambda` exist in AWS. No CF stacks deployed for sqs-to-rds. Template registered in deploy.ini but never deployed. Clean-slate scenario.
2. **Naming Decision (AC2):** Option B chosen — align all consumers to CF-defined name `lenie-dev-sqs-to-rds-lambda`. Zero deployment risk, follows Gen 2+ `${ProjectCode}-${Environment}-<description>` convention.
3. **Lambda Template (AC5):** No changes needed — already uses `!Sub '${ProjectCode}-${Environment}-sqs-to-rds-lambda'` which produces `lenie-dev-sqs-to-rds-lambda`.
4. **Step Function Template (AC3):** Updated `SqsToRdsLambdaFunctionName` default from `lenie-sqs-to-db` to `lenie-dev-sqs-to-rds-lambda`.
5. **Parameter File (AC4):** Updated `SqsToRdsLambdaFunctionName` value from `lenie-sqs-to-db` to `lenie-dev-sqs-to-rds-lambda`.
6. **Lambda Update Script (AC6):** Updated `FUNCTION_NAME` from `lenie-sqs-to-db` to `lenie-dev-sqs-to-rds-lambda`.
7. **cfn-lint (AC7):** Both templates pass with zero errors.
8. **Stale References (AC8):** Zero matches for `lenie-sqs-to-db` in infra/, backend/, docs/, CLAUDE.md, README.md. Only historical BMAD artifacts retain the old name (completed story files, PRD, epics). **[Review fix]** S3Key `sqs-to-db.zip` in `sqs-to-rds-lambda.yaml:70` and `sqs-to-db` in `function_list.txt:7` were missed — updated to `sqs-into-rds` to match directory naming convention.

### File List

- `infra/aws/cloudformation/templates/sqs-to-rds-step-function.yaml` — Updated SqsToRdsLambdaFunctionName default to `lenie-dev-sqs-to-rds-lambda`
- `infra/aws/cloudformation/parameters/dev/sqs-to-rds-step-function.json` — Updated SqsToRdsLambdaFunctionName value to `lenie-dev-sqs-to-rds-lambda`
- `infra/aws/serverless/lambdas/sqs-into-rds/lambda_update` — Updated FUNCTION_NAME to `lenie-dev-sqs-to-rds-lambda`
- `_bmad-output/implementation-artifacts/11-9-reconcile-lambda-function-name-mismatch.md` — Story file with Dev Agent Record
- `infra/aws/cloudformation/templates/sqs-to-rds-lambda.yaml` — [Review fix] Updated S3Key from `sqs-to-db.zip` to `sqs-into-rds.zip`
- `infra/aws/serverless/function_list.txt` — [Review fix] Updated legacy entry from `sqs-to-db` to `sqs-into-rds`
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — Status updated to review → done

### Change Log

- 2026-02-17: Reconciled Lambda function name mismatch — aligned Step Function template, parameter file, and lambda_update script to CF-defined name `lenie-dev-sqs-to-rds-lambda` (Option B). No AWS deployment changes needed; neither Lambda existed in AWS.
- 2026-02-18: Code review fixes — updated S3Key in sqs-to-rds-lambda.yaml from `sqs-to-db.zip` to `sqs-into-rds.zip` (matches function_list_cf.txt and lambdas/ directory convention), updated legacy function_list.txt entry
