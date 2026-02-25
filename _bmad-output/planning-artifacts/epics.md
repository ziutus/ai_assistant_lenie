---
stepsCompleted:
  - step-01-validate-prerequisites
  - step-02-design-epics
  - step-03-create-stories
  - step-04-final-validation
inputDocuments:
  - _bmad-output/planning-artifacts/prd.md
  - _bmad-output/planning-artifacts/architecture.md
---

# lenie-server-2025 - Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for lenie-server-2025. Sprint 4 (Epics 13–16) covers AWS Infrastructure Consolidation & Tooling addressing 6 backlog items: B-4, B-5, B-11, B-12, B-14, B-19. Sprint 5 (Epics 17–18) covers Operational Fixes & Lambda Analysis — deployment safety, bug fixes, database connectivity, API Gateway custom domain (B-15), and Lambda consolidation analysis. Backlog sections include: completed non-sprint work (landing page, app2 infrastructure), Epic 19 (Multi-User Admin Interface — all 4 stories DONE), and Frontend Architecture & API Contract (B-49 shared types DONE, B-50 API type sync pipeline BACKLOG, B-51 deploy scripts DONE).

## Requirements Inventory

### Functional Requirements

**B-4: Remove Elastic IP from EC2 (FR1-FR5)**

- FR1: Remove `ElasticIP` (AWS::EC2::EIP) resource from `infra/aws/cloudformation/templates/ec2-lenie.yaml`
- FR2: Remove `EIPAssociation` (AWS::EC2::EIPAssociation) resource from `infra/aws/cloudformation/templates/ec2-lenie.yaml`
- FR3: Remove `Outputs.PublicIP` entirely from `ec2-lenie.yaml` (nothing consumes this output; Route53 is updated via `aws_ec2_route53.py`)
- FR4: Verify `infra/aws/tools/aws_ec2_route53.py` updates Route53 A record with the EC2 dynamic public IP on each instance start
- FR5: Verify EC2 instance launches with a dynamic public IP via the public subnet's `MapPublicIpOnLaunch: 'true'` setting in `vpc.yaml` (lines 83, 98)

**B-5: Fix Redundant Lambda Function Names (FR6-FR11)**

- FR6: Change `FunctionName` in `infra/aws/cloudformation/templates/lambda-rds-start.yaml` from `${AWS::StackName}-rds-start-function` to `${ProjectCode}-${Environment}-rds-start`
- FR7: Verify all other Lambda templates already use the `${ProjectCode}-${Environment}-<description>` naming pattern (no `${AWS::StackName}` usage)
- FR8: Update `infra/aws/cloudformation/parameters/dev/lambda-rds-start.json` if any parameter references the old function name
- FR9: Verify `SqsToRdsLambdaFunctionName` parameter in `sqs-to-rds-step-function.json` does not reference the renamed Lambda function
- FR10: Verify `api-gw-infra.yaml` Lambda function references resolve correctly after the rename
- FR11: Verify the renamed Lambda function is invocable by the Step Function defined in `sqs-to-rds-step-function.yaml`

**B-14: Consolidate api-gw-url-add into api-gw-app (FR12-FR21a)**

- FR12: Add the `/url_add` POST endpoint definition (with Lambda proxy integration) from `api-gw-url-add.yaml` into the OpenAPI Body of `api-gw-app.yaml`
- FR13: Add the `/url_add` OPTIONS endpoint definition (CORS mock integration) from `api-gw-url-add.yaml` into `api-gw-app.yaml`
- FR14: Add the Lambda permission resource for the `url-add` Lambda function to `api-gw-app.yaml`
- FR15: Verify the merged `api-gw-app.yaml` template size remains under the 51200 byte CloudFormation inline limit
- FR16: Update the default endpoint URL in `web_chrome_extension/popup.html` to the `api-gw-app` gateway URL. Bump version in `manifest.json` to `1.0.23` and add changelog entry in `CHANGELOG.md`
- FR17: Update the hardcoded API URL in `web_add_url_react/src/App.js` to the `api-gw-app` gateway URL. Bump version in `package.json` and add changelog entry in the new `CHANGELOG.md`
- FR17a: Create `CHANGELOG.md` in `web_add_url_react/` following Keep a Changelog format. Include initial entry for version `0.1.0` (current state) and a new entry for the API URL update
- FR18: Remove or archive the `api-gw-url-add.yaml` template from `infra/aws/cloudformation/templates/`
- FR19: Remove the `api-gw-url-add.json` parameter file from `infra/aws/cloudformation/parameters/dev/`
- FR20: Delete the `lenie-dev-api-gw-url-add` CloudFormation stack from AWS after the consolidated gateway is deployed and verified
- FR21: Verify the `/url_add` endpoint on the consolidated `api-gw-app` gateway returns successful responses with the existing API key

**B-11: Add AWS Account Info to zip-to-s3 Script (FR22-FR25)**

- FR22: Display the sourced environment file name (`env.sh` or `env_lenie_2025.sh`) when running `zip_to_s3.sh`
- FR23: Display the AWS account ID (`AWS_ACCOUNT_ID` variable) when running `zip_to_s3.sh`
- FR24: Display the AWS profile name, environment, and S3 bucket name before deployment begins
- FR25: Confirm or abort deployment after reviewing the displayed account information

