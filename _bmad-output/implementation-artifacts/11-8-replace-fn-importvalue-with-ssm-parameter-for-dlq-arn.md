# Story 11.8: Replace Fn::ImportValue with SSM Parameter for DLQ ARN in Step Function Template

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **developer**,
I want to replace `Fn::ImportValue` for the DLQ ARN in `sqs-to-rds-step-function.yaml` with an SSM Parameter reference,
so that the template follows the project-standard SSM-only cross-stack communication pattern and eliminates the CloudFormation Exports anti-pattern.

## Acceptance Criteria

1. **AC1 — SSM Parameter published for DLQ ARN:** `sqs-application-errors.yaml` contains a new `AWS::SSM::Parameter` resource that publishes the DLQ ARN to SSM at path `/${ProjectCode}/${Environment}/sqs/problems-dlq/arn`.

2. **AC2 — Step Function template consumes DLQ ARN via SSM:** `sqs-to-rds-step-function.yaml` replaces `Fn::ImportValue: !Sub '${ProjectCode}-${Environment}-problems-dlq-arn'` (line 418) with an `AWS::SSM::Parameter::Value<String>` parameter that resolves the DLQ ARN from SSM.

3. **AC3 — EventBridge DeadLetterConfig uses SSM parameter:** The `EventBridgeScheduler` resource's `Target.DeadLetterConfig.Arn` references the new SSM-backed parameter instead of `Fn::ImportValue`.

4. **AC4 — Parameter file updated:** `parameters/dev/sqs-to-rds-step-function.json` includes the new SSM parameter path for the DLQ ARN.

5. **AC5 — cfn-lint validation passes:** Both `sqs-application-errors.yaml` and `sqs-to-rds-step-function.yaml` pass cfn-lint with zero errors.

6. **AC6 — Zero Fn::ImportValue for DLQ ARN:** After changes, `grep "problems-dlq-arn" infra/aws/cloudformation/templates/sqs-to-rds-step-function.yaml` shows only the SSM parameter reference, not `Fn::ImportValue`.

7. **AC7 — CF Export preserved for safe deployment:** The existing `Export` in `sqs-application-errors.yaml` Outputs section is preserved (NOT removed) to avoid deployment failures during the transition. Removal is deferred to a separate cleanup after both stacks are deployed.

## Tasks / Subtasks

