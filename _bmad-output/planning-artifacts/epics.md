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

This document provides the complete epic and story breakdown for lenie-server-2025 Sprint 3 (Code Cleanup — Endpoint & Dead Code Removal), decomposing the requirements from the PRD and Architecture into implementable stories.

## Requirements Inventory

### Functional Requirements

**Endpoint Removal — `/ai_ask`**

- FR1: Developer can remove `/ai_ask` endpoint from `backend/server.py`
- FR2: Developer can remove `/ai_ask` endpoint from `infra/aws/serverless/app-server-internet/lambda_function.py`
- FR3: Developer can remove `/ai_ask` endpoint definition from `infra/aws/cloudformation/templates/api-gw-app.yaml`
- FR4: Developer can remove or disable `handleCorrectUsingAI()` function from `web_interface_react/src/hooks/useManageLLM.js`
- FR5: Developer can verify `ai_ask()` function in `backend/library/ai.py` remains intact and is called by `backend/imports/youtube_processing.py`

**Endpoint Removal — `/translate`**

- FR6: Developer can remove `/translate` endpoint from `infra/aws/serverless/app-server-internet/lambda_function.py`
- FR7: Developer can remove `/translate` endpoint definition from `infra/aws/cloudformation/templates/api-gw-app.yaml`
- FR8: Developer can remove or disable `handleTranslate()` function from `web_interface_react/src/hooks/useManageLLM.js`
- FR9: Developer can verify backend module `library.translate` does not exist (endpoint already broken)

**Endpoint Removal — `/infra/ip-allow`**

- FR10: Developer can remove `/infra/ip-allow` endpoint definition from `infra/aws/cloudformation/templates/api-gw-app.yaml`
- FR11: Developer can delete or archive Lambda function `infra-allow-ip-in-secrutity-group` from AWS account
- FR12: Developer can verify zero frontend references to `/infra/ip-allow` endpoint

**Dead Code Removal**

- FR13: Developer can remove `ai_describe_image()` function from `backend/library/ai.py`
- FR14: Developer can verify `ai_describe_image()` has zero callers across entire codebase

**CloudFormation Improvements — Tagging**

- FR15: Developer can add `Project` tag to all resources across all CloudFormation templates
- FR16: Developer can add `Environment` tag to all resources across all CloudFormation templates
- FR17: Developer can verify tags enable filtering in AWS Cost Explorer

**CloudFormation Improvements — SSM Pattern**

- FR18: Developer can replace `{{resolve:ssm:...}}` with `AWS::SSM::Parameter::Value<String>` in `infra/aws/cloudformation/templates/sqs-to-rds-step-function.yaml`
- FR19: Developer can verify updated template passes cfn-lint validation with zero errors

**CloudFormation Improvements — Lambda Parameterization**

- FR20: Developer can parameterize hardcoded Lambda function name `lenie-sqs-to-db` in `sqs-to-rds-step-function.yaml` DefinitionSubstitutions
- FR21: Developer can verify parameterized Lambda name resolves correctly in Step Function definition

**CloudFormation Improvements — ApiDeployment Fix**

- FR22: Developer can fix ApiDeployment pattern in `api-gw-app.yaml` to force redeployment when RestApi Body changes
- FR23: Developer can verify API Gateway redeploys automatically without manual `aws apigateway create-deployment` command

**CloudFormation Improvements — Lambda Typo Fix**

- FR24: Developer can rename Lambda function `infra-allow-ip-in-secrutity-group` to `infra-allow-ip-in-security-group` in AWS account
- FR25: Developer can update `api-gw-app.yaml` to reference corrected Lambda function name
- FR26: Developer can verify API Gateway integration references correct Lambda function after deployment

**CloudFormation Improvements — REST Compliance Review**

- FR27: Developer can review `/website_delete` GET method in `api-gw-app.yaml`
- FR28: Developer can document REST-compliant alternative (DELETE method) with frontend impact analysis
- FR29: Developer can document decision (implement now, defer, or reject) based on frontend change scope

**Reference Cleanup**

