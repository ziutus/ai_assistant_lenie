# CloudFormation Deployment

## Directory Structure

```
cloudformation/
├── deploy.sh              # Deployment script
├── deploy.ini             # Configuration - template list per environment
├── templates/             # CloudFormation templates (YAML)
├── parameters/            # Parameters per environment
│   ├── dev/               # Parameters for dev environment
│   └── landing-prod/      # Parameters for landing page (production)
├── apigw/                 # Exported API Gateway definitions (OpenAPI)
└── step_functions/        # Step Functions definitions (JSON)
```

## deploy.sh Script

Universal script for creating, updating, and deleting CloudFormation stacks.

### Required Tools

- `aws` (AWS CLI)
- `jq` (JSON processing)

### Running from Claude Code

The script uses `file://` URIs with `$PWD` paths. Git Bash (MSYS) on Windows translates paths incorrectly (`/c/Users/...` instead of `/mnt/c/Users/...`), so the script **must be run via WSL**:

```bash
wsl bash -c "cd /mnt/c/Users/ziutus/git/_lenie-all/lenie-server-2025/infra/aws/cloudformation && ./deploy.sh -p lenie -s dev -y"
```

The `-y` flag skips the interactive confirmation prompt (required for non-interactive execution from Claude Code).

### Usage

```bash
./deploy.sh -p <PROJECT_CODE> -s <STAGE> [-r <REGION>] [-d] [-t] [-y]
```

| Flag  | Description | Default |
|-------|-------------|---------|
| `-p`  | Project code (e.g. `lenie`) | required |
| `-s`  | Environment (currently: `dev`; `prod`, `qa` post-MVP) | required |
| `-r`  | AWS region | `us-east-1` |
| `-d`  | Delete stacks (instead of create/update) | disabled |
| `-t`  | Change-set mode (preview changes before applying) | disabled |
| `-y`, `--yes` | Skip confirmation prompt (for automation/CI) | disabled |

### Examples