**B-12: Fix CRLF Git Config for Parameter Files (FR26-FR28)**

- FR26: Verify all 29 parameter files in `infra/aws/cloudformation/parameters/dev/` have LF line endings
- FR27: Verify `.gitattributes` rules cover `*.json` files with `text eol=lf`
- FR28: Document the verification result — either update `.gitattributes` with additional rules, or confirm current config is adequate with explanation

**B-19: Consolidate Duplicated Documentation Counts (FR29-FR32)**

- FR29: Create a single-source metrics file at `docs/infrastructure-metrics.md` containing authoritative counts for: API Gateway endpoints (per gateway), CloudFormation templates, Lambda functions, server.py endpoints
- FR30: Fix all discrepancies across documentation files (`CLAUDE.md`, `README.md`, `backend/CLAUDE.md`, `docs/index.md`, `docs/api-contracts-backend.md`, `infra/aws/CLAUDE.md`, `infra/aws/cloudformation/CLAUDE.md`) to reference the single-source file or use consistent correct values
- FR31: Create an automated verification script that compares documented counts against actual infrastructure counts and reports any discrepancies
- FR32: Verify zero discrepancies between documented and actual counts after running the verification script

### NonFunctional Requirements

**Reliability & Safety (NFR1-NFR5)**

- NFR1: Existing API Gateway endpoints continue to function correctly after `api-gw-url-add` consolidation into `api-gw-app`, verified by `smoke-test-url-add.sh` passing with exit code 0
- NFR2: EC2 instance remains accessible via SSH and HTTP/HTTPS after Elastic IP removal, with Route53 A record updated within 5 minutes of instance start
- NFR3: No actively used CloudFormation resources are removed — only resources being consolidated or replaced
- NFR4: All infrastructure changes preserve rollback capability through version control (git) and CloudFormation stack operations
- NFR5: Chrome extension and add-url React app successfully submit URLs via the consolidated API Gateway endpoint

**IaC Quality & Validation (NFR6-NFR9)**

- NFR6: All modified CloudFormation templates pass cfn-lint validation with zero errors before deployment
- NFR7: All Lambda functions follow the naming convention `${ProjectCode}-${Environment}-<description>` with zero `${AWS::StackName}` usage in FunctionName properties
- NFR8: The consolidated `api-gw-app.yaml` template remains under the 51200 byte CloudFormation inline limit
- NFR9: CloudFormation deployment order in `deploy.ini` remains correct after template removal (no dangling dependencies)

**Operational Safety (NFR10-NFR12)**

- NFR10: `zip_to_s3.sh` displays AWS account ID, profile, and environment on every execution before any S3 upload or Lambda update occurs
- NFR11: `zip_to_s3.sh` requires explicit user confirmation before proceeding with deployment to prevent accidental cross-account deployments
- NFR12: Parameter files in `infra/aws/cloudformation/parameters/dev/` have consistent LF line endings verified by `.gitattributes` enforcement

**Documentation Quality (NFR13-NFR15)**

- NFR13: Documentation metrics (endpoint counts, template counts, Lambda function counts) have a single source of truth with zero cross-file discrepancies
- NFR14: An automated verification script exists that detects documentation metric drift and can be run as part of CI or manual review
- NFR15: All documentation files reference post-consolidation state: 2 API Gateway templates (app + infra) with url-add.yaml retaining its own REST API (3 total), correct endpoint counts per gateway (app: 11, infra: 7, url-add: 1), correct total template count

### Additional Requirements

**From Architecture — Implementation Patterns & Constraints:**

- Implementation sequence: B-11 → B-12 → B-4/B-5 (parallel) → B-14 → B-19
- OpenAPI merge pattern: `/url_add` must follow exact same structure as existing endpoints in `api-gw-app.yaml` OpenAPI Body
- Lambda permission resource: `UrlAddLambdaInvokePermission` with `!Sub '${ProjectCode}-${Environment}-url-add'`
- Bash script modification pattern: `--yes` flag for automation bypass, info header display, no colors (match existing style)
- CloudFormation resource removal: clean deletion, no commented-out remnants, no placeholder comments
- Documentation metrics file: organized by deployment perspective (Flask server vs AWS Serverless vs CloudFormation)
- Hybrid Lambda naming: new `/url_add` uses parameterized `!Sub`, existing endpoints keep hardcoded names (deferred to B-3)
- API Gateway Architecture Principle: 2 categories — app (application logic) + infra (AWS management)
- Template size monitoring: verify 51200 byte limit post-merge, fallback to `aws cloudformation package`
- Gen 2+ canonical template pattern from Sprint 1 remains in effect for all CF modifications
- Hardcoded Lambda names (`lenie_2_db`, `lenie_2_internet`) in `api-gw-app.yaml` — intentional, deferred to future B-3
- Client app versioning: Chrome extension bumps manifest version + CHANGELOG entry; web_add_url_react gets new CHANGELOG.md + version bump

**From Architecture — Starter Template:**

- No new templates from scratch — all Sprint 4 changes modify or remove existing templates
- `api-gw-app.yaml` special case: inline OpenAPI Body specification (not standard CF resource pattern)
- Bash scripts follow existing project conventions: sourcing env files, AWS CLI, standard bash error handling

