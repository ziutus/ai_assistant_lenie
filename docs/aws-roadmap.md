# AWS Infrastructure Roadmap

> Plan rozwoju infrastruktury AWS w Project Lenie. Dokument zbiorczy — łączy informacje z [backlog-reference.md](backlog-reference.md), [aws-sync-backlog.md](aws-sync-backlog.md), [technology-choices.md](technology-choices.md) i [architecture-decisions.md](architecture-decisions.md).
>
> **Last updated:** 2026-03-31

## Current State

### What works (production — application account)

- **29 CloudFormation templates** managing: VPC, RDS PostgreSQL, DynamoDB, SQS, S3, 11 Lambda functions, 2 API Gateways, Step Functions, CloudFront, ACM, budgets
- **API Gateway** as secure entry point (API keys, no NAT Gateway)
- **DynamoDB + SQS** as always-available buffer for incoming documents (mobile → cloud → local sync)
- **$8/month budget target** with SCPs and budget alerts
- **Deploy script**: `infra/aws/cloudformation/deploy.sh` (universal create/update/delete)

### What's on hold

- **Lambda/API Gateway deployment** — not actively deployed. Changes are developed locally (NAS/Docker) and tracked in [aws-sync-backlog.md](aws-sync-backlog.md)
- **CI/CD** — all pipelines inactive, configuration files remain in repo

### What's active (local)

- **NAS (QNAP)**: PostgreSQL (port 5434), Flask backend (port 5055), Vault (port 8210)
- **Docker Compose**: local development stack (PostgreSQL + Flask + React)

## Phase 1: Prerequisites (before AWS can be restored)

| ID | Task | Status | Notes |
|----|------|--------|-------|
| [B-68](backlog-reference.md) | Upgrade Python Lambda runtime to 3.12+ | backlog | Python 3.11 EOL: Oct 2027. SSM parameter makes this straightforward |
| [B-75](backlog-reference.md) | Standardize Node.js to 24 LTS | backlog | Docker already on 24, update docs/CI |
| — | Apply [aws-sync-backlog.md](aws-sync-backlog.md) changes | pending | DB schema (uuid rename), Lambda code, DynamoDB compatibility |
| [B-64](backlog-reference.md) | Verify pre-commit secret detection | backlog | Before any CI/CD restoration |

## Phase 2: CI/CD Restoration

| ID | Task | Status | Depends on |
|----|------|--------|------------|
| [B-70](backlog-reference.md) | Common prerequisites (test harness, lint, Docker build) | backlog | Phase 1 |
| [B-71](backlog-reference.md) | GitHub Actions pipeline | backlog | B-70 |
| [B-72](backlog-reference.md) | CircleCI pipeline | backlog | B-70 |
| [B-73](backlog-reference.md) | GitLab CI pipeline | backlog | B-70 |
| [B-74](backlog-reference.md) | Jenkins pipeline | backlog | B-70 |
| [B-76](backlog-reference.md) | Restore pytest-html for CI reports | backlog | B-70 |

**Goal:** At least one working CI/CD pipeline (likely GitHub Actions) before restoring Lambda deployments.

## Phase 3: Security Hardening

| ID | Task | Status | Notes |
|----|------|--------|-------|
| [B-86](backlog-reference.md) | Triage clear-text logging (12 HIGH) | backlog | CodeQL findings |
| [B-87](backlog-reference.md) | Fix stack trace exposure (7 MEDIUM) | backlog | |
| [B-88](backlog-reference.md) | Review reflected XSS (8 MEDIUM) | backlog | |
| [B-89](backlog-reference.md) | Fix ReDoS vulnerability | backlog | |
| [B-90](backlog-reference.md) | Add timeout to all requests calls | backlog | |
| [B-91](backlog-reference.md) | Migrate SQL f-strings to parameterized queries | backlog | Consider combining with psycopg3 migration |

## Phase 4: AWS Restoration & Sync

1. Apply all pending changes from [aws-sync-backlog.md](aws-sync-backlog.md)
2. Rebuild Lambda layers with Python 3.12+
3. Re-deploy CloudFormation stacks to application account
4. Verify API Gateway endpoints match local Flask routes
5. Test DynamoDB → SQS → RDS pipeline end-to-end

## Phase 5: IaC Comparison — CloudFormation vs CDK

**Status:** Not started. See [ADR-016](adr/adr-016-cloudformation-vs-cdk.md) for decision context.

**Plan:**
1. Pick a self-contained subset of infrastructure (e.g., SQS + Lambda + DynamoDB pipeline)
2. Reimplement in CDK (TypeScript or Python)
3. Compare: developer experience, template size, type safety, testing, drift detection
4. Document findings — decide whether to migrate, keep CF, or use both
5. **Tool:** Install [AWS Serverless plugin](https://claude.com/plugins/aws-serverless) for Claude Code when starting CDK work

**Why CDK is interesting:**
- Type-safe constructs (vs YAML/JSON strings)
- Built-in best practices (L2/L3 constructs)
- Testing with standard frameworks (jest, pytest)
- Smaller codebase for equivalent infrastructure
- Growing community and AWS investment

**Why CF may still be preferred:**
- No build step — YAML is directly deployable
- Full AWS feature coverage on day 1
- Existing 29 templates + deploy.sh are battle-tested
- Simpler mental model (declarative, no code execution)
- No CDK bootstrap required

## Phase 6: Account Migration

**Target:** Migrate from application account → target account when everything is ready (including RDS data).

Prerequisites:
- All phases above completed
- Data migration strategy for RDS (pg_dump/restore or DMS)
- DNS/CloudFront reconfiguration
- Vault secrets re-provisioned on new account
- All SSM parameters recreated

## Future Directions

| Direction | Notes |
|-----------|-------|
| **Graph database (Neo4j)** | [B-102](backlog-reference.md) — evaluate Neo4j AuraDB Free for document relationships |
| **MCP server for Lenie** | Expose search/retrieval to Claude Desktop via MCP (see [system-evolution.md](system-evolution.md)) |
| **Serverless YouTube processing** | [B-67](backlog-reference.md) — choose compute model (Lambda vs Fargate vs Step Functions) |
| **psycopg3 migration** | Would solve SQL injection concerns (B-91) via server-side parameter binding |
| **Kubernetes (GKE)** | Alternative deployment target, already has Kustomize configs in `infra/kubernetes/` |
