# Story 5.1: Remove Legacy AWS Resources

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer,
I want to remove all 9 legacy AWS resources following a documented dependency order,
so that the AWS account contains only actively used, IaC-managed resources.

## Acceptance Criteria

1. **Given** the documented list of 9 legacy resources with removal rationale
   **When** developer removes resources in dependency order
   **Then** CloudFront `E19SWSRXVWFGJQ` is deleted first (depends on S3 origin)
   **And** S3 `lenie-s3-web-test` is deleted after its CloudFront distribution is removed
   **And** Lambda `lenie_2_internet_tmp` is deleted (no dependents)
   **And** Lambda `lenie-url-add` is deleted (replaced by CF-managed `lenie-dev-url-add`)
   **And** API Gateway `pir31ejsf2` is deleted (no dependents after Lambda removal)
   **And** SNS topic `rds-monitor-sns` is deleted (dead subscription)
   **And** SNS topic `ses-monitoring` is deleted (not referenced by code)
   **And** SES identity `lenie-ai.eu` is deleted (not used by application)
   **And** SES identity `dev.lenie-ai.eu` is deleted (not used by application)

2. **Given** all legacy resources have been removed
   **When** developer verifies the codebase
   **Then** no references to these resources exist in the codebase (verified via code search)
   **And** the `ses.yaml` template file is deleted from `infra/aws/cloudformation/templates/`
   **And** the `ses.yaml` entry is removed from `deploy.ini` (all environment sections: qa, qa2, qa3, dev)
   **And** `infra/aws/README.md` section 15 is updated to reflect the cleanup

## Tasks / Subtasks