### FR Coverage Map

FR1: Epic 14 — Remove ElasticIP from ec2-lenie.yaml
FR2: Epic 14 — Remove EIPAssociation from ec2-lenie.yaml
FR3: Epic 14 — Remove Outputs.PublicIP entirely
FR4: Epic 14 — Verify aws_ec2_route53.py updates Route53
FR5: Epic 14 — Verify MapPublicIpOnLaunch in vpc.yaml
FR6: Epic 14 — Fix FunctionName in lambda-rds-start.yaml
FR7: Epic 14 — Verify all other Lambda templates use clean pattern
FR8: Epic 14 — Update lambda-rds-start.json if needed
FR9: Epic 14 — Verify SqsToRdsLambdaFunctionName not affected
FR10: Epic 14 — Verify api-gw-infra.yaml references
FR11: Epic 14 — Verify Step Function invocation
FR12: Epic 15 — Add /url_add POST to api-gw-app.yaml
FR13: Epic 15 — Add /url_add OPTIONS to api-gw-app.yaml
FR14: Epic 15 — Add LambdaPermission for url-add
FR15: Epic 15 — Verify 51200 byte limit
FR16: Epic 15 — Update Chrome extension URL + version bump + CHANGELOG
FR17: Epic 15 — Update add-url React app URL + version bump + CHANGELOG
FR17a: Epic 15 — Create CHANGELOG.md for web_add_url_react
FR18: Epic 15 — Remove api-gw-url-add.yaml template
FR19: Epic 15 — Remove api-gw-url-add.json parameter file
FR20: Epic 15 — Delete lenie-dev-api-gw-url-add CF stack
FR21: Epic 15 — Verify /url_add on consolidated gateway
FR22: Epic 13 — Display env file name in zip_to_s3.sh
FR23: Epic 13 — Display AWS account ID
FR24: Epic 13 — Display profile, environment, S3 bucket
FR25: Epic 13 — Confirmation prompt before deployment
FR26: Epic 13 — Verify parameter files LF endings
FR27: Epic 13 — Verify .gitattributes coverage
FR28: Epic 13 — Document CRLF verification result
FR29: Epic 16 — Create infrastructure-metrics.md
FR30: Epic 16 — Fix discrepancies across 7+ files
FR31: Epic 16 — Create verification script
FR32: Epic 16 — Verify zero discrepancies

## Epic List

### Epic 13: Operational Safety & Tooling

Developer can deploy safely with full AWS account visibility and confirmed file format consistency — preventing accidental cross-account deployments and closing the CRLF investigation from Sprint 3.

**FRs covered:** FR22, FR23, FR24, FR25, FR26, FR27, FR28
**NFRs addressed:** NFR10, NFR11, NFR12

Implementation notes:
- B-11: Add info header, `--yes` flag, confirmation prompt to `zip_to_s3.sh`
- B-12: Verify parameter file line endings and `.gitattributes` coverage
- Fully independent — no dependencies on other epics
- Immediate operational benefit for all subsequent deployments

### Epic 14: Infrastructure Cost & Naming Cleanup

Developer has clean, cost-efficient infrastructure — no idle Elastic IP charges (~$3.65/month saved) and no redundant Lambda function names (clean `${ProjectCode}-${Environment}-<description>` pattern).

**FRs covered:** FR1, FR2, FR3, FR4, FR5, FR6, FR7, FR8, FR9, FR10, FR11
**NFRs addressed:** NFR2, NFR3, NFR4, NFR6, NFR7

Implementation notes:
- B-4: Remove ElasticIP and EIPAssociation from ec2-lenie.yaml, remove Outputs.PublicIP entirely
- B-5: Fix FunctionName in lambda-rds-start.yaml, verify all consumers
- B-4 and B-5 are independent of each other — can be done in parallel
- Architecture decision: EIP removal safe because `aws_ec2_route53.py` handles dynamic DNS
- Architecture decision: Lambda rename is in-place CF replacement (acceptable brief downtime for on-demand function)

### Epic 15: API Gateway Consolidation

The duplicate `api-gw-url-add.yaml` template is removed and its CF stack deleted — the `/url_add` endpoint is consolidated into `api-gw-app.yaml`. Client applications (Chrome extension, add-url React app) are updated with new URLs and versioned releases. Note: `url-add.yaml` retains its own REST API Gateway (3 REST APIs total in AWS: app, infra, url-add).

**FRs covered:** FR12, FR13, FR14, FR15, FR16, FR17, FR17a, FR18, FR19, FR20, FR21
**NFRs addressed:** NFR1, NFR5, NFR6, NFR8, NFR9

Implementation notes:
- B-14: Most architecturally complex story in Sprint 4
- Inline merge of /url_add into api-gw-app.yaml OpenAPI Body
- New /url_add uses parameterized `!Sub` Lambda name (hybrid with existing hardcoded names)
- Chrome extension: bump to 1.0.23 + CHANGELOG entry
- web_add_url_react: create CHANGELOG.md + version bump
- Verify 51200 byte template size limit post-merge
- 5-step cleanup sequence: verify → delete CF stack → remove from deploy.ini → remove template → remove parameters
- Soft dependency on Epic 14 (B-5 Lambda naming ideally done first)

