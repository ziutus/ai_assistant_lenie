# Serverless (AWS Lambda)

Source code for Lambda functions and Lambda layers, along with scripts for packaging, deploying, and managing them.

## Directory Structure

```
serverless/
├── env.sh                     # Environment config (current AWS account)
├── env_lenie_2025.sh          # Environment config (closed AWS account, kept for reference only)
├── zip_to_s3.sh               # Package and deploy Lambda code to S3 + update function
├── function_list_cf.txt       # Functions deployed via CloudFormation (simple)
├── function_list_cf_app.txt   # Functions deployed via CloudFormation (app - include backend/library)
├── tmp/                       # Temporary build artifacts (zip files)
├── lambdas/                   # Lambda function source code
│   ├── rds-manager/           # RDS instance management (start/stop/status) — consolidated from rds-start, rds-stop, rds-status
│   ├── ec2-manager/           # EC2 instance management (start/stop/status) — consolidated from ec2-start, ec2-stop, ec2-status
│   ├── sqs-size/              # Get SQS queue message count
│   ├── sqs-into-rds/          # Process SQS messages into RDS (document ingestion)
│   ├── sqs-weblink-put-into/  # Put web links into SQS queue
│   ├── app-server-db/         # Main app Lambda - DB operations (uses backend/library)
│   ├── app-server-internet/   # Main app Lambda - internet operations (uses backend/library)
│   └── tmp/                   # Empty Lambda placeholder
└── lambda_layers/             # Lambda layer build scripts
    ├── layer_create_psycop2_new.sh  # psycopg2-binary layer
    ├── layer_create_lenie_all.sh    # Application dependencies layer
    ├── layer_openai_2.sh            # OpenAI SDK layer
    └── tmp/                         # Layer build artifacts
```

## Environment Configuration

Two environment files exist, one per AWS account:

| File | AWS Account | Profile | S3 Bucket Pattern | Status |
|------|------------|---------|-------------------|--------|
| `env.sh` | `<AWS_ACCOUNT_ID_PROD>` | `default` | `lenie-dev-cloudformation` | **active — current production** |
| `env_lenie_2025.sh` | `<AWS_ACCOUNT_ID_LEGACY>` | `lenie-ai-2025-admin` | `lenie-2025-dev-cloudformation` | **closed 2026-07-02** (was an earlier, abandoned environment — never became the production target despite the name; fully decommissioned and closed via `organizations close-account`, 90-day grace period until permanent deletion) |

Common variables:
- `PYTHON_VERSION=3.11` - Lambda runtime version
- `PLATFORM=manylinux2014_x86_64` - pip platform for binary packages
- `PROJECT_NAME=lenie`, `ENVIRONMENT=dev`

**Important**: Scripts source `env.sh` by default — this is correct, `env.sh` points to the active account. `env_lenie_2025.sh` should no longer be sourced; it targets a closed account and is kept only for historical reference.

## Lambda Functions

### Two categories

**Simple functions** (`function_list_cf.txt`): standalone Lambdas with no dependency on `backend/library`. Packaged as a single `lambda_function.py` zip file.

**App functions** (`function_list_cf_app.txt`): Lambdas that include the full `backend/library` directory in the zip package. These contain the core application logic.

### Function Details

#### Infrastructure Management (simple)

| Function | Env Vars | Description |
|----------|----------|-------------|
| `sqs-size` | SSM: `/lenie/dev/sqs_queue/new_links` | Get approximate message count in SQS queue |

`rds-manager` and `ec2-manager` (RDS + OpenVPN start/stop/status) were removed from `api-gw-infra.yaml` and deleted from AWS on 2026-07-02 — RDS was decommissioned (unused since ~2026-04). The source directories `lambdas/rds-manager/` and `lambdas/ec2-manager/` are now dead code, kept only for reference; not part of `function_list_cf.txt` anymore.

#### Document Processing (simple)

| Function | Description |
|----------|-------------|
| `sqs-weblink-put-into` | Receives URL data via API Gateway, stores text/HTML in S3, saves metadata to DynamoDB, sends message to SQS. Env vars: `AWS_QUEUE_URL_ADD`, `BUCKET_NAME`, `DYNAMODB_TABLE_NAME` |

#### Application Server (app - includes backend/library)

| Function | Endpoints | Description |
|----------|-----------|-------------|
| `app-server-db` | `/website_list`, `/website_get`, `/website_save`, `/website_delete`, `/website_is_paid`, `/website_get_next_to_correct`, `/website_similar`, `/website_split_for_embedding` | DB-facing operations. Requires PostgreSQL env vars, `OPENAI_*`, `EMBEDDING_MODEL`, `BACKEND_TYPE`. **⚠ RDS was decommissioned 2026-07-02 — this function's PostgreSQL connection no longer resolves. All endpoints in this row currently fail when called through the "AWS Serverless" frontend mode. Not yet fixed; needs a decision (point at DynamoDB instead, or retire the AWS Serverless document-browsing path entirely in favor of Docker/NAS mode).** |
| `app-server-internet` | `/website_download_text_content`, `/ai_embedding_get` | Internet-facing operations (downloads, AI calls, embeddings). Requires `OPENAI_*`, `AI_MODEL_SUMMARY`, `EMBEDDING_MODEL`. Not affected — no RDS dependency. |

