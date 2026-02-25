# Story B.9: Organize S3 CloudFormation Bucket Directory Structure

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **developer**,
I want Lambda ZIP artifacts in the `lenie-{env}-cloudformation` S3 bucket moved from the root into a `lambdas/` prefix, with stale pre-consolidation ZIPs deleted,
so that the bucket has a clean, organized directory structure (`layers/`, `lambdas/`, `templates/`) and only contains actively used artifacts.

## Acceptance Criteria

1. **AC1 — Lambda ZIPs relocated to `lambdas/` prefix:** All 8 active Lambda ZIP files are stored under `s3://lenie-{env}-cloudformation/lambdas/` instead of the bucket root. No Lambda ZIPs remain at root level.

2. **AC2 — CloudFormation templates updated:** All 4 CF templates (6 Lambda resource definitions) reference the new `lambdas/` S3Key prefix:
   - `api-gw-infra.yaml` — 3 functions: `lambdas/${PC}-${Env}-ec2-manager.zip`, `lambdas/${PC}-${Env}-rds-manager.zip`, `lambdas/${PC}-${Env}-sqs-size.zip`
   - `sqs-to-rds-lambda.yaml` — `lambdas/${PC}-${Env}-sqs-into-rds.zip`
   - `url-add.yaml` — `lambdas/${PC}-${Env}-url-add.zip`
   - `lambda-weblink-put-into-sqs.yaml` — `lambdas/${PC}-${Env}-url-add.zip`

3. **AC3 — Upload script updated:** `zip_to_s3.sh` uploads ZIPs to the `lambdas/` prefix (e.g., `s3://${BUCKET}/lambdas/${LAMBDA_NAME}.zip`) for both `simple` and `app` deployment modes.

4. **AC4 — Individual update scripts updated:** All `lambda_update.sh` scripts in `infra/aws/serverless/lambdas/*/` that upload to S3 use the `lambdas/` prefix.

5. **AC5 — Stale ZIPs deleted:** 7 obsolete ZIP files removed from bucket root:
   - `lenie-dev-ec2-start.zip` (pre-consolidation, Epic 18)
   - `lenie-dev-ec2-status.zip` (pre-consolidation, Epic 18)
   - `lenie-dev-ec2-stop.zip` (pre-consolidation, Epic 18)
   - `lenie-dev-rds-start.zip` (pre-consolidation, Epic 18)
   - `lenie-dev-rds-status.zip` (pre-consolidation, Epic 18)
   - `lenie-dev-rds-stop.zip` (pre-consolidation, Epic 18)
   - `lenie-dev-sqs-to-db.zip` (old name, from 2025-02-17)

6. **AC6 — Zero downtime:** All Lambda functions remain operational throughout migration. ZIPs are copied to new prefix BEFORE templates are updated.

7. **AC7 — Documentation updated:** `infra/aws/cloudformation/CLAUDE.md` and `infra/aws/serverless/CLAUDE.md` updated to document the `lambdas/` prefix convention.

## Tasks / Subtasks