- FR30: Developer can verify zero stale references to `/ai_ask` endpoint across entire codebase
- FR31: Developer can verify zero stale references to `/translate` endpoint across entire codebase
- FR32: Developer can verify zero stale references to `/infra/ip-allow` endpoint across entire codebase
- FR33: Developer can verify zero stale references to `ai_describe_image()` function across entire codebase
- FR34: Developer can verify all modified CloudFormation templates pass cfn-lint validation with zero errors
- FR35: Developer can verify API Gateway endpoint count in documentation reflects actual count after removal

### NonFunctional Requirements

**Reliability & Safety**

- NFR1: Existing API Gateway endpoints (all except `/ai_ask`, `/translate`, `/infra/ip-allow`) continue to function correctly after template modification and redeployment
- NFR2: `ai_ask()` function in `library/ai.py` remains operational and callable by `youtube_processing.py` after `/ai_ask` endpoint removal
- NFR3: No actively used code, endpoints, or functions are removed — only confirmed-unused or broken resources
- NFR4: All cleanup operations preserve rollback capability through version control (git) and CloudFormation stack operations
- NFR5: Frontend application loads and functions after React hook modifications (`handleCorrectUsingAI`, `handleTranslate` removed or disabled)

**IaC Quality & Validation**

- NFR6: All modified CloudFormation templates pass cfn-lint validation with zero errors before deployment
- NFR7: All CloudFormation resources include Project and Environment tags for cost allocation tracking
- NFR8: CloudFormation templates use consistent patterns: `AWS::SSM::Parameter::Value<String>` instead of `{{resolve:ssm:...}}`, parameterized Lambda names instead of hardcoded values
- NFR9: ApiDeployment resource triggers redeployment automatically when RestApi Body changes (no manual `aws apigateway create-deployment` required)
- NFR10: Codebase-wide search (grep + semantic review) confirms zero stale references to removed endpoints, dead code, or incorrect numeric counts

**Documentation Quality**

- NFR11: API Gateway endpoint count in CLAUDE.md and README.md matches actual deployed count with zero discrepancies
- NFR12: No documentation file references removed endpoints (`/ai_ask`, `/translate`, `/infra/ip-allow`) or dead code (`ai_describe_image()`)
- NFR13: CloudFormation improvement decisions (implement, defer, or reject) are documented with rationale for future reference

### Additional Requirements

From Architecture document (Sprint 1/2 — applicable patterns for Sprint 3):

- All CloudFormation templates must follow the Gen 2+ canonical template pattern (Parameters → Conditions → Resources with SSM exports last)
- SSM Parameter consumption must use `AWS::SSM::Parameter::Value<String>` parameter type, NOT `{{resolve:ssm:...}}` dynamic references
- Tags `Environment` (from `!Ref Environment`) and `Project` (from `!Ref ProjectCode`) are required on all taggable resources
- Template validation with `aws cloudformation validate-template` before deployment
- cfn-lint validation before committing changes
- All descriptions and comments in English
- Resource Deletion Checklist (from Epic 7 retro): before removing any AWS resource — (1) check code references, (2) check active state in AWS, (3) check dependency chain
- Semantic review expanded beyond grep (from Epic 8/9 retro): verify numeric counts, package names, terminology consistency

### FR Coverage Map