- [x] Task 1: Pre-deletion verification and documentation (AC: #1, #2)
  - [x] 1.1: Verify each legacy resource still exists in AWS before attempting deletion
  - [x] 1.2: Verify no active dependencies exist (e.g., CloudFront `E19SWSRXVWFGJQ` origin, SNS subscriptions)
  - [x] 1.3: Document current state of each resource for audit trail

- [x] Task 2: Remove CloudFront and S3 test resources (AC: #1)
  - [x] 2.1: Disable CloudFront distribution `E19SWSRXVWFGJQ` (must be disabled before deletion)
  - [x] 2.2: Wait for CloudFront distribution to reach `Deployed` state with disabled status
  - [x] 2.3: Delete CloudFront distribution `E19SWSRXVWFGJQ`
  - [x] 2.4: Empty S3 bucket `lenie-s3-web-test` (delete all objects)
  - [x] 2.5: Delete S3 bucket `lenie-s3-web-test`

- [x] Task 3: Remove legacy Lambda functions (AC: #1)
  - [x] 3.1: Delete Lambda function `lenie_2_internet_tmp`
  - [x] 3.2: Delete Lambda function `lenie-url-add`

- [x] Task 4: Remove legacy API Gateway (AC: #1)
  - [x] 4.1: Delete API Gateway `pir31ejsf2` (`lenie_chrome_extension`)

- [x] Task 5: Remove SNS topics (AC: #1)
  - [x] 5.1: Delete SNS topic `rds-monitor-sns` (including any subscriptions)
  - [x] 5.2: Delete SNS topic `ses-monitoring` (including any subscriptions)

- [x] Task 6: Remove SES identities (AC: #1)
  - [x] 6.1: Delete SES identity `lenie-ai.eu`
  - [x] 6.2: Delete SES identity `dev.lenie-ai.eu`

- [x] Task 7: Clean up codebase references (AC: #2)
  - [x] 7.1: Delete `infra/aws/cloudformation/templates/ses.yaml`
  - [x] 7.2: Remove `ses.yaml` entries from `deploy.ini` (sections: qa, qa2, qa3, and commented entry in dev)
  - [x] 7.3: Update `api-gw-app.yaml` — remove `/url_add` endpoint that references deleted `lenie-url-add` Lambda, then update the live CF stack
  - [x] 7.4: Update `web_chrome_extension/README.md` — replace legacy API Gateway URL `pir31ejsf2` with current CF-managed URL `jg40fjwz61`
  - [x] 7.5: Run codebase-wide search to verify no remaining references to deleted resources
  - [x] 7.6: Update `infra/aws/README.md` section 15 — remove entries for deleted resources, update summary table

- [x] Task 8: Post-deletion verification (AC: #1, #2)
  - [x] 8.1: Verify all 9 resources are gone from AWS (CLI checks)
  - [x] 8.2: Verify the main API Gateway `1bkc3kz7c9` still works (remaining endpoints unaffected)
  - [x] 8.3: Verify `grep`/code search confirms no remaining references in codebase

## Dev Notes

### Critical: Dependency Order for Resource Deletion

Resources MUST be deleted in this exact order to avoid dependency failures:

```
Phase 1 (CloudFront + S3 pair):
  1. Disable CloudFront E19SWSRXVWFGJQ
  2. Wait for disabled state
  3. Delete CloudFront E19SWSRXVWFGJQ
  4. Empty & Delete S3 lenie-s3-web-test

Phase 2 (Lambda + API Gateway chain):
  5. Delete Lambda lenie_2_internet_tmp (independent)
  6. Delete Lambda lenie-url-add
  7. Delete API Gateway pir31ejsf2 (after Lambda removal)

Phase 3 (Independent resources):
  8. Delete SNS rds-monitor-sns
  9. Delete SNS ses-monitoring
  10. Delete SES lenie-ai.eu
  11. Delete SES dev.lenie-ai.eu
```

### CRITICAL: API Gateway Template Update Required

The `api-gw-app.yaml` template (CF stack `lenie-dev-api-gw-app`) contains a `/url_add` endpoint that references `lenie-url-add` Lambda (hardcoded ARN in OpenAPI body, line ~681). After deleting the `lenie-url-add` Lambda:

1. The `/url_add` endpoint in the live API will return errors
2. The template must be updated to remove the `/url_add` path from the OpenAPI body
3. The CF stack must be updated: `aws cloudformation update-stack --stack-name lenie-dev-api-gw-app`
4. This was explicitly noted as out-of-scope in Story 4.2: _"Updating the `/url_add` endpoint to point to new Lambda — that's Epic 5 or post-cleanup"_

**Strategy:** Delete the Lambda first, then update `api-gw-app.yaml` to remove the `/url_add` path, then update the CF stack. The `/url_add` endpoint is superseded by:
- `/url_add2` (Step Functions integration in the same API)
- Chrome extension API (`api-gw-url-add.yaml`, separate API Gateway `lenie_dev_add_from_chrome_extension`)

**Template update must use S3 upload** (template exceeds 51200 byte inline limit, per Story 4.2 findings):
```bash
MSYS_NO_PATHCONV=1 aws s3 cp infra/aws/cloudformation/templates/api-gw-app.yaml \
  s3://lenie-dev-cloudformation/templates/api-gw-app.yaml --region us-east-1

MSYS_NO_PATHCONV=1 aws cloudformation update-stack \
  --stack-name lenie-dev-api-gw-app \
  --template-url https://lenie-dev-cloudformation.s3.amazonaws.com/templates/api-gw-app.yaml \
  --parameters file://infra/aws/cloudformation/parameters/dev/api-gw-app.json \
  --capabilities CAPABILITY_NAMED_IAM \
  --region us-east-1
```

### CloudFront Deletion Process

CloudFront distributions cannot be deleted directly. The process requires:
1. **Disable the distribution** — update configuration with `Enabled: false`
2. **Wait** — distribution must reach `Deployed` status while disabled (~15-20 min)
3. **Delete** — only then can the distribution be deleted

```bash
# Get current config (need ETag for update)
MSYS_NO_PATHCONV=1 aws cloudfront get-distribution-config --id E19SWSRXVWFGJQ --region us-east-1

# Disable (requires full DistributionConfig with Enabled: false + ETag)
MSYS_NO_PATHCONV=1 aws cloudfront update-distribution --id E19SWSRXVWFGJQ \
  --distribution-config <config-with-enabled-false> --if-match <etag> --region us-east-1

# Wait for deployed state
MSYS_NO_PATHCONV=1 aws cloudfront wait distribution-deployed --id E19SWSRXVWFGJQ --region us-east-1

# Delete
MSYS_NO_PATHCONV=1 aws cloudfront delete-distribution --id E19SWSRXVWFGJQ --if-match <new-etag> --region us-east-1
```

### S3 Bucket Deletion

S3 buckets must be emptied before deletion:
```bash
MSYS_NO_PATHCONV=1 aws s3 rm s3://lenie-s3-web-test --recursive --region us-east-1
MSYS_NO_PATHCONV=1 aws s3api delete-bucket --bucket lenie-s3-web-test --region us-east-1
```

### AWS CLI Commands for Resource Deletion

```bash
# Lambda functions
MSYS_NO_PATHCONV=1 aws lambda delete-function --function-name lenie_2_internet_tmp --region us-east-1
MSYS_NO_PATHCONV=1 aws lambda delete-function --function-name lenie-url-add --region us-east-1

# API Gateway
MSYS_NO_PATHCONV=1 aws apigateway delete-rest-api --rest-api-id pir31ejsf2 --region us-east-1

# SNS topics (need ARN — account 008971653395)
MSYS_NO_PATHCONV=1 aws sns delete-topic --topic-arn arn:aws:sns:us-east-1:008971653395:rds-monitor-sns --region us-east-1
MSYS_NO_PATHCONV=1 aws sns delete-topic --topic-arn arn:aws:sns:us-east-1:008971653395:ses-monitoring --region us-east-1

# SES identities
MSYS_NO_PATHCONV=1 aws ses delete-identity --identity lenie-ai.eu --region us-east-1
MSYS_NO_PATHCONV=1 aws ses delete-identity --identity dev.lenie-ai.eu --region us-east-1
```

### deploy.ini Changes

Current `ses.yaml` entries to remove:
- Line 11: `templates/ses.yaml` (in `[qa]` section)
- Line 14: `templates/ses.yaml` (in `[qa2]` section)
- Line 17: `templates/ses.yaml` (in `[qa3]` section)
- Line 47: `;templates/ses.yaml` (commented, in `[dev]` section)

### Chrome Extension README Update

`web_chrome_extension/README.md` line 30 contains the old legacy API Gateway URL:
```
https://pir31ejsf2.execute-api.us-east-1.amazonaws.com/v1/url_add
```
Replace with the current CF-managed URL:
```
https://jg40fjwz61.execute-api.us-east-1.amazonaws.com/v1/url_add
```

**Note:** The `popup.html` default URL (line 111) already uses `jg40fjwz61` — only the README is outdated.

### Endpoint `/url_add` Usage Analysis

The `/url_add` endpoint in API Gateway `1bkc3kz7c9` (`lenie_split`) is **NOT used by any active client**:
- **Chrome extension** uses separate API GW `jg40fjwz61` (`api-gw-url-add.yaml`, CF-managed)
- **web_add_url_react** uses configurable `apiUrl` pointing to Docker or CF-managed API
- **backend/server.py** has its own Flask route (Docker/K8s only)
- The `/url_add` endpoint in `lenie_split` was superseded by `/url_add2` (Step Functions)

Safe to remove from `api-gw-app.yaml` without breaking any client.

### README.md Section 15 Update

After cleanup, update `infra/aws/README.md` section 15:
- **15.1 S3 Buckets**: Remove `lenie-s3-web-test` row. Keep `lenie-s3-tmp` with note "migrated, pending deletion" or remove if already deleted
- **15.2 CloudFront**: Remove `E19SWSRXVWFGJQ` row. Remove `ETIQTXICZBECA` row (now CF-managed via Story 4.1)
- **15.3 Lambda Functions**: Remove `lenie_2_internet_tmp` and `lenie-url-add` rows
- **15.4 DynamoDB**: Remove all 3 rows (now CF-managed via Story 1.1)
- **15.5 SNS Topics**: Remove both rows (section can be removed entirely)
- **15.6 API Gateway**: Remove `pir31ejsf2` row. Remove `1bkc3kz7c9` row (now CF-managed via Story 4.2)
- **15.7 SES Identities**: Remove `lenie-ai.eu` row. Keep `krzysztof@itsnap.eu` if still exists
- **15.8 Lambda Layers**: Remove all 3 rows (now CF-managed via Story 2.1)
- **15.9 Summary**: Update counts to reflect current state

### MSYS_NO_PATHCONV=1 Prefix

All AWS CLI commands with `/` paths MUST use `MSYS_NO_PATHCONV=1` prefix on Windows/MSYS to prevent path conversion. This was established in Story 2.1.

### What This Story Does NOT Include

- Deleting `lenie-s3-tmp` (the old website content bucket) — that was part of Story 3.1 migration
- Removing `step-function-test` Lambda — mentioned in README but not in the 9-resource cleanup list
- Modifying any CloudFormation stacks other than `lenie-dev-api-gw-app` (for `/url_add` removal)
- Updating `deploy.ini` with new template positions — that is Story 6.1's responsibility
- Cleaning up Lambda Layers, DynamoDB tables, or other resources now managed by CF (Epics 1-2)

### Lessons from Previous Stories (MUST Apply)

1. **MSYS_NO_PATHCONV=1** for all AWS CLI commands with `/` paths on Windows/MSYS (Story 2.1)
2. **Template S3 upload** for `api-gw-app.yaml` — exceeds 51200 byte inline limit (Story 4.2)
3. **Verify before delete** — always confirm resource exists before attempting deletion
4. **No hardcoded account IDs** — use `${AWS::AccountId}` in templates. The current account is `008971653395` (Story 4.2 finding)
5. **Drift detection after stack updates** — verify `api-gw-app.yaml` stack is IN_SYNC after removing `/url_add` endpoint

### Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Deleting wrong resource | Critical | Verify resource ID/name matches exactly before each deletion |
| `/url_add` endpoint breaks before template update | Low | Delete Lambda, immediately update API GW template — short window |
| CloudFront deletion takes too long | Low | Disable first, wait, delete — can run other tasks in parallel |
| SNS topic has active subscriptions | Low | `delete-topic` removes all subscriptions automatically |
| SES identity deletion breaks email | Low | SES identities confirmed not used by application code |
| `api-gw-app.yaml` stack update fails | Medium | Test template validation before updating stack; rollback available |

### Project Structure Notes

- Files to DELETE: `infra/aws/cloudformation/templates/ses.yaml`
- Files to MODIFY: `infra/aws/cloudformation/deploy.ini`, `infra/aws/cloudformation/templates/api-gw-app.yaml`, `infra/aws/README.md`
- No new files created in this story
- All changes are within `infra/aws/` directory

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 5.1] — Acceptance criteria and 9 legacy resources list
- [Source: _bmad-output/planning-artifacts/architecture.md#Legacy Resource Cleanup (Updated)] — 9 resources with removal rationale
- [Source: _bmad-output/planning-artifacts/architecture.md#Implementation Patterns & Consistency Rules] — Template consistency rules for api-gw-app.yaml update
- [Source: infra/aws/README.md#Section 15] — Current documentation of unmanaged resources
- [Source: infra/aws/cloudformation/deploy.ini] — ses.yaml entries in qa/qa2/qa3/dev sections
- [Source: infra/aws/cloudformation/templates/api-gw-app.yaml] — `/url_add` endpoint referencing `lenie-url-add` Lambda
- [Source: _bmad-output/implementation-artifacts/4-2-update-api-gateway-main-application-cloudformation-template.md] — API GW import learnings, template S3 upload requirement, RestApi-only strategy, `/url_add` update deferred to Epic 5
- [Source: _bmad-output/implementation-artifacts/2-1-create-lambda-layer-cloudformation-templates.md] — MSYS_NO_PATHCONV fix for Windows/MSYS
- [Source: infra/aws/cloudformation/CLAUDE.md] — deploy.sh usage, stack naming, deploy.ini format
- [Source: infra/aws/CLAUDE.md] — AWS account architecture, services overview

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List

- Task 1 completed: All 9 legacy resources verified as existing in AWS (2026-02-15). Dependencies documented: CloudFront E19SWSRXVWFGJQ → S3 lenie-s3-web-test origin confirmed. SNS rds-monitor-sns has 1 lambda subscription (rds-start-reporter-sns). SNS ses-monitoring has 1 email subscription. All will be auto-deleted with topics.
- Task 2 completed: CloudFront E19SWSRXVWFGJQ disabled, waited for Deployed state, deleted. S3 lenie-s3-web-test emptied (15 objects) and deleted.
- Task 3 completed: Lambda lenie_2_internet_tmp and lenie-url-add deleted.
- Task 4 completed: API Gateway pir31ejsf2 (lenie_chrome_extension) deleted.
- Task 5 completed: SNS topics rds-monitor-sns and ses-monitoring deleted (subscriptions auto-removed).
- Task 6 completed: SES identities lenie-ai.eu and dev.lenie-ai.eu deleted.
- Task 7 completed: ses.yaml template deleted, deploy.ini cleaned, /url_add endpoint removed from api-gw-app.yaml, CF stack updated, Chrome extension README updated, docs/API_Usage.md fixed (extra reference found), README.md section 15 updated.
- Task 8 completed: All 9 resources confirmed deleted via AWS CLI. Main API Gateway 1bkc3kz7c9 verified AVAILABLE. Codebase search confirmed no remaining references in active code.
- Code review fixes (2026-02-15): Removed stale `ses.yaml` documentation from README Section 11 and CLAUDE.md. Fixed S3 bucket count (6→5) in Section 15.9 summary. Added missing helm bucket to header table. Added `api-gw-app.json` to File List.

### Change Log

- 2026-02-15: Story 5.1 implementation complete. Removed 9 legacy AWS resources, cleaned codebase references, updated CF stack and documentation.

### File List

- DELETED: `infra/aws/cloudformation/templates/ses.yaml`
- MODIFIED: `infra/aws/cloudformation/deploy.ini` (removed ses.yaml entries from qa/qa2/qa3/dev)
- MODIFIED: `infra/aws/cloudformation/templates/api-gw-app.yaml` (removed /url_add endpoint)
- MODIFIED: `infra/aws/cloudformation/parameters/dev/api-gw-app.json` (renamed parameter stage → Environment)
- MODIFIED: `infra/aws/README.md` (updated sections 11 and 15 — removed deleted resources, updated summary)
- MODIFIED: `web_chrome_extension/README.md` (updated API Gateway URL from pir31ejsf2 to jg40fjwz61)
- MODIFIED: `docs/API_Usage.md` (updated API Gateway URL from pir31ejsf2 to jg40fjwz61)