*(`sqs-into-rds` — read SQS, wrote to RDS — removed 2026-07-02 along with the `lenie-dev-sqs-to-rds-lambda` CloudFormation stack.)*

Both app functions use path-based routing (`event['path']`) via API Gateway proxy integration.

#### IAM Permissions for Non-CF-Managed Lambdas

`app-server-db` and `app-server-internet` are **not managed by CloudFormation** — their IAM roles are created manually. When using `SECRETS_BACKEND=aws` (config_loader reads from SSM Parameter Store), the execution role must include:

```json
{
  "Effect": "Allow",
  "Action": [
    "ssm:GetParametersByPath",
    "ssm:GetParameter"
  ],
  "Resource": "arn:aws:ssm:<region>:<account-id>:parameter/lenie/<env>/*"
}
```

Replace `<region>`, `<account-id>`, and `<env>` with actual values (e.g., `eu-central-1`, `<AWS_ACCOUNT_ID_PROD>`, `dev`).

Without this permission, `load_config()` will fail at Lambda cold start when `SECRETS_BACKEND=aws` is set.

### Archived Functions

| Function | Archived | Git Tag | Description |
|----------|----------|---------|-------------|
| `ses-with-excel` | 2026-02 | `archive/ses-with-excel` | Generated Excel (openpyxl), uploaded to S3, sent via SES. Prototype with hardcoded test data. Restore: `git checkout archive/ses-with-excel -- infra/aws/serverless/lambdas/ses-with-excel/` |
| `jenkins-job-start` | 2026-02 | `archive/jenkins-job-start` | Triggered Jenkins job via HTTP API with CSRF crumb auth. Jenkins not in use. Restore: `git checkout archive/jenkins-job-start -- infra/aws/serverless/lambdas/jenkins-job-start/` |
| `jenkins-start-job` | 2026-02 | `archive/jenkins-start-job` | AWS Lambda `jenkins-start-job`. Newer variant of `jenkins-job-start` with added branch parameter and event logging. Runtime: python3.13, bundled requests library. Downloaded from AWS (code not previously in repo). Restore: `git checkout archive/jenkins-start-job -- infra/aws/serverless/lambdas/jenkins-start-job/` |
| `infra-allow-ip-in-security-group` | 2026-02 | `archive/infra-allow-ip-in-security-group` | AWS Lambda `infra-allow-ip-in-secrutity-group` (note: typo in original AWS name). Adds caller's IP to a hardcoded Security Group (sg-0929bfcae31074fb8) on RDP port 3389. Uses AWS Lambda Powertools. Runtime: python3.12. Downloaded from AWS (code not previously in repo). Lambda deleted from AWS (Story 10.3, 2026-02). Restore: `git checkout archive/infra-allow-ip-in-security-group -- infra/aws/serverless/lambdas/infra-allow-ip-in-security-group/` |
| `jenkins-start-run-job` (Step Function) | 2026-02 | `archive/jenkins-start-run-job` | Step Function `jenkins-start-run-job`. Starts EC2 Jenkins instance, waits 60s, invokes `jenkins-start-job` Lambda. JSONata query language, STANDARD type. Jenkins no longer in use. Definition saved in `cloudformation/step_functions/jenkins_start_run_job.json`. Restore: `git checkout archive/jenkins-start-run-job -- infra/aws/cloudformation/step_functions/jenkins_start_run_job.json` |
| `ec2-ami-backup-pipeline` (4 Lambdas) | 2026-02 | `archive/ec2-ami-backup-pipeline` | AMI backup pipeline for EC2-based Lenie distribution. 4 functions: `createImageLambda` (create AMI from tagged EC2), `getImageStateLambda` (poll AMI status), `copyImageLambda` (copy AMI to DR region, encrypted), `setSsmParamLambda` (store AMI ID in SSM). All python3.12, no external deps. Approach shelved — VM-based distribution (Linux VM connecting to database) is no longer pursued. Downloaded from AWS (code not previously in repo). Restore: `git checkout archive/ec2-ami-backup-pipeline -- infra/aws/serverless/lambdas/ec2-ami-backup-pipeline/` |
| `ses-excel-summary` | 2026-02 | `archive/ses-excel-summary` | AWS Lambda `lenie_ses_excel_summary`. Generated Excel report (openpyxl), uploaded to S3 (`lenie-dev-excel-reports`), sent as email attachment via SES. Prototype with hardcoded test data and email addresses. Runtime: python3.11, bundled openpyxl 3.1.5. Downloaded from AWS (code not previously in repo). Restore: `git checkout archive/ses-excel-summary -- infra/aws/serverless/lambdas/ses-excel-summary/` |
| `git-webhooks` | 2026-02 | `archive/git-webhooks` | AWS Lambda `git-webhooks`. Received Git webhook events (via API Gateway), extracted branch name from `ref` field, and triggered the `jenkins-start-run-job` Step Function. Runtime: python3.13. Jenkins CI pipeline no longer in use. Downloaded from AWS (code not previously in repo). Restore: `git checkout archive/git-webhooks -- infra/aws/serverless/lambdas/git-webhooks/` |
| `ses-s3-send-email` | 2026-02 | `archive/ses-s3-send-email` | AWS Lambda `ses_s3_send_email`. Generic email sender: downloads attachment from S3, sends HTML email with attachment via SES using `send_raw_email`. Event-driven (expects `nadawca`, `odbiorca`, `temat`, `tresc_html`, `s3_bucket`, `s3_object_key`). Runtime: python3.13, no external deps. Downloaded from AWS (code not previously in repo). Restore: `git checkout archive/ses-s3-send-email -- infra/aws/serverless/lambdas/ses-s3-send-email/` |

