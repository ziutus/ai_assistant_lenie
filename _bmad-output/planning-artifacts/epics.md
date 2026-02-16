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

This document provides the complete epic and story breakdown for lenie-server-2025 Sprint 2 (Cleanup & Vision Documentation), decomposing the requirements from the PRD and Architecture into implementable stories.

## Requirements Inventory

### Functional Requirements

**AWS Resource Removal**

- FR1: Developer can delete 3 DynamoDB cache tables (`lenie_cache_ai_query`, `lenie_cache_language`, `lenie_cache_translation`) from AWS account
- FR2: Developer can delete the CloudFormation stacks associated with the 3 DynamoDB cache tables
- FR3: Developer can update the Step Function `sqs-to-rds` schedule to 5:00 AM Warsaw time (Europe/Warsaw timezone) and redeploy the CF stack
- FR4: Developer can delete SSM Parameters associated with removed DynamoDB tables

**CloudFormation Template & Configuration Cleanup**

- FR5: Developer can remove 3 DynamoDB CF templates from `infra/aws/cloudformation/templates/`
- FR6: Developer can remove 3 DynamoDB parameter files from `infra/aws/cloudformation/parameters/dev/`
- FR7: Developer can remove DynamoDB cache table entries from `deploy.ini`
- ~~FR8: Developer can remove Step Function entry from `deploy.ini`~~ *(withdrawn — Step Function retained)*
- FR9: Developer can remove `/url_add2` endpoint and associated Step Function parameters from `api-gw-app.yaml`
- FR10: Developer can redeploy API Gateway after template modification (via S3 upload workflow)

**Code Archival**

- ~~FR11: Developer can archive the Step Function CF template~~ *(withdrawn — Step Function retained)*
- ~~FR12: Developer can archive the Step Function state machine definition~~ *(withdrawn — Step Function retained)*
- ~~FR13: Archived files include a README for Step Function~~ *(withdrawn — Step Function retained)*

**Reference Cleanup**

- FR14: Developer can verify zero stale references to removed DynamoDB tables across entire codebase
- ~~FR15: Developer can verify zero stale references to removed Step Function~~ *(withdrawn — Step Function retained)*
- FR16: Developer can verify zero stale references to `/url_add2` endpoint across entire codebase
- FR17: Developer can run `cfn-lint` on all modified CF templates and receive zero errors

**Documentation Updates**

- FR18: Developer can update README.md with project vision: Lenie-AI as MCP server for Claude Desktop + Obsidian vault workflow
- FR19: Developer can update README.md with phased roadmap (current state -> MCP server -> Obsidian integration)
- FR20: Developer can update CLAUDE.md to reflect current project state after cleanup
- FR21: Developer can update `infra/aws/README.md` to remove references to deleted resources
- FR22: Developer can update any other documentation files that reference removed resources

### NonFunctional Requirements

**Reliability & Safety**

- NFR1: Existing API Gateway endpoints (all except `/url_add2`) continue to function correctly after template modification and redeployment
- NFR2: No actively used AWS resources are affected by the cleanup — only confirmed-unused resources are removed
- ~~NFR3: Step Function code is archived and retrievable before AWS stack deletion~~ *(withdrawn — Step Function retained)*
- NFR4: All cleanup operations are performed through CloudFormation (IaC-managed) to ensure consistent, repeatable, and rollback-capable changes

**IaC Quality & Validation**

- NFR5: All modified CloudFormation templates pass `cfn-lint` validation with zero errors before deployment
- NFR6: Codebase-wide search (grep) confirms zero stale references to removed resources after cleanup
- NFR7: `deploy.ini` contains only entries for active, deployable templates — zero commented-out or dead entries for removed resources

**Documentation Quality**

- NFR8: README.md contains: project purpose, current architecture summary, target vision (MCP server + Obsidian), and phased roadmap — readable without consulting other files
- NFR9: No documentation file references resources that no longer exist in AWS or in the codebase

### Additional Requirements

**From Architecture Document (Sprint 1 technical context relevant to Sprint 2 cleanup):**

