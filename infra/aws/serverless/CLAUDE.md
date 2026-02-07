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
│   ├── ses-with-excel/        # Send email with Excel attachment via SES
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
| `ses-with-excel` | Generates an Excel file (openpyxl), uploads to S3, sends via SES as email attachment. Env var: `S3_BUCKET_NAME` |
| `rds-reports` | Diagnostic script for listing RDS instances and their tags (can run locally) |

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

## Related Components

- **CloudFormation templates**: `cloudformation/templates/` - Lambda function and API Gateway infrastructure definitions
- **Backend library**: `backend/library/` - shared code bundled into `app-server-*` Lambdas
- **S3 bucket**: Lambda code is stored in the CloudFormation S3 bucket (created by `cloudformation/templates/s3-cloudformation.yaml`)