## Lambda Layers

Three layers provide shared dependencies to Lambda functions:

| Layer | Script | Packages | Used By |
|-------|--------|----------|---------|
| `psycopg2_new_layer` | `layer_create_psycop2_new.sh` | `psycopg2-binary` | `sqs-into-rds`, `app-server-db` |
| `lenie_all_layer` | `layer_create_lenie_all.sh` | `urllib3`, `requests`, `beautifulsoup4`, `python-dotenv` | `app-server-db`, `app-server-internet`, `sqs-into-rds` |
| `lenie_openai` | `layer_openai_2.sh` | `openai` | `app-server-internet` |

Layer build process:
1. Source `env.sh` for Python version and platform
2. `pip install` with `--platform manylinux2014_x86_64 --only-binary=:all:` into a `python/` directory
3. Zip the `python/` directory
4. Publish via `aws lambda publish-layer-version`

## Known Limitations

### Lambda Layer Size Limit (50 MB zipped / 250 MB unzipped)

**`pytubefix` cannot be included in Lambda layers.** The `pytubefix` package depends on `nodejs-wheel-binaries` (~60 MB Node.js binary), which alone exceeds the 50 MB Lambda layer ZIP limit. This was discovered when the `lenie_all_layer` ZIP grew to 66 MB after switching from the deprecated `pytube` to `pytubefix`.

**Impact:** YouTube video metadata extraction and download (`stalker_youtube_file.py`, `youtube_processing.py`) is **not available** in any Lambda function. Currently these modules are only used by batch scripts and the Flask server (Docker/K8s), so existing Lambda endpoints are unaffected.

**Future architecture decision required:** If YouTube processing is ever needed in the serverless path (e.g., triggered by SQS or API Gateway), Lambda alone cannot support it. Possible alternatives:
- **ECS Fargate task** — on-demand container with full `pytubefix` available, triggered by Step Functions or EventBridge
- **ECS Fargate service** — long-running container for YouTube processing workloads
- **Step Functions + ECS task** — orchestrate: receive request via Lambda → start ECS task for YouTube processing → Lambda writes results to DB
- **Lambda with container image** (up to 10 GB) — package `pytubefix` in a Docker image deployed as Lambda, avoids layer limit but increases cold start time

This is a **blocking architectural constraint** for any serverless YouTube processing feature. A decision must be made before implementing such functionality.

### No NAT Gateway — VPC Lambda Cannot Access External APIs

Lambda functions running inside VPC (e.g., `app-server-db`, `sqs-to-rds-lambda`) cannot access AWS APIs (SSM, Secrets Manager, S3) or the internet without a NAT Gateway (~$30/month) or VPC Endpoints (~$7-22/month). This exceeds the $8/month budget.

**Impact:** VPC Lambdas must use `SECRETS_BACKEND=env` (Lambda environment variables) rather than `SECRETS_BACKEND=aws` (SSM Parameter Store) for configuration.

## Deployment Scripts

### zip_to_s3.sh

Packages Lambda code and deploys it. Two modes:

```bash
# Simple functions (single lambda_function.py)
./zip_to_s3.sh simple

# App functions (lambda_function.py + backend/library)
./zip_to_s3.sh app
```

