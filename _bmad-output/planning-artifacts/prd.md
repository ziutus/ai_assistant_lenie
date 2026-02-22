---
stepsCompleted:
  - step-01-init
  - step-02-discovery
  - step-03-success
  - step-04-journeys
  - step-05-domain
  - step-06-innovation
  - step-07-project-type
  - step-08-scoping
  - step-09-functional
  - step-10-nonfunctional
  - step-11-polish
  - step-12-complete
  - step-e-01-discovery
  - step-e-02-review
  - step-e-03-edit
  - step-e-01-discovery
  - step-e-02-review
  - step-e-03-edit
classification:
  projectType: web_app
  domain: personal_ai_knowledge_management
  complexity: low
  projectContext: brownfield
inputDocuments:
  - docs/index.md
  - docs/project-overview.md
  - docs/architecture-backend.md
  - docs/architecture-infra.md
  - docs/api-contracts-backend.md
  - docs/data-models-backend.md
  - docs/integration-architecture.md
  - docs/architecture-web_interface_react.md
  - docs/architecture-web_chrome_extension.md
  - docs/source-tree-analysis.md
  - docs/development-guide.md
  - _bmad-output/implementation-artifacts/epic-1-6-retro-2026-02-15.md
  - _bmad-output/implementation-artifacts/epic-7-retro-2026-02-16.md
  - _bmad-output/implementation-artifacts/epic-8-retro-2026-02-16.md
  - _bmad-output/implementation-artifacts/epic-9-retro-2026-02-16.md
  - _bmad-output/implementation-artifacts/epic-10-retro-2026-02-18.md
  - _bmad-output/implementation-artifacts/epic-11-retro-2026-02-18.md
  - _bmad-output/implementation-artifacts/epic-12-retro-2026-02-18.md
workflowType: 'prd'
lastEdited: '2026-02-19'
editHistory:
  - date: '2026-02-16'
    changes: 'Updated from Sprint 2 (Cleanup & Vision) to Sprint 3 (Code Cleanup). Rewrote all sections. Applied validation fixes.'
  - date: '2026-02-19'
    changes: 'Updated from Sprint 3 (Code Cleanup) to Sprint 4 (AWS Infrastructure Consolidation & Tooling). 6 backlog stories: B-4, B-5, B-11, B-12, B-14, B-19. Added API Gateway Architecture Principle section.'
---

# Product Requirements Document - lenie-server-2025

**Author:** Ziutus
**Date:** 2026-02-19
**Sprint:** 4 — AWS Infrastructure Consolidation & Tooling

## Executive Summary

Lenie-server-2025 is a personal AI knowledge management system for collecting, managing, and searching press articles, web content, and YouTube transcriptions using LLMs and vector similarity search (PostgreSQL + pgvector).

**This sprint** executes Phase 2 of the five-phase strategic plan: Infrastructure Consolidation & Tooling. Following the principle "Clean first -> Consolidate -> Secure -> Build new," Sprint 4 consolidates AWS infrastructure and improves operational tooling after Sprint 3 completed code cleanup. Sprint 1 achieved 100% IaC coverage (6 epics, 10 stories). Sprint 2 removed unused AWS resources and documented project vision (3 epics, 5 stories). Sprint 3 removed 3 endpoints, 1 dead function, and applied 6 CloudFormation improvements (3 epics, 33 stories total across sprints). Sprint 4 addresses 6 backlog items: remove Elastic IP from EC2 (B-4), fix redundant Lambda function names (B-5), consolidate API Gateways from 3 to 2 (B-14), add AWS account info to deployment script (B-11), verify CRLF git config for parameter files (B-12), and consolidate duplicated documentation metrics (B-19).

**Target vision:** Private knowledge base in Obsidian vault, managed by Claude Desktop, powered by Lenie-AI as an MCP server. This sprint consolidates infrastructure to reduce AWS costs and operational friction before security hardening and feature development.

## Success Criteria

### User Success (Developer Experience)

