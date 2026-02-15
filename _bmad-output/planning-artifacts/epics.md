---
stepsCompleted:
  - step-01-validate-prerequisites
  - step-02-design-epics
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
- FR3: Developer can delete the Step Function `sqs-to-rds` CloudFormation stack from AWS account
- FR4: Developer can delete SSM Parameters associated with removed DynamoDB tables and Step Function

**CloudFormation Template & Configuration Cleanup**

- FR5: Developer can remove 3 DynamoDB CF templates from `infra/aws/cloudformation/templates/`
- FR6: Developer can remove 3 DynamoDB parameter files from `infra/aws/cloudformation/parameters/dev/`
- FR7: Developer can remove DynamoDB cache table entries from `deploy.ini`
- FR8: Developer can remove Step Function entry from `deploy.ini`
- FR9: Developer can remove `/url_add2` endpoint and associated Step Function parameters from `api-gw-app.yaml`
- FR10: Developer can redeploy API Gateway after template modification (via S3 upload workflow)

**Code Archival**

- FR11: Developer can archive the Step Function CF template (`sqs-to-rds-step-function.yaml`) to `infra/archive/`
- FR12: Developer can archive the Step Function state machine definition (`sqs_to_rds.json`) to `infra/archive/`
- FR13: Archived files include a README explaining the Step Function's purpose, original deployment location, and dependencies

**Reference Cleanup**

- FR14: Developer can verify zero stale references to removed DynamoDB tables across entire codebase
- FR15: Developer can verify zero stale references to removed Step Function across entire codebase
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
- NFR3: Step Function code is archived and retrievable before AWS stack deletion
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
- Step Function `sqs-to-rds` code should be preserved (archived) for potential future reuse before AWS stack deletion

### FR Coverage Map

| FR | Epic | Description |
|---|---|---|
| FR1 | Epic 2 | Delete 3 DynamoDB cache tables from AWS |
| FR2 | Epic 2 | Delete CF stacks for DynamoDB cache tables |
| FR3 | Epic 1 | Delete Step Function CF stack from AWS |
| FR4 | Epic 1 + 2 | Delete SSM Parameters (Step Function in E1, DynamoDB in E2) |
| FR5 | Epic 2 | Remove 3 DynamoDB CF templates from repo |
| FR6 | Epic 2 | Remove 3 DynamoDB parameter files from repo |
| FR7 | Epic 2 | Remove DynamoDB entries from deploy.ini |
| FR8 | Epic 1 | Remove Step Function entry from deploy.ini |
| FR9 | Epic 1 | Remove `/url_add2` from api-gw-app.yaml |
| FR10 | Epic 1 | Redeploy API Gateway after template modification |
| FR11 | Epic 1 | Archive Step Function CF template to infra/archive/ |
| FR12 | Epic 1 | Archive Step Function state machine definition to infra/archive/ |
| FR13 | Epic 1 | README for archived Step Function files |
| FR14 | Epic 2 | Verify zero stale DynamoDB cache table references |
| FR15 | Epic 1 | Verify zero stale Step Function references |
| FR16 | Epic 1 | Verify zero stale `/url_add2` references |
| FR17 | Epic 1 | cfn-lint on modified api-gw-app.yaml |
| FR18 | Epic 3 | README with MCP server + Obsidian vision |
| FR19 | Epic 3 | README with phased roadmap |
| FR20 | Epic 3 | Update CLAUDE.md to reflect current state |
| FR21 | Epic 3 | Update infra/aws/README.md |
| FR22 | Epic 3 | Update other docs referencing removed resources |

## Epic List

### Epic 1: Step Function Cleanup & API Gateway Simplification
Developer safely archives the unfinished `sqs-to-rds` Step Function code and removes all related AWS resources (CF stack, SSM Parameters), the `/url_add2` endpoint from API Gateway, and deploy.ini entries — resulting in a cleaner API and reduced AWS costs.
**FRs covered:** FR3, FR4 (Step Function SSM params), FR8, FR9, FR10, FR11, FR12, FR13, FR15, FR16, FR17
**NFRs:** NFR1 (existing endpoints work), NFR3 (archive before delete), NFR4 (CF-managed ops), NFR5 (cfn-lint pass)
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
