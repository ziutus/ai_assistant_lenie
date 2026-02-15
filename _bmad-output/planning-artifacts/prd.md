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
workflowType: 'prd'
---

# Product Requirements Document - lenie-server-2025

**Author:** Ziutus
**Date:** 2026-02-15
**Sprint:** 2 — Cleanup & Vision Documentation

## Executive Summary

Lenie-server-2025 is a personal AI knowledge management system for collecting, managing, and searching press articles, web content, and YouTube transcriptions using LLMs and vector similarity search (PostgreSQL + pgvector).

**This sprint** focuses on AWS infrastructure cleanup and project vision documentation. Sprint 1 achieved 100% IaC coverage (6 epics, 10 stories). Sprint 2 removes unused resources (3 DynamoDB cache tables, 1 Step Function), cleans the API Gateway template, and documents the project's future direction.

**Target vision:** Private knowledge base in Obsidian vault, managed by Claude Desktop, powered by Lenie-AI as an MCP server for searching and managing content. This sprint prepares the codebase for that transformation.

## Success Criteria

### User Success (Developer Experience)

- Developer sees only active, used templates in deploy.ini — zero dead entries
- README.md communicates project vision: Lenie-AI as MCP server for Claude Desktop + Obsidian vault
- Codebase contains no references to non-existent AWS resources
- Archived Step Function code is preserved and accessible for potential future reuse

### Business Success

- Lower AWS costs through elimination of unused DynamoDB tables, Step Function, and associated CloudWatch logs
- Cleaner project — easier onboarding and maintenance
- Project conceptually prepared for MCP server transformation

### Technical Success

- 3 DynamoDB cache tables deleted from AWS and CloudFormation
- Step Function `sqs-to-rds` archived (code preserved) and deleted from AWS
- Endpoint `/url_add2` removed from API Gateway template
- Zero stale references remaining (SSM Parameters, IAM policies, deploy.ini, docs)
- All CF templates validate without errors after changes

### Measurable Outcomes

- 3 DynamoDB tables deleted from AWS
- 3 CF templates + 3 parameter files removed
- 1 Step Function stack deleted from AWS
- `/url_add2` endpoint removed from API Gateway template
- 0 stale references in codebase (verified by grep)
- README.md updated with project vision and roadmap

## Product Scope

### Phase 1 — This Sprint (Cleanup & Vision Documentation)

1. **DynamoDB Cache Table Removal** — Delete 3 tables (`lenie_cache_ai_query`, `lenie_cache_language`, `lenie_cache_translation`) from AWS, remove CF templates, parameter files, deploy.ini entries, SSM Parameters, and all documentation references
2. **Step Function Archival** — Move `sqs-to-rds` CF template and state machine definition to `infra/archive/`, delete AWS stack, clean all references
3. **API Gateway `/url_add2` Removal** — Remove endpoint and associated Step Function parameters from `api-gw-app.yaml`, redeploy
4. **README.md Vision Update** — Document project direction: Lenie-AI as MCP server for Claude Desktop + Obsidian vault workflow
5. **Documentation Consistency** — Update CLAUDE.md, deploy.ini, infra docs to reflect current state

### Phase 2 (Future — MCP Server Foundation)

- Implement MCP server protocol — expose search/retrieve endpoints as MCP tools
- Claude Desktop integration — configure Lenie-AI as MCP server in Claude Desktop
- API adaptation — adjust endpoint patterns for MCP tool consumption

### Phase 3 (Future — Obsidian Integration)

- Obsidian vault integration — synchronization, linking, note creation
- Semantic search from within Obsidian via Claude Desktop + MCP
- Advanced vector search refinements for personal knowledge management

## User Journeys

### Journey 1: Developer Cleanup Sprint

**Persona:** Ziutus — sole developer and project owner, intermediate skill level.

**Opening Scene:** Ziutus opens the project after completing Sprint 1 (IaC Coverage). The deploy.ini contains entries for unused resources, 3 DynamoDB cache tables sit empty in AWS generating costs, and an unfinished Step Function `sqs-to-rds` lingers in the codebase. The README.md says nothing about the project's future direction.

**Rising Action:** Ziutus identifies resources for removal, archives the Step Function code for potential future reuse, deletes the 3 DynamoDB cache tables, removes the `/url_add2` endpoint from the API Gateway template, and systematically cleans all references across CF templates, deploy.ini, SSM Parameters, and documentation.

**Climax:** After a codebase-wide grep — zero stale references remain. All CF templates validate cleanly. The API Gateway operates without `/url_add2`. The Step Function code is safely archived.

**Resolution:** The project is clean. README.md clearly communicates the vision: Lenie-AI as an MCP server for Claude Desktop + Obsidian vault. AWS costs have dropped. The project is ready for its next chapter — MCP server transformation.

### Journey 2: Future Developer Onboarding

**Persona:** A new developer (or Ziutus returning after months away) opening the project for the first time.

**Opening Scene:** The developer opens README.md to understand the project's purpose and current state.

**Rising Action:** README clearly describes the current state, target architecture (MCP server), and the Obsidian vault + Claude Desktop workflow vision. deploy.ini contains only active templates. No documentation references non-existent resources.

**Resolution:** The developer understands the project, its direction, and its current state without confusing dead references or unclear purpose.

