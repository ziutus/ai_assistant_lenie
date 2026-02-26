# Sprint 5: Operational Fixes & Lambda Analysis — Archived Epics

> **Status:** ALL DONE — Archived 2026-02-26
> **Epics:** 17, 18

## Sprint 5 Overview

Sprint 5 addresses operational issues discovered during and after Sprint 4 deployment, fixes bugs, and prepares analysis for Lambda function consolidation. It also completes the API Gateway custom domain setup (B-15 from backlog) and fully removes the url-add.yaml template, bringing the total REST API count from 3 to 2.

---

## Epic 17: Operational Safety & Bug Fixes

Developer has reliable deployment tooling, working endpoints, secure database connectivity from Lambda, and API access via a professional custom domain — operational issues from Sprint 4 deployment are resolved and infrastructure is production-ready.

**Stories:** 17-1, 17-2, 17-3, 17-4, 17-5

Implementation notes:
- 17-1: Add safety confirmation to `deploy.sh` (follows same pattern as Sprint 4 zip_to_s3.sh safety)
- 17-2: Fix `/metrics` endpoint returning HTTP 500 (empty `pass` body)
- 17-3: Rename legacy Lambda functions `lenie_2_db`/`lenie_2_internet` to `${ProjectCode}-${Environment}-*` pattern (deferred from B-3)
- 17-4: Fix sqs-to-rds Lambda deployment: SSL connectivity, Step Function error handling, Secrets Manager auto-generated password
- 17-5: Add API Gateway custom domain `api.dev.lenie-ai.eu` (B-15), remove url-add.yaml (2 REST APIs remain)

### Story 17.1: Add Deployment Safety Confirmation to deploy.sh

As a **developer**,
I want deploy.sh to require explicit confirmation before creating/updating CloudFormation stacks,
so that I can verify the target AWS account, region, and stage before any infrastructure changes are applied.

**Acceptance Criteria:**

**Given** the developer runs `deploy.sh -p lenie -s dev`
**When** the script displays the AWS account information
**Then** the script also displays the number of templates to be processed and prompts for confirmation
**And** the developer can abort by pressing Enter or typing `n`/`N`

**Given** the developer passes `--yes` or `-y` flag
**When** the script runs
**Then** the confirmation prompt is skipped (for automation/CI)

**Given** the developer runs `deploy.sh` in delete or change-set mode
**When** the script displays the deployment info
**Then** the action type (CREATE/UPDATE, DELETE, or CHANGE-SET) is displayed in the info header

**Status:** done

### Story 17.2: Fix Metrics Endpoint Returns 500

As a **developer**,
I want the `/metrics` endpoint to return a valid response instead of HTTP 500,
so that Kubernetes health monitoring and Prometheus scraping work correctly.

**Acceptance Criteria:**

**Given** a GET request to `/metrics`
**When** the server processes the request
**Then** the server returns HTTP 200 with a minimal valid Prometheus text format response
**And** the Content-Type is `text/plain; charset=utf-8`
**And** it includes basic application info metrics (`lenie_app_info{version="..."} 1`)

**Given** existing health check endpoints
**When** the `/metrics` fix is deployed
**Then** no existing endpoints are affected

**Status:** done

### Story 17.3: Rename Legacy Lambda lenie_2_internet and lenie_2_db

As a **developer**,
I want to rename the legacy Lambda functions `lenie_2_db` and `lenie_2_internet` to follow the `${ProjectCode}-${Environment}-<description>` naming convention,
so that all Lambda functions have consistent, non-redundant names.

**Acceptance Criteria:**

**Given** Lambda function `lenie_2_db` exists in AWS
**When** the developer renames it
**Then** the new name is `lenie-dev-app-server-db` (matching source directory)

**Given** Lambda function `lenie_2_internet` exists in AWS
**When** the developer renames it
**Then** the new name is `lenie-dev-app-server-internet`

**Given** `api-gw-app.yaml` has 10 endpoints referencing hardcoded Lambda names
**When** the developer updates the template
**Then** all URIs use `!Sub` with `${ProjectCode}-${Environment}-*` pattern
**And** the template passes cfn-lint validation

**Given** documentation references old names
**When** the developer updates affected docs
**Then** all CLAUDE.md files and `docs/infrastructure-metrics.md` reflect new names

**Status:** ready-for-dev

### Story 17.4: Fix sqs-to-rds Lambda Deployment and DB Connectivity

As a **developer**,
I want the sqs-to-rds Lambda function to deploy correctly and connect to RDS with SSL,
so that the SQS-to-database pipeline processes documents reliably.

**Acceptance Criteria:**

**Given** the sqs-to-rds Lambda function requires `backend/library/` modules
**When** the developer moves it from the simple function list to the app function list
**Then** `zip_to_s3.sh` packages it with the full backend library

