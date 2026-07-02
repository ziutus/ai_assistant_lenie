# AWS Infrastructure

AWS infrastructure for Project Lenie. As a hobby project, three IaC approaches are used for comparison:
- **CloudFormation** - primary, manages the majority of resources
- **Terraform** - VPC + bastion host (subset for learning)
- **CDK** - not yet implemented

Cost optimization is a priority. DynamoDB is used for data that doesn't need complex queries — the metadata buffer for new entries, and the source for cross-environment synchronization (`imports/dynamodb_sync.py` pulls into local Postgres). RDS (PostgreSQL) was decommissioned 2026-07-02: it sat idle since ~2026-04 (only DynamoDB was actually being used for document metadata), so the instance, its start/stop Step Function, the OpenVPN bastion used to reach it, and the RDS-password secret were all removed. A final snapshot (`lenie-dev-final-snapshot-20260702`) was kept as a safety net.

## Architecture Design Principles

### API Gateway as Security Boundary

AWS API Gateway is the entry point to the cloud solution. As a fully managed service, it handles TLS termination, request throttling, and DDoS protection — reducing the operational burden of securing internet-facing endpoints. Access is secured via API keys, which allows focusing on application development rather than maintaining and patching exposed services.

### Scalable Asynchronous Ingestion via SQS

Individual document uploads can be several hundred KB to 1 MB (full webpage content including HTML/JavaScript), and SQS decouples ingestion from processing. **Note:** the original SQS→RDS batch-processing consumer was removed along with RDS (2026-07-02); `sqs-weblink-put-into` still enqueues a message after writing to DynamoDB, but nothing currently consumes the queue — messages simply expire after the 14-day retention window. Follow-up: either wire up a new consumer or stop enqueueing.

### DynamoDB for Cloud-Local Synchronization

DynamoDB serves as a persistent, always-available store for document metadata. Data sent from mobile devices (phone, tablet) via the Chrome extension lands in DynamoDB immediately. This enables the local database to be synchronized with cloud data at any time via `imports/dynamodb_sync.py` — the cloud acts as a continuously available buffer that the local environment pulls from. This is now the sole cloud→local sync path (RDS is decommissioned).

### Cost Optimization

No NAT Gateway (saves ~$30/month), DynamoDB PAY_PER_REQUEST billing, budget alerts at $8/month. RDS (and its Step Functions start/stop automation) was removed entirely 2026-07-02 rather than kept as a stop/start-on-demand resource, since it had gone unused for months.

### Lambda Serverless Constraints

Lambda layers have a **50 MB zipped / 250 MB unzipped** size limit. This prevents including packages with large binary dependencies (e.g., `pytubefix` with its `nodejs-wheel-binaries` ~60 MB dependency). YouTube video processing is therefore **not available** in Lambda functions — only in Docker/K8s deployments and batch scripts.

VPC-attached Lambdas cannot access AWS APIs or the internet without NAT Gateway (~$30/month) or VPC Endpoints (~$7-22/month), both exceeding the $8/month budget. VPC Lambdas must use Lambda environment variables for configuration instead of SSM Parameter Store.

**Architectural decision pending:** If YouTube processing is ever needed in the serverless path, an alternative compute model must be chosen (ECS Fargate task, Lambda container image, or hybrid Step Functions orchestration). See `serverless/CLAUDE.md` "Known Limitations" for detailed options.

See [README.md](README.md) for a detailed inventory of all AWS resources (CloudFormation stacks, Lambda functions, API Gateway endpoints, parameters, and architecture diagram).

## Directory Structure

```
aws/
├── CLAUDE.md
├── ubuntu_aws_cli_install.sh   # WSL/Ubuntu setup script for AWS CLI and tools
├── cloudformation/             # CloudFormation templates and deployment scripts
│   └── CLAUDE.md
├── eks/                        # EKS cluster configurations (eksctl + Karpenter)
│   └── CLAUDE.md
├── serverless/                 # Lambda function source code, layers, and deploy scripts
│   └── CLAUDE.md
├── terraform/                  # Terraform configuration (VPC + bastion)
│   └── CLAUDE.md
└── tools/                      # Operational helper scripts
    └── aws_ec2_route53.py      # Start EC2 instance + update Route53 DNS (CLI tool)
```

## Subdirectories

### cloudformation/
Primary IaC approach. Custom `deploy.sh` script manages stack lifecycle (create/update/delete) across environments. Templates organized by layer: networking (VPC), database (DynamoDB — RDS decommissioned 2026-07-02), queues (SQS, SNS), storage (S3), compute (EC2, Lambda), API Gateway (2 REST APIs: app 11 + infra 1 endpoint, custom domain with base path mappings), CDN (CloudFront for app, app2, landing page), organization (SCPs, Identity Store), and monitoring (budgets). See `cloudformation/CLAUDE.md` for details and `docs/infrastructure-metrics.md` for authoritative counts.