### Journey Requirements Summary

| Journey | Capabilities Required |
|---------|----------------------|
| Developer Cleanup | AWS resource deletion, CF template removal, deploy.ini update, API GW template update, codebase-wide reference cleanup, SSM Parameter cleanup |
| Developer Cleanup | Step Function archival (preserve code, delete AWS resources) |
| Developer Cleanup | Documentation updates (README vision, CLAUDE.md, infra docs) |
| Future Onboarding | Clear README with project vision and roadmap |
| Future Onboarding | Clean deploy.ini with only active templates |
| Future Onboarding | No stale references anywhere in codebase or docs |

## Web App Technical Context

Brownfield web application: React 18 SPA (CloudFront + S3) + Flask REST API (API Gateway + Lambda) + PostgreSQL 17 with pgvector (RDS). No new web features in this sprint — cleanup only.

**Key constraint:** `api-gw-app.yaml` exceeds 51200 byte inline limit — requires S3 upload for CloudFormation deployment (`aws cloudformation package` → S3 → deploy).

**Deletion safety:** 3 DynamoDB cache tables confirmed unused by production code (backend has zero references). `lenie_dev_documents` table is actively used and explicitly excluded from cleanup. AWS resource deletion must follow dependency-aware order and use CF stack operations for rollback capability.

## Risk Mitigation

**Technical Risks:**
- *API Gateway template size* — Mitigated by established S3 upload workflow from Sprint 1
- *Stale references after deletion* — Mitigated by codebase-wide grep verification (proven in Sprint 1)
- *Accidental deletion of active resources* — Mitigated by confirmed analysis: cache tables unused, `lenie_dev_documents` explicitly excluded

**Resource Risks:**
- *Context loss between sessions* — Mitigated by detailed story files and BMad Method tracking
- *AWS resource deletion irreversibility* — Mitigated by archiving Step Function code before deletion; DynamoDB tables confirmed empty

## Functional Requirements

### AWS Resource Removal

- FR1: Developer can delete 3 DynamoDB cache tables (`lenie_cache_ai_query`, `lenie_cache_language`, `lenie_cache_translation`) from AWS account
- FR2: Developer can delete the CloudFormation stacks associated with the 3 DynamoDB cache tables
- FR3: Developer can delete the Step Function `sqs-to-rds` CloudFormation stack from AWS account
- FR4: Developer can delete SSM Parameters associated with removed DynamoDB tables and Step Function

### CloudFormation Template & Configuration Cleanup

- FR5: Developer can remove 3 DynamoDB CF templates from `infra/aws/cloudformation/templates/`
- FR6: Developer can remove 3 DynamoDB parameter files from `infra/aws/cloudformation/parameters/dev/`
- FR7: Developer can remove DynamoDB cache table entries from `deploy.ini`
- FR8: Developer can remove Step Function entry from `deploy.ini`
- FR9: Developer can remove `/url_add2` endpoint and associated Step Function parameters from `api-gw-app.yaml`
- FR10: Developer can redeploy API Gateway after template modification (via S3 upload workflow)

### Code Archival

- FR11: Developer can archive the Step Function CF template (`sqs-to-rds-step-function.yaml`) to `infra/archive/`
- FR12: Developer can archive the Step Function state machine definition (`sqs_to_rds.json`) to `infra/archive/`
- FR13: Archived files include a README explaining the Step Function's purpose, original deployment location, and dependencies

### Reference Cleanup

- FR14: Developer can verify zero stale references to removed DynamoDB tables across entire codebase
- FR15: Developer can verify zero stale references to removed Step Function across entire codebase
- FR16: Developer can verify zero stale references to `/url_add2` endpoint across entire codebase
- FR17: Developer can run `cfn-lint` on all modified CF templates and receive zero errors

### Documentation Updates

- FR18: Developer can update README.md with project vision: Lenie-AI as MCP server for Claude Desktop + Obsidian vault workflow
- FR19: Developer can update README.md with phased roadmap (current state → MCP server → Obsidian integration)
- FR20: Developer can update CLAUDE.md to reflect current project state after cleanup
- FR21: Developer can update `infra/aws/README.md` to remove references to deleted resources
- FR22: Developer can update any other documentation files that reference removed resources

## Non-Functional Requirements

### Reliability & Safety

- NFR1: Existing API Gateway endpoints (all except `/url_add2`) continue to function correctly after template modification and redeployment
- NFR2: No actively used AWS resources are affected by the cleanup — only confirmed-unused resources are removed
- NFR3: Step Function code is archived and retrievable before AWS stack deletion
- NFR4: All cleanup operations are performed through CloudFormation (IaC-managed) to ensure consistent, repeatable, and rollback-capable changes

### IaC Quality & Validation

- NFR5: All modified CloudFormation templates pass `cfn-lint` validation with zero errors before deployment
- NFR6: Codebase-wide search (grep) confirms zero stale references to removed resources after cleanup
- NFR7: `deploy.ini` contains only entries for active, deployable templates — zero commented-out or dead entries for removed resources

### Documentation Quality

- NFR8: README.md contains: project purpose, current architecture summary, target vision (MCP server + Obsidian), and phased roadmap — readable without consulting other files
- NFR9: No documentation file references resources that no longer exist in AWS or in the codebase
