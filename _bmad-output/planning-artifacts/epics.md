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

This document provides the complete epic and story breakdown for lenie-server-2025 Sprint 4 — AWS Infrastructure Consolidation & Tooling. It decomposes the requirements from the PRD and Architecture into implementable stories addressing 6 backlog items: B-4, B-5, B-11, B-12, B-14, B-19.

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