- `api-gw-app.yaml` exceeds 51200 byte inline limit — requires S3 upload for CloudFormation deployment (`aws cloudformation package` -> S3 -> deploy). This constraint applies when modifying and redeploying the API Gateway template (FR9, FR10)
- `deploy.ini` uses an 8-layer deployment model; DynamoDB cache entries are in Layer 4 (Storage), Step Function entry is in Layer 7 (Orchestration). Entries must be removed from correct positions
- SSM Parameters follow path pattern `/${ProjectCode}/${Environment}/<service>/<resource-name>/<attribute>` — removal of SSM Parameters for deleted resources (FR4) must target this pattern
- CF stack deletion should follow dependency-aware order — Layer 7 (Step Function) before Layer 4 (DynamoDB) if dependencies exist
- Template validation via `aws cloudformation validate-template` is the established procedure for modified templates
- The 3 DynamoDB cache tables were confirmed unused by production code (backend has zero references) — safe for deletion
- `lenie_dev_documents` DynamoDB table is actively used and explicitly excluded from cleanup
- Step Function `sqs-to-rds` is actively used for cost optimization (auto start/stop RDS) and must be retained

### FR Coverage Map

| FR | Epic | Description |
|---|---|---|
| FR1 | Epic 2 | Delete 3 DynamoDB cache tables from AWS |
| FR2 | Epic 2 | Delete CF stacks for DynamoDB cache tables |
| FR3 | Epic 1 | Update Step Function schedule to 5:00 AM Warsaw time |
| FR4 | Epic 2 | Delete SSM Parameters (DynamoDB cache tables) |
| FR5 | Epic 2 | Remove 3 DynamoDB CF templates from repo |
| FR6 | Epic 2 | Remove 3 DynamoDB parameter files from repo |
| FR7 | Epic 2 | Remove DynamoDB entries from deploy.ini |
| ~~FR8~~ | ~~Epic 1~~ | ~~Remove Step Function entry from deploy.ini~~ *(withdrawn)* |
| FR9 | Epic 1 | Remove `/url_add2` from api-gw-app.yaml |
| FR10 | Epic 1 | Redeploy API Gateway after template modification |
| ~~FR11~~ | ~~Epic 1~~ | ~~Archive Step Function CF template~~ *(withdrawn)* |
| ~~FR12~~ | ~~Epic 1~~ | ~~Archive Step Function state machine definition~~ *(withdrawn)* |
| ~~FR13~~ | ~~Epic 1~~ | ~~README for archived Step Function files~~ *(withdrawn)* |
| FR14 | Epic 2 | Verify zero stale DynamoDB cache table references |
| ~~FR15~~ | ~~Epic 1~~ | ~~Verify zero stale Step Function references~~ *(withdrawn)* |
| FR16 | Epic 1 | Verify zero stale `/url_add2` references |
| FR17 | Epic 1 | cfn-lint on modified api-gw-app.yaml |
| FR18 | Epic 3 | README with MCP server + Obsidian vision |
| FR19 | Epic 3 | README with phased roadmap |
| FR20 | Epic 3 | Update CLAUDE.md to reflect current state |
| FR21 | Epic 3 | Update infra/aws/README.md |
| FR22 | Epic 3 | Update other docs referencing removed resources |

## Epic List

### Epic 1: Step Function Update & API Gateway Simplification
Developer updates the `sqs-to-rds` Step Function schedule to 5:00 AM Warsaw time (Europe/Warsaw timezone), removes the `/url_add2` endpoint from API Gateway, and redeploys — preserving the cost-optimization workflow while cleaning the unused API endpoint.
**FRs covered:** FR3 (update schedule), FR9, FR10, FR16, FR17
**NFRs:** NFR1 (existing endpoints work), NFR4 (CF-managed ops), NFR5 (cfn-lint pass)
**Dependencies:** None — standalone epic.