- Developer sees clean Lambda function names following `${ProjectCode}-${Environment}-<description>` pattern with zero redundancy
- Developer deploys via `zip_to_s3.sh` with visible AWS account ID confirmation before any upload
- Developer manages 2 API Gateways instead of 3 (app + infra), with clear separation principle documented
- Developer finds documentation metrics (endpoint counts, template counts) in a single source of truth with zero cross-file discrepancies

### Business Success

- Lower AWS costs: ~$3.65/month saved by removing idle Elastic IP
- Reduced API Gateway count (3 to 2) simplifies infrastructure management and monitoring
- Documentation accuracy eliminates confusion about system scope (previously: 12 vs 18 endpoints, 29 vs 34 templates)
- Foundation prepared for Phase 3 (Security hardening) and Phase 4 (MCP Server implementation)

### Technical Success

- EC2 `ElasticIP` and `EIPAssociation` resources removed from `ec2-lenie.yaml`; Route53 A record updated dynamically via `aws_ec2_route53.py`
- Lambda `FunctionName` in `lambda-rds-start.yaml` changed from `${AWS::StackName}-rds-start-function` to `${ProjectCode}-${Environment}-rds-start` (eliminates `lenie-dev-lambda-rds-start-rds-start-function` redundancy)
- `api-gw-url-add.yaml` merged into `api-gw-app.yaml`; Chrome extension and add-url React app updated with new endpoint URL
- `zip_to_s3.sh` displays AWS account ID and requires confirmation before deployment
- `.gitattributes` coverage verified for parameter files; documented if current config is adequate
- Single-source documentation metrics file created with automated drift verification

### Measurable Outcomes

- 2 CloudFormation resources removed from `ec2-lenie.yaml` (`ElasticIP`, `EIPAssociation`)
- API Gateways reduced from 3 to 2 (app + infra)
- 0 Lambda functions with redundant names (all follow `${ProjectCode}-${Environment}-<description>`)
- `zip_to_s3.sh` outputs AWS account ID on every run
- 0 discrepancies between documentation metric counts and actual infrastructure counts
- 0 parameter files with CRLF line endings

## Product Scope

### Phase 2 — This Sprint (Infrastructure Consolidation & Tooling)

1. **B-4: Remove Elastic IP from EC2** — Remove `ElasticIP` (AWS::EC2::EIP) and `EIPAssociation` resources from `infra/aws/cloudformation/templates/ec2-lenie.yaml`. EC2 launches with dynamic public IP; Route53 A record updated via `infra/aws/tools/aws_ec2_route53.py` on each start. Update `Outputs` section to reference dynamic IP instead of EIP. Saves ~$3.65/month.

2. **B-5: Fix redundant Lambda function names** — Fix `FunctionName` properties that produce redundant names when `${AWS::StackName}` is used (e.g., `lenie-dev-lambda-rds-start-rds-start-function`). Replace with `${ProjectCode}-${Environment}-<description>` pattern. Affected template: `lambda-rds-start.yaml` (confirmed: uses `${AWS::StackName}-rds-start-function`). Verify all other Lambda templates already use the clean pattern. Update all consumers: API Gateway integrations, Step Function definitions, IAM policies, parameter files referencing the old function name.

3. **B-14: Consolidate api-gw-url-add into api-gw-app** — Merge the `/url_add` endpoint from `api-gw-url-add.yaml` into `api-gw-app.yaml`. Remove or archive `api-gw-url-add.yaml` template and its parameter file `parameters/dev/api-gw-url-add.json`. Migrate API key, usage plan, and Lambda permission resources. Update Chrome extension default endpoint URL (currently `https://jg40fjwz61.execute-api.us-east-1.amazonaws.com/v1/url_add`) and add-url React app endpoint URL (currently `https://1bkc3kz7c9.execute-api.us-east-1.amazonaws.com/v1`). The `api-gw-infra.yaml` template is not affected.

4. **B-11: Add AWS account info to zip-to-s3 script** — Script `infra/aws/serverless/zip_to_s3.sh` sources `env.sh` by default (account `008971653395`, the current production account). Add: display `AWS_ACCOUNT_ID` during execution, display which env file is sourced, warn/confirm before proceeding with deployment. Two env configs: `env.sh` (account `008971653395`, current production) and `env_lenie_2025.sh` (account `049706517731`, target migration account).