FR1: Epic 10 - Remove `/ai_ask` from server.py
FR2: Epic 10 - Remove `/ai_ask` from Lambda internet
FR3: Epic 10 - Remove `/ai_ask` from API GW template
FR4: Epic 10 - Remove/disable `handleCorrectUsingAI()` from React
FR5: Epic 10 - Verify `ai_ask()` preserved for youtube_processing.py
FR6: Epic 10 - Remove `/translate` from Lambda internet
FR7: Epic 10 - Remove `/translate` from API GW template
FR8: Epic 10 - Remove/disable `handleTranslate()` from React
FR9: Epic 10 - Verify backend module `library.translate` does not exist
FR10: Epic 10 - Remove `/infra/ip-allow` from API GW template
FR11: Epic 10 - Delete or archive Lambda `infra-allow-ip-in-secrutity-group`
FR12: Epic 10 - Verify zero frontend references to `/infra/ip-allow`
FR13: Epic 10 - Remove `ai_describe_image()` from ai.py
FR14: Epic 10 - Verify `ai_describe_image()` has zero callers
FR15: Epic 11 - Add `Project` tag to all CF resources
FR16: Epic 11 - Add `Environment` tag to all CF resources
FR17: Epic 11 - Verify tags enable AWS Cost Explorer filtering
FR18: Epic 11 - Replace `{{resolve:ssm:...}}` with `Parameter::Value<String>` in step function
FR19: Epic 11 - Verify updated step function template passes cfn-lint
FR20: Epic 11 - Parameterize hardcoded Lambda name in step function
FR21: Epic 11 - Verify parameterized Lambda name resolves correctly
FR22: Epic 11 - Fix ApiDeployment to force redeployment on Body changes
FR23: Epic 11 - Verify API GW redeploys automatically
FR24: Epic 11 - Rename Lambda function (typo fix: secrutity → security)
FR25: Epic 11 - Update api-gw-app.yaml with corrected Lambda name
FR26: Epic 11 - Verify API GW integration references correct Lambda
FR27: Epic 11 - Review `/website_delete` GET method
FR28: Epic 11 - Document REST-compliant alternative with frontend impact
FR29: Epic 11 - Document decision (implement, defer, or reject)
FR30: Epic 12 - Verify zero stale references to `/ai_ask`
FR31: Epic 12 - Verify zero stale references to `/translate`
FR32: Epic 12 - Verify zero stale references to `/infra/ip-allow`
FR33: Epic 12 - Verify zero stale references to `ai_describe_image()`
FR34: Epic 12 - Verify all modified CF templates pass cfn-lint
FR35: Epic 12 - Verify endpoint count in docs matches actual

## Epic List

### Epic 10: Endpoint & Dead Code Removal

Developer can remove all unused endpoints and dead code from the codebase — resulting in a clean API surface with only active endpoints, while preserving the `ai_ask()` function used by `youtube_processing.py`.

**FRs covered:** FR1, FR2, FR3, FR4, FR5, FR6, FR7, FR8, FR9, FR10, FR11, FR12, FR13, FR14
**NFRs addressed:** NFR1, NFR2, NFR3, NFR4, NFR5

Implementation notes:
- Critical dependency: `ai_ask()` in `backend/library/ai.py` must be preserved (called by `youtube_processing.py`)
- `/translate` endpoint is already broken (no backend module) — removal is low-risk
- `/infra/ip-allow` Lambda has typo in name (`secrutity`) — interaction with Epic 11 FR24-FR26
- Follow Resource Deletion Checklist: (1) check code references, (2) check active state in AWS, (3) check dependency chain

### Epic 11: CloudFormation Template Improvements

Developer can bring all CloudFormation templates to production quality — consistent SSM patterns, parameterized Lambda names, cost allocation tags on all resources, automatic API Gateway redeployment, corrected naming, and documented REST compliance decisions.

**FRs covered:** FR15, FR16, FR17, FR18, FR19, FR20, FR21, FR22, FR23, FR24, FR25, FR26, FR27, FR28, FR29
**NFRs addressed:** NFR6, NFR7, NFR8, NFR9

Implementation notes:
- FR24-FR26 (Lambda typo fix) has potential interaction with Epic 10 FR10-FR11: if the Lambda is deleted in Epic 10, the rename becomes moot — resolve during story creation
- FR27-FR29 (REST compliance review) is a document-only decision — may result in defer/reject rather than implementation
- All templates must follow Gen 2+ canonical pattern (Parameters → Conditions → Resources)
- cfn-lint validation required before committing any CF changes

### Epic 12: Cross-Cutting Verification & Documentation

Developer can verify the entire codebase is in a clean state — zero stale references to removed endpoints and dead code, all modified CloudFormation templates pass cfn-lint, and documentation accurately reflects the current endpoint count and project state.

**FRs covered:** FR30, FR31, FR32, FR33, FR34, FR35
**NFRs addressed:** NFR10, NFR11, NFR12, NFR13

