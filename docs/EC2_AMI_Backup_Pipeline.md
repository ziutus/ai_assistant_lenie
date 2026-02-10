# EC2 AMI Backup Pipeline (Shelved)

> **Status:** Archived (2026-02). VM-based distribution approach is no longer pursued.
>
> **Parent document:** [../README.md](../README.md) — project overview.
> See also: [VM_Setup.md](VM_Setup.md) — VM provisioning instructions.

## Overview

This pipeline was designed to automate AMI (Amazon Machine Image) backups for EC2 instances running Lenie as a Linux virtual machine connecting directly to the database. The idea was to distribute Lenie as a pre-configured VM image that could be deployed on EC2.

This approach has been **shelved** in favor of:
- **Containerized deployment** (Docker/Kubernetes) — see `infra/docker/` and `infra/kubernetes/`
- **Serverless deployment** (AWS Lambda) — see `infra/aws/serverless/`

## Pipeline Architecture

The pipeline consisted of 4 AWS Lambda functions that worked together:

```
createImageLambda → getImageStateLambda → copyImageLambda → setSsmParamLambda
     │                     │                     │                    │
     ▼                     ▼                     ▼                    ▼
Create AMI from      Poll until AMI        Copy AMI to DR       Store final AMI ID
tagged EC2 instance  state = "available"   region (encrypted)   in SSM Parameter Store
```

### Lambda Functions

| Function | Runtime | Purpose |
|----------|---------|---------|
| `createImageLambda` | python3.12 | Creates an AMI from an EC2 instance tagged for backup |
| `getImageStateLambda` | python3.12 | Polls AMI creation status until it becomes `available` |
| `copyImageLambda` | python3.12 | Copies the AMI to a disaster recovery region with encryption |
| `setSsmParamLambda` | python3.12 | Stores the final AMI ID in AWS SSM Parameter Store for reference |

All functions use only boto3 (no external dependencies).

## Restoring the Code

The Lambda source code is archived in a git tag:

```bash
git checkout archive/ec2-ami-backup-pipeline -- infra/aws/serverless/lambdas/ec2-ami-backup-pipeline/
```

This restores the 4 Python files:
- `createImageLambda.py`
- `getImageStateLambda.py`
- `copyImageLambda.py`
- `setSsmParamLambda.py`

See also: `infra/aws/serverless/CLAUDE.md` — archived functions table.

## Why This Approach Was Shelved

Running Lenie on a dedicated EC2 VM had several drawbacks compared to the current architecture:
- **Cost**: EC2 instances run 24/7 (or require start/stop automation), while Lambda scales to zero
- **Maintenance**: OS patching, security updates, and AMI lifecycle management
- **Deployment**: AMI-based deployments are slow compared to container image pushes or Lambda code updates
- **Scalability**: Single VM vs. auto-scaling containers or serverless functions

The current serverless architecture (Lambda + API Gateway + SQS + DynamoDB) and Docker/K8s options provide better cost efficiency, simpler deployments, and automatic scaling.
