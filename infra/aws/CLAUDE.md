# AWS Infrastructure

AWS infrastructure for Project Lenie. As a hobby project, three IaC approaches are used for comparison:
- **CloudFormation** - primary, manages the majority of resources
- **Terraform** - VPC + bastion host (subset for learning)
- **CDK** - not yet implemented

Cost optimization is a priority. DynamoDB is used for data that doesn't need complex queries (cache for new entries before they reach RDS, cross-environment metadata). RDS is started/stopped on demand via Step Functions and Lambda.

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
    ├── jenkins_start.py        # Start Jenkins EC2 + update Route53 DNS
    └── openvpn_own_start.py    # Start OpenVPN EC2 + update Route53 DNS
```

## Subdirectories

### cloudformation/
Primary IaC approach. Custom `deploy.sh` script manages stack lifecycle (create/update/delete) across environments. Covers 27 templates organized by layer: networking (VPC), database (RDS, DynamoDB), queues (SQS, SNS), storage (S3), compute (EC2, Lambda), API Gateway (3 APIs with 13+ endpoints), orchestration (Step Functions), email (SES), organization (SCPs, Identity Store), and monitoring (budgets). See `cloudformation/CLAUDE.md` for details.

### serverless/
Lambda function source code (14 functions) and Lambda layer build scripts (psycopg2, lenie_all, openai). Two function categories: simple infrastructure Lambdas (RDS/EC2/SQS management) and app Lambdas that bundle `backend/library/` for document processing and AI operations. Includes packaging scripts (`zip_to_s3.sh`, `create_empty_lambdas.sh`). See `serverless/CLAUDE.md` for details.

### eks/
EKS cluster configurations. Main cluster `lenie-ai` (K8s 1.31, spot instances, us-east-1) and a Karpenter POC cluster. Managed via `eksctl` with addons: EBS CSI Driver, Metrics Server, Stakater Reloader, AWS Load Balancer Controller. Includes automated deployment script for Karpenter setup. See `eks/CLAUDE.md` for details.

### terraform/
Terraform configuration (AWS provider ~> 5.0) covering VPC with 4 subnets (2 public + 2 private) and an EC2 bastion host module. Exists primarily for IaC comparison purposes. See `terraform/CLAUDE.md` for details.

### tools/
Python helper scripts for starting EC2 instances and updating Route53 DNS records. Both scripts follow the same pattern: start EC2 instance, wait for running state, get public IP, upsert Route53 A record. Configuration via `.env` file.

| Script | Purpose | Env vars |
|--------|---------|----------|
| `jenkins_start.py` | Start Jenkins server | `JENKINS_AWS_INSTANCE_ID`, `AWS_HOSTED_ZONE_ID`, `JENKINS_DOMAIN_NAME` |
| `openvpn_own_start.py` | Start OpenVPN server | `OPENVPN_OWN_AWS_INSTANCE_ID`, `AWS_HOSTED_ZONE_ID`, `OPENVPN_OWN_DOMAIN_NAME` |

## Environment Setup

`ubuntu_aws_cli_install.sh` installs required tools on WSL/Ubuntu:
- AWS CLI v2, Python 3, pip, jq, moreutils (sponge), mc
- Symlinks `~/.aws/` from Windows host (`/mnt/c/Users/ziutus/.aws/`)

## Key AWS Services Used

| Service | Purpose |
|---------|---------|
| VPC | Networking with public/private/DB subnets |
| RDS (PostgreSQL) | Primary document database with pgvector |
| DynamoDB | Document metadata cache, cross-env sync |
| SQS | Asynchronous document processing queue |
| SNS | Error notifications via email |
| S3 | Lambda code artifacts, video transcriptions, web content |
| Lambda | 14 functions for infra management and app logic |
| API Gateway | 3 REST APIs (app, infra management, Chrome extension) |
| Step Functions | SQS-to-RDS workflow with auto DB start/stop |
| SES | Transactional email with DKIM |
| EC2 | Application server, bastion host, Jenkins, OpenVPN |
| EKS | Kubernetes cluster (alternative deployment target) |
| Route53 | DNS for lenie-ai.eu domain |
| Secrets Manager | Database credentials |
| SSM Parameter Store | Cross-stack value sharing |
| CloudWatch | Logging, Step Function execution monitoring |
| Budgets | Cost alerts ($20/month threshold) |
| Organizations + SCPs | Multi-account governance, region restrictions |
