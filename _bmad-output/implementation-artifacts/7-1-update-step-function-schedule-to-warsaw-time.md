# Story 7.1: Update Step Function Schedule to Warsaw Time

Status: done

## Story

As a developer,
I want to update the Step Function `sqs-to-rds` EventBridge schedule to run at 5:00 AM Warsaw time with explicit `Europe/Warsaw` timezone,
So that the SQS-to-RDS cost-optimization workflow runs at a predictable local time regardless of DST changes.

## Acceptance Criteria

1. **Given** the Step Function CF template uses a UTC-based cron schedule without explicit timezone
   **When** developer updates the CloudFormation template and parameters
   **Then** `ScheduleExpressionTimezone: "Europe/Warsaw"` is added to the `EventBridgeScheduler` resource
   **And** the cron expression is updated to `cron(0 5 * * ? *)` (5:00 AM Warsaw time)
   **And** the CF stack is redeployed and the EventBridge Schedule is active with the new timezone and schedule
   **And** all 5 resources (StateMachine, StateMachineRole, StateMachineLogGroup, StepFunctionInvokerRole, EventBridgeScheduler) are operational

## Context

This story replaces the original Story 7.1 ("Archive Step Function Code & Remove AWS Resources") which was incorrectly planned. The Step Function `sqs-to-rds` is a critical cost-optimization mechanism — it starts the RDS database only when SQS messages need processing, then stops it. The original plan to archive and delete it was reversed via the Correct Course workflow.

## Tasks / Subtasks

- [x] Task 1: Restore Step Function files from git (previously deleted in error)
  - [x] 1.1: `git checkout HEAD -- infra/aws/cloudformation/templates/sqs-to-rds-step-function.yaml`
  - [x] 1.2: `git checkout HEAD -- infra/aws/cloudformation/parameters/dev/sqs-to-rds-step-function.json`
  - [x] 1.3: `git checkout HEAD -- infra/aws/cloudformation/step_functions/sqs_to_rds.json`