- [x] **Task 1: Add SSM Parameter resource to sqs-application-errors.yaml** (AC: #1)
  - [x] 1.1 Add `AWS::SSM::Parameter` resource named `ProblemsDlqArnParameter` after the existing resources
  - [x] 1.2 Set SSM path to `!Sub '/${ProjectCode}/${Environment}/sqs/problems-dlq/arn'`
  - [x] 1.3 Set Value to `!GetAtt LenieDevProblemsDLQ.Arn`
  - [x] 1.4 Add Description: `'ARN of the problems dead letter queue for cross-stack reference'`
  - [x] 1.5 Keep existing `Outputs` section and CF Export intact (safe transition)

- [x] **Task 2: Add SSM-backed parameter to sqs-to-rds-step-function.yaml** (AC: #2, #3)
  - [x] 2.1 Add new parameter `ProblemsDlqArn` with `Type: AWS::SSM::Parameter::Value<String>` and `Default: '/lenie/dev/sqs/problems-dlq/arn'`
  - [x] 2.2 Add Description: `'DLQ ARN for EventBridge schedule failures (resolved from SSM)'`
  - [x] 2.3 Replace lines 416-418 (`DeadLetterConfig` block) — change `Fn::ImportValue: !Sub '${ProjectCode}-${Environment}-problems-dlq-arn'` to `!Ref ProblemsDlqArn`

- [x] **Task 3: Update parameter file** (AC: #4)
  - [x] 3.1 Add `ProblemsDlqArn` entry to `parameters/dev/sqs-to-rds-step-function.json` with value `/lenie/dev/sqs/problems-dlq/arn`

- [x] **Task 4: Validate and verify** (AC: #5, #6, #7)
  - [x] 4.1 Run `cfn-lint infra/aws/cloudformation/templates/sqs-application-errors.yaml` — zero errors
  - [x] 4.2 Run `cfn-lint infra/aws/cloudformation/templates/sqs-to-rds-step-function.yaml` — zero errors
  - [x] 4.3 Verify `Fn::ImportValue` for DLQ ARN is removed from `sqs-to-rds-step-function.yaml`
  - [x] 4.4 Verify CF Export is still present in `sqs-application-errors.yaml` (safe transition)

## Dev Notes

### The Situation

The `sqs-to-rds-step-function.yaml` template uses `Fn::ImportValue` to consume the DLQ ARN from `sqs-application-errors.yaml`. This is an anti-pattern per the project's Gen 2+ canonical template standard, which mandates SSM Parameter Store for all cross-stack communication.

**Current state (line 416-418 of `sqs-to-rds-step-function.yaml`):**
```yaml
DeadLetterConfig:
  Arn:
    Fn::ImportValue: !Sub '${ProjectCode}-${Environment}-problems-dlq-arn'
```

**Exporting stack (`sqs-application-errors.yaml`, line 50-58):**
```yaml
Outputs:
  SqsApplicationErrorsQueueARN:
    Description: 'ARN queue for default DLQ application'
    Value: !GetAtt LenieDevProblemsDLQ.Arn
    Export:
      Name: !Sub ${ProjectCode}-${Environment}-problems-dlq-arn
```

The exporting stack currently does NOT publish the DLQ ARN to SSM — only via CloudFormation Export. This story adds the SSM Parameter and migrates the consumer.

### Two-Stack Change: Deployment Sequencing

**Critical:** Both stacks must be deployed in a specific order:

1. **First deploy `sqs-application-errors.yaml`** (Layer 4) — adds SSM Parameter, keeps CF Export
2. **Then deploy `sqs-to-rds-step-function.yaml`** (Layer 7) — switches from ImportValue to SSM

This matches the existing `deploy.ini` ordering. A single run of `./deploy.sh -p lenie -s dev` will deploy them in the correct order.

**CF Export removal:** The `Export` in `sqs-application-errors.yaml` must be preserved during this story. CloudFormation prevents removing an Export while it's still imported by another stack. After both stacks are deployed (ImportValue removed), the Export becomes orphaned and can be safely removed in a future cleanup. Attempting to remove the Export in the same deploy run risks failure because `deploy.sh` processes `sqs-application-errors.yaml` before `sqs-to-rds-step-function.yaml`.

### Other Fn::ImportValue Usages (Out of Scope)

The following templates also use `Fn::ImportValue` — NOT addressed in this story:
- `url-add.yaml:130` — `Fn::ImportValue: !Sub "${ProjectCode}-${Environment}-dynamodb-documents-TableArn"` (DynamoDB)
- `ec2-lenie.yaml:34` — `Fn::ImportValue: !Sub '${ProjectCode}-${Environment}-publicSubnet1'` (VPC)
- `ec2-lenie.yaml:49` — `Fn::ImportValue: !Sub '${ProjectCode}-${Environment}-vpcId'` (VPC)

These should be migrated to SSM in future stories to fully eliminate the `Fn::ImportValue` anti-pattern.

### Architecture Compliance

**Gen 2+ canonical template pattern requirements:**
- `AWS::SSM::Parameter::Value<String>` for consuming cross-stack values (NOT `Fn::ImportValue`)
- SSM path convention: `/${ProjectCode}/${Environment}/<service>/<resource-path>`
- For DLQ ARN: `/${ProjectCode}/${Environment}/sqs/problems-dlq/arn`
- SSM Parameter resources placed last in the Resources section
- All taggable resources have `Project` and `Environment` tags (already present in both templates)
- cfn-lint validation before commit

**Anti-patterns to avoid:**
- Do NOT use `Fn::ImportValue` (project standard is SSM Parameters)
- Do NOT use `{{resolve:ssm:...}}` for parameters that can use `AWS::SSM::Parameter::Value<String>` type
- Do NOT remove CF Export from `sqs-application-errors.yaml` in this story (deployment ordering constraint)
- Do NOT add `Outputs` section to new templates (but existing one in `sqs-application-errors.yaml` is kept for transition safety)

### Pre-existing Issues in sqs-application-errors.yaml (Out of Scope)

- Line 2: Description in Polish (`'Template do utworzenia kolejki SQS DLQ'`) — should be English but not in scope
- Lines 50-58: `Outputs` section with CF Exports — anti-pattern but kept for transition safety
- No `Conditions` section — acceptable for this simple template
- Description missing canonical suffix "for Project Lenie"

These are noted for awareness but NOT addressed in this story.

### Project Structure Notes

- Both templates are already registered in `deploy.ini` — no changes needed
- `sqs-application-errors.yaml` is in Layer 4 (Storage), `sqs-to-rds-step-function.yaml` is in Layer 7 (Orchestration)
- Deployment order in `deploy.ini`: `sqs-application-errors.yaml` deploys first — SSM parameter will exist when step function template is deployed
- No new files created — only modifications to existing templates and parameter file

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 11.8] — Story definition with acceptance criteria
- [Source: infra/aws/cloudformation/templates/sqs-to-rds-step-function.yaml:416-418] — `Fn::ImportValue` to replace
- [Source: infra/aws/cloudformation/templates/sqs-application-errors.yaml:50-58] — CF Export source (DLQ ARN)
- [Source: infra/aws/cloudformation/parameters/dev/sqs-to-rds-step-function.json] — Parameter file to update
- [Source: _bmad-output/planning-artifacts/architecture.md#Implementation Patterns] — Gen 2+ canonical pattern, SSM consumption pattern
- [Source: _bmad-output/planning-artifacts/architecture.md#Anti-Patterns] — `Fn::ImportValue` listed as anti-pattern
- [Source: _bmad-output/implementation-artifacts/11-7-replace-legacy-lenie-websites-queue-references.md] — Previous story with SSM parameterization patterns
- [Source: _bmad-output/implementation-artifacts/11-2-improve-step-function-template-ssm-pattern-and-lambda-parameterization.md] — Story that first identified this ImportValue as code review finding

### Previous Story Intelligence

**From Story 11.7 (done) — Replace Legacy lenie_websites Queue References:**
- Used `AWS::SSM::Parameter::Value<String>` for SQS URL in `url-add.yaml`
- Noted `Fn::ImportValue` on line 117 of `url-add.yaml` as out of scope anti-pattern (same pattern as this story)
- All cfn-lint validations passed
- Commit prefix: `chore:` for infrastructure template changes

**From Story 11.6 (done) — Parameterize sqs-to-rds-lambda Infrastructure Values:**
- Successfully parameterized hardcoded infrastructure values in Lambda template
- Used SSM parameters following the same convention this story will use
- Commit: `cda9fd9 chore: parameterize hardcoded values in sqs-to-rds-lambda template`

**From Story 11.2 (done) — Improve Step Function Template:**
- Code review explicitly flagged `Fn::ImportValue` for DLQ ARN as → Story 11.8
- Already replaced `{{resolve:ssm:...}}` with `AWS::SSM::Parameter::Value<String>` in same template
- Established the precedent for SSM parameters in `sqs-to-rds-step-function.yaml`

### Git Intelligence

**Recent commits:**
```
cda9fd9 chore: parameterize hardcoded values in sqs-to-rds-lambda template
7f82301 chore: complete stories 10-3 and 11-3 with code review fixes
4a11307 chore: replace resolve:ssm with SSM Parameter types and parameterize Lambda name in step function
```

**Patterns to follow:**
- Commit prefix: `chore:` for infrastructure template changes
- cfn-lint validation before commit
- Parameter files updated alongside templates
- Template changes are incremental (one logical change per commit)

### Library / Framework Requirements

No new libraries or dependencies. Pure CloudFormation template modifications.

### File Structure Requirements

**Files to MODIFY:**

| File | Change |
|------|--------|
| `infra/aws/cloudformation/templates/sqs-application-errors.yaml` | Add `AWS::SSM::Parameter` resource for DLQ ARN (after existing resources, before Outputs) |
| `infra/aws/cloudformation/templates/sqs-to-rds-step-function.yaml` | Add `ProblemsDlqArn` SSM-backed parameter; replace `Fn::ImportValue` with `!Ref ProblemsDlqArn` |
| `infra/aws/cloudformation/parameters/dev/sqs-to-rds-step-function.json` | Add `ProblemsDlqArn` SSM path entry |

**Files NOT to touch:**
```
infra/aws/cloudformation/templates/url-add.yaml          [NO CHANGE] Has its own ImportValue, separate story
infra/aws/cloudformation/templates/ec2-lenie.yaml         [NO CHANGE] Has its own ImportValues, separate story
infra/aws/cloudformation/templates/sqs-documents.yaml     [NO CHANGE] Not related
infra/aws/cloudformation/templates/sqs-to-rds-lambda.yaml [NO CHANGE] Already fixed in Story 11.6
infra/aws/cloudformation/deploy.sh                        [NO CHANGE] Deployment script
infra/aws/cloudformation/deploy.ini                       [NO CHANGE] Both templates already registered
infra/aws/cloudformation/parameters/dev/sqs-application-errors.json [NO CHANGE] No new parameters needed
```

### Testing Requirements

**Validation (before commit):**
```bash
cfn-lint infra/aws/cloudformation/templates/sqs-application-errors.yaml
cfn-lint infra/aws/cloudformation/templates/sqs-to-rds-step-function.yaml
```

**Verification (grep checks):**
```bash
# Verify ImportValue for DLQ ARN is removed
grep -n "ImportValue" infra/aws/cloudformation/templates/sqs-to-rds-step-function.yaml
# Expected: zero matches

# Verify SSM Parameter resource exists in sqs-application-errors.yaml
grep -n "AWS::SSM::Parameter" infra/aws/cloudformation/templates/sqs-application-errors.yaml
# Expected: at least one match

# Verify CF Export is still present (safe transition)
grep -n "Export:" infra/aws/cloudformation/templates/sqs-application-errors.yaml
# Expected: one match (preserved)
```

**No unit or integration tests needed** — this is a pure infrastructure template change.

**Post-deploy verification (optional, not part of this story):**
```bash
# Verify SSM parameter was created
aws ssm get-parameter --name /lenie/dev/sqs/problems-dlq/arn --query 'Parameter.Value' --output text

# Verify EventBridge schedule still references valid DLQ ARN
aws scheduler get-schedule --name lenie-dev-sqs-to-rds --query 'Target.DeadLetterConfig.Arn' --output text
```

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6 (claude-opus-4-6)

### Debug Log References

- Step function template changes (`ProblemsDlqArn` parameter + `!Ref` replacement) were co-mingled with Story 11-7 commit `5a69cbe` — only the consumer-side change was committed. The producer-side change (`sqs-application-errors.yaml` SSM Parameter) and parameter file were left uncommitted, creating a split delivery. Resolved by committing all remaining deliverables in a dedicated Story 11-8 commit.

### Completion Notes List

- Added `ProblemsDlqArnParameter` (`AWS::SSM::Parameter`) resource to `sqs-application-errors.yaml` publishing DLQ ARN to SSM at `/${ProjectCode}/${Environment}/sqs/problems-dlq/arn`
- Added `ProblemsDlqArn` parameter with `Type: AWS::SSM::Parameter::Value<String>` to `sqs-to-rds-step-function.yaml`
- Replaced `Fn::ImportValue` with `!Ref ProblemsDlqArn` in EventBridge `DeadLetterConfig`
- Updated parameter file with SSM path entry
- CF Export preserved in `sqs-application-errors.yaml` for safe deployment transition
- cfn-lint passed with zero errors on both templates
- grep verified: zero `ImportValue` matches in step function template, `AWS::SSM::Parameter` present in errors template, `Export:` preserved

### File List

Starting state: `review → done`

- `infra/aws/cloudformation/templates/sqs-application-errors.yaml` — Modified: added `ProblemsDlqArnParameter` SSM Parameter resource
- `infra/aws/cloudformation/templates/sqs-to-rds-step-function.yaml` — Modified: added `ProblemsDlqArn` parameter, replaced `Fn::ImportValue` with `!Ref ProblemsDlqArn` *(committed in Story 11-7 commit `5a69cbe`)*
- `infra/aws/cloudformation/parameters/dev/sqs-to-rds-step-function.json` — Modified: added `ProblemsDlqArn` entry

## Change Log

- 2026-02-17: Replaced `Fn::ImportValue` for DLQ ARN with SSM Parameter pattern — added SSM Parameter to producing stack, added SSM-backed parameter to consuming stack, updated parameter file. CF Export preserved for safe transition deployment.
- 2026-02-17: **Code Review Round 2** — Found 4 issues (1 HIGH, 1 MEDIUM, 2 LOW). HIGH: uncommitted code changes (recurring pattern). MEDIUM: split commit — consumer committed in Story 11-7 (`5a69cbe`) without producer, creating broken deployment state on fresh checkout. LOW: Debug Log omitted co-mingled commit detail, File List missing state tracking. All fixed and committed.