5. **B-12: Fix CRLF git config for parameter files** — Verify parameter files in `infra/aws/cloudformation/parameters/dev/` (29 JSON files) have correct LF line endings. `.gitattributes` already enforces LF for `*.json`. Sprint 3 story 7-2 found CRLF warning was due to Windows `core.autocrlf` setting, not file content. Verify current state, update `.gitattributes` if needed, or document that current config is adequate.

6. **B-19: Consolidate duplicated documentation counts** — Same metrics (endpoint counts, template counts, Lambda function counts) are duplicated across 7+ files with known discrepancies: `api-gw-app` documented as "12 endpoints" (actual: 10), `api-gw-infra` as "9 endpoints" (actual: 8), total templates documented as "29" (actual: 34). Affected files: `CLAUDE.md`, `README.md`, `backend/CLAUDE.md`, `docs/index.md`, `docs/api-contracts-backend.md`, `infra/aws/CLAUDE.md`, `infra/aws/cloudformation/CLAUDE.md`. Create single source of truth file. Add automated verification script to catch future drift.

### Phase 3 (Future — Security Hardening)

- Lambda Layer security audit (dependencies ~1.5+ years old)
- CORS hardening (replace wildcard `Access-Control-Allow-Origin: '*'`)
- Lambda function CloudFormation management (replace hardcoded ARNs)
- Remove 36 stale API Gateway deployments

### Phase 4 (Future — MCP Server Foundation)

- Database abstraction layer (separate raw psycopg2 from business logic)
- Implement MCP server protocol (expose search/retrieve endpoints as MCP tools)
- Claude Desktop integration (configure Lenie-AI as MCP server)
- API adaptation for MCP tool consumption

### Phase 5 (Future — Obsidian Integration)

- Obsidian vault integration (synchronization, linking, note creation)
- Semantic search from within Obsidian via Claude Desktop + MCP
- Advanced vector search refinements for personal knowledge management

### Phase 6 (Future — Multiuser Support on AWS)

Realizowane na samym końcu, po zakończeniu wszystkich pozostałych faz. Umożliwi korzystanie z systemu przez wielu użytkowników na infrastrukturze AWS.

- **B-23: Uwierzytelnianie użytkowników (AWS Cognito)** — Wdrożenie AWS Cognito User Pool do rejestracji i logowania użytkowników. Integracja z API Gateway (Cognito Authorizer) zamiast obecnego statycznego klucza API.
- **B-24: Własność danych w bazie** — Dodanie kolumny `user_id` (owner) do tabel `web_documents` i `websites_embeddings`. Migracja istniejących danych do domyślnego użytkownika. Indeksy uwzględniające `user_id`.
- **B-25: Izolacja danych per użytkownik w API** — Wszystkie endpointy filtrują dane po `user_id` z tokena Cognito. Użytkownik widzi i modyfikuje tylko swoje dokumenty.
- **B-26: Zamiana wspólnego klucza API na tokeny per użytkownik** — Usunięcie mechanizmu `x-api-key` na rzecz JWT z Cognito. Aktualizacja wszystkich klientów (frontend, Chrome extension, add-url app).
- **B-27: UI logowania/wylogowania** — Ekrany logowania i rejestracji w aplikacjach frontendowych. Obsługa sesji użytkownika i odświeżania tokenów.
- **B-28: Panel administracyjny użytkowników** — Zarządzanie użytkownikami (lista, blokowanie, usuwanie). Widoczność statystyk per użytkownik (liczba dokumentów, zużycie embeddingów).

## User Journeys

### Journey 1: Developer Infrastructure Consolidation Sprint

**Persona:** Ziutus — sole developer and project owner, intermediate skill level.

**Opening Scene:** Ziutus opens the project after completing Sprint 3 (Code Cleanup). The codebase is clean — no dead endpoints or unused functions. However, infrastructure has accumulated debt: an idle Elastic IP costs $3.65/month, Lambda function names contain redundant segments (`lenie-dev-lambda-rds-start-rds-start-function`), three API Gateways exist where two suffice, the deployment script does not show which AWS account it targets, and documentation metrics are inconsistent across 7+ files.

