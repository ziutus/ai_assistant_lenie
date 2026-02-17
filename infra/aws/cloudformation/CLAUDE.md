# CloudFormation Deployment

## Directory Structure

```
cloudformation/
├── deploy.sh              # Deployment script
├── deploy.ini             # Configuration - template list per environment
├── templates/             # CloudFormation templates (YAML)
├── parameters/            # Parameters per environment
│   └── dev/               # Parameters for dev environment
├── apigw/                 # Exported API Gateway definitions (OpenAPI)
└── step_functions/        # Step Functions definitions (JSON)
```

## deploy.sh Script

Universal script for creating, updating, and deleting CloudFormation stacks.

### Required Tools

- `aws` (AWS CLI)
- `jq` (JSON processing)
- `sponge` (from `moreutils` package - Debian: `apt install moreutils`)

### Usage

```bash
./deploy.sh -p <PROJECT_CODE> -s <STAGE> [-r <REGION>] [-d] [-t]
```

| Flag  | Description | Default |
|-------|-------------|---------|
| `-p`  | Project code (e.g. `lenie`) | required |
| `-s`  | Environment (currently: `dev`; `prod`, `qa` post-MVP) | required |
| `-r`  | AWS region | `us-east-1` |
| `-d`  | Delete stacks (instead of create/update) | disabled |
| `-t`  | Change-set mode (preview changes before applying) | disabled |

### Examples

```bash
# Deploy dev environment (create/update)
./deploy.sh -p lenie -s dev

# Deploy with change preview (change-set)
./deploy.sh -p lenie -s dev -t

# Delete dev stacks
./deploy.sh -p lenie -s dev -d
```

### How the Script Works

1. Parses `deploy.ini` and collects templates from `[common]` and `[<STAGE>]` sections.
2. For each template, checks whether the stack already exists (`describe-stacks`).
3. Automatically selects the action: `create-stack` (new) or `update-stack` (existing).
4. If a parameter file exists at `parameters/<STAGE>/<template_name>.json`, it is included automatically.
5. If the parameters contain a `timestamp` field, it is updated to the current time.
6. In change-set mode (`-t`), the script creates a change-set and waits for user confirmation.
7. When deleting (`-d`), stacks are removed in reverse order.
8. For `prod`, templates from the `[common]` section are also processed.
9. After deploying `api-gw-app`, automatically creates a new API Gateway deployment to apply any RestApi Body changes (skipped in change-set mode).

### Stack Naming Convention

```
<PROJECT_CODE>-<STAGE>-<template_name>
```

Example: template `templates/vpc.yaml` in the `dev` environment of project `lenie` creates the stack `lenie-dev-vpc`.

## deploy.ini File

Configuration defining which templates are deployed per environment. INI format with per-environment sections.

- `[common]` - templates deployed once per region (used only for `prod`)
- `[dev]` - currently the only active environment (post-MVP: add `[prod]`, `[qa]`)
- Lines starting with `;` are commented out (template skipped)

Template order in the file matters - stacks are created in this order and deleted in reverse.

## Parameters

JSON files in `parameters/<STAGE>/` directory, named to match the template (e.g. `vpc.json` for `templates/vpc.yaml`).

Standard CloudFormation format:
```json
[
  { "ParameterKey": "ProjectName", "ParameterValue": "lenie" },
  { "ParameterKey": "Environment", "ParameterValue": "dev" }
]
```

Parameters can reference SSM Parameter Store (e.g. VPC ID, subnet ID) - values are resolved by CloudFormation.

## Templates Overview

### Networking and Base Infrastructure

| Template | Resources | Description |
|----------|-----------|-------------|
| `env-setup.yaml` | SSM Parameter | Runtime version configuration (python3.11) |
| `vpc.yaml` | VPC, 6 Subnets, IGW, Route Table, SSM | Multi-AZ network (public, private, DB subnets) |
| `1-domain-route53.yaml` | Route53 Hosted Zone | Domain `lenie-ai.eu` |
| `security-groups.yaml` | Security Group | SSH access from specific IPs |
| `secrets.yaml` | Secrets Manager | Database credentials (RDS username/password) |