### Epic 16: Documentation Consolidation & Verification

Developer has a single source of truth for infrastructure metrics with automated drift detection — zero discrepancies between documentation and actual infrastructure counts.

**FRs covered:** FR29, FR30, FR31, FR32
**NFRs addressed:** NFR13, NFR14, NFR15

Implementation notes:
- B-19: Create `docs/infrastructure-metrics.md` organized by deployment perspective
- Fix discrepancies across 7+ documentation files
- Create `scripts/verify-documentation-metrics.sh` for automated drift detection
- Best executed after Epic 15 to capture post-consolidation state (2 API GWs, correct endpoint counts)
- Architecture pattern: metrics organized by Flask server vs AWS Serverless vs CloudFormation

---

## Epic 13: Operational Safety & Tooling

### Story 13.1: Add Deployment Safety Header to zip_to_s3.sh

As a **developer**,
I want to see the target AWS account, profile, environment, and S3 bucket before any deployment proceeds,
So that I can verify I'm deploying to the correct account and abort if something looks wrong.

**Acceptance Criteria:**

**Given** the developer runs `infra/aws/serverless/zip_to_s3.sh`
**When** the script sources the env file (`env.sh` or `env_lenie_2025.sh`)
**Then** the script displays: sourced env file name, AWS account ID, AWS profile, environment, and S3 bucket name
**And** the info is displayed before any S3 upload or Lambda update occurs

**Given** the deployment info is displayed
**When** the developer reviews the information
**Then** the script prompts for confirmation (`Continue with deployment? (y/N)`)
**And** the developer can abort by pressing Enter or typing `n`/`N`

**Given** the developer passes `--yes` or `-y` flag
**When** the script runs
**Then** the confirmation prompt is skipped (for automation)
**And** the deployment info is still displayed

**Given** `env.sh` is sourced (default)
**When** the script displays account info
**Then** account `008971653395` and profile `default` are shown

**Given** `env_lenie_2025.sh` is sourced instead
**When** the script displays account info
**Then** account `049706517731` and profile `lenie-ai-2025-admin` are shown

**FRs covered:** FR22, FR23, FR24, FR25

### Story 13.2: Verify CRLF Git Config for Parameter Files

As a **developer**,
I want to verify that all CloudFormation parameter files have correct LF line endings and `.gitattributes` enforces this,
So that the CRLF investigation from Sprint 3 is formally closed with documented findings.

**Acceptance Criteria:**

**Given** 29+ parameter files exist in `infra/aws/cloudformation/parameters/dev/`
**When** the developer checks line endings of all JSON parameter files
**Then** all files have LF line endings (no CRLF)

**Given** `.gitattributes` exists in the repository root
**When** the developer reviews its rules
**Then** `*.json` files are covered with `text eol=lf` (or equivalent rule ensuring LF)

**Given** the verification is complete
**When** the developer documents the result
**Then** one of two outcomes is documented:
- `.gitattributes` is updated with additional rules if current coverage is inadequate
- Current config is confirmed adequate with explanation (referencing Sprint 3 Story 7-2 finding that CRLF warning was due to Windows `core.autocrlf`, not file content)

**FRs covered:** FR26, FR27, FR28

---

## Epic 14: Infrastructure Cost & Naming Cleanup

### Story 14.1: Remove Elastic IP from EC2 Instance

As a **developer**,
I want to remove the Elastic IP from the EC2 CloudFormation template and rely on dynamic public IP with Route53 DNS updates,
So that unnecessary EIP idle charges (~$3.65/month) are eliminated while maintaining DNS-based access to the instance.

**Acceptance Criteria:**

**Given** `infra/aws/cloudformation/templates/ec2-lenie.yaml` contains `ElasticIP` (AWS::EC2::EIP) resource
**When** the developer removes the `ElasticIP` resource
**Then** the resource definition is deleted entirely (no commented-out remnants)

**Given** `ec2-lenie.yaml` contains `EIPAssociation` (AWS::EC2::EIPAssociation) resource
**When** the developer removes the `EIPAssociation` resource
**Then** the resource definition is deleted entirely

**Given** `ec2-lenie.yaml` contains `Outputs.PublicIP` referencing the Elastic IP
**When** the developer removes the output
**Then** the `PublicIP` output is deleted entirely (nothing consumes it)

**Given** the EC2 template is modified
**When** the developer runs cfn-lint validation
**Then** the template passes with zero errors

**Given** `infra/aws/tools/aws_ec2_route53.py` exists
**When** the developer reviews its behavior
**Then** the script correctly retrieves the EC2 dynamic public IP and updates the Route53 A record on each instance start

**Given** `infra/aws/cloudformation/templates/vpc.yaml` defines public subnets
**When** the developer verifies `MapPublicIpOnLaunch: 'true'` (lines 83, 98)
**Then** EC2 instances launched in these subnets receive a dynamic public IP automatically

**FRs covered:** FR1, FR2, FR3, FR4, FR5

### Story 14.2: Fix Redundant Lambda Function Name in lambda-rds-start

