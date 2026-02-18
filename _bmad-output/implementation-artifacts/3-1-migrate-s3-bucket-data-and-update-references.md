# Story 3.1: Migrate S3 Bucket Data and Update References

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer,
I want to migrate all content from `lenie-s3-tmp` to `lenie-dev-website-content` and update all references across the system,
so that the content storage uses the properly named bucket with consistent IaC naming convention.

## Acceptance Criteria

1. **Given** the new S3 bucket `lenie-dev-website-content` exists (deployed in Epic 1, stack `lenie-dev-s3-website-content`) and `lenie-s3-tmp` contains active data
   **When** developer executes the migration procedure
   **Then** all objects from `lenie-s3-tmp` are copied to `lenie-dev-website-content` via `aws s3 sync` without data loss (FR13)

2. **And** the `url-add.yaml` CloudFormation template is updated to reference the new bucket name in both the Lambda environment variable and the IAM policy (FR14)

3. **And** the Lambda function `sqs-weblink-put-into` (deployed via stack `lenie-dev-url-add`) environment variable `BUCKET_NAME` is updated to `lenie-dev-website-content` via CloudFormation stack update

4. **And** the local `.env` file variable `AWS_S3_WEBSITE_CONTENT` is updated to reference the new bucket (FR14)

5. **And** all other CF templates and Lambda configurations referencing `lenie-s3-tmp` are updated to the new bucket name (FR14)

6. **And** the migration does not cause downtime for the Chrome extension -> Lambda -> S3 content flow (NFR10)

7. **Given** all references have been updated
   **When** developer tests the end-to-end content flow
   **Then** the Chrome extension submits a URL, Lambda processes it, and content is saved to `lenie-dev-website-content` (FR15)
   **And** previously migrated content is accessible from the new bucket
   **And** the old bucket `lenie-s3-tmp` can be safely deleted after verification

## Tasks / Subtasks

