# Serverless (AWS Lambda)

Source code for Lambda functions and Lambda layers, along with scripts for packaging, deploying, and managing them.

## Directory Structure

```
serverless/
├── env.sh                     # Environment config (old AWS account)
├── env_lenie_2025.sh          # Environment config (current AWS account)
├── create_empty_lambdas.sh    # Create placeholder Lambda functions in AWS
├── zip_to_s3.sh               # Package and deploy Lambda code to S3 + update function
├── function_list.txt          # Legacy function list (manual Lambda management)
├── function_list_cf.txt       # Functions deployed via CloudFormation (simple)
├── function_list_cf_app.txt   # Functions deployed via CloudFormation (app - include backend/library)
├── tmp/                       # Temporary build artifacts (zip files)
├── lambdas/                   # Lambda function source code
│   ├── rds-start/             # Start RDS instance
│   ├── rds-stop/              # Stop RDS instance
│   ├── rds-status/            # Check RDS instance status
│   ├── rds-reports/           # RDS reporting/diagnostics
│   ├── ec2-start/             # Start EC2 instance
│   ├── ec2-stop/              # Stop EC2 instance
│   ├── ec2-status/            # Check EC2 instance status
│   ├── sqs-size/              # Get SQS queue message count
│   ├── sqs-into-rds/          # Process SQS messages into RDS (document ingestion)
│   ├── sqs-weblink-put-into/  # Put web links into SQS queue
│   ├── app-server-db/         # Main app Lambda - DB operations (uses backend/library)
│   ├── app-server-internet/   # Main app Lambda - internet operations (uses backend/library)
│   ├── jenkins-job-start/     # Trigger Jenkins job via API
│   └── tmp/                   # Empty Lambda placeholder
└── lambda_layers/             # Lambda layer build scripts
    ├── layer_create_psycop2_new.sh  # psycopg2-binary layer
    ├── layer_create_lenie_all.sh    # Application dependencies layer
    ├── layer_openai_2.sh            # OpenAI SDK layer
    └── tmp/                         # Layer build artifacts
```

## Environment Configuration

Two environment files exist for different AWS accounts:

| File | AWS Account | Profile | S3 Bucket Pattern |
|------|------------|---------|-------------------|
| `env.sh` | `008971653395` | `default` | `lenie-dev-cloudformation` |
| `env_lenie_2025.sh` | `049706517731` | `lenie-ai-2025-admin` | `lenie-2025-dev-cloudformation` |

Common variables:
- `PYTHON_VERSION=3.11` - Lambda runtime version
- `PLATFORM=manylinux2014_x86_64` - pip platform for binary packages
- `PROJECT_NAME=lenie`, `ENVIRONMENT=dev`

**Important**: Scripts source `env.sh` by default. To use the current account, either update `env.sh` or change the source line in scripts to `env_lenie_2025.sh`.

## Lambda Functions

### Two categories

**Simple functions** (`function_list_cf.txt`): standalone Lambdas with no dependency on `backend/library`. Packaged as a single `lambda_function.py` zip file.

**App functions** (`function_list_cf_app.txt`): Lambdas that include the full `backend/library` directory in the zip package. These contain the core application logic.

### Function Details

#### Infrastructure Management (simple)

| Function | Env Vars | Description |
|----------|----------|-------------|
| `rds-start` | `DB_ID` | Start an RDS instance |
| `rds-stop` | `DB_ID` | Stop an RDS instance |
| `rds-status` | `DB_ID` | Check RDS instance status (available/stopped/etc.) |
| `ec2-start` | `INSTANCE_ID` | Start an EC2 instance |
| `ec2-stop` | `INSTANCE_ID` | Stop an EC2 instance |
| `ec2-status` | `INSTANCE_ID` | Check EC2 instance state |
| `sqs-size` | SSM: `/lenie/dev/sqs_queue/new_links` | Get approximate message count in SQS queue |

#### Document Processing (simple)

| Function | Description |
|----------|-------------|
| `sqs-into-rds` | Reads SQS message, creates `StalkerWebDocumentDB`, saves document to PostgreSQL. Uses `backend/library` via Lambda layer. |
| `sqs-weblink-put-into` | Receives URL data via API Gateway, stores text/HTML in S3, saves metadata to DynamoDB, sends message to SQS. Env vars: `AWS_QUEUE_URL_ADD`, `BUCKET_NAME`, `DYNAMODB_TABLE_NAME` |

#### Application Server (app - includes backend/library)

| Function | Endpoints | Description |
|----------|-----------|-------------|
| `app-server-db` | `/website_list`, `/website_get`, `/website_save`, `/website_delete`, `/website_is_paid`, `/website_get_next_to_correct`, `/website_similar`, `/website_split_for_embedding` | DB-facing operations. Requires PostgreSQL env vars, `OPENAI_*`, `EMBEDDING_MODEL`, `BACKEND_TYPE`. |
| `app-server-internet` | `/translate`, `/website_download_text_content`, `/ai_embedding_get`, `/ai_ask` | Internet-facing operations (downloads, AI calls, embeddings). Requires `OPENAI_*`, `AI_MODEL_SUMMARY`, `EMBEDDING_MODEL`. |