As a **developer**,
I want to fix the Lambda function name in `lambda-rds-start.yaml` from the redundant `${AWS::StackName}-rds-start-function` to the clean `${ProjectCode}-${Environment}-rds-start` pattern,
So that all Lambda functions follow a consistent, non-redundant naming convention.

**Acceptance Criteria:**

**Given** `infra/aws/cloudformation/templates/lambda-rds-start.yaml` uses `FunctionName: !Sub '${AWS::StackName}-rds-start-function'`
**When** the developer changes it to `FunctionName: !Sub '${ProjectCode}-${Environment}-rds-start'`
**Then** the template produces the clean name `lenie-dev-rds-start` instead of `lenie-dev-lambda-rds-start-rds-start-function`

**Given** the FunctionName is changed
**When** the developer runs cfn-lint validation
**Then** the template passes with zero errors

**Given** all other Lambda templates exist in `infra/aws/cloudformation/templates/`
**When** the developer audits their `FunctionName` properties
**Then** zero templates use `${AWS::StackName}` in FunctionName (all use `${ProjectCode}-${Environment}-<description>`)

**Given** `infra/aws/cloudformation/parameters/dev/lambda-rds-start.json` exists
**When** the developer reviews its contents
**Then** the parameter file is updated if it references the old function name, or confirmed clean if it doesn't

**Given** `infra/aws/cloudformation/parameters/dev/sqs-to-rds-step-function.json` contains `SqsToRdsLambdaFunctionName`
**When** the developer verifies it
**Then** the value references `lenie-dev-sqs-to-rds-lambda` (not the renamed rds-start function) — no change needed

**Given** `infra/aws/cloudformation/templates/api-gw-infra.yaml` references Lambda functions
**When** the developer verifies the rds-start reference
**Then** it already uses `${ProjectCode}-${Environment}-rds-start` pattern — no change needed (confirmed from architecture analysis)

**Given** `infra/aws/cloudformation/templates/sqs-to-rds-step-function.yaml` defines a Step Function
**When** the developer verifies Lambda invocation references
**Then** the Step Function does not reference the rds-start Lambda directly (uses sqs-to-rds-lambda) — no change needed

**FRs covered:** FR6, FR7, FR8, FR9, FR10, FR11

---

## Epic 15: API Gateway Consolidation

### Story 15.1: Merge /url_add Endpoint into api-gw-app.yaml

As a **developer**,
I want to add the `/url_add` endpoint (POST + OPTIONS with CORS) and its Lambda permission into `api-gw-app.yaml`,
So that all application endpoints are served by a single API Gateway.

**Acceptance Criteria:**

**Given** `api-gw-url-add.yaml` defines a `/url_add` POST endpoint with Lambda proxy integration
**When** the developer adds the `/url_add` POST path to the OpenAPI Body in `api-gw-app.yaml`
**Then** the endpoint uses `!Sub` with `${ProjectCode}-${Environment}-url-add` for the Lambda integration URI
**And** the endpoint includes `security: [{api_key: []}]` (same as all other endpoints)
**And** the timeout is set to 29000ms (matching current api-gw-url-add.yaml)
**And** the path is added at the end of the paths section (after `/ai_embedding_get`)

**Given** the `/url_add` POST endpoint needs CORS support
**When** the developer adds the `/url_add` OPTIONS method
**Then** the OPTIONS method uses mock integration with CORS response headers (`Access-Control-Allow-Origin`, `Access-Control-Allow-Methods`, `Access-Control-Allow-Headers`)
**And** the pattern matches existing OPTIONS methods in api-gw-app.yaml

**Given** the url-add Lambda function needs invoke permission
**When** the developer adds `UrlAddLambdaInvokePermission` (AWS::Lambda::Permission) resource
**Then** `FunctionName` uses `!Sub '${ProjectCode}-${Environment}-url-add'`
**And** `SourceArn` is scoped to `/*/*/url_add` (not wildcard)
**And** the resource is placed after existing Lambda permission resources

**Given** all changes are applied to `api-gw-app.yaml`
**When** the developer checks the template file size
**Then** the template remains under the 51200 byte CloudFormation inline limit
**And** if exceeded, the developer documents the fallback to `aws cloudformation package`

**Given** the modified template
**When** the developer runs cfn-lint validation
**Then** the template passes with zero errors

**Given** existing endpoints in `api-gw-app.yaml`
**When** the developer reviews them
**Then** no existing endpoint definitions were modified during the merge

**FRs covered:** FR12, FR13, FR14, FR15

### Story 15.2: Update Client Applications and Version Releases

As a **developer**,
I want to update the Chrome extension and add-url React app with the new API Gateway URL and release new versions,
So that both client applications point to the consolidated `api-gw-app` gateway endpoint.

**Acceptance Criteria:**

**Given** `web_chrome_extension/popup.html` contains the default endpoint URL `https://jg40fjwz61.execute-api.us-east-1.amazonaws.com/v1/url_add`
**When** the developer updates it to the `api-gw-app` gateway URL
**Then** the default URL points to the consolidated gateway's `/url_add` endpoint

**Given** the Chrome extension URL is updated
**When** the developer bumps the version in `web_chrome_extension/manifest.json`
**Then** the version changes from `1.0.22` to `1.0.23`