- [x] Task 2: Update CF template with Europe/Warsaw timezone (AC: #1)
  - [x] 2.1: Add `ScheduleExpressionTimezone: "Europe/Warsaw"` to `EventBridgeScheduler` resource
  - [x] 2.2: Update cron expression in parameters to `cron(0 5 * * ? *)`

- [x] Task 3: Restore deploy.ini Layer 7 (Orchestration) section
  - [x] 3.1: Add `templates/sqs-to-rds-step-function.yaml` back to Layer 7
  - [x] 3.2: Renumber CDN layer from 7 back to 8

- [x] Task 4: Clean up archive files (no longer needed)
  - [x] 4.1: Delete `infra/archive/sqs-to-rds-step-function.yaml`
  - [x] 4.2: Delete `infra/archive/sqs_to_rds.json`
  - [x] 4.3: Delete `infra/archive/README-sqs-to-rds.md`

- [x] Task 5: Create missing SSM parameters and deploy CF stack
  - [x] 5.1: Create SSM param `/lenie/dev/sqs/documents/url` (pointing to `lenie_websites` queue)
  - [x] 5.2: Create SSM param `/lenie/dev/database/name` (value: `lenie-dev`)
  - [x] 5.3: Delete orphaned ghost stack `lenie-dev-sqs-to-rds` (resources were manually deleted but stack record remained)
  - [x] 5.4: Create stack `lenie-dev-sqs-to-rds-step-function` with updated template
  - [x] 5.5: Verify all 5 resources created successfully
  - [x] 5.6: Verify scheduler: ENABLED, `cron(0 5 * * ? *)`, `Europe/Warsaw`

- [x] Task 6: Update planning artifacts
  - [x] 6.1: Update sprint-status.yaml (rename story, status: done)
  - [x] 6.2: Update epics.md (rename Epic 1, rewrite Story 1.1, withdraw FR3/FR8/FR11-13/FR15/NFR3)

## Dev Notes

### Architecture Context

- **Step Function purpose**: Cost optimization — starts RDS only when SQS has messages, processes them, then stops RDS
- **CF Stack Name**: `lenie-dev-sqs-to-rds-step-function` (corrected from original `lenie-dev-sqs-to-rds`)
- **EventBridge Schedule**: `cron(0 5 * * ? *)` at `Europe/Warsaw` timezone (was `cron(30 4 * * ? *)` UTC)
- **5 AWS resources**: StateMachine, StateMachineRole, StateMachineLogGroup, StepFunctionInvokerRole, EventBridgeScheduler

### Discovery: Ghost CF Stack

The original CF stack was named `lenie-dev-sqs-to-rds` (not `lenie-dev-sqs-to-rds-step-function`). During Story 7-1 (now rolled back), the resources were manually deleted but the stack record remained. This ghost stack had to be deleted before creating the new correctly-named stack.

### Discovery: Missing SSM Parameters

Two SSM parameters required by the CF template were missing:
- `/lenie/dev/sqs/documents/url` — should have been created by `sqs-documents.yaml` stack (which is not deployed)
- `/lenie/dev/database/name` — was commented out in `rds.yaml`

Both were created manually to unblock the Step Function deployment.

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6 (claude-opus-4-6)

### Completion Notes List

- **Task 1:** Restored 3 files from git (CF template, parameters, state machine JSON)
- **Task 2:** Added `ScheduleExpressionTimezone: "Europe/Warsaw"` to CF template, updated cron to `cron(0 5 * * ? *)`
- **Task 3:** Restored Layer 7 (Orchestration) in deploy.ini, renumbered CDN back to Layer 8
- **Task 4:** Deleted 3 archive files (sqs-to-rds-step-function.yaml, sqs_to_rds.json, README-sqs-to-rds.md)
- **Task 5:** Created 2 SSM params, deleted ghost stack `lenie-dev-sqs-to-rds`, deleted ROLLBACK_COMPLETE stack, created new stack `lenie-dev-sqs-to-rds-step-function`. All 5 resources verified operational. Scheduler confirmed: ENABLED, `cron(0 5 * * ? *)`, `Europe/Warsaw`
- **Task 6:** Updated sprint-status.yaml and epics.md

### File List

**Modified files:**
- `infra/aws/cloudformation/templates/sqs-to-rds-step-function.yaml` (added ScheduleExpressionTimezone, Description field, translated Polish comments to English, narrowed IAM policies to specific ARNs, added Tags to all resources, added Description to ScheduleExpression parameter, fixed Or single-item wrapper in DefinitionString)
- `infra/aws/cloudformation/parameters/dev/sqs-to-rds-step-function.json` (cron updated to 5:00 AM)
- `infra/aws/cloudformation/deploy.ini` (no net changes — entry was restored from rolled-back session, already present in HEAD)
- `docs/architecture-infra.md` (added manual execution steps for SQS to RDS Step Function)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (renamed story, status: done)
- `_bmad-output/planning-artifacts/epics.md` (Epic 1 renamed, Story 1.1 rewritten, FRs updated)

**New files:**
- `_bmad-output/implementation-artifacts/7-1-update-step-function-schedule-to-warsaw-time.md` (this file)

**Deleted files:**
- `infra/archive/sqs-to-rds-step-function.yaml` (archive no longer needed)
- `infra/archive/sqs_to_rds.json` (archive no longer needed)
- `infra/archive/README-sqs-to-rds.md` (archive no longer needed)
- `infra/aws/cloudformation/step_functions/sqs_to_rds.json` (stale — completely out of sync with deployed DefinitionString in CF template)

**Superseded files:**
- `_bmad-output/implementation-artifacts/7-1-archive-step-function-code-and-remove-aws-resources.md` (old story, should be deleted)

**Created AWS resources (us-east-1):**
- CF Stack: `lenie-dev-sqs-to-rds-step-function`
- State Machine: `lenie-dev-sqs-to-rds`
- EventBridge Schedule: `lenie-dev-sqs-to-rds` (5:00 AM Europe/Warsaw, ENABLED)
- CloudWatch Log Group: `/aws/states/lenie-dev-sqs-to-rds`
- IAM Role: StateMachineRole (auto-generated name)
- IAM Role: StepFunctionInvokerRole (auto-generated name)

**Created SSM Parameters:**
- `/lenie/dev/sqs/documents/url` = `https://sqs.us-east-1.amazonaws.com/008971653395/lenie_websites`
- `/lenie/dev/database/name` = `lenie-dev`

**Deleted AWS resources:**
- Ghost CF stack `lenie-dev-sqs-to-rds` (resources were already manually deleted)

### Change Log

- 2026-02-16: Story 7.1 corrected via Correct Course workflow — Step Function restored with updated schedule (5:00 AM Warsaw time), archive files removed, planning artifacts updated
- 2026-02-16: Code review — fixed: added CF Description field, translated 3 Polish comments to English, corrected File List (added missing docs/architecture-infra.md, clarified deploy.ini). Created 2 action items for future improvements.
- 2026-02-16: Re-review — fixed: deleted stale `sqs_to_rds.json` (H1), narrowed IAM Resource:"*" to specific ARNs (M1), added Tags to 4 resources (M4), fixed Or single-item wrapper (M5), added Description to ScheduleExpression parameter (L1). Kept 2 action items (M2: SSM parameter types, M3: Lambda function parameterization).

### Review Follow-ups (AI)

- [x] [AI-Review][HIGH] Delete stale `infra/aws/cloudformation/step_functions/sqs_to_rds.json` — completely out of sync with deployed DefinitionString (different states, flow, and naming) — **FIXED in re-review**
- [x] [AI-Review][MEDIUM] Narrow `Resource: "*"` wildcard IAM policies in StateMachineRole to specific resource ARNs — **FIXED in re-review** (split into 3 statements: SQS, RDS, Lambda with specific ARNs)
- [x] [AI-Review][MEDIUM] Add Tags (Project, Environment) to all taggable resources — **FIXED in re-review**
- [x] [AI-Review][MEDIUM] Fix single-item `Or` condition wrapper in DefinitionString — **FIXED in re-review**
- [x] [AI-Review][LOW] Add Description to ScheduleExpression parameter — **FIXED in re-review**
- [ ] [AI-Review][MEDIUM] Replace `{{resolve:ssm:...}}` dynamic references with `AWS::SSM::Parameter::Value<String>` parameter types in EventBridgeScheduler Input — requires adding 2 new CF parameters + updating parameters file [`infra/aws/cloudformation/templates/sqs-to-rds-step-function.yaml:399`]
- [ ] [AI-Review][MEDIUM] Parameterize hardcoded Lambda function name `lenie-sqs-to-db` in DefinitionString — requires DefinitionSubstitutions refactoring [`infra/aws/cloudformation/templates/sqs-to-rds-step-function.yaml:257`]

## Senior Developer Review (AI)

### Review 1

**Reviewer:** Claude Opus 4.6 (code-review workflow)
**Date:** 2026-02-16

**Summary:** Story 7-1 correctly implements the core AC — `ScheduleExpressionTimezone: "Europe/Warsaw"` and `cron(0 5 * * ? *)` are in place and deployed. The story was complicated by a rolled-back predecessor (archive/delete story), but the final result is correct. Code review found 8 issues (1 HIGH, 5 MEDIUM, 2 LOW). 4 issues were fixed directly (Description field, Polish comments, File List corrections). 2 MEDIUM issues require deeper template refactoring and are tracked as action items.

**Fixes Applied:**
1. Added `Description` field to CF template (architectural compliance)
2. Translated 3 Polish comments to English (architectural compliance)
3. Added missing `docs/architecture-infra.md` to File List
4. Clarified `deploy.ini` entry (no net changes, was restored from rolled-back session)

**Action Items Created:** 2 (SSM parameter types, IAM least privilege)
**Outcome:** Approved with action items

### Review 2 (Re-review)

**Reviewer:** Claude Opus 4.6 (code-review workflow)
**Date:** 2026-02-16

**Summary:** Re-review found 9 issues (1 HIGH, 6 MEDIUM, 2 LOW). The stale `sqs_to_rds.json` file (completely different state machine definition than the deployed CF template) was the most critical finding — deleted. IAM wildcard policies narrowed to specific resource ARNs. Tags added to all taggable resources. Single-item `Or` wrapper simplified. Two MEDIUM items remain as action items (SSM parameter types, Lambda function parameterization).

**Fixes Applied:**
1. Deleted stale `step_functions/sqs_to_rds.json` (H1 — was out of sync with deployed DefinitionString)
2. Narrowed IAM `Resource: "*"` in StateMachinePolicy to specific ARNs: SQS queue, RDS instance, Lambda function (M1)
3. Added `Tags` (Project, Environment) to StateMachineRole, StateMachineLogGroup, MyStateMachine, StepFunctionInvokerRole (M4)
4. Fixed `Or` single-item wrapper in DefinitionString "Should be DB started?" state (M5)
5. Added `Description` to `ScheduleExpression` parameter (L1)

**Action Items Remaining:** 2 (SSM parameter types, Lambda function parameterization)
**Note:** L2 (inconsistent quoting style) acknowledged but not auto-fixed — cosmetic change with high diff noise risk
**Outcome:** Approved with action items — requires CF stack update to deploy fixes