**Rising Action:** Ziutus removes the Elastic IP from `ec2-lenie.yaml` and verifies that `aws_ec2_route53.py` correctly updates Route53 with the dynamic public IP on each EC2 start. Ziutus fixes the Lambda function name in `lambda-rds-start.yaml` from `${AWS::StackName}-rds-start-function` to `${ProjectCode}-${Environment}-rds-start` and updates all consumers. Ziutus merges the `/url_add` endpoint from `api-gw-url-add.yaml` into `api-gw-app.yaml`, updates the Chrome extension's default endpoint URL and the add-url React app's hardcoded URL, then removes the standalone template. Ziutus adds account ID display and confirmation to `zip_to_s3.sh`. Ziutus verifies parameter file line endings and documents the finding. Ziutus creates a single-source metrics file and an automated verification script, then fixes all discrepancies across documentation files.

**Climax:** After deployment — EC2 starts with dynamic IP and Route53 updates automatically. Lambda functions have clean names. Two API Gateways serve all endpoints (app: 11 endpoints including `/url_add`, infra: 8 endpoints). The deployment script clearly shows target account `008971653395` before proceeding. Documentation metrics match actual infrastructure with zero discrepancies. The verification script confirms consistency.

**Resolution:** Infrastructure is consolidated. Monthly costs are reduced. Operational safety is improved (account visibility in deployment). Documentation is accurate and maintainable. The project is ready for Phase 3 (Security Hardening).

### Journey 2: Developer Deploying Lambda Code

**Persona:** Ziutus deploying updated Lambda code to AWS.

**Opening Scene:** Ziutus runs `./zip_to_s3.sh simple` from `infra/aws/serverless/`.

**Rising Action:** The script displays: sourcing `env.sh`, AWS account ID `008971653395`, profile `default`, environment `dev`, S3 bucket `lenie-dev-cloudformation`. Ziutus reviews the information and confirms deployment. The script packages each Lambda function and uploads to S3.

**Resolution:** Ziutus has full visibility into which AWS account receives the deployment. No accidental cross-account deployments. If `env_lenie_2025.sh` were sourced instead, the script would display account `049706517731` and profile `lenie-ai-2025-admin`, making the difference immediately visible.

### Journey Requirements Summary

| Journey | Capabilities Required |
|---------|----------------------|
| Infra Consolidation | Remove ElasticIP and EIPAssociation from ec2-lenie.yaml |
| Infra Consolidation | Update ec2-lenie.yaml Outputs to reference dynamic public IP |
| Infra Consolidation | Fix Lambda FunctionName in lambda-rds-start.yaml to clean pattern |
| Infra Consolidation | Update all consumers of renamed Lambda function |
| Infra Consolidation | Merge api-gw-url-add.yaml /url_add endpoint into api-gw-app.yaml |
| Infra Consolidation | Update Chrome extension and add-url React app endpoint URLs |
| Infra Consolidation | Remove or archive api-gw-url-add.yaml template |
| Infra Consolidation | Add account ID display and confirmation to zip_to_s3.sh |
| Infra Consolidation | Verify parameter file line endings in .gitattributes |
| Infra Consolidation | Create single-source documentation metrics file |
| Infra Consolidation | Add automated verification script for documentation drift |
| Lambda Deployment | See AWS account ID before deployment proceeds |
| Lambda Deployment | Confirm deployment target before uploads begin |

## API Gateway Architecture Principle

The project uses two categories of API Gateway:

1. **Application API Gateway (`api-gw-app.yaml`)** — Endpoints that serve application functionality: document CRUD, search, AI operations, content download, URL submission. These endpoints correspond to Flask `server.py` routes and Lambda functions (`app-server-db`, `app-server-internet`, `sqs-weblink-put-into`).

2. **Infrastructure API Gateway (`api-gw-infra.yaml`)** — Endpoints that manage AWS infrastructure: RDS start/stop/status, EC2 start/stop/status, SQS queue size. These endpoints have no equivalent in the Flask `server.py` and exist only in the AWS serverless deployment.

**Rationale:** This separation enables direct comparison between deployment targets. Application endpoints exist in Docker (server.py), AWS Lambda, and future GCP deployments. Infrastructure endpoints are AWS-specific and have no cross-platform equivalent. Keeping them in separate API Gateways makes this boundary explicit.