**Given** the Chrome extension version is bumped
**When** the developer adds an entry to `web_chrome_extension/CHANGELOG.md`
**Then** the entry follows the existing Keep a Changelog format (in Polish)
**And** the entry describes the API Gateway endpoint URL update

**Given** `web_add_url_react/src/App.js` contains the hardcoded API URL `https://1bkc3kz7c9.execute-api.us-east-1.amazonaws.com/v1`
**When** the developer updates it to the `api-gw-app` gateway URL
**Then** the default URL points to the consolidated gateway

**Given** `web_add_url_react/` has no CHANGELOG.md
**When** the developer creates `web_add_url_react/CHANGELOG.md`
**Then** the file follows Keep a Changelog format
**And** includes an initial entry for version `0.1.0` (current state)
**And** includes a new entry for the API URL update with version bump

**Given** the add-url React app URL is updated
**When** the developer bumps the version in `web_add_url_react/package.json`
**Then** the version is incremented appropriately

**Given** both client apps are updated
**When** the developer verifies the `/url_add` endpoint on the consolidated gateway
**Then** both apps can successfully submit URLs via the new endpoint with the existing API key

**FRs covered:** FR16, FR17, FR17a, FR21

### Story 15.3: Remove Old api-gw-url-add Gateway and Clean Up

As a **developer**,
I want to remove the standalone `api-gw-url-add` template, parameter file, deploy.ini entry, and CloudFormation stack,
So that no orphaned infrastructure remains after the consolidation.

**Acceptance Criteria:**

**Given** the `/url_add` endpoint works on the consolidated `api-gw-app` gateway (verified in Story 15.1 and 15.2)
**When** the developer deletes the `lenie-dev-api-gw-url-add` CloudFormation stack from AWS
**Then** the stack is successfully deleted
**And** the old API Gateway and its resources are removed from AWS

**Given** the CF stack is deleted
**When** the developer removes `api-gw-url-add.yaml` from `infra/aws/cloudformation/templates/`
**Then** the template file is deleted (not commented out or archived)

**Given** the template is removed
**When** the developer removes `api-gw-url-add.json` from `infra/aws/cloudformation/parameters/dev/`
**Then** the parameter file is deleted

**Given** template and parameter files are removed
**When** the developer updates `infra/aws/cloudformation/deploy.ini`
**Then** the `templates/api-gw-url-add.yaml` entry is removed from the `[dev]` section
**And** the deployment order of remaining templates is correct (no dangling dependencies)

**Given** `infra/aws/cloudformation/smoke-test-url-add.sh` may reference the old gateway URL
**When** the developer reviews the smoke test
**Then** the endpoint URL is updated to the consolidated `api-gw-app` gateway URL (if hardcoded)

**FRs covered:** FR18, FR19, FR20

---

## Epic 16: Documentation Consolidation & Verification

### Story 16.1: Create Single-Source Infrastructure Metrics File

As a **developer**,
I want to create a single authoritative metrics file and fix all discrepancies across documentation,
So that infrastructure counts (endpoints, templates, Lambda functions) are accurate and consistent everywhere.

**Acceptance Criteria:**

**Given** infrastructure metrics are duplicated across 7+ files with known discrepancies
**When** the developer creates `docs/infrastructure-metrics.md`
**Then** the file contains authoritative counts organized by deployment perspective:
- Flask Server (Docker/Kubernetes): endpoint count and list
- AWS Serverless (Lambda + API Gateway): endpoints per gateway (api-gw-app: 11, api-gw-infra: 7, url-add: 1), Lambda function count and list
- CloudFormation: template count in deploy.ini, total template file count

**Given** the metrics file is created with post-consolidation values (2 API Gateway templates + url-add.yaml with own REST API = 3 REST APIs total, /url_add in api-gw-app)
**When** the developer reviews each of the 7+ documentation files
**Then** all discrepancies are fixed in: `CLAUDE.md`, `README.md`, `backend/CLAUDE.md`, `docs/index.md`, `docs/api-contracts-backend.md`, `infra/aws/CLAUDE.md`, `infra/aws/cloudformation/CLAUDE.md`
**And** each file either references `docs/infrastructure-metrics.md` as the source of truth or uses consistent correct values

**Given** all files are updated
**When** the developer compares documented counts against actual infrastructure
**Then** zero discrepancies exist between any documentation file and the actual state

**FRs covered:** FR29, FR30

### Story 16.2: Create Automated Documentation Drift Verification Script

As a **developer**,
I want an automated script that detects documentation metric drift by comparing documented counts against actual infrastructure,
So that future discrepancies are caught early instead of accumulating silently.

**Acceptance Criteria:**

**Given** `docs/infrastructure-metrics.md` exists as the single source of truth
**When** the developer creates `scripts/verify-documentation-metrics.sh`
**Then** the script compares documented counts against actual counts by:
- Counting endpoints in `api-gw-app.yaml` and `api-gw-infra.yaml` OpenAPI paths
- Counting templates listed in `deploy.ini`
- Counting total `.yaml` template files in `infra/aws/cloudformation/templates/`
- Counting Lambda function definitions across templates
- Counting endpoints in `backend/server.py`

**Given** the verification script exists
**When** the developer runs it
**Then** it reports any discrepancies between documented and actual counts
**And** exits with code 0 if all counts match, non-zero if discrepancies found