**Given** Lambda connects to RDS within VPC
**When** the developer adds `POSTGRESQL_SSLMODE=require` to `sqs-to-rds-lambda.yaml`
**Then** the Lambda uses SSL for database connections

**Given** the Step Function Map state processes SQS messages
**When** any Lambda in the pipeline fails
**Then** the Step Function catches the error (Catch with States.ALL) and proceeds to stop the database
**And** the database is not left running indefinitely on failure (cost protection)

**Given** `secrets.yaml` uses hardcoded password
**When** the developer migrates to `GenerateSecretString`
**Then** the password is auto-generated by Secrets Manager
**And** the secret ARN is exported to SSM for cross-stack reference
**And** `rds.yaml` uses `SecretTargetAttachment` for password rotation support

**Given** the RDS instance requires a PostgreSQL user for the application
**When** the developer creates the `lenie` user in RDS
**Then** the user exists with appropriate permissions (previously only existed in Docker)

**Status:** done

### Story 17.5: Add API Gateway Custom Domain

As a **developer**,
I want API Gateway endpoints accessible through a custom domain `api.dev.lenie-ai.eu` instead of auto-generated AWS execute-api URLs,
so that API consumers have stable, memorable URLs that survive API Gateway recreation.

**Acceptance Criteria:**

**Given** the project uses two API Gateways (app and infra)
**When** the developer creates `api-gw-custom-domain.yaml`
**Then** the template provisions: ACM certificate (DNS validation), API Gateway DomainName (REGIONAL, TLS 1.2), BasePathMappings (root → app API, /infra → infra API), Route53 A-record alias, SSM exports

**Given** the custom domain is deployed
**When** a client sends a request to `https://api.dev.lenie-ai.eu/website_list`
**Then** the request routes to the app API Gateway (no `/v1` stage prefix needed)

**Given** the custom domain is deployed
**When** a client sends a request to `https://api.dev.lenie-ai.eu/infra/sqs/size`
**Then** the request routes to the infra API Gateway

**Given** `url-add.yaml` Lambda template previously had its own REST API Gateway
**When** it is fully removed
**Then** the post-consolidation state is 2 REST APIs in AWS (app + infra), down from 3

**Backlog item:** B-15
**Status:** done

---

## Epic 18: Lambda Consolidation Analysis

Developer has a documented analysis and recommendation for whether to consolidate EC2 management Lambdas (ec2-start, ec2-stop, ec2-status) and RDS management Lambdas (rds-start, rds-stop, rds-status) into fewer functions — reducing infrastructure complexity if beneficial.

**Stories:** 18-1, 18-2

Implementation notes:
- 18-1: Analysis of EC2 Lambda consolidation feasibility (code overlap, IAM scope, cold start impact)
- 18-2: Analysis of RDS Lambda consolidation feasibility (includes Step Function integration analysis)
- Both are analysis-only stories — no code changes, only recommendation documents
- Joint recommendation across both stories: consolidate EC2 only, RDS only, both, or keep separate

### Story 18.1: Analyze EC2 Lambda Consolidation

As a **developer**,
I want to analyze whether the EC2 management Lambda functions (ec2-start, ec2-stop, ec2-status) can be consolidated into a single function,
so that I can reduce infrastructure complexity and maintenance overhead.

**Acceptance Criteria:**

**Given** three separate Lambda functions exist for EC2 management
**When** the developer analyzes their code, configuration, and usage
**Then** a written analysis document is produced with a clear recommendation (consolidate or keep separate)

**Given** the analysis is complete
**When** the developer reviews the findings
**Then** the document includes: current resource costs, code overlap, shared dependencies, and migration complexity

**Given** a consolidation recommendation
**When** the developer proposes the new architecture
**Then** the proposal includes: single function with action parameter routing, updated API Gateway integration, backward compatibility plan

**Status:** done

### Story 18.2: Analyze RDS Lambda Consolidation

As a **developer**,
I want to analyze whether the RDS management Lambda functions (rds-start, rds-stop, rds-status) can be consolidated into a single function,
so that I can reduce infrastructure complexity and maintenance overhead.

**Acceptance Criteria:**

**Given** three separate Lambda functions exist for RDS management
**When** the developer analyzes their code, configuration, and usage
**Then** a written analysis document is produced with a clear recommendation

**Given** the RDS functions are used by `sqs-to-rds-step-function.yaml`
**When** the developer evaluates consolidation
**Then** the analysis explicitly addresses Step Function integration — how the consolidated function would be invoked and whether ASL definition changes are needed

**Given** Story 18.1 (EC2 analysis) may recommend consolidation
**When** the developer completes the RDS analysis
**Then** a joint recommendation is provided: consolidate EC2 only, RDS only, both into one function, or keep all separate

**Status:** done