**Consolidation decision:** The Chrome extension API (`api-gw-url-add.yaml`) serves the `/url_add` endpoint, which is application-level functionality (document submission). It belongs in `api-gw-app.yaml`, not in a standalone API Gateway. Sprint 4 merges it, reducing API Gateways from 3 to 2.

**Post-consolidation state:**
- `api-gw-app.yaml` — 11 endpoints: `/website_list`, `/website_get`, `/website_save`, `/website_delete`, `/website_is_paid`, `/website_get_next_to_correct`, `/website_similar`, `/website_split_for_embedding`, `/website_download_text_content`, `/ai_embedding_get`, `/url_add`
- `api-gw-infra.yaml` — 8 endpoints: `/rds/start`, `/rds/stop`, `/rds/status`, `/ec2/status`, `/ec2/start`, `/ec2/stop`, `/sqs/size`, `/git-webhooks`

## Web App Technical Context

Brownfield web application: React 18 SPA (Amplify) + Flask REST API (API Gateway + Lambda) + PostgreSQL 17 with pgvector (RDS). Sprint 4 modifies CloudFormation templates, deployment scripts, and client endpoint configurations — no backend application code changes.

**API Gateway template size:** `api-gw-app.yaml` is under the 51200 byte CloudFormation inline limit after Sprint 3 endpoint removal. Adding the `/url_add` endpoint (POST + OPTIONS with CORS, ~60 lines of OpenAPI) will increase size. Monitor that merged template stays under the inline limit. If exceeded, switch to S3-based template deployment (`aws cloudformation package`).

**Chrome extension endpoint URL:** Currently hardcoded in `web_chrome_extension/popup.html` as `https://jg40fjwz61.execute-api.us-east-1.amazonaws.com/v1/url_add`. After API Gateway consolidation, this URL changes to the `api-gw-app` gateway URL. The extension allows user override via the settings field.

**Add-URL React app endpoint URL:** Currently hardcoded in `web_add_url_react/src/App.js` as `https://1bkc3kz7c9.execute-api.us-east-1.amazonaws.com/v1`. After consolidation, this must point to the `api-gw-app` gateway URL.

**Lambda function naming:** Stack naming convention is `<PROJECT_CODE>-<STAGE>-<template_name>`. The `lambda-rds-start.yaml` template uses `${AWS::StackName}` in `FunctionName`, producing `lenie-dev-lambda-rds-start-rds-start-function` (stack name `lenie-dev-lambda-rds-start` + suffix `-rds-start-function`). Other Lambda templates already use the clean `${ProjectCode}-${Environment}-<description>` pattern directly: `sqs-to-rds-lambda.yaml` produces `lenie-dev-sqs-to-rds-lambda`, `lambda-weblink-put-into-sqs.yaml` produces `lenie-dev-weblink-put-into-sqs`.

**AWS accounts:**
- `008971653395` — CURRENT production account (all active infrastructure runs here)
- `049706517731` — TARGET migration account (will be used after full migration including RDS data)

**Deployment script:** `infra/aws/serverless/zip_to_s3.sh` sources `env.sh` by default, which targets account `008971653395`. The script currently provides no account visibility — a developer could source the wrong env file and deploy to the wrong account without warning.

## Risk Mitigation

**Technical Risks:**
- *EC2 unreachable after EIP removal* — Mitigated by verifying `aws_ec2_route53.py` updates Route53 A record with dynamic IP on each EC2 start. TTL is 300 seconds. Makefile target `aws-start-openvpn` already uses this script.
- *Lambda function rename breaks API Gateway integrations* — Mitigated by: (1) verifying `api-gw-infra.yaml` already references `${ProjectCode}-${Environment}-rds-start` (confirmed from codebase), (2) updating Step Function definitions and parameter files that reference the old name, (3) deploying Lambda template before API Gateway template.
- *API Gateway consolidation breaks Chrome extension / add-url app* — Mitigated by: (1) updating hardcoded URLs in client code, (2) migrating API key and usage plan resources, (3) testing `/url_add` endpoint on new gateway before removing old gateway.
- *`api-gw-app.yaml` exceeds 51200 byte inline limit after adding /url_add* — Mitigated by checking template size after merge. Fallback: use `aws cloudformation package` for S3-based deployment.
- *Wrong AWS account deployment* — Mitigated by adding explicit account display and confirmation prompt to `zip_to_s3.sh`.