### Epic 2: DynamoDB Cache Table Removal
Developer removes 3 unused DynamoDB cache tables (`lenie_cache_ai_query`, `lenie_cache_language`, `lenie_cache_translation`) from AWS, deletes all related CloudFormation templates, parameter files, deploy.ini entries, and SSM Parameters — eliminating unnecessary costs and dead infrastructure.
**FRs covered:** FR1, FR2, FR4 (DynamoDB SSM params), FR5, FR6, FR7, FR14
**NFRs:** NFR2 (only unused resources), NFR4 (CF-managed ops), NFR6 (grep zero refs), NFR7 (clean deploy.ini)
**Dependencies:** None — standalone epic. Independent of Epic 1.

### Epic 3: Project Vision & Documentation Update
Developer can read README.md to understand the target architecture (Lenie-AI as MCP server for Claude Desktop + Obsidian vault) and phased roadmap. All documentation accurately reflects the current state after cleanup.
**FRs covered:** FR18, FR19, FR20, FR21, FR22
**NFRs:** NFR8 (README with vision and roadmap), NFR9 (no stale doc references)
**Dependencies:** Best done after Epic 1 and 2 (to reflect post-cleanup state), but FR18-FR19 (vision/roadmap) can be written independently.

## Epic 1: Step Function Update & API Gateway Simplification

Developer updates the `sqs-to-rds` Step Function schedule to 5:00 AM Warsaw time (Europe/Warsaw timezone), removes the `/url_add2` endpoint from API Gateway, and redeploys — preserving the cost-optimization workflow while cleaning the unused API endpoint.

### Story 1.1: Update Step Function Schedule to Warsaw Time

As a developer,
I want to update the Step Function `sqs-to-rds` EventBridge schedule to run at 5:00 AM Warsaw time with explicit `Europe/Warsaw` timezone,
So that the SQS-to-RDS cost-optimization workflow runs at a predictable local time regardless of DST changes.

**Acceptance Criteria:**

**Given** the Step Function CF template (`sqs-to-rds-step-function.yaml`) uses a UTC-based cron schedule without explicit timezone
**When** developer updates the CloudFormation template and parameters
**Then** `ScheduleExpressionTimezone: "Europe/Warsaw"` is added to the `EventBridgeScheduler` resource in the CF template (FR3)
**And** the cron expression in `parameters/dev/sqs-to-rds-step-function.json` is updated to `cron(0 5 * * ? *)` (5:00 AM)
**And** the CF stack is redeployed and the EventBridge Schedule is active with the new timezone and schedule
**And** all 5 resources (StateMachine, StateMachineRole, StateMachineLogGroup, StepFunctionInvokerRole, EventBridgeScheduler) are operational

### Story 1.2: Remove `/url_add2` Endpoint from API Gateway & Redeploy

As a developer,
I want to remove the `/url_add2` endpoint and its associated Step Function parameters from `api-gw-app.yaml`, validate the template, and redeploy the API Gateway,
So that the API Gateway no longer exposes a dead endpoint and all existing endpoints continue to function correctly.

**Acceptance Criteria:**

**Given** the `api-gw-app.yaml` template contains the `/url_add2` endpoint definition and Step Function integration parameters
**When** developer modifies the API Gateway template
**Then** the `/url_add2` endpoint resource, method, and integration are removed from `api-gw-app.yaml` (FR9)
**And** any Step Function-related parameters (ARN, role) referenced only by `/url_add2` are removed from the template (FR9)
**And** the modified template passes `cfn-lint` validation with zero errors (FR17, NFR5)
**And** the modified template passes `aws cloudformation validate-template` validation

**Given** the modified template is validated
**When** developer redeploys the API Gateway via S3 upload workflow (`aws cloudformation package` -> S3 -> deploy)
**Then** the API Gateway is redeployed successfully without errors (FR10)
**And** all existing API Gateway endpoints (except `/url_add2`) continue to function correctly (NFR1)
**And** codebase-wide grep confirms zero stale references to `/url_add2` (FR16, NFR6)

## Epic 2: DynamoDB Cache Table Removal

Developer removes 3 unused DynamoDB cache tables (`lenie_cache_ai_query`, `lenie_cache_language`, `lenie_cache_translation`) from AWS, deletes all related CloudFormation templates, parameter files, deploy.ini entries, and SSM Parameters — eliminating unnecessary costs and dead infrastructure.