Process:
1. For each function in the list file, copies source from `lambdas/<function>/`
2. For `app` type, also copies `backend/library/` into the package
3. Creates a zip file named `<project>-<env>-<function>.zip`
4. Uploads to S3 bucket under `lambdas/` prefix (e.g., `s3://<bucket>/lambdas/<project>-<env>-<function>.zip`)
5. Updates Lambda function code via `aws lambda update-function-code`

### Per-function lambda_update.sh

Each Lambda directory contains a `lambda_update.sh` script for quick individual deployment:

```bash
cd lambdas/sqs-size/
./lambda_update.sh
```

This zips just the `lambda_function.py` and updates the function directly.

## Flask Server vs Lambda Split

### Why Two Lambdas?

The Flask backend (`backend/server.py`) is the unified server used in Docker and Kubernetes deployments. In AWS serverless, the endpoints are split into two Lambda functions due to **VPC networking constraints**:

- **`app-server-db`** runs **inside VPC** to access RDS (PostgreSQL). It cannot make outbound internet calls because there is **no NAT Gateway** (cost optimization for a hobby project). **RDS was decommissioned 2026-07-02 — this Lambda's PostgreSQL connection currently fails; not yet re-pointed at another store.**
- **`app-server-internet`** runs **outside VPC** with internet access for downloading web pages, calling LLM APIs (OpenAI), and computing embeddings.

The `/url_add` endpoint from `server.py` is replaced in AWS by the `sqs-weblink-put-into` Lambda, which stores data in S3 + DynamoDB and sends a message to SQS. That message previously got processed by `sqs-into-rds` to sync into RDS; that consumer was removed with RDS (2026-07-02), so messages now just expire unread after 14 days. Documents uploaded from mobile devices (phone, tablet) still land immediately in DynamoDB and S3, and are synced to the local PostgreSQL database via `imports/dynamodb_sync.py` — this remains the actual working sync path.

### Endpoint Mapping: server.py vs Lambdas

| `server.py` endpoint | Lambda | Notes |
|---|---|---|
| `/` (GET) | - | Info endpoint, server.py only |
| `/url_add` (POST) | `sqs-weblink-put-into` | Different architecture: S3+DynamoDB+SQS instead of direct DB write |
| `/website_list` (GET) | `app-server-db` | Lambda does not return `all_results_count` |
| `/website_is_paid` (POST) | `app-server-db` | Functionally equivalent |
| `/website_get` (GET) | `app-server-db` | Functionally equivalent |
| `/website_get_next_to_correct` (GET) | `app-server-db` | Lambda accepts extra params: `document_type`, `document_state` |
| `/website_similar` (POST) | `app-server-db` | Lambda receives pre-computed embeddings; server.py computes them internally |
| `/website_split_for_embedding` (POST) | `app-server-db` | Functionally equivalent |
| `/website_delete` (GET) | `app-server-db` | Functionally equivalent |
| `/website_save` (POST) | `app-server-db` | Functionally equivalent |
| `/ai_get_embedding` (POST) | `app-server-internet` | **Different endpoint name in Lambda: `/ai_embedding_get`** |
| `/website_download_text_content` (POST) | `app-server-internet` | Functionally equivalent |
| `/website_text_remove_not_needed` (POST) | - | server.py only, not implemented in Lambda |
| `/healthz`, `/startup`, `/readiness`, `/liveness` (GET) | - | Kubernetes health probes, not needed in Lambda |
| `/version` (GET) | - | server.py only |
| `/metrics` (GET) | - | Prometheus metrics stub, server.py only |

### Known Differences Between Implementations

1. **Endpoint naming inconsistency**: `/ai_get_embedding` (server.py) vs `/ai_embedding_get` (Lambda Internet)
2. **`/website_similar` flow**: In server.py, embeddings are computed server-side. In Lambda, the frontend must call `/ai_embedding_get` first (Lambda Internet) and then pass the result to `/website_similar` (Lambda DB) — because one Lambda cannot do both DB access and internet calls.
3. **`/website_list` response**: server.py returns `all_results_count` field; Lambda does not
4. **`/website_get_next_to_correct`**: Lambda version accepts `document_type` and `document_state` filter params; server.py only accepts `id`
5. **Authentication**: server.py validates `x-api-key` header via `before_request` hook; Lambda functions rely on API Gateway for auth (API key or IAM)
6. **`/website_text_remove_not_needed`**: Missing from Lambda — text cleaning is not available in serverless deployment

## Related Components

- **CloudFormation templates**: `cloudformation/templates/` - Lambda function and API Gateway infrastructure definitions
- **Backend library**: `backend/library/` - shared code bundled into `app-server-*` Lambdas
- **S3 bucket**: Lambda code is stored in the CloudFormation S3 bucket under the `lambdas/` prefix (created by `cloudformation/templates/s3-cloudformation.yaml`). Bucket structure: `lambdas/` (Lambda ZIP packages), `layers/` (Lambda layer ZIPs), `templates/` (exported API definitions)