**Given** the script runs successfully after Story 16.1 updates
**When** the developer verifies the output
**Then** zero discrepancies are reported

**Given** the `scripts/` directory may not exist
**When** the developer creates the script
**Then** the directory is created if needed
**And** the script is executable (`chmod +x`)

**FRs covered:** FR31, FR32

---

## Sprint 5: Operational Fixes & Lambda Analysis

### Overview

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

---

## Backlog: Frontend & Multi-User Platform

### Overview

Work completed outside of Sprint 4/5 scope: landing page deployment and app2 (multi-user UI) infrastructure setup. Epic 19 captures the future development of the target multi-user admin interface.

### Completed Work (Non-Sprint)

**Landing Page (www.lenie-ai.eu):**
- Migrated landing page to monorepo (`web_landing_page/`): Next.js 14.2 + React 18 + Tailwind 3.4
- Completed TypeScript migration (45 files JSX→TSX)
- Deployed on S3 + CloudFront via CloudFormation stacks (`s3-landing-web`, `cloudfront-landing`)
- Status: **LIVE** — publicly accessible at `www.lenie-ai.eu`

**app2 Infrastructure (app2.dev.lenie-ai.eu):**
- Created `s3-app2-web.yaml` — S3 bucket with CloudFront OAC, AES256 encryption, fully blocked public access
- Created `cloudfront-app2.yaml` — CloudFront distribution with SPA routing, TLSv1.2, Route53 alias
- Added both templates to `deploy.ini [dev]` (Layer 4 and Layer 8)
- `web_interface_app2/` — admin panel scaffolded from purchased layout (original reference layout removed from repo)
- Status: **Deployed** — admin panel with API key authentication live at `app2.dev.lenie-ai.eu`

---

## Epic 19: Multi-User Admin Interface (app2) — DONE

All 4 stories completed (2026-02-24). Admin panel at `app2.dev.lenie-ai.eu` is scaffolded, has API key login gate, professional layout, and connected backend API.

Developer has a new admin interface at `app2.dev.lenie-ai.eu` — scaffolded from a purchased layout (now removed from repo) with API key authentication, API integration, and own code in `web_interface_app2/`.

**Stories:** 19-1 ✅, 19-2 ✅, 19-3 ✅, 19-4 ✅

Implementation notes:
- Authentication uses `x-api-key` (same as backend) instead of originally planned username/password env vars — simpler, sufficient for dev/single-user. AWS Cognito migration planned for Phase 9 (B-33).
- Infrastructure provisioned and deployed (S3 + CloudFront stacks)
- Original purchased layout reference removed from repo (commit e8a44fd); design incorporated into `web_interface_app2/`
- Tech stack: Vite 6, React 18, Redux, React Bootstrap, TypeScript, Sass
- Current single-user app: `web_interface_react/` at `app.dev.lenie-ai.eu`
- Deploy script created with SSM integration (B-51)
- Domain: `app2.dev.lenie-ai.eu` (fixed from `app2.lenie-ai.eu` in B-43)

### Story 19.1: Scaffold Multi-User App Project

As a **developer**,
I want to create a new web application project (`web_interface_app2/`) with a modern React + TypeScript stack,
so that development of the multi-user interface can begin with a clean, properly structured codebase.

**Acceptance Criteria:**

**Given** the purchased layout uses React 18, Redux, React Bootstrap, TypeScript, and Sass
**When** the developer scaffolds the new project
**Then** the project uses a compatible modern stack (Vite + React 18 + TypeScript + Redux Toolkit + React Bootstrap)
**And** the project is created in `web_interface_app2/` directory
**And** it builds and runs on port 3001

**Given** the app2 CloudFront distribution exists
**When** the developer configures the build
**Then** static export is compatible with S3 + CloudFront SPA hosting (index.html fallback)

**Status:** done
**Completed:** 2026-02-24 (commit 478b62c)

### Story 19.2: Add Login Page and Route Protection

As a **developer**,
I want app2 to require login before showing any content,
so that the admin interface is not publicly accessible to unauthorized users.

**Acceptance Criteria:**

**Given** app2 is publicly accessible at `app2.dev.lenie-ai.eu` without authentication
**When** the developer adds a login page
**Then** all routes except `/login` redirect to the login page when the user is not authenticated
**And** the login page has a simple form with API key field

**Given** the user submits a valid API key
**When** the login form processes the submission
**Then** the app stores the API key in localStorage
**And** the user is redirected to the main dashboard
**And** all protected routes become accessible

**Given** the user submits an incorrect API key
**When** the login form processes the submission
**Then** an error message is displayed
**And** the user remains on the login page

**Implementation note:** Original spec called for username/password with env vars (`APP2_AUTH_USERNAME`, `APP2_AUTH_PASSWORD`). Actual implementation uses `x-api-key` authentication — the same API key used by the backend. This is simpler and sufficient for single-user/dev use. Migration to AWS Cognito (B-33) planned for Phase 9.

**Status:** done
**Completed:** 2026-02-24 (commits: 478b62c, a5422fc, 9c279e7, 5c57356)

### Story 19.3: Implement Core Layout and Navigation