Implementation notes:
- Builds upon Epic 10 (endpoint/code removal) and Epic 11 (CF improvements)
- Verification must use both grep-based search AND semantic review (numeric counts, terminology consistency)
- Documentation updates include CLAUDE.md, README.md, and any infra docs referencing removed resources
- CloudFormation improvement decisions (implement/defer/reject from FR27-FR29) must be documented with rationale

---

## Epic 10: Endpoint & Dead Code Removal

### Story 10.1: Remove `/ai_ask` Endpoint

As a **developer**,
I want to remove the `/ai_ask` endpoint from backend, Lambda, API Gateway, and frontend,
So that the API surface contains only active endpoints while preserving the `ai_ask()` function used by `youtube_processing.py`.

**Acceptance Criteria:**

**Given** the `/ai_ask` endpoint exists in `backend/server.py`
**When** the developer removes the route definition
**Then** `server.py` no longer exposes `/ai_ask`
**And** `ai_ask()` function in `backend/library/ai.py` remains intact and callable

**Given** the `/ai_ask` endpoint exists in `infra/aws/serverless/app-server-internet/lambda_function.py`
**When** the developer removes the route handler
**Then** the Lambda function no longer handles `/ai_ask` requests

**Given** the `/ai_ask` endpoint is defined in `infra/aws/cloudformation/templates/api-gw-app.yaml`
**When** the developer removes the endpoint definition
**Then** the API Gateway template no longer includes `/ai_ask` path

**Given** `handleCorrectUsingAI()` in `web_interface_react/src/hooks/useManageLLM.js` calls `/ai_ask`
**When** the developer removes or disables the function
**Then** the React frontend loads without errors
**And** no frontend code references `/ai_ask`

**Given** `ai_ask()` is called by `backend/imports/youtube_processing.py`
**When** the developer verifies the call chain
**Then** `youtube_processing.py` successfully imports and calls `ai_ask()` without errors

**FRs covered:** FR1, FR2, FR3, FR4, FR5

### Story 10.2: Remove `/translate` Endpoint

As a **developer**,
I want to remove the `/translate` endpoint from Lambda, API Gateway, and frontend,
So that the broken endpoint no longer appears in the API surface.

**Acceptance Criteria:**

**Given** the `/translate` endpoint exists in `infra/aws/serverless/app-server-internet/lambda_function.py`
**When** the developer removes the route handler
**Then** the Lambda function no longer handles `/translate` requests

**Given** the `/translate` endpoint is defined in `infra/aws/cloudformation/templates/api-gw-app.yaml`
**When** the developer removes the endpoint definition
**Then** the API Gateway template no longer includes `/translate` path

**Given** `handleTranslate()` in `web_interface_react/src/hooks/useManageLLM.js` calls `/translate`
**When** the developer removes or disables the function
**Then** the React frontend loads without errors
**And** no frontend code references `/translate`

**Given** the backend has no `library.translate` module
**When** the developer verifies the backend codebase
**Then** zero references to `library.translate` exist (confirming endpoint was already broken)

**FRs covered:** FR6, FR7, FR8, FR9

### Story 10.3: Remove `/infra/ip-allow` Endpoint

As a **developer**,
I want to remove the `/infra/ip-allow` endpoint from API Gateway and delete/archive its Lambda function,
So that the unused infrastructure endpoint and its Lambda are cleaned up.

**Acceptance Criteria:**

**Given** the `/infra/ip-allow` endpoint is defined in `infra/aws/cloudformation/templates/api-gw-app.yaml`
**When** the developer removes the endpoint definition
**Then** the API Gateway template no longer includes `/infra/ip-allow` path

**Given** the Lambda function `infra-allow-ip-in-secrutity-group` exists in AWS
**When** the developer deletes or archives the Lambda function
**Then** the function no longer runs in AWS
**And** the Resource Deletion Checklist was followed: (1) code references checked, (2) active state verified, (3) dependency chain reviewed

**Given** the `/infra/ip-allow` endpoint may be referenced in frontend code
**When** the developer searches the entire frontend codebase
**Then** zero references to `/infra/ip-allow` exist

**FRs covered:** FR10, FR11, FR12

### Story 10.4: Remove `ai_describe_image()` Dead Code