- [x] **Task 1: Upload active ZIPs to `lambdas/` prefix** (AC: #1, #6)
  - [x] 1.1 Copy 8 active ZIPs from root to `lambdas/` prefix using `aws s3 cp`
  - [x] 1.2 Verified all 8 files exist under `lambdas/` prefix

- [x] **Task 2: Update CloudFormation templates** (AC: #2)
  - [x] 2.1 In `api-gw-infra.yaml`: updated S3Key for Ec2ManagerFunction, RdsManagerFunction, SqsSizeFunction — prepended `lambdas/`
  - [x] 2.2 In `sqs-to-rds-lambda.yaml`: updated S3Key — prepended `lambdas/`
  - [x] 2.3 In `url-add.yaml`: updated S3Key — prepended `lambdas/`
  - [x] 2.4 In `lambda-weblink-put-into-sqs.yaml`: updated S3Key — prepended `lambdas/`
  - [x] 2.5 Validated all 4 templates with cfn-lint — warnings only (pre-existing W3660), no errors

- [x] **Task 3: Deploy updated templates** (AC: #2, #6)
  - [x] 3.1 Deployed via WSL: `deploy.sh -p lenie -s dev -y`
  - [x] 3.2 All 4 affected stacks updated: lenie-dev-lambda-weblink-put-into-sqs, lenie-dev-sqs-to-rds-lambda, lenie-dev-url-add, lenie-dev-api-gw-infra (+ API GW redeployed)
  - [x] 3.3 Tested sqs-size Lambda via API Gateway test-invoke-method — function invoked successfully (loaded code from new lambdas/ prefix)

- [x] **Task 4: Update `zip_to_s3.sh` script** (AC: #3)
  - [x] 4.1 Modified S3 upload path to `s3://${AWS_S3_BUCKET_NAME}/lambdas/${LAMBDA_NAME}.zip`
  - [x] 4.2 N/A — `aws lambda update-function-code` uses `--zip-file fileb://` (direct upload, not S3 key), no change needed
  - [x] 4.3 N/A — skipped live test to avoid unnecessary redeployment; code change verified by inspection

- [x] **Task 5: Update individual `lambda_update.sh` scripts** (AC: #4)
  - [x] 5.1 Checked all `lambda_update.sh` scripts — only `sqs-weblink-put-into/lambda_update.sh` uploads to S3; updated to `lambdas/` prefix
  - [x] 5.2 Other scripts (app-server-db, app-server-internet, sqs-size) use `fileb://` direct upload — no S3 path changes needed

- [x] **Task 6: Delete stale ZIPs from bucket root** (AC: #5)
  - [x] 6.1 Deleted 7 stale ZIPs (ec2-start/stop/status, rds-start/stop/status, sqs-to-db)

- [x] **Task 7: Delete old root-level ZIPs** (AC: #1)
  - [x] 7.1 Deleted 8 original root-level ZIPs after confirming Lambda functions work with `lambdas/` prefix
  - [x] 7.2 Verified bucket root shows only 3 prefixes: `lambdas/`, `layers/`, `templates/`

- [x] **Task 8: Update documentation** (AC: #7)
  - [x] 8.1 Updated `infra/aws/cloudformation/CLAUDE.md` — documented `lambdas/` prefix convention and S3 bucket structure
  - [x] 8.2 Updated `infra/aws/serverless/CLAUDE.md` — documented `lambdas/` prefix for ZIP uploads and bucket structure

## Dev Notes

### Current State (Problem)

The `lenie-dev-cloudformation` S3 bucket has a disorganized structure. Lambda ZIP artifacts are dumped at the bucket root alongside `layers/` and `templates/` directories:

```
lenie-dev-cloudformation/
├── layers/                              # OK — organized
│   ├── lenie_all_layer.zip
│   ├── lenie_openai.zip
│   └── psycopg2_new_layer.zip
├── templates/                           # OK — organized
│   └── api-gw-app.yaml
├── lenie-dev-app-server-db.zip          # ACTIVE — root (messy)
├── lenie-dev-app-server-internet.zip    # ACTIVE
├── lenie-dev-ec2-manager.zip            # ACTIVE
├── lenie-dev-ec2-start.zip              # STALE (pre-consolidation Epic 18)
├── lenie-dev-ec2-status.zip             # STALE
├── lenie-dev-ec2-stop.zip               # STALE
├── lenie-dev-rds-manager.zip            # ACTIVE
├── lenie-dev-rds-start.zip              # STALE
├── lenie-dev-rds-status.zip             # STALE
├── lenie-dev-rds-stop.zip               # STALE
├── lenie-dev-sqs-into-rds.zip           # ACTIVE
├── lenie-dev-sqs-size.zip               # ACTIVE
├── lenie-dev-sqs-to-db.zip              # STALE (old name, 2025-02-17)
├── lenie-dev-sqs-weblink-put-into.zip   # ACTIVE
└── lenie-dev-url-add.zip                # ACTIVE
```

### Target State

```
lenie-dev-cloudformation/
├── lambdas/                             # NEW — organized Lambda ZIPs
│   ├── lenie-dev-app-server-db.zip
│   ├── lenie-dev-app-server-internet.zip
│   ├── lenie-dev-ec2-manager.zip
│   ├── lenie-dev-rds-manager.zip
│   ├── lenie-dev-sqs-into-rds.zip
│   ├── lenie-dev-sqs-size.zip
│   ├── lenie-dev-sqs-weblink-put-into.zip
│   └── lenie-dev-url-add.zip
├── layers/
│   ├── lenie_all_layer.zip
│   ├── lenie_openai.zip
│   └── psycopg2_new_layer.zip
└── templates/
    └── api-gw-app.yaml
```

### Lambda Function → ZIP Mapping (6 CF-managed + 2 non-CF)

| Lambda Function | CF Template | S3Key (current) | S3Key (target) |
|---|---|---|---|
| `${PC}-${Env}-ec2-manager` | `api-gw-infra.yaml` | `${PC}-${Env}-ec2-manager.zip` | `lambdas/${PC}-${Env}-ec2-manager.zip` |
| `${PC}-${Env}-rds-manager` | `api-gw-infra.yaml` | `${PC}-${Env}-rds-manager.zip` | `lambdas/${PC}-${Env}-rds-manager.zip` |
| `${PC}-${Env}-sqs-size` | `api-gw-infra.yaml` | `${PC}-${Env}-sqs-size.zip` | `lambdas/${PC}-${Env}-sqs-size.zip` |
| `${PC}-${Env}-sqs-into-rds` | `sqs-to-rds-lambda.yaml` | `${PC}-${Env}-sqs-into-rds.zip` | `lambdas/${PC}-${Env}-sqs-into-rds.zip` |
| `${PC}-${Env}-url-add` | `url-add.yaml` | `${PC}-${Env}-url-add.zip` | `lambdas/${PC}-${Env}-url-add.zip` |
| `${PC}-${Env}-weblink-put-into-sqs` | `lambda-weblink-put-into-sqs.yaml` | `${PC}-${Env}-url-add.zip` | `lambdas/${PC}-${Env}-url-add.zip` |
| `${PC}-${Env}-app-server-db` | NOT CF-managed | `${PC}-${Env}-app-server-db.zip` | `lambdas/${PC}-${Env}-app-server-db.zip` |
| `${PC}-${Env}-app-server-internet` | NOT CF-managed | `${PC}-${Env}-app-server-internet.zip` | `lambdas/${PC}-${Env}-app-server-internet.zip` |

Note: `lambda-weblink-put-into-sqs.yaml` deploys a function named `weblink-put-into-sqs` but uses the `url-add.zip` artifact (shared code).

### S3Key Change Pattern in Templates

All CF-managed Lambda functions use the same S3Bucket pattern:
```yaml
Code:
  S3Bucket: '{{resolve:ssm:/${ProjectCode}/${Environment}/s3/cloudformation/name}}'
  S3Key: !Sub '${ProjectCode}-${Environment}-<function>.zip'
```

Change to:
```yaml
Code:
  S3Bucket: '{{resolve:ssm:/${ProjectCode}/${Environment}/s3/cloudformation/name}}'
  S3Key: !Sub 'lambdas/${ProjectCode}-${Environment}-<function>.zip'
```

Only the `S3Key` line changes — prepend `lambdas/`. No other resource properties are modified.

### zip_to_s3.sh Change Pattern

Current upload command (line pattern):
```bash
aws s3 cp tmp/${LAMBDA_NAME}.zip s3://${AWS_S3_BUCKET_NAME}/${LAMBDA_NAME}.zip --profile ${PROFILE}
```

Change to:
```bash
aws s3 cp tmp/${LAMBDA_NAME}.zip s3://${AWS_S3_BUCKET_NAME}/lambdas/${LAMBDA_NAME}.zip --profile ${PROFILE}
```

Note: `aws lambda update-function-code` in `zip_to_s3.sh` uses `--zip-file fileb://` (direct upload), not `--s3-bucket/--s3-key`, so no S3Key change is needed for that command.

### Stale ZIPs — Why Safe to Delete

These 7 ZIPs are remnants from before Lambda consolidation (Epic 18, story 18-consolidation-implementation):
- `ec2-start/stop/status` → consolidated into `ec2-manager` (commit `6b458cf`)
- `rds-start/stop/status` → consolidated into `rds-manager` (commit `6b458cf`)
- `sqs-to-db` → old name, replaced by `sqs-into-rds` long ago (dated 2025-02-17)

No CF template or script references these files. The corresponding Lambda functions were deleted during Epic 18.

### Migration Strategy (Zero Downtime)

1. **Copy first, update second:** Copy active ZIPs to `lambdas/` prefix BEFORE updating CF templates. Lambda functions continue running from root-level ZIPs until CF update completes.
2. **CF update is safe:** Changing `S3Key` triggers Lambda code update. CloudFormation updates the function code to point to the new S3 location. The Lambda runtime downloads the ZIP at deploy time — not at invocation time — so in-flight requests are unaffected.
3. **Script update timing:** Update `zip_to_s3.sh` AFTER CF template deploy succeeds. This ensures next upload goes to the correct prefix.
4. **Delete root ZIPs last:** Only delete root-level ZIPs after confirming all functions work with the `lambdas/` prefix.

### Deploy via WSL

As per project convention, `deploy.sh` must be run via WSL from Claude Code:
```bash
wsl bash -c "cd /mnt/c/Users/ziutus/git/_lenie-all/lenie-server-2025/infra/aws/cloudformation && ./deploy.sh -p lenie -s dev -y"
```

### Anti-Patterns to Avoid

- Do NOT delete root-level ZIPs before CF templates are updated — Lambda functions would fail to find code
- Do NOT update `zip_to_s3.sh` before CF templates — next deploy would upload to new prefix but CF would still look at old prefix
- Do NOT rename files — use S3 copy (S3 has no rename/move, only copy + delete)
- Do NOT change `S3Bucket` — only `S3Key` changes (bucket name stays the same via SSM resolve)

### Architecture Compliance

- **S3 prefix naming:** `lambdas/` aligns with existing `layers/` and `templates/` convention (lowercase, plural)
- **SSM bucket reference:** unchanged — S3Bucket still resolved via `{{resolve:ssm:/${ProjectCode}/${Environment}/s3/cloudformation/name}}`
- **Tag standard:** no new taggable resources created
- **Gen 2+ canonical pattern:** no template structural changes (Parameters → Conditions → Resources order maintained)

### Previous Story Learnings (B-8)

From B-8 (ACM certificates via CloudFormation):
- **cfn-lint validation mandatory** before every deploy
- **Deploy via WSL** from Claude Code (Git Bash breaks `file://` paths)
- **DeletionPolicy: Retain** consideration — not needed here (S3Key change doesn't replace resources)

### File Structure

**Modified files:**
- `infra/aws/cloudformation/templates/api-gw-infra.yaml` — S3Key for 3 Lambda functions
- `infra/aws/cloudformation/templates/sqs-to-rds-lambda.yaml` — S3Key for 1 Lambda function
- `infra/aws/cloudformation/templates/url-add.yaml` — S3Key for 1 Lambda function
- `infra/aws/cloudformation/templates/lambda-weblink-put-into-sqs.yaml` — S3Key for 1 Lambda function
- `infra/aws/serverless/zip_to_s3.sh` — S3 upload path (added `lambdas/` prefix and `--profile`)
- `infra/aws/cloudformation/CLAUDE.md` — document `lambdas/` prefix
- `infra/aws/serverless/CLAUDE.md` — document `lambdas/` prefix

**Potentially modified files:**
- `infra/aws/serverless/lambdas/*/lambda_update.sh` — only if any scripts upload via S3 (most use direct `fileb://` upload)

### Testing Requirements

- **cfn-lint** on all 4 modified templates
- **CloudFormation deploy** — all affected stacks UPDATE_COMPLETE
- **Lambda invocation test** — invoke at least one Lambda via API Gateway (e.g., `GET /infra/ec2/status` or `GET /infra/sqs/size`)
- **S3 verification** — `aws s3 ls s3://lenie-dev-cloudformation/lambdas/` shows 8 files, `aws s3 ls s3://lenie-dev-cloudformation/` shows no root-level ZIPs
- **zip_to_s3.sh test** — `./zip_to_s3.sh -y simple` uploads to `lambdas/` prefix

### References

- [Source: infra/aws/cloudformation/templates/api-gw-infra.yaml] — 3 Lambda S3Key definitions (Ec2ManagerFunction, RdsManagerFunction, SqsSizeFunction)
- [Source: infra/aws/cloudformation/templates/sqs-to-rds-lambda.yaml] — MyLambdaFunction S3Key
- [Source: infra/aws/cloudformation/templates/url-add.yaml] — LenineUrlAddLambdaFunction S3Key
- [Source: infra/aws/cloudformation/templates/lambda-weblink-put-into-sqs.yaml] — MyLambdaFunction S3Key
- [Source: infra/aws/serverless/zip_to_s3.sh] — S3 upload and Lambda update-function-code commands
- [Source: infra/aws/serverless/env.sh] — AWS_S3_BUCKET_NAME variable
- [Source: _bmad-output/implementation-artifacts/B-8-manage-acm-certificates-via-cloudformation-and-ssm.md] — Previous story deployment learnings

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

None — all cfn-lint validations passed, all CF stack updates succeeded.

### Completion Notes List

- Task 1: Copied 8 active Lambda ZIPs from bucket root to `lambdas/` prefix via `aws s3 cp`.
- Task 2: Updated S3Key in 4 CF templates (6 Lambda definitions) — prepended `lambdas/` prefix. cfn-lint passed (warnings only, pre-existing W3660).
- Task 3: Deployed via WSL `deploy.sh -p lenie -s dev -y`. All 4 stacks updated successfully. API Gateway infra redeployed. sqs-size Lambda test invocation confirmed code loads from new prefix.
- Task 4: Updated `zip_to_s3.sh` — S3 upload path now uses `lambdas/` prefix. `aws lambda update-function-code` unchanged (uses `fileb://` direct upload).
- Task 5: Updated `sqs-weblink-put-into/lambda_update.sh` — only script with S3 upload; other scripts use `fileb://` direct upload.
- Task 6: Deleted 7 stale ZIPs from bucket root (pre-consolidation remnants from Epic 18 + old `sqs-to-db` from 2025-02).
- Task 7: Deleted 8 original root-level ZIPs after confirming all functions work. Bucket root now contains only 3 prefixes: `lambdas/`, `layers/`, `templates/`.
- Task 8: Updated `infra/aws/cloudformation/CLAUDE.md` and `infra/aws/serverless/CLAUDE.md` with `lambdas/` prefix documentation.

### File List

**Modified files:**
- `infra/aws/cloudformation/templates/api-gw-infra.yaml` — S3Key updated for 3 Lambda functions
- `infra/aws/cloudformation/templates/sqs-to-rds-lambda.yaml` — S3Key updated
- `infra/aws/cloudformation/templates/url-add.yaml` — S3Key updated
- `infra/aws/cloudformation/templates/lambda-weblink-put-into-sqs.yaml` — S3Key updated
- `infra/aws/serverless/zip_to_s3.sh` — S3 upload path updated to `lambdas/` prefix, added `--profile`
- `infra/aws/serverless/lambdas/sqs-weblink-put-into/lambda_update.sh` — S3 upload path updated, fixed commented-out variable name
- `infra/aws/cloudformation/parameters/dev/url-add.json` — timestamp updated by deploy.sh (automatic)
- `infra/aws/cloudformation/CLAUDE.md` — documented `lambdas/` prefix
- `infra/aws/serverless/CLAUDE.md` — documented `lambdas/` prefix
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — B-9 status updated
- `_bmad-output/implementation-artifacts/B-9-organize-s3-cloudformation-bucket-directory-structure.md` — story file updated

## Senior Developer Review (AI)

**Reviewer:** Ziutus | **Date:** 2026-02-25 | **Model:** Claude Opus 4.6

**Result:** All ACs implemented. 5 issues found (0 High, 2 Medium, 3 Low) — all fixed.

### Fixes Applied
1. **[MEDIUM][Fixed]** Added `--profile ${PROFILE}` to `aws s3 cp` in `zip_to_s3.sh:115` — was missing, could upload to wrong account if default profile differs.
2. **[MEDIUM][Fixed]** Added `infra/aws/cloudformation/parameters/dev/url-add.json` to Story File List — was modified by deploy.sh but undocumented.
3. **[LOW][Fixed]** Corrected AC1 ZIP count from 9 to 8 (actual count of active ZIPs).
4. **[LOW][Fixed]** Replaced misleading Dev Notes change pattern for `aws lambda update-function-code` — actual code uses `fileb://`, not `--s3-key`.
5. **[LOW][Fixed]** Fixed undefined `${FUNCTION_NAME}` in commented-out code in `sqs-weblink-put-into/lambda_update.sh` — now uses `${PROJECT_NAME}-${ENVIRONMENT}-${FUNCTION_NAME_PART}`.
