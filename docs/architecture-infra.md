# Architecture — Infrastructure

> Generated: 2026-02-13 | Part: infra | Type: Multi-cloud IaC

## Architecture Pattern

**Multi-cloud Infrastructure as Code** supporting three deployment targets: Docker (local), AWS (serverless), Kubernetes (GKE).

## Deployment Targets

### 1. Docker Compose (Local Development)

3-service stack defined in `infra/docker/compose.yaml`:

| Service | Image | Port | Description |
|---------|-------|------|-------------|
| lenie-ai-server | Built from `backend/Dockerfile` | 5000 | Flask REST API |
| lenie-ai-db | Custom PostgreSQL 17 + pgvector | 5433 | Database |
| lenie-ai-fronted | Built from `web_interface_react/Dockerfile` | 3000 | React frontend |

PostgreSQL uses custom Dockerfile (`infra/docker/Postgresql/Dockerfile`) based on `postgres:17-bookworm` with `postgresql-17-pgvector` installed.

### 2. AWS Serverless

API Gateway serves as managed entry point with API key authentication.

**Infrastructure (29 CloudFormation templates):**

| Category | Templates | Key Resources |
|----------|-----------|---------------|
| Networking | vpc, security-groups | VPC (6 subnets), IGW, Route Tables |
| Database | rds, dynamodb-documents | PostgreSQL (db.t3.micro), DynamoDB (PAY_PER_REQUEST) |
| Queues | sqs-documents, sqs-application-errors | Document processing queue (14-day retention), DLQ with SNS alerts |
| Storage | s3, s3-cloudformation, s3-helm | Video transcriptions, Lambda code, Helm charts |
| Compute | ec2-lenie, lambda-rds-start, lambda-weblink-put-into, sqs-to-rds-lambda | EC2 (t4g.micro ARM64), Lambda functions |
| API | api-gw-infra, api-gw-app, api-gw-url-add | 3 API Gateways (infra, app, chrome extension) |
| DNS | 1-domain-route53 | lenie-ai.eu hosted zone |
| Email | ses | SES with DKIM |
| Orchestration | sqs-to-rds-step-function | Workflow: SQS → start DB → process → stop DB |
| Governance | organization, identityStore, scp-*, budget | AWS Organization, SCPs, $8/month budget |

**Lambda Functions (12):**

| Function | Purpose | VPC |
|----------|---------|-----|
| app-server-db | DB endpoints (8 routes) | Inside VPC |
| app-server-internet | Internet endpoints (4 routes) | Outside VPC |
| sqs-weblink-put-into | URL ingestion (S3 + DynamoDB + SQS) | No |
| sqs-into-rds | SQS → PostgreSQL processing | Inside VPC |
| rds-start/stop/status | RDS lifecycle management | No |
| ec2-start/stop/status | EC2 lifecycle management | No |
| sqs-size | Queue monitoring | No |

**Lambda Layers:**
- psycopg2_new_layer (PostgreSQL driver)
- lenie_all_layer (requests, beautifulsoup4, urllib3)
- lenie_openai (OpenAI SDK)

**Data Flow (Serverless):**
```
Browser Extension → API Gateway → Lambda (sqs-weblink-put-into)
  → S3 (text/HTML) + DynamoDB (metadata) + SQS (message)
Step Function → Lambda (rds-start) → Lambda (sqs-into-rds) → Lambda (rds-stop)
React Frontend → API Gateway → Lambda (app-server-db or app-server-internet)
```

**Step Function `sqs-to-rds` — Manual Execution:**

The Step Function runs automatically via EventBridge Schedule (daily at 5:00 AM Warsaw time). To run it manually:

```bash
MSYS_NO_PATHCONV=1 aws stepfunctions start-execution \
  --state-machine-arn "arn:aws:states:us-east-1:008971653395:stateMachine:lenie-dev-sqs-to-rds" \
  --input '{"QueueUrl":"https://sqs.us-east-1.amazonaws.com/008971653395/lenie_websites","DbInstanceIdentifier":"lenie-dev","StopDatabase":"yes"}' \
  --region us-east-1
```

| Parameter | Description | Value |
|-----------|-------------|-------|
| `QueueUrl` | SQS queue URL with documents to process | SSM: `/lenie/dev/sqs/documents/url` |
| `DbInstanceIdentifier` | RDS instance identifier | SSM: `/lenie/dev/database/name` |
| `StopDatabase` | Stop RDS after processing (`yes`/`no`) | `yes` for cost savings, `no` to keep DB running |

### 3. Kubernetes (GKE)

Kustomize-based deployment with base + overlays:

**Base Resources:**
- Namespace: `lenie-ai-dev`
- Database: StatefulSet (PostgreSQL + pgvector, 1Gi/2Gi memory)
- Server: Deployment (Flask, health probes, pod security)
- Client: Deployment (React frontend)

**GKE Dev Overlay:** Secrets, ConfigMaps, Ingress, service patches

**Helm Chart (v0.2.14):** Alternative deployment with templates for deployment, service, ingress, configmap, secrets, HPA.

### 4. Google Cloud

Terraform configuration for:
- Cloud Run jobs (ebook conversion)
- DNS configuration
- Docker repository (Artifact Registry)
- Storage buckets

## CI/CD Pipelines

| Tool | Config | Purpose |
|------|--------|---------|
| CircleCI | `.circleci/config.yml` | EC2-based testing |
| GitLab CI | `.gitlab-ci.yml` | Qodana security scanning |
| Jenkins | `Jenkinsfile` | AWS EC2 orchestration, Semgrep security |

## Build Automation (Makefile)

Naming convention: `aws-*` (AWS), `gcloud-*` (GCloud), no prefix (local).

Key targets: `build`, `dev`, `down`, `install`, `lint`, `security`, `docker-release`, `aws-start-openvpn`

## Cost Optimization Decisions

- **No NAT Gateway**: Lambda split into VPC (DB) and public (internet) functions
- **RDS on-demand**: Database starts/stops via Lambda + Step Function (runs only when needed)
- **DynamoDB PAY_PER_REQUEST**: No provisioned capacity charges
- **t4g.micro (ARM64)**: Cost-effective EC2 instance
- **Budget alert**: $8/month with 50%, 80%, 100% thresholds