As a **developer**,
I want to remove the `ai_describe_image()` function from `backend/library/ai.py`,
So that the codebase contains no dead code.

**Acceptance Criteria:**

**Given** `ai_describe_image()` exists in `backend/library/ai.py`
**When** the developer searches the entire codebase for callers
**Then** zero callers of `ai_describe_image()` are found

**Given** `ai_describe_image()` has zero callers
**When** the developer removes the function
**Then** `backend/library/ai.py` no longer contains `ai_describe_image()`
**And** all remaining functions in `ai.py` continue to work (especially `ai_ask()`)

**FRs covered:** FR13, FR14

---

## Epic 11: CloudFormation Template Improvements

### Story 11.1: Add Project and Environment Tags to All CloudFormation Templates

As a **developer**,
I want to add `Project` and `Environment` tags to all resources across all CloudFormation templates,
So that AWS Cost Explorer can filter costs by project and environment.

**Acceptance Criteria:**

**Given** CloudFormation templates exist in `infra/aws/cloudformation/templates/`
**When** the developer adds `Project` (from `!Ref ProjectCode`) and `Environment` (from `!Ref Environment`) tags to all taggable resources
**Then** every resource in every template includes both tags

**Given** templates may not have `ProjectCode` and `Environment` parameters
**When** the developer adds missing parameters
**Then** parameters follow the Gen 2+ canonical pattern (Parameters section at top)
**And** parameter files in `infra/aws/cloudformation/parameters/dev/` are updated with values

**Given** all templates are updated with tags
**When** the developer runs cfn-lint validation
**Then** all templates pass with zero errors

**FRs covered:** FR15, FR16, FR17

### Story 11.2: Improve Step Function Template — SSM Pattern and Lambda Parameterization

As a **developer**,
I want to replace `{{resolve:ssm:...}}` with `AWS::SSM::Parameter::Value<String>` and parameterize the hardcoded Lambda name in `sqs-to-rds-step-function.yaml`,
So that the template follows consistent SSM and parameterization patterns established in Sprint 1.

**Acceptance Criteria:**

**Given** `sqs-to-rds-step-function.yaml` uses `{{resolve:ssm:...}}` dynamic references
**When** the developer replaces them with `AWS::SSM::Parameter::Value<String>` parameter type
**Then** SSM values are resolved at deploy time via CloudFormation parameters
**And** the template follows the project-standard SSM consumption pattern

**Given** the Lambda function name `lenie-sqs-to-db` is hardcoded in `DefinitionSubstitutions`
**When** the developer creates a parameter for the Lambda name
**Then** the Lambda name is configurable via parameter
**And** the Step Function definition resolves the parameterized name correctly

**Given** both changes are applied
**When** the developer runs cfn-lint validation
**Then** the template passes with zero errors

**FRs covered:** FR18, FR19, FR20, FR21

### Story 11.3: Fix ApiDeployment Pattern for Automatic Redeployment

As a **developer**,
I want to fix the `ApiDeployment` resource in `api-gw-app.yaml` to force redeployment when RestApi Body changes,
So that API Gateway redeploys automatically without requiring manual `aws apigateway create-deployment`.

**Acceptance Criteria:**

**Given** the current `ApiDeployment` resource does not trigger redeployment on Body changes
**When** the developer applies a fix (hash/timestamp in logical ID, or separate `AWS::ApiGateway::Stage` resource)
**Then** CloudFormation creates a new deployment when the RestApi Body is modified

**Given** the fix is applied
**When** the developer modifies the API Gateway template and deploys
**Then** the API Gateway automatically reflects the changes
**And** no manual `aws apigateway create-deployment` command is required

**Given** the template is modified
**When** the developer runs cfn-lint validation
**Then** the template passes with zero errors

**FRs covered:** FR22, FR23

### Story 11.4: Resolve Lambda Function Name Typo

As a **developer**,
I want to resolve the Lambda function name typo (`secrutity` → `security`),
So that no misspelled resource names remain in the infrastructure.

**Acceptance Criteria:**