As a **developer**,
I want to implement the core layout structure (sidebar, header, main content area) inspired by the purchased layout,
so that the application has a professional multi-user admin interface look and feel.

**Acceptance Criteria:**

**Given** `web_interface_app2/` already contains the layout scaffolded from the purchased template
**When** the developer reviews the layout structure
**Then** the app has a professional visual structure with own code (sidebar navigation, header bar, content area)
**And** responsive design works on desktop and tablet

**Given** the current app has 7 pages (document list, search, link/webpage/youtube/movie editors)
**When** the developer plans the navigation
**Then** the sidebar includes routes for all existing features plus user management (future)

**Given** Story 19.2 (login) is implemented
**When** the layout is rendered
**Then** all layout pages are behind the authentication guard

**Implementation note:** Layout scaffolded from purchased template. Purchased template reference (`web_interface_target/`) removed from repo (commit e8a44fd) — design already incorporated into app2 codebase.

**Status:** done
**Completed:** 2026-02-24 (commit 478b62c)

### Story 19.4: Connect Backend API

As a **developer**,
I want the new multi-user interface to connect to the existing backend API,
so that all current functionality (document CRUD, search, AI operations) works through the new UI.

**Acceptance Criteria:**

**Given** the backend API is accessible at `api.dev.lenie-ai.eu`
**When** the developer integrates API calls
**Then** all existing endpoints work: document list, get, save, delete, search, download content, AI embedding
**And** the `x-api-key` authentication header is included in all requests

**Given** the current app (`web_interface_react/`) has working API integration
**When** the developer reviews its implementation
**Then** the API service layer is adapted for the new app (axios, error handling, auth)

**Implementation note:** Hardcoded API key removed (commit 5c57356), API key now provided via login page. Redux store manages API server configuration.

**Status:** done
**Completed:** 2026-02-24 (commits: 478b62c, 5c57356)

---

## Backlog: Frontend Architecture & API Contract

### Overview

Work completed and planned to address frontend-backend type drift and shared code infrastructure. The `shared/` TypeScript package was extracted (B-49) and a strategy document for full API type synchronization was written (`docs/api-type-sync-strategy.md`). The main backlog item (B-50) covers the multi-phase implementation of Pydantic → OpenAPI → generated TypeScript types.

### Completed Work (Non-Sprint)

**B-49: Extract Shared TypeScript Types to shared/ Package** — DONE (2026-02-25)
- Created `shared/` package with domain types: `WebDocument`, `ApiType`, `SearchResult`, `ListItem`
- Added constants (`DEFAULT_API_URLS`) and factory values (`emptyDocument`)
- Both frontends (`web_interface_react/`, `web_interface_app2/`) reference via `@lenie/shared` alias (tsconfig paths + Vite resolve.alias)
- No build step — Vite transpiles directly via esbuild
- Commit: 64e3213

**B-51: Frontend Deployment Scripts with SSM** — DONE (2026-02-25)
- Created `deploy.sh` for `web_interface_react/` and `web_interface_app2/`
- Scripts resolve S3 bucket name and CloudFront distribution ID from SSM Parameter Store
- Support `--skip-build` and `--skip-invalidation` flags
- Commit: f2432ce

### B-50: API Type Synchronization Pipeline (Pydantic → OpenAPI → TypeScript)

**Problem:** Frontend (`shared/types/`) and backend (`backend/library/`) define the same data structures independently, leading to drift. Known issues documented in `docs/api-type-sync-strategy.md`:

| Issue | Detail |
|-------|--------|
| `id` type mismatch | TS: `string`, Python: `int` (serial PK) |
| `WebDocument` missing fields | Backend returns 13 fields not in TS interface |
| `ListItem` field count | TS: 5 fields, backend: 10 |
| `SearchResult` field count | TS: 5 fields, backend: 12 |
| Enums as plain strings | Backend has typed enums, frontend treats as `string` |
| No contract | No OpenAPI, JSON Schema, or Pydantic — backend uses custom classes + raw dicts |

**Chosen approach:** Python Pydantic models (source of truth) → OpenAPI schema (generated) → TypeScript types (generated)

**Implementation phases (from `docs/api-type-sync-strategy.md`):**

1. **Phase 1: Pydantic Response Models** — Create Pydantic v2 models in `backend/library/models/schemas/` for all API response shapes (WebDocumentResponse, WebDocumentListItem, SearchResultItem, ListResponse, SearchResponse, ErrorResponse)
2. **Phase 2: Use Models in Flask Routes** — Replace raw dict returns with Pydantic model serialization in `server.py` and Lambda handlers
3. **Phase 3: Generate OpenAPI Schema** — Manual export script or flask-smorest integration to produce `docs/openapi.json`
4. **Phase 4: Generate TypeScript from OpenAPI** — Use `openapi-typescript` to generate `shared/types/generated.ts` from OpenAPI schema
5. **Phase 5: CI Integration** — Add generation + diff check to CI pipeline to prevent future drift

**Migration path:** Incremental, one endpoint at a time. Start with `/website_get`, then `/website_list`, `/website_similar`. Hand-written `shared/types/` coexists with generated types during migration.

**Status:** backlog
**Strategy document:** `docs/api-type-sync-strategy.md`
**Depends on:** B-49 (shared types package) — DONE