### Story 2.1: Delete DynamoDB Cache Tables & Remove All Related Artifacts

As a developer,
I want to delete the 3 unused DynamoDB cache tables (`lenie_cache_ai_query`, `lenie_cache_language`, `lenie_cache_translation`) from AWS and remove all related CloudFormation templates, parameter files, deploy.ini entries, and SSM Parameters,
So that the AWS account no longer contains unused cache tables generating costs, and the codebase has no dead infrastructure artifacts.

**Acceptance Criteria:**

**Given** the 3 DynamoDB cache tables are confirmed unused by production code (backend has zero references) and `lenie_dev_documents` is explicitly excluded
**When** developer deletes the CloudFormation stacks
**Then** the CF stacks for `lenie_cache_ai_query`, `lenie_cache_language`, and `lenie_cache_translation` are deleted from AWS via CF stack delete operations (FR1, FR2, NFR4)
**And** all SSM Parameters associated with the 3 DynamoDB cache tables (path pattern `/${ProjectCode}/${Environment}/dynamodb/cache-*/`) are deleted from AWS (FR4)
**And** the `lenie_dev_documents` DynamoDB table and its CF stack are NOT affected (NFR2)

**Given** the AWS resources are deleted
**When** developer removes the codebase artifacts
**Then** the 3 CF templates (`dynamodb-cache-ai-query.yaml`, `dynamodb-cache-language.yaml`, `dynamodb-cache-translation.yaml`) are deleted from `infra/aws/cloudformation/templates/` (FR5)
**And** the 3 parameter files (`dynamodb-cache-ai-query.json`, `dynamodb-cache-language.json`, `dynamodb-cache-translation.json`) are deleted from `infra/aws/cloudformation/parameters/dev/` (FR6)
**And** the 3 DynamoDB cache table entries are removed from `deploy.ini` Layer 4 (Storage) section (FR7)
**And** `deploy.ini` contains no commented-out or dead entries for the removed tables (NFR7)
**And** codebase-wide grep confirms zero stale references to `lenie_cache_ai_query`, `lenie_cache_language`, and `lenie_cache_translation` (FR14, NFR6)

## Epic 3: Project Vision & Documentation Update

Developer can read README.md to understand the target architecture (Lenie-AI as MCP server for Claude Desktop + Obsidian vault) and phased roadmap. All documentation accurately reflects the current state after cleanup.

### Story 3.1: Update README.md with Project Vision & Roadmap

As a developer (or future contributor),
I want to read README.md and understand the project's target architecture (Lenie-AI as MCP server for Claude Desktop + Obsidian vault) and phased roadmap,
So that I know where the project is heading and can plan contributions accordingly.

**Acceptance Criteria:**

**Given** the current README.md does not describe the project's future direction
**When** developer updates README.md
**Then** README.md contains a clear description of the target vision: Lenie-AI as an MCP server for Claude Desktop + Obsidian vault workflow (FR18)
**And** README.md contains a phased roadmap: current state -> MCP server foundation -> Obsidian integration (FR19)
**And** README.md contains: project purpose, current architecture summary, target vision, and phased roadmap — readable without consulting other files (NFR8)
**And** README.md is self-contained — a new developer can understand the project's purpose and direction from this single file

### Story 3.2: Update Documentation to Reflect Post-Cleanup State

As a developer,
I want all documentation files to accurately reflect the current state of the project after cleanup (no references to deleted DynamoDB cache tables, Step Function, or `/url_add2`),
So that no documentation misleads about resources that no longer exist.

**Acceptance Criteria:**

**Given** Epic 1 and Epic 2 cleanup is complete and AWS resources have been removed
**When** developer updates documentation files
**Then** CLAUDE.md is updated to reflect the current project state — no references to removed DynamoDB cache tables or `/url_add2` (FR20)
**And** `infra/aws/README.md` is updated to remove references to deleted resources (FR21)
**And** any other documentation files referencing removed resources are updated or corrected (FR22)
**And** no documentation file in the repository references resources that no longer exist in AWS or in the codebase (NFR9)