### serverless/
Lambda function source code and Lambda layer build scripts (psycopg2, lenie_all, openai). 3 deployed Lambda functions remain (`url-add`, `sqs-weblink-put-into`, `sqs-size` — all CF-managed). The app-server-db/internet document-serving Lambdas (formerly non-CF-managed) were deleted 2026-07-02; their sources and sanitized config snapshots stay in the repo for restoration. Includes packaging script (`zip_to_s3.sh`). See `serverless/CLAUDE.md` for details and [docs/aws-serverless-restoration.md](../../docs/aws-serverless-restoration.md) for the restoration guide.

### eks/
EKS cluster configurations. Main cluster `lenie-ai` (K8s 1.31, spot instances, us-east-1) and a Karpenter POC cluster. Managed via `eksctl` with addons: EBS CSI Driver, Metrics Server, Stakater Reloader, AWS Load Balancer Controller. Includes automated deployment script for Karpenter setup. See `eks/CLAUDE.md` for details.

### terraform/
Terraform configuration (AWS provider ~> 5.0) covering VPC with 4 subnets (2 public + 2 private) and an EC2 bastion host module. Exists primarily for IaC comparison purposes. See `terraform/CLAUDE.md` for details.

### tools/
Single CLI script `aws_ec2_route53.py` that starts an EC2 instance, waits for it to be running, retrieves its public IP, and upserts a Route53 A record. Accepts `--instance-id`, `--hosted-zone-id`, `--domain-name` arguments (with env var fallback). Its Makefile target (`aws-start-openvpn`) was removed 2026-07-02 along with the OpenVPN instance it targeted (RDS decommissioned, so the bastion had no remaining purpose); the script itself is generic and could still be reused for other instances.

Jenkins target (`aws-start-jenkins`) was removed since Jenkins is not currently in use. See `docs/CICD/Jenkins.md` for restoration instructions.

## Environment Setup

`ubuntu_aws_cli_install.sh` installs required tools on WSL/Ubuntu:
- AWS CLI v2, Python 3, pip, jq, moreutils (sponge), mc
- Symlinks `~/.aws/` from Windows host (`/mnt/c/Users/ziutus/.aws/`)

## Key AWS Services Used

| Service | Purpose |
|---------|---------|
| VPC | Only the AWS default VPC remains — the empty CF-managed VPC (`lenie-dev-vpc`) and its SSH security-groups stack were deleted 2026-07-02 |
| DynamoDB | Document metadata store, cross-env sync (now the sole cloud document store — RDS decommissioned 2026-07-02) |
| SQS | Document processing queue — currently has no consumer since the RDS pipeline was removed (see "Scalable Asynchronous Ingestion via SQS" above) |
| SNS | Error notifications via email |
| S3 | Lambda code artifacts, video transcriptions, web content |
| Lambda | 3 functions: `url-add` (Chrome extension ingestion), `sqs-weblink-put-into`, `sqs-size`. The app-server-db/internet document-serving Lambdas were deleted 2026-07-02 — see [docs/aws-serverless-restoration.md](../../docs/aws-serverless-restoration.md) |
| API Gateway | 2 REST APIs (app: 1 endpoint — `/url_add`; infra: 1 endpoint — `/sqs/size`) + custom domain `api.{env}.lenie-ai.eu` with base path mappings |
| EC2 | None running — the orphaned `ec2-lenie` stack was deleted 2026-07-02; only the (unused) launch template stack remains |
| EKS | Kubernetes cluster (alternative deployment target) |
| Route53 | DNS for lenie-ai.eu domain |
| SSM Parameter Store | Cross-stack value sharing |
| CloudWatch | Logging, Step Function execution monitoring |
| Budgets | Cost alerts ($8/month threshold) |
| Organizations + SCPs | Multi-account governance, region restrictions |
| CloudFront | CDN for the landing page (`www.lenie-ai.eu`) only — app/app2 hosting deleted 2026-07-02 |

## Frontend Hosting

Only the landing page is hosted via S3 + CloudFront:
- **Landing page** (`web_landing_page/`, Next.js static export) — `www.lenie-ai.eu` via `s3-landing-web` + `cloudfront-landing` stacks

The React app (`app.dev.lenie-ai.eu`) and admin panel (`app2.dev.lenie-ai.eu`) hosting stacks were **deleted 2026-07-02** — they required the AWS document API (`app-server-db`), which was decommissioned. Both frontends now run only against the Docker/NAS backend. Restoration: [docs/aws-serverless-restoration.md](../../docs/aws-serverless-restoration.md).

### Historical Context

The React frontend was originally deployed via a **GitLab CI pipeline** that synced built static files to S3 and invalidated a CloudFront distribution. This was later replaced by AWS Amplify (now removed), then migrated back to S3 + CloudFront. The archived pipeline is in `infra/archive/gitlab-ci-frontend.yml`.