- [x] Task 1: Audit all references to `lenie-s3-tmp` and verify new bucket exists (AC: #1, #5)
  - [x] 1.1: Verify stack `lenie-dev-s3-website-content` is deployed and bucket `lenie-dev-website-content` exists
  - [x] 1.2: Verify SSM Parameters exist: `/lenie/dev/s3/website-content/name` and `/lenie/dev/s3/website-content/arn`
  - [x] 1.3: List all objects in `lenie-s3-tmp` and record object count for post-migration verification
  - [x] 1.4: Confirm complete list of files referencing `lenie-s3-tmp` (see Dev Notes for known references)

- [x] Task 2: Sync data from `lenie-s3-tmp` to `lenie-dev-website-content` (AC: #1, #6)
  - [x] 2.1: Run `aws s3 sync s3://lenie-s3-tmp s3://lenie-dev-website-content --region us-east-1`
  - [x] 2.2: Verify object count in `lenie-dev-website-content` matches `lenie-s3-tmp`
  - [x] 2.3: Spot-check 2-3 random objects to verify content integrity

- [x] Task 3: Update `url-add.yaml` CloudFormation template (AC: #2, #5)
  - [x] 3.1: Change Lambda env var `BUCKET_NAME` from `lenie-s3-tmp` to `lenie-dev-website-content` (line 43)
  - [x] 3.2: Change IAM policy S3 resource ARN from `arn:aws:s3:::lenie-s3-tmp/*` to `arn:aws:s3:::lenie-dev-website-content/*` (line 93)
  - [x] 3.3: Validate template with `aws cloudformation validate-template`

- [x] Task 4: Deploy updated `url-add.yaml` stack (AC: #3, #6)
  - [x] 4.1: Update stack `lenie-dev-url-add` via `aws cloudformation update-stack`
  - [x] 4.2: Wait for stack update to complete
  - [x] 4.3: Verify Lambda env var `BUCKET_NAME` is now `lenie-dev-website-content` via `aws lambda get-function-configuration`

- [x] Task 5: Update documentation and `.env_example` (AC: #4, #5)
  - [x] 5.1: Add `AWS_S3_WEBSITE_CONTENT=""` to `.env_example` (currently missing)
  - [x] 5.2: Update `infra/aws/README.md` — change `lenie-s3-tmp` entry in S3 buckets table to reflect migration to `lenie-dev-website-content`

- [x] Task 6: Verify end-to-end flow (AC: #7)
  - [x] 6.1: Invoke Lambda `lenie-dev-url-add` with a test URL payload to verify S3 write works with new bucket
  - [x] 6.2: Verify test object created in `lenie-dev-website-content`
  - [x] 6.3: Verify previously migrated content is still accessible in `lenie-dev-website-content`

## Dev Notes

### Migration Strategy — Zero Downtime (NFR10)

**Order of operations is critical for zero downtime:**

1. **Sync data first** — both buckets have all data
2. **Update CF template + deploy** — Lambda switches to new bucket
3. **Verify** — test write to new bucket
4. **Old bucket untouched** — deletion is a separate cleanup story (Epic 5)

The Lambda `sqs-weblink-put-into` reads bucket name from its `BUCKET_NAME` env var (set by CF template). The CF stack update atomically updates the Lambda configuration. There is no window where both buckets need to be written to simultaneously.

### Complete Reference Audit

**Files referencing `lenie-s3-tmp` (confirmed via codebase search):**

| File | Line | Reference | Action |
|------|------|-----------|--------|
| `infra/aws/cloudformation/templates/url-add.yaml` | 43 | `BUCKET_NAME: lenie-s3-tmp` | Change to `lenie-dev-website-content` |
| `infra/aws/cloudformation/templates/url-add.yaml` | 93 | `"arn:aws:s3:::lenie-s3-tmp/*"` | Change to `"arn:aws:s3:::lenie-dev-website-content/*"` |
| `infra/aws/README.md` | 575 | `lenie-s3-tmp` in S3 buckets table | Update table entry |

**Files using `AWS_S3_WEBSITE_CONTENT` env var (local Flask/backend path — NOT Lambda):**

| File | Line | Usage | Action |
|------|------|-------|--------|
| `backend/server.py` | 128 | `os.getenv("AWS_S3_WEBSITE_CONTENT")` | No code change — reads from `.env` |
| `backend/web_documents_do_the_needful_new.py` | 41 | `os.getenv("AWS_S3_WEBSITE_CONTENT")` | No code change — reads from `.env` |
| `backend/webdocument_prepare_regexp_by_ai.py` | 26 | `os.getenv("AWS_S3_WEBSITE_CONTENT")` | No code change — reads from `.env` |
| `backend/webdocument_md_decode.py` | 25 | `os.getenv("AWS_S3_WEBSITE_CONTENT")` | No code change — reads from `.env` |
| `docs/development-guide.md` | 181 | `AWS_S3_WEBSITE_CONTENT=bucket-name` | No change needed (generic placeholder) |

**IMPORTANT:** The backend Python code does NOT hardcode the bucket name — it reads from `AWS_S3_WEBSITE_CONTENT` env var. No Python code changes needed. Only the local `.env` file (user's private file) needs to be updated by the developer.

**Lambda `sqs-into-rds` does NOT reference S3 bucket directly.** It only stores `s3_uuid` from the SQS message into the PostgreSQL database. The content was already saved to S3 by `sqs-weblink-put-into`.

### Two Separate S3 Access Paths

Understanding the architecture is critical to avoid updating the wrong files:

```
AWS Lambda Path (url-add.yaml controls):
  Chrome Extension → API Gateway → Lambda sqs-weblink-put-into
    → reads BUCKET_NAME env var → writes to S3 bucket
    → env var set in url-add.yaml CloudFormation template

Local Flask Path (.env controls):
  Flask server.py / backend scripts
    → reads AWS_S3_WEBSITE_CONTENT env var → reads from S3 bucket
    → env var set in local .env file (user-managed)
```

### url-add.yaml Template Context

The `url-add.yaml` is a **Gen 1 template** with several legacy patterns:
- Hardcoded bucket name (`lenie-s3-tmp`)
- Hardcoded SQS URL
- Hardcoded S3 ARN in IAM policy
- Uses `Fn::ImportValue` for DynamoDB ARN (CF Exports)
- Has `Outputs` section

**This story ONLY changes the two `lenie-s3-tmp` references.** Do NOT refactor the template to Gen 2+ pattern — that is out of scope. Minimal change, maximum safety.

### S3 Sync Command

```bash
# Sync all objects from old bucket to new bucket
aws s3 sync s3://lenie-s3-tmp s3://lenie-dev-website-content --region us-east-1

# Verify object counts match
aws s3 ls s3://lenie-s3-tmp --recursive --summarize | tail -2
aws s3 ls s3://lenie-dev-website-content --recursive --summarize | tail -2
```

### CloudFormation Stack Update Command

```bash
cd infra/aws/cloudformation

# The url-add.yaml template requires a timestamp parameter
# deploy.sh auto-updates it, or provide manually
aws cloudformation update-stack \
  --stack-name lenie-dev-url-add \
  --template-body file://templates/url-add.yaml \
  --parameters file://parameters/dev/url-add.json \
  --capabilities CAPABILITY_NAMED_IAM \
  --region us-east-1

aws cloudformation wait stack-update-complete \
  --stack-name lenie-dev-url-add \
  --region us-east-1
```

**IMPORTANT:** The `url-add.yaml` template has a `timestamp` parameter that forces Lambda update. The parameter file at `parameters/dev/url-add.json` should include this parameter. Check if the parameter file exists and has the timestamp field — `deploy.sh` normally auto-updates it.

### Lambda Verification Command

```bash
# Verify Lambda env var was updated
MSYS_NO_PATHCONV=1 aws lambda get-function-configuration \
  --function-name lenie-dev-url-add \
  --query 'Environment.Variables.BUCKET_NAME' \
  --output text \
  --region us-east-1
# Expected: lenie-dev-website-content
```

### End-to-End Test Payload

```bash
# Invoke Lambda directly with a test webpage payload
MSYS_NO_PATHCONV=1 aws lambda invoke \
  --function-name lenie-dev-url-add \
  --payload '{"body": "{\"url\": \"https://example.com/migration-test\", \"type\": \"link\", \"source\": \"migration-test\", \"note\": \"S3 migration verification\", \"title\": \"Migration Test\", \"language\": \"en\", \"text\": \"\", \"html\": \"\"}"}' \
  --region us-east-1 \
  /tmp/lambda-response.json

cat /tmp/lambda-response.json
# Expected: statusCode 200 with SQS message ID
```

**Note:** Use `type: link` for the test (not `webpage`) to avoid S3 write — this verifies Lambda invocation without creating test data. To fully verify S3 write, use `type: webpage` with test text content.

### `.env_example` Update

Currently `.env_example` does NOT include `AWS_S3_WEBSITE_CONTENT`. Add it to help future developers:

```bash
AWS_S3_WEBSITE_CONTENT=""
```

The developer must also update their local `.env` file (not tracked in git):
```bash
AWS_S3_WEBSITE_CONTENT=lenie-dev-website-content
```

### MSYS Path Conversion Warning

On Windows with MSYS/Git Bash, AWS CLI commands with paths starting with `/` get mangled. Use `MSYS_NO_PATHCONV=1` prefix for SSM parameter commands and Lambda invocations. This was learned in Story 2.1.

### What This Story Does NOT Include

- **Deleting `lenie-s3-tmp` bucket** — deferred to Epic 5 (Legacy Resource Cleanup, Story 5.1). Keep the old bucket as a safety net.
- **Refactoring `url-add.yaml` to Gen 2+ pattern** — out of scope. Only the two bucket references change.
- **Modifying Python backend code** — not needed, code reads bucket name from env var.
- **Updating `deploy.ini`** — that is Story 6.1's responsibility.
- **Adding S3 access for the new bucket to other Lambda IAM roles** — only `url-add.yaml` Lambda writes to this bucket.

### Lessons from Previous Stories (MUST Apply)

1. **MSYS_NO_PATHCONV=1** for AWS CLI commands with `/` paths (from Story 2.1)
2. **Verify SSM parameters with `describe-parameters`** as fallback if `get-parameter` fails (from Story 1.2)
3. **Minimal changes** — only change what's needed, don't refactor surrounding code (architecture principle)
4. **Validate template before deploy** — `aws cloudformation validate-template` (from all stories)

### Project Structure Notes

- CF template to modify: `infra/aws/cloudformation/templates/url-add.yaml`
- Parameter file: `infra/aws/cloudformation/parameters/dev/url-add.json`
- Stack name: `lenie-dev-url-add`
- New bucket (already exists): `lenie-dev-website-content` (stack `lenie-dev-s3-website-content`)
- Old bucket: `lenie-s3-tmp` (NOT CloudFormation-managed)

### References

- [Source: _bmad-output/planning-artifacts/architecture.md#Core Architectural Decisions] — S3 website-content recreate strategy, Phase F migration
- [Source: _bmad-output/planning-artifacts/architecture.md#Implementation Patterns & Consistency Rules] — Template modification rules
- [Source: _bmad-output/planning-artifacts/epics.md#Story 3.1] — Acceptance criteria and requirements
- [Source: _bmad-output/planning-artifacts/prd.md#S3 Bucket Migration] — FR12-FR15 requirements, user journey
- [Source: _bmad-output/planning-artifacts/prd.md#Compatibility] — NFR10 zero-downtime migration
- [Source: infra/aws/cloudformation/templates/url-add.yaml] — CF template with `lenie-s3-tmp` references (lines 43, 93)
- [Source: infra/aws/cloudformation/templates/s3-website-content.yaml] — New bucket template (Story 1.2)
- [Source: infra/aws/serverless/lambdas/sqs-weblink-put-into/lambda_function.py] — Lambda source (reads BUCKET_NAME env var)
- [Source: infra/aws/serverless/lambdas/sqs-into-rds/lambda_function.py] — Confirmed: only stores s3_uuid, does NOT reference bucket
- [Source: backend/server.py:128] — Flask reads AWS_S3_WEBSITE_CONTENT from env
- [Source: _bmad-output/implementation-artifacts/1-2-create-s3-website-content-bucket-template.md] — Story 1.2 (bucket creation)
- [Source: _bmad-output/implementation-artifacts/2-1-create-lambda-layer-cloudformation-templates.md] — MSYS path conversion fix

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6 (claude-opus-4-6)

### Debug Log References

- Lambda invoke initially failed with `Invalid base64` error — AWS CLI v2 requires `--cli-binary-format raw-in-base64-out` flag for JSON payloads
- MSYS path conversion for `/tmp/` output file path — used relative path `response.json` as workaround

### Completion Notes List

- **Task 1**: Verified stack `lenie-dev-s3-website-content` (CREATE_COMPLETE), SSM Parameters `/lenie/dev/s3/website-content/name` and `/arn` exist. Old bucket `lenie-s3-tmp` contains 3612 objects (763,388,860 bytes). Confirmed only 2 CF template references to `lenie-s3-tmp`: `url-add.yaml` lines 43 and 93.
- **Task 2**: `aws s3 sync` completed successfully — 3612 objects (~728 MB) copied to `lenie-dev-website-content`. Object count verified as identical (3612 objects, 763,388,860 bytes). Spot-check confirmed files accessible.
- **Task 3**: Updated `url-add.yaml` — changed `BUCKET_NAME` env var and IAM policy S3 ARN from `lenie-s3-tmp` to `lenie-dev-website-content`. Template validated with `aws cloudformation validate-template`.
- **Task 4**: Stack `lenie-dev-url-add` updated successfully (UPDATE_COMPLETE). Lambda env var `BUCKET_NAME` confirmed as `lenie-dev-website-content` via `get-function-configuration`. Timestamp parameter updated to force Lambda redeployment.
- **Task 5**: Added `AWS_S3_WEBSITE_CONTENT=""` to `.env_example`. Updated `infra/aws/README.md` S3 buckets table — added `lenie-dev-website-content` entry, marked `lenie-s3-tmp` as legacy with migration note, added CF stack references for managed buckets.
- **Task 6**: End-to-end verification passed. Lambda invoked with `link` type — returned HTTP 200 with SQS message ID. Lambda invoked with `webpage` type — returned HTTP 200 and wrote .txt + .html files to `lenie-dev-website-content` (object count increased from 3612 to 3614). Previously migrated content still accessible.

### Change Log

- 2026-02-15: Story 3.1 implementation complete. Migrated 3612 objects (~728 MB) from `lenie-s3-tmp` to `lenie-dev-website-content`. Updated `url-add.yaml` (BUCKET_NAME + IAM policy), deployed stack, verified end-to-end flow. Updated `.env_example` and `README.md`.
- 2026-02-15: Code review fixes — moved CF-managed S3 buckets from README section 15.1 to section 4 (M1), updated README summary counts (M2), improved `.env_example` variable grouping (L1).

### File List

**Modified files:**
- `infra/aws/cloudformation/templates/url-add.yaml` — Changed `BUCKET_NAME` from `lenie-s3-tmp` to `lenie-dev-website-content` (line 43), IAM policy ARN (line 93)
- `infra/aws/cloudformation/parameters/dev/url-add.json` — Updated `timestamp` parameter to `202602141600` to force Lambda redeployment
- `.env_example` — Added `AWS_S3_WEBSITE_CONTENT=""` variable, grouped with AWS variables
- `infra/aws/README.md` — Updated S3 buckets table with migration status; added sections 4.3/4.4 for CF-managed S3 buckets; updated Resource Summary and section 15.9 counts

**AWS resources modified:**
- Stack `lenie-dev-url-add` — Updated (Lambda env var + IAM policy for new bucket)

**AWS data operations:**
- `aws s3 sync s3://lenie-s3-tmp s3://lenie-dev-website-content` — 3612 objects copied