```bash
# Deploy dev environment (create/update)
./deploy.sh -p lenie -s dev

# Deploy landing page (production)
./deploy.sh -p lenie -s landing-prod

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
9. After deploying `api-gw-app` or `api-gw-infra`, automatically creates a new API Gateway deployment to apply any RestApi Body changes (skipped in change-set mode).

### Stack Naming Convention

```
<PROJECT_CODE>-<STAGE>-<template_name>
```

Example: template `templates/vpc.yaml` in the `dev` environment of project `lenie` creates the stack `lenie-dev-vpc`.

## deploy.ini File

Configuration defining which templates are deployed per environment. INI format with per-environment sections.

- `[common]` - account-wide resources deployed once (stacks named `lenie-all-<template>`): organization, SCPs
- `[dev]` - dev environment (stacks named `lenie-dev-<template>`)
- `[landing-prod]` - production landing page resources (stacks named `lenie-landing-prod-<template>`), deployed separately via `deploy.sh -s landing-prod`
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
| `1-domain-route53.yaml` | Route53 Hosted Zone | DISABLED — creates duplicate zone. Domain `lenie-ai.eu` hosted zone is managed by legacy stack `lenie-domain-route53-definition` (with SSM exports for all environments). |
| `security-groups.yaml` | Security Group | SSH access from specific IPs |
| `secrets.yaml` | Secrets Manager, SSM Parameter | Database credentials (auto-generated password, username in `GenerateSecretString`). Exports secret ARN to SSM at `/${ProjectCode}/${Environment}/rds/secret-arn` |

### Database

| Template | Resources | Description |
|----------|-----------|-------------|
| `rds.yaml` | RDS (PostgreSQL), DB Subnet Group, SG, SecretTargetAttachment | `db.t3.micro` instance, 20GB, snapshot restore support. `SecretTargetAttachment` links Secrets Manager secret to RDS instance (enables future auto-rotation). `RDSPasswordSecretArn` resolved from SSM |
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
| `s3-cloudformation.yaml` | S3 Bucket, SSM | Lambda code and CF artifacts bucket. Directory structure: `lambdas/` (Lambda ZIP packages), `layers/` (Lambda layers), `templates/` (exported API definitions) |
| `s3-website-content.yaml` | S3 Bucket, Bucket Policy, SSM | Website content storage (`lenie-{stage}-website-content`, AES256) |
| `s3-app-web.yaml` | S3 Bucket, Bucket Policy, SSM | Frontend hosting bucket (`lenie-{stage}-app-web`, CloudFront OAC) |
| `s3-app2-web.yaml` | S3 Bucket, Bucket Policy, SSM | Target multi-user UI hosting bucket (`lenie-{stage}-app2-web`, CloudFront OAC) |
| `s3-landing-web.yaml` | S3 Bucket, Bucket Policy, SSM | Landing page hosting bucket (`lenie-{stage}-landing-web`, CloudFront OAC). Deployed in `[landing-prod]` section — production resource. |
| `helm.yaml` | S3 Bucket, Bucket Policy, CloudFront OAI, CloudFront Distribution | Helm chart repository and CDN (`helm.{env}.lenie-ai.eu`). Certificate ARN resolved from SSM. |

### Lambda Layers

| Template | Resources | Description |
|----------|-----------|-------------|
| `lambda-layer-lenie-all.yaml` | Lambda Layer, SSM | Shared library layer (pytubefix, urllib3, requests, beautifulsoup4) |
| `lambda-layer-openai.yaml` | Lambda Layer, SSM | OpenAI SDK layer |
| `lambda-layer-psycopg2.yaml` | Lambda Layer, SSM | PostgreSQL driver layer (psycopg2-binary) |

### Compute

| Template | Resources | Description |
|----------|-----------|-------------|
| `ec2-lenie.yaml` | EC2 (t4g.micro ARM64), SG, IAM | Instance with dynamic public IP and SSM |
| `lenie-launch-template.yaml` | Launch Template | EC2 launch template |
| `lambda-rds-start.yaml` | Lambda, IAM Role | REDUNDANT — commented out in deploy.ini; rds-start Lambda is managed by api-gw-infra.yaml. Delete stack `lenie-dev-lambda-rds-start` manually. |
| `lambda-weblink-put-into-sqs.yaml` | Lambda | Function to put web links into SQS |
| `sqs-to-rds-lambda.yaml` | Lambda, IAM Role | Transfer messages from SQS to RDS (VPC, layers, `POSTGRESQL_SSLMODE: require`) |
| `url-add.yaml` | Lambda, IAM, Logs | URL addition Lambda function (API GW removed — `/url_add` endpoint served via `api-gw-app.yaml`) |

### API Gateway

| Template | Resources | Description |
|----------|-----------|-------------|
| `api-gw-infra.yaml` | REST API, 3 Lambdas, 3 IAM Roles, SSM | Infrastructure management API (7 endpoints: RDS start/stop/status, EC2/VPN start/stop/status, SQS size). 3 consolidated Lambdas: rds-manager, ec2-manager, sqs-size. Each Lambda has its own least-privilege IAM role with resource-level scoping (SQS scoped to project queues, RDS scoped to specific DB instance via SSM, EC2 start/stop scoped to specific instance). Paths without `/infra` prefix (routing via custom domain base path mapping). Exports API ID and invoke URL to SSM. |
| `api-gw-app.yaml` | REST API, Stage, Lambda Permissions, SSM | Main application API (11 endpoints, x-api-key). Separate `ApiStage` resource manages v1 stage settings (logging, tracing, metrics). References 3 Lambda functions: `${PC}-${Env}-app-server-db`, `${PC}-${Env}-app-server-internet`, `${PC}-${Env}-url-add`. All Lambda names fully parameterized. Exports API ID, root resource ID, and invoke URL to SSM. |
| `api-gw-custom-domain.yaml` | ACM Certificate, API GW DomainName, BasePathMappings, Route53, SSM | Custom domain `api.{env}.lenie-ai.eu` with TLS 1.2. Root path (`/`) maps to app API, `/infra` maps to infra API. DNS validation via Route53. |

**`api-gw-app` stage configuration (managed by CloudFormation):**
The `v1` stage is managed by a separate `ApiStage` resource (`AWS::ApiGateway::Stage`) in `api-gw-app.yaml`. Stage settings:
- `LoggingLevel: INFO` (error and info CloudWatch logs)
- `MetricsEnabled: true` (detailed CloudWatch metrics)
- `DataTraceEnabled: true` (full request/response body logging — review before enabling in production)
- `TracingEnabled: true` (X-Ray tracing)

These settings apply to all methods/resources via wildcard `MethodSettings` (`HttpMethod: '*'`, `ResourcePath: '/*'`). The `ApiDeployment` resource retains `StageName: v1` (CloudFormation does not support removing it from an existing resource). Note: CloudWatch logging requires an account-level IAM role (`cloudwatchRoleArn`) — verify with `aws apigateway get-account`.

**Note:** `api-gw-infra` does NOT currently have stage logging or tracing configured in its CloudFormation template.

### Orchestration

| Template | Resources | Description |
|----------|-----------|-------------|
| `sqs-to-rds-step-function.yaml` | Step Functions, EventBridge, IAM, Logs | Workflow: SQS -> start DB -> process -> stop DB. Map state has `Catch` with `States.ALL` to stop DB on Lambda failure (cost protection) |

### Certificates

| Template | Resources | Description |
|----------|-----------|-------------|
| `acm-certificates.yaml` | ACM Certificate, SSM Parameter | Wildcard certificate for CloudFront distributions (`*.{env}.lenie-ai.eu` for dev, `*.lenie-ai.eu` for prod). DNS validation via Route53. ARN exported to SSM at `/${ProjectCode}/${Environment}/acm/cloudfront/arn`. Deployed in `[dev]` Layer 8 before CloudFront stacks. |

### CDN

| Template | Resources | Description |
|----------|-----------|-------------|
| `cloudfront-app.yaml` | CloudFront Distribution, OAC, Route53 A-Record, SSM | CDN for frontend application (`app.{env}.lenie-ai.eu`) with SPA error responses (403/404 → index.html) and Route53 alias record. Certificate ARN resolved from SSM via `{{resolve:ssm:...}}` dynamic reference. |
| `cloudfront-app2.yaml` | CloudFront Distribution, OAC, Route53 A-Record, SSM | CDN for target multi-user UI (`app2.{env}.lenie-ai.eu`) with SPA error responses and Route53 alias record. Certificate ARN resolved from SSM. |
| `cloudfront-landing.yaml` | CloudFront Distribution, OAC, ACM Certificate, Route53 A-Record, SSM | CDN for landing page (`www.lenie-ai.eu`) with static 404 error page, Route53 alias record, and self-contained inline ACM certificate (DNS validation). Deployed in `[landing-prod]` section — production resource, not per-environment. |

### Email

*(SES template `ses.yaml` removed during legacy resource cleanup. SES is no longer used by the application.)*

### Organization and Governance (`[common]` section — stacks named `lenie-all-*`)

| Template | Resources | Description |
|----------|-----------|-------------|
| `organization.yaml` | AWS Organization | Organization (FeatureSet: ALL). Exports `organization-root-id` for use by SCP templates |
| `scp-block-sso-creation.yaml` | SCP | Block SSO instance creation. Auto-attached to organization root |
| `scp-only-allowed-reginos.yaml` | SCP | Restrict to regions: eu-west-1/2, eu-central-1, us-east-1. Auto-attached to organization root |

**PREREQUISITE for fresh account setup:** Before deploying SCP stacks, enable SCP policy type manually (one-time):
```bash
aws organizations enable-policy-type --root-id <ROOT_ID> --policy-type SERVICE_CONTROL_POLICY
```
CloudFormation does not support enabling policy types.

**Removed templates:**
- `identityStore.yaml` — template exists but not deployed (Identity Store `d-9067dcf0bd` no longer exists)
- `scp-block-all.yaml` — available for inactive accounts, not deployed by default

### Monitoring

| Template | Resources | Description |
|----------|-----------|-------------|
| `budget.yaml` | AWS Budget | $8/month budget with alerts at 50%, 80% (actual) and 100% (forecast) |

## Recommended Deployment Order (New Environment)

Stacks have dependencies between them. When creating a new environment from scratch, deploy templates in layer order as defined in `deploy.ini [dev]` section:

### Layer 0: Account-wide (`[common]`, stacks `lenie-all-*`)
- `organization.yaml` - AWS Organization (prerequisite: enable SCP policy type manually)
- `scp-block-sso-creation.yaml` - Block SSO creation (auto-attached to root)
- `scp-only-allowed-reginos.yaml` - Region restrictions (auto-attached to root)

### Layer 1: Foundation
- `env-setup.yaml` - base configuration (SSM parameters)
- `budget.yaml` - cost alerts
- ~~`1-domain-route53.yaml`~~ - DISABLED (duplicate zone; managed by legacy stack `lenie-domain-route53-definition`)

### Layer 2: Networking
- `vpc.yaml` - VPC, subnets, IGW
- `security-groups.yaml` - SSH access rules

### Layer 3: Security
- `secrets.yaml` - database credentials (password auto-generated via `GenerateSecretString`, secret ARN exported to SSM)

### Layer 4: Storage
- `s3.yaml` - video transcription bucket
- `s3-cloudformation.yaml` - Lambda code and CF artifacts bucket
- `dynamodb-documents.yaml` - documents table
- `s3-website-content.yaml` - website content storage
- `s3-app-web.yaml` - frontend hosting bucket
- `s3-app2-web.yaml` - target multi-user UI hosting bucket
- `sqs-documents.yaml` - document processing queue
- `sqs-application-errors.yaml` - DLQ with email notification
- `rds.yaml` - database (commented out; deployed separately, managed lifecycle via Step Functions)

### Layer 5: Compute
- `lambda-layer-lenie-all.yaml` - shared library layer
- `lambda-layer-openai.yaml` - OpenAI SDK layer
- `lambda-layer-psycopg2.yaml` - PostgreSQL driver layer
- `ec2-lenie.yaml` - application server
- `lenie-launch-template.yaml` - EC2 launch template
- ~~`lambda-rds-start.yaml`~~ - REDUNDANT, commented out (rds-start Lambda managed by api-gw-infra.yaml)
- `lambda-weblink-put-into-sqs.yaml` - Lambda for SQS ingestion
- `sqs-to-rds-lambda.yaml` - SQS to RDS transfer Lambda
- `url-add.yaml` - URL addition Lambda (no API Gateway — served via `api-gw-app.yaml`)

### Layer 6: API
- `api-gw-infra.yaml` - infrastructure management API (7 endpoints, SSM exports)
- `api-gw-app.yaml` - main application API (11 endpoints including /url_add)
- `api-gw-custom-domain.yaml` - custom domain `api.{env}.lenie-ai.eu` with base path mappings (root → app API, `/infra` → infra API)

### Layer 7: Orchestration
- `sqs-to-rds-step-function.yaml` - SQS -> start DB -> process -> stop DB

### Layer 8: Certificates & CDN
- `acm-certificates.yaml` - wildcard certificate for dev CloudFront distributions (SSM export)
- `cloudfront-app.yaml` - CDN for frontend application (`app.{env}.lenie-ai.eu`, cert from SSM)
- `cloudfront-app2.yaml` - CDN for target multi-user UI (`app2.{env}.lenie-ai.eu`, cert from SSM)
- `helm.yaml` - Helm chart repository and CDN (cert from SSM)

This order is reflected in the `deploy.ini` file under the `[dev]` section. Run `./deploy.sh -p lenie -s dev` to deploy all templates in order.

### Landing Page (`[landing-prod]`, stacks `lenie-landing-prod-*`)
- `s3-landing-web.yaml` - landing page hosting bucket (`lenie-prod-landing-web`)
- `cloudfront-landing.yaml` - CDN for landing page (`www.lenie-ai.eu`) with self-contained inline ACM certificate

The landing page is a production resource, not per-environment. Deploy separately via `./deploy.sh -p lenie -s landing-prod`.

## Notes

- All stacks use `CAPABILITY_NAMED_IAM` (creating IAM resources with custom names).
- SSM Parameters (`AWS::SSM::Parameter`) are used to pass values between stacks (e.g. VPC ID, subnet ID).
- Lambdas use code from the S3 bucket (`s3-cloudformation`) under the `lambdas/` prefix (e.g., `s3://lenie-dev-cloudformation/lambdas/lenie-dev-sqs-size.zip`). Code must be uploaded before deploying Lambda templates.
- Step Function automatically starts and stops RDS to save costs.
