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
| `-s`  | Environment: `dev`, `qa`, `prod`, `cob`, `test`, `feature`, `staging` | required |
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

### Stack Naming Convention

```
<PROJECT_CODE>-<STAGE>-<template_name>
```

Example: template `templates/vpc.yaml` in the `dev` environment of project `lenie` creates the stack `lenie-dev-vpc`.

## deploy.ini File

Configuration defining which templates are deployed per environment. INI format with per-environment sections.

- `[common]` - templates deployed once per region (used only for `prod`)
- `[dev]`, `[qa]`, `[prod]`, ... - templates per environment
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
| `api-gw-app.yaml` | REST API, 2 Lambdas | Main application API (13 endpoints, x-api-key) |
| `api-gw-url-add.yaml` | REST API, API Key, Usage Plan | Chrome extension API (rate limiting) |

### Orchestration

| Template | Resources | Description |
|----------|-----------|-------------|
| `sqs-to-rds-step-function.yaml` | Step Functions, EventBridge, IAM, Logs | Workflow: SQS -> start DB -> process -> stop DB |

### Email

| Template | Resources | Description |
|----------|-----------|-------------|
| `ses.yaml` | SES Identity, Lambda, Custom Resource | Email with DKIM, auto-update Route53 records |

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
| `budget.yaml` | AWS Budget | $20/month budget with alerts at 50%, 80% (actual) and 100% (forecast) |

## Recommended Deployment Order (New Environment)

Stacks have dependencies between them. When creating a new environment from scratch, follow this order:

1. `env-setup.yaml` - base configuration
2. `budget.yaml` - cost alerts
3. `1-domain-route53.yaml` - domain
4. `vpc.yaml` - network
5. `secrets.yaml` - credentials (change the default password manually after creation)
6. `sqs-application-errors.yaml` - DLQ
7. `s3-cloudformation.yaml` - Lambda artifacts bucket
8. `rds.yaml` - database (requires VPC, secrets)
9. `sqs-documents.yaml` - document queue
10. `lambda-rds-start.yaml` - Lambda for DB start
11. Remaining Lambdas and API Gateways
12. `sqs-to-rds-step-function.yaml` - orchestration (requires Lambda and SQS)

This order is reflected in the `deploy.ini` file under the `[dev]` section.

## Notes

- All stacks use `CAPABILITY_NAMED_IAM` (creating IAM resources with custom names).
- SSM Parameters (`AWS::SSM::Parameter`) are used to pass values between stacks (e.g. VPC ID, subnet ID).
- Lambdas use code from the S3 bucket (`s3-cloudformation`) - code must be uploaded before deploying Lambda templates.
- Step Function automatically starts and stops RDS to save costs.