**Resource Risks:**
- *Context loss between sessions* — Mitigated by detailed story files and BMad Method tracking
- *Documentation drift reoccurs after consolidation* — Mitigated by automated verification script that compares documented counts against actual infrastructure
- *CloudFormation validation failures* — Mitigated by cfn-lint validation before every deployment

**Process Risks:**
- *Retro action items not tracked* — Mitigated by adding retro commitments to sprint-status.yaml
- *Old API Gateway left running after consolidation* — Mitigated by story requiring explicit deletion or decommission step for api-gw-url-add stack

## Functional Requirements

### B-4: Remove Elastic IP from EC2

- FR1: Developer can remove `ElasticIP` (AWS::EC2::EIP) resource from `infra/aws/cloudformation/templates/ec2-lenie.yaml`
- FR2: Developer can remove `EIPAssociation` (AWS::EC2::EIPAssociation) resource from `infra/aws/cloudformation/templates/ec2-lenie.yaml`
- FR3: Developer can update `Outputs.PublicIP` in `ec2-lenie.yaml` to reference the EC2 instance dynamic public IP instead of the Elastic IP
- FR4: Developer can verify `infra/aws/tools/aws_ec2_route53.py` updates Route53 A record with the EC2 dynamic public IP on each instance start
- FR5: Developer can verify EC2 instance launches with a dynamic public IP via the public subnet's `MapPublicIpOnLaunch: 'true'` setting in `infra/aws/cloudformation/templates/vpc.yaml` (lines 83, 98)

### B-5: Fix Redundant Lambda Function Names

- FR6: Developer can change `FunctionName` in `infra/aws/cloudformation/templates/lambda-rds-start.yaml` from `${AWS::StackName}-rds-start-function` to `${ProjectCode}-${Environment}-rds-start`
- FR7: Developer can verify all other Lambda templates already use the `${ProjectCode}-${Environment}-<description>` naming pattern (no `${AWS::StackName}` usage)
- FR8: Developer can update `infra/aws/cloudformation/parameters/dev/lambda-rds-start.json` if any parameter references the old function name
- FR9: Developer can verify `SqsToRdsLambdaFunctionName` parameter in `infra/aws/cloudformation/parameters/dev/sqs-to-rds-step-function.json` (currently `lenie-dev-sqs-to-rds-lambda`) does not reference the renamed Lambda function and update if needed
- FR10: Developer can verify `api-gw-infra.yaml` Lambda function references (FunctionName properties) resolve correctly after the rename
- FR11: Developer can verify the renamed Lambda function is invocable by the Step Function defined in `sqs-to-rds-step-function.yaml`

### B-14: Consolidate api-gw-url-add into api-gw-app

- FR12: Developer can add the `/url_add` POST endpoint definition (with Lambda proxy integration) from `api-gw-url-add.yaml` into the OpenAPI Body of `api-gw-app.yaml`
- FR13: Developer can add the `/url_add` OPTIONS endpoint definition (CORS mock integration) from `api-gw-url-add.yaml` into `api-gw-app.yaml`
- FR14: Developer can add the Lambda permission resource for the `url-add` Lambda function to `api-gw-app.yaml`
- FR15: Developer can verify the merged `api-gw-app.yaml` template size remains under the 51200 byte CloudFormation inline limit
- FR16: Developer can update the default endpoint URL in `web_chrome_extension/popup.html` to the `api-gw-app` gateway URL
- FR17: Developer can update the hardcoded API URL in `web_add_url_react/src/App.js` to the `api-gw-app` gateway URL
- FR18: Developer can remove or archive the `api-gw-url-add.yaml` template from `infra/aws/cloudformation/templates/`
- FR19: Developer can remove the `api-gw-url-add.json` parameter file from `infra/aws/cloudformation/parameters/dev/`
- FR20: Developer can delete the `lenie-dev-api-gw-url-add` CloudFormation stack from AWS after the consolidated gateway is deployed and verified
- FR21: Developer can verify the `/url_add` endpoint on the consolidated `api-gw-app` gateway returns successful responses with the existing API key