### Database

| Template | Resources | Description |
|----------|-----------|-------------|
| `rds.yaml` | RDS (PostgreSQL), DB Subnet Group, SG | `db.t3.micro` instance, 20GB, snapshot restore support |
| `dynamodb-documents.yaml` | DynamoDB Table | Documents table with GSI (DateIndex), PITR for prod |

### Queues and Notifications

| Template | Resources | Description |
|----------|-----------|-------------|
| `sqs-documents.yaml` | SQS Queue, SSM Parameters | Document processing queue (14-day retention) |
| `sqs-application-errors.yaml` | SQS (DLQ), SNS Topic, Subscription | Dead Letter Queue with email notification |

### Storage

| Template | Resources | Description |
|----------|-----------|-------------|
| `s3.yaml` | S3 Bucket | Video transcription bucket (`lenie-{stage}-video-to-text`) |
| `s3-cloudformation.yaml` | S3 Bucket, SSM | Lambda code and CF artifacts bucket |
| `s3-website-content.yaml` | S3 Bucket, Bucket Policy, SSM | Website content storage (`lenie-{stage}-website-content`, AES256) |
| `s3-app-web.yaml` | S3 Bucket, Bucket Policy, SSM | Frontend hosting bucket (`lenie-{stage}-app-web`, CloudFront OAC) |
| `s3-helm.yaml` | S3 Bucket, Bucket Policy, CloudFront OAI | Helm chart repository bucket with OAI for CloudFront access |
| `cloudfront-helm.yaml` | CloudFront Distribution | CDN for Helm chart repository (`helm.{env}.lenie-ai.eu`) |

### Lambda Layers

| Template | Resources | Description |
|----------|-----------|-------------|
| `lambda-layer-lenie-all.yaml` | Lambda Layer, SSM | Shared library layer (pytubefix, urllib3, requests, beautifulsoup4) |
| `lambda-layer-openai.yaml` | Lambda Layer, SSM | OpenAI SDK layer |
| `lambda-layer-psycopg2.yaml` | Lambda Layer, SSM | PostgreSQL driver layer (psycopg2-binary) |

### Compute

| Template | Resources | Description |
|----------|-----------|-------------|
| `ec2-lenie.yaml` | EC2 (t4g.micro ARM64), EIP, SG, IAM | Instance with Elastic IP and SSM |
| `lenie-launch-template.yaml` | Launch Template | EC2 launch template |
| `lambda-rds-start.yaml` | Lambda, IAM Role | Function to start RDS |
| `lambda-weblink-put-into-sqs.yaml` | Lambda | Function to put web links into SQS |
| `sqs-to-rds-lambda.yaml` | Lambda, IAM Role | Transfer messages from SQS to RDS (VPC, layers) |
| `url-add.yaml` | Lambda, API GW, API Key, IAM, Logs | URL addition (standalone with its own API Gateway) |

### API Gateway

| Template | Resources | Description |
|----------|-----------|-------------|
| `api-gw-infra.yaml` | REST API, 7 Lambdas | Infrastructure management API (RDS start/stop, EC2, SQS) |
| `api-gw-app.yaml` | REST API, 2 Lambdas | Main application API (12 endpoints, x-api-key) |
| `api-gw-url-add.yaml` | REST API, API Key, Usage Plan | Chrome extension API (rate limiting) |

**`api-gw-app` stage configuration (manual, not in CloudFormation):**
The `v1` stage has the following settings configured directly in the AWS console — they are NOT managed by the CloudFormation template:
- CloudWatch logs: Error and info logs
- Detailed CloudWatch metrics: Active
- Data tracing: Active
- X-Ray tracing: Active

These settings will be lost if the stage is recreated. To codify them, add `MethodSettings` and `TracingEnabled` to the `ApiStage` resource in `api-gw-app.yaml`.

### Orchestration

| Template | Resources | Description |
|----------|-----------|-------------|
| `sqs-to-rds-step-function.yaml` | Step Functions, EventBridge, IAM, Logs | Workflow: SQS -> start DB -> process -> stop DB |