**Given** Epic 10 Story 10.3 removes `/infra/ip-allow` endpoint and deletes/archives the Lambda `infra-allow-ip-in-secrutity-group`
**When** the developer verifies the outcome of Epic 10
**Then** one of two paths applies:

*Path A — Lambda deleted:*
**Given** the Lambda was deleted in Epic 10
**When** the developer searches the entire codebase for `secrutity`
**Then** zero references to the misspelled name remain
**And** FR24-FR26 are satisfied by removal

*Path B — Lambda archived (kept in AWS):*
**Given** the Lambda was archived but not deleted
**When** the developer renames the Lambda to `infra-allow-ip-in-security-group`
**Then** the corrected name is used in all references
**And** `api-gw-app.yaml` references the correct function name (if endpoint was preserved)

**FRs covered:** FR24, FR25, FR26

### Story 11.5: REST Compliance Review for `/website_delete`

As a **developer**,
I want to review the `/website_delete` GET method and document a REST-compliant alternative,
So that a decision is made and documented for future reference.

**Acceptance Criteria:**

**Given** `/website_delete` uses HTTP GET for a destructive operation in `api-gw-app.yaml`
**When** the developer reviews the endpoint
**Then** a document is created with: (1) current implementation, (2) REST-compliant alternative (DELETE method), (3) frontend impact analysis

**Given** the review is complete
**When** the developer evaluates the change scope
**Then** a decision is documented: implement now, defer to future sprint, or reject
**And** the rationale is recorded for future reference

**Given** the decision is "defer" or "reject"
**When** no code changes are made
**Then** the current GET method continues to function unchanged

**FRs covered:** FR27, FR28, FR29

---

## Epic 12: Cross-Cutting Verification & Documentation

### Story 12.1: Codebase-Wide Stale Reference Verification

As a **developer**,
I want to verify zero stale references to removed endpoints and dead code across the entire codebase,
So that no orphaned references cause confusion or runtime errors.

**Acceptance Criteria:**

**Given** `/ai_ask` endpoint was removed in Epic 10
**When** the developer searches the entire codebase (grep + semantic review)
**Then** zero stale references to `/ai_ask` as an endpoint remain
**And** legitimate uses of `ai_ask()` function (in `ai.py`, `youtube_processing.py`) are confirmed intact

**Given** `/translate` endpoint was removed in Epic 10
**When** the developer searches the entire codebase
**Then** zero stale references to `/translate` endpoint remain

**Given** `/infra/ip-allow` endpoint was removed in Epic 10
**When** the developer searches the entire codebase
**Then** zero stale references to `/infra/ip-allow` remain
**And** zero references to `infra-allow-ip-in-secrutity-group` (misspelled) remain

**Given** `ai_describe_image()` was removed in Epic 10
**When** the developer searches the entire codebase
**Then** zero references to `ai_describe_image` remain

**Given** all searches are complete
**When** the developer performs semantic review beyond grep
**Then** numeric counts (e.g., "19 endpoints" in CLAUDE.md), package names, and terminology are verified for consistency

**FRs covered:** FR30, FR31, FR32, FR33

### Story 12.2: CloudFormation Validation and Documentation Update

As a **developer**,
I want to validate all modified CloudFormation templates and update documentation to reflect the current state,
So that the project documentation is accurate and all templates are deployment-ready.

**Acceptance Criteria:**

**Given** CloudFormation templates were modified in Epic 10 and Epic 11
**When** the developer runs cfn-lint on all modified templates
**Then** all templates pass with zero errors

**Given** endpoints were removed (3 fewer endpoints)
**When** the developer reviews CLAUDE.md and README.md
**Then** the API Gateway endpoint count matches the actual deployed count
**And** no documentation references `/ai_ask`, `/translate`, `/infra/ip-allow`, or `ai_describe_image()`

**Given** CloudFormation improvement decisions were made in Epic 11 (especially Story 11.5 REST review)
**When** the developer reviews documentation
**Then** all decisions (implement, defer, reject) are documented with rationale

**Given** all updates are complete
**When** the developer performs a final review
**Then** CLAUDE.md, README.md, and infra docs accurately reflect the post-Sprint 3 state

**FRs covered:** FR34, FR35