Both app functions use path-based routing (`event['path']`) via API Gateway proxy integration.

#### Utility (simple)

| Function | Description |
|----------|-------------|
| `jenkins-job-start` | Triggers a Jenkins job via HTTP API with CSRF crumb authentication. Env vars: `JENKINS_URL`, `JENKINS_USER`, `JENKINS_PASSWORD`, `JENKINS_JOB_NAME` |
| `rds-reports` | Diagnostic script for listing RDS instances and their tags (can run locally) |

### Archived Functions

| Function | Archived | Git Tag | Description |
|----------|----------|---------|-------------|
| `ses-with-excel` | 2026-02 | `archive/ses-with-excel` | Generated Excel (openpyxl), uploaded to S3, sent via SES. Prototype with hardcoded test data. Restore: `git checkout archive/ses-with-excel -- infra/aws/serverless/lambdas/ses-with-excel/` |

## Lambda Layers

Three layers provide shared dependencies to Lambda functions:

| Layer | Script | Packages | Used By |
|-------|--------|----------|---------|
| `psycopg2_new_layer` | `layer_create_psycop2_new.sh` | `psycopg2-binary` | `sqs-into-rds`, `app-server-db` |
| `lenie_all_layer` | `layer_create_lenie_all.sh` | `pytube`, `urllib3`, `requests`, `beautifulsoup4` | `app-server-db`, `app-server-internet` |
| `lenie_openai` | `layer_openai_2.sh` | `openai` | `app-server-internet` |

Layer build process:
1. Source `env.sh` for Python version and platform
2. `pip install` with `--platform manylinux2014_x86_64 --only-binary=:all:` into a `python/` directory
3. Zip the `python/` directory
4. Publish via `aws lambda publish-layer-version`

## Deployment Scripts

### create_empty_lambdas.sh

Creates placeholder Lambda functions in AWS for functions listed in `function_list.txt`. Checks if each function already exists and skips if so.

```bash
./create_empty_lambdas.sh
```

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
4. Uploads to S3 bucket
5. Updates Lambda function code via `aws lambda update-function-code`

### Per-function lambda_update.sh

Each Lambda directory contains a `lambda_update.sh` script for quick individual deployment:

```bash
cd lambdas/rds-start/
./lambda_update.sh
```

This zips just the `lambda_function.py` and updates the function directly.

## Flask Server vs Lambda Split

### Why Two Lambdas?

The Flask backend (`backend/server.py`) is the unified server used in Docker and Kubernetes deployments. In AWS serverless, the endpoints are split into two Lambda functions due to **VPC networking constraints**:

- **`app-server-db`** runs **inside VPC** to access RDS (PostgreSQL). It cannot make outbound internet calls because there is **no NAT Gateway** (cost optimization for a hobby project).
- **`app-server-internet`** runs **outside VPC** with internet access for downloading web pages, calling LLM APIs (OpenAI), and computing embeddings.

The `/url_add` endpoint from `server.py` is replaced in AWS by the `sqs-weblink-put-into` Lambda, which stores data in S3 + DynamoDB and sends a message to SQS (processed later by `sqs-into-rds` when RDS is available).

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
| `/ai_ask` (POST) | `app-server-internet` | Lambda ignores `model` from request, always uses `llm_simple_jobs_model` env var |
| `/website_text_remove_not_needed` (POST) | - | server.py only, not implemented in Lambda |
| - | `app-server-internet` `/translate` | Lambda only, not implemented in server.py |
| `/healthz`, `/startup`, `/readiness`, `/liveness` (GET) | - | Kubernetes health probes, not needed in Lambda |
| `/version` (GET) | - | server.py only |
| `/metrics` (GET) | - | Prometheus metrics stub, server.py only |

### Known Differences Between Implementations

1. **Endpoint naming inconsistency**: `/ai_get_embedding` (server.py) vs `/ai_embedding_get` (Lambda Internet)
2. **`/ai_ask` model handling**: server.py uses `model` from the request body; Lambda always uses `llm_simple_jobs_model` from env vars
3. **`/website_similar` flow**: In server.py, embeddings are computed server-side. In Lambda, the frontend must call `/ai_embedding_get` first (Lambda Internet) and then pass the result to `/website_similar` (Lambda DB) — because one Lambda cannot do both DB access and internet calls.
4. **`/website_list` response**: server.py returns `all_results_count` field; Lambda does not
5. **`/website_get_next_to_correct`**: Lambda version accepts `document_type` and `document_state` filter params; server.py only accepts `id`
6. **Authentication**: server.py validates `x-api-key` header via `before_request` hook; Lambda functions rely on API Gateway for auth (API key or IAM)
7. **`/website_text_remove_not_needed`**: Missing from Lambda — text cleaning is not available in serverless deployment
8. **`/translate`**: Missing from server.py — translation is only available in AWS Lambda (uses AWS Translate or similar)

## Related Components

- **CloudFormation templates**: `cloudformation/templates/` - Lambda function and API Gateway infrastructure definitions
- **Backend library**: `backend/library/` - shared code bundled into `app-server-*` Lambdas
- **S3 bucket**: Lambda code is stored in the CloudFormation S3 bucket (created by `cloudformation/templates/s3-cloudformation.yaml`)