### B-11: Add AWS Account Info to zip-to-s3 Script

- FR22: Developer can see the sourced environment file name (`env.sh` or `env_lenie_2025.sh`) displayed when running `infra/aws/serverless/zip_to_s3.sh`
- FR23: Developer can see the AWS account ID (`AWS_ACCOUNT_ID` variable) displayed when running `zip_to_s3.sh`
- FR24: Developer can see the AWS profile name, environment, and S3 bucket name displayed before deployment begins
- FR25: Developer can confirm or abort deployment after reviewing the displayed account information

### B-12: Fix CRLF Git Config for Parameter Files

- FR26: Developer can verify all 29 parameter files in `infra/aws/cloudformation/parameters/dev/` have LF line endings
- FR27: Developer can verify `.gitattributes` rules cover `*.json` files with `text eol=lf`
- FR28: Developer can document the verification result — either update `.gitattributes` with additional rules, or confirm current config is adequate with explanation

### B-19: Consolidate Duplicated Documentation Counts

- FR29: Developer can create a single-source metrics file at `docs/infrastructure-metrics.md` containing authoritative counts for: API Gateway endpoints (per gateway), CloudFormation templates, Lambda functions, server.py endpoints
- FR30: Developer can fix all discrepancies across documentation files (`CLAUDE.md`, `README.md`, `backend/CLAUDE.md`, `docs/index.md`, `docs/api-contracts-backend.md`, `infra/aws/CLAUDE.md`, `infra/aws/cloudformation/CLAUDE.md`) to reference the single-source file or use consistent correct values
- FR31: Developer can run an automated verification script that compares documented counts against actual infrastructure counts and reports any discrepancies
- FR32: Developer can verify zero discrepancies between documented and actual counts after running the verification script

## Non-Functional Requirements

### Reliability & Safety

- NFR1: Existing API Gateway endpoints continue to function correctly after `api-gw-url-add` consolidation into `api-gw-app`, verified by `infra/aws/cloudformation/smoke-test-url-add.sh` passing with exit code 0 (tests API Gateway → Lambda → DynamoDB flow)
- NFR2: EC2 instance remains accessible via SSH and HTTP/HTTPS after Elastic IP removal, with Route53 A record updated within 5 minutes of instance start
- NFR3: No actively used CloudFormation resources are removed — only resources being consolidated or replaced
- NFR4: All infrastructure changes preserve rollback capability through version control (git) and CloudFormation stack operations
- NFR5: Chrome extension and add-url React app successfully submit URLs via the consolidated API Gateway endpoint

### IaC Quality & Validation

- NFR6: All modified CloudFormation templates pass cfn-lint validation with zero errors before deployment
- NFR7: All Lambda functions follow the naming convention `${ProjectCode}-${Environment}-<description>` with zero `${AWS::StackName}` usage in FunctionName properties
- NFR8: The consolidated `api-gw-app.yaml` template remains under the 51200 byte CloudFormation inline limit
- NFR9: CloudFormation deployment order in `deploy.ini` remains correct after template removal (no dangling dependencies)

### Operational Safety

- NFR10: `zip_to_s3.sh` displays AWS account ID, profile, and environment on every execution before any S3 upload or Lambda update occurs
- NFR11: `zip_to_s3.sh` requires explicit user confirmation before proceeding with deployment to prevent accidental cross-account deployments
- NFR12: Parameter files in `infra/aws/cloudformation/parameters/dev/` have consistent LF line endings verified by `.gitattributes` enforcement

### Documentation Quality

- NFR13: Documentation metrics (endpoint counts, template counts, Lambda function counts) have a single source of truth with zero cross-file discrepancies
- NFR14: An automated verification script exists that detects documentation metric drift and can be run as part of CI or manual review
- NFR15: All documentation files reference post-consolidation state: 2 API Gateways (app + infra), correct endpoint counts per gateway, correct total template count