### CDN

| Template | Resources | Description |
|----------|-----------|-------------|
| `cloudfront-app.yaml` | CloudFront Distribution, OAC, SSM | CDN for frontend application (`app.{env}.lenie-ai.eu`) |

### Email

*(SES template `ses.yaml` removed during legacy resource cleanup. SES is no longer used by the application.)*

### Organization and Governance

| Template | Resources | Description |
|----------|-----------|-------------|
| `organization.yaml` | AWS Organization | Organization (FeatureSet: ALL) |
| `identityStore.yaml` | Identity Store Group, Membership | Developer group and user assignment |
| `scp-block-all.yaml` | SCP | Block all actions (for inactive accounts) |
| `scp-block-sso-creation.yaml` | SCP | Block SSO instance creation |
| `scp-only-allowed-reginos.yaml` | SCP | Restrict to regions: eu-west-1/2, eu-central-1, us-east-1 |

### Monitoring

| Template | Resources | Description |
|----------|-----------|-------------|
| `budget.yaml` | AWS Budget | $8/month budget with alerts at 50%, 80% (actual) and 100% (forecast) |

## Recommended Deployment Order (New Environment)

Stacks have dependencies between them. When creating a new environment from scratch, deploy templates in layer order as defined in `deploy.ini [dev]` section:

### Layer 1: Foundation
- `env-setup.yaml` - base configuration (SSM parameters)
- `budget.yaml` - cost alerts
- `1-domain-route53.yaml` - domain

### Layer 2: Networking
- `vpc.yaml` - VPC, subnets, IGW
- `security-groups.yaml` - SSH access rules

### Layer 3: Security
- `secrets.yaml` - database credentials (change the default password manually after creation)

### Layer 4: Storage
- `s3.yaml` - video transcription bucket
- `s3-cloudformation.yaml` - Lambda code and CF artifacts bucket
- `dynamodb-documents.yaml` - documents table
- `s3-website-content.yaml` - website content storage
- `s3-app-web.yaml` - frontend hosting bucket
- `sqs-documents.yaml` - document processing queue
- `sqs-application-errors.yaml` - DLQ with email notification
- `rds.yaml` - database (commented out; deployed separately, managed lifecycle via Step Functions)

### Layer 5: Compute
- `lambda-layer-lenie-all.yaml` - shared library layer
- `lambda-layer-openai.yaml` - OpenAI SDK layer
- `lambda-layer-psycopg2.yaml` - PostgreSQL driver layer
- `ec2-lenie.yaml` - application server
- `lenie-launch-template.yaml` - EC2 launch template
- `lambda-rds-start.yaml` - Lambda for DB start
- `lambda-weblink-put-into-sqs.yaml` - Lambda for SQS ingestion
- `sqs-to-rds-lambda.yaml` - SQS to RDS transfer Lambda
- `url-add.yaml` - URL addition Lambda with API Gateway

### Layer 6: API
- `api-gw-infra.yaml` - infrastructure management API
- `api-gw-app.yaml` - main application API
- `api-gw-url-add.yaml` - Chrome extension API

### Layer 7: Orchestration
- `sqs-to-rds-step-function.yaml` - SQS -> start DB -> process -> stop DB

### Layer 8: CDN
- `cloudfront-app.yaml` - CDN for frontend application
- `s3-helm.yaml` - Helm chart repository bucket
- `cloudfront-helm.yaml` - CDN for Helm charts

This order is reflected in the `deploy.ini` file under the `[dev]` section. Run `./deploy.sh -p lenie -s dev` to deploy all templates in order.

## Notes

- All stacks use `CAPABILITY_NAMED_IAM` (creating IAM resources with custom names).
- SSM Parameters (`AWS::SSM::Parameter`) are used to pass values between stacks (e.g. VPC ID, subnet ID).
- Lambdas use code from the S3 bucket (`s3-cloudformation`) - code must be uploaded before deploying Lambda templates.
- Step Function automatically starts and stops RDS to save costs.
