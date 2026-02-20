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
workflowType: 'prd'
lastEdited: '2026-02-16'
editHistory:
  - date: '2026-02-16'
    changes: 'Updated from Sprint 2 (Cleanup & Vision) to Sprint 3 (Code Cleanup — Endpoint & Dead Code Removal). Rewrote Executive Summary, Success Criteria, Product Scope, User Journeys, Risk Mitigation, FRs (22→35), NFRs (9→13). Applied 3 validation fixes (FR13, FR17, NFR8). Added Phase 2 (Security) to roadmap.'
---

# Product Requirements Document - lenie-server-2025

**Author:** Ziutus
**Date:** 2026-02-16
**Sprint:** 3 — Code Cleanup (Endpoint & Dead Code Removal)

## Executive Summary

Lenie-server-2025 is a personal AI knowledge management system for collecting, managing, and searching press articles, web content, and YouTube transcriptions using LLMs and vector similarity search (PostgreSQL + pgvector).

**This sprint** executes Phase 1 of the three-phase strategic plan: Code Cleanup. Following the principle "Clean first → Secure second → Build new third," Sprint 3 removes unnecessary functionality before investing in security updates or new features. Sprint 1 achieved 100% IaC coverage (6 epics, 10 stories). Sprint 2 removed unused AWS resources (3 DynamoDB cache tables, `/url_add2` endpoint) and documented project vision (3 epics, 5 stories). Sprint 3 removes 3 endpoints (`/ai_ask`, `/translate`, `/infra/ip-allow`), removes dead code (`ai_describe_image()`), and applies 6 tactical CloudFormation template improvements (tagging, SSM pattern, ApiDeployment fix, Lambda typo, Lambda name parameterization, `/website_delete` review).

**Target vision:** Private knowledge base in Obsidian vault, managed by Claude Desktop, powered by Lenie-AI as an MCP server. This sprint continues codebase cleanup to prepare for that transformation.

## Success Criteria

### User Success (Developer Experience)

- Developer sees zero stale endpoint references after removal of `/ai_ask`, `/translate`, and `/infra/ip-allow`
- API Gateway template reflects only active endpoints (21 reduced to 18)
- CloudFormation templates use consistent patterns (AWS::SSM::Parameter::Value<String>, parameterized Lambda names, resource tagging)
- Code review confirms `ai_ask()` function remains intact (used by `youtube_processing.py`) despite endpoint removal

### Business Success

- Lower AWS costs through elimination of 3 unused endpoints and associated CloudWatch logs
- Cleaner codebase — reduced attack surface, easier maintenance
- All CloudFormation resources tagged with Project and Environment for AWS Cost Explorer filtering
- Foundation prepared for Phase 2 (Security hardening) and Phase 3 (MCP Server implementation)

### Technical Success

- 3 endpoints removed from server.py, Lambda functions, API Gateway template, and React frontend
- 1 dead code function (`ai_describe_image()`) removed from library/ai.py
- Zero stale references remaining (verified by grep + semantic review)
- All CloudFormation templates pass cfn-lint validation with zero errors
- 6 tactical template improvements applied (tagging, SSM pattern, ApiDeployment fix, Lambda typo, parameterization, REST review)

### Measurable Outcomes

- 3 endpoints removed (server.py: 1, Lambda app-server-internet: 2, API Gateway: 3)
- 1 Lambda function deleted or archived from AWS (`infra-allow-ip-in-security-group`)
- 1 dead code function removed (`ai_describe_image()`)
- Frontend: 2 hook functions removed from `useManageLLM.js` (`handleCorrectUsingAI`, `handleTranslate`)
- 0 stale references in codebase (verified by grep + semantic review)
- All CF resources tagged with Project and Environment
- SSM pattern replaced, ApiDeployment fixed, Lambda typo corrected, Lambda name parameterized, `/website_delete` REST compliance reviewed

## Product Scope

### Phase 1 — This Sprint (Code Cleanup)

1. **Endpoint Removal: `/ai_ask`** — Remove from server.py, Lambda app-server-internet, API Gateway template, and React frontend (useManageLLM.js). CRITICAL: Preserve `ai_ask()` function in library/ai.py (used by youtube_processing.py:290 for AI summary generation)
2. **Endpoint Removal: `/translate`** — Remove from Lambda app-server-internet, API Gateway template, and React frontend (useManageLLM.js). Backend module `library.translate` already missing — endpoint broken
3. **Endpoint Removal: `/infra/ip-allow`** — Remove from API Gateway template, delete or archive Lambda function `infra-allow-ip-in-secrutity-group` from AWS. Function has typo in name, hardcoded security group ID, not used for RDP access
4. **Dead Code Removal** — Remove `ai_describe_image()` function from library/ai.py (defined at line 97, never called)
5. **CF Improvements — Tagging** — Add Project and Environment tags to all resources across all CF templates for AWS Cost Explorer filtering
6. **CF Improvements — SSM Pattern** — Replace `{{resolve:ssm:...}}` with `AWS::SSM::Parameter::Value<String>` in sqs-to-rds-step-function.yaml
7. **CF Improvements — Lambda Parameterization** — Parameterize hardcoded Lambda function name `lenie-sqs-to-db` in sqs-to-rds-step-function.yaml DefinitionSubstitutions
8. **CF Improvements — ApiDeployment Fix** — Fix ApiDeployment pattern in api-gw-app.yaml to force redeployment on RestApi Body changes (add hash/timestamp or separate AWS::ApiGateway::Stage resource)
9. **CF Improvements — Lambda Typo** — Fix Lambda function name typo `infra-allow-ip-in-secrutity-group` → `infra-allow-ip-in-security-group` (requires AWS-side rename first)
10. **CF Improvements — REST Compliance Review** — Review `/website_delete` GET method in api-gw-app.yaml and propose REST-compliant alternative (DELETE method). Document frontend impact
11. **Reference Cleanup** — Verify zero stale references across entire codebase (grep + semantic review). Update documentation to reflect post-cleanup state

### Phase 2 (Future — Security Hardening)

- Lambda Layer security audit (dependencies ~1.5+ years old)
- CORS hardening (replace wildcard `Access-Control-Allow-Origin: '*'`)
- Lambda function CloudFormation management (replace hardcoded ARNs)
- Remove 36 stale API Gateway deployments

### Phase 3 (Future — MCP Server Foundation)

- Database abstraction layer (separate raw psycopg2 from business logic)
- Implement MCP server protocol (expose search/retrieve endpoints as MCP tools)
- Claude Desktop integration (configure Lenie-AI as MCP server)
- API adaptation for MCP tool consumption

### Phase 4 (Future — Obsidian Integration)

- Obsidian vault integration (synchronization, linking, note creation)
- Semantic search from within Obsidian via Claude Desktop + MCP
- Advanced vector search refinements for personal knowledge management

## User Journeys

### Journey 1: Developer Code Cleanup Sprint

**Persona:** Ziutus — sole developer and project owner, intermediate skill level.

**Opening Scene:** Ziutus opens the project after completing Sprint 2 (AWS Cleanup & Vision Documentation). Three endpoints (`/ai_ask`, `/translate`, `/infra/ip-allow`) are confirmed unnecessary. One dead function (`ai_describe_image()`) sits unused. CloudFormation templates contain tactical debt (no tagging, hardcoded values, ApiDeployment doesn't force redeployment, Lambda typo). The Sprint 3 backlog includes 6 tactical improvements identified during Epics 7-8 code reviews.

**Rising Action:** Ziutus removes `/ai_ask` endpoint from server.py, Lambda app-server-internet, API Gateway template, and React frontend — but preserves the `ai_ask()` function because it's called by `youtube_processing.py`. Ziutus removes `/translate` endpoint (already broken — backend module missing). Ziutus removes `/infra/ip-allow` endpoint and archives the Lambda function. Ziutus deletes `ai_describe_image()` from library/ai.py. Ziutus applies 6 CloudFormation improvements: adds Project and Environment tags, replaces `{{resolve:ssm:...}}` with `AWS::SSM::Parameter::Value<String>`, parameterizes hardcoded Lambda name, fixes ApiDeployment pattern, fixes Lambda typo (`secrutity` → `security`), reviews `/website_delete` GET method.

**Climax:** After codebase-wide grep and semantic review — zero stale references remain. All CloudFormation templates pass cfn-lint validation with zero errors. API Gateway operates with 18 endpoints (down from 21). Frontend components no longer reference removed endpoints. `ai_ask()` function remains intact and operational for YouTube summary generation.

**Resolution:** The project is cleaner. Three unused endpoints are gone. Dead code is removed. CloudFormation templates follow consistent patterns with tagging for cost allocation. The codebase is ready for Phase 2 (Security Hardening) and Phase 3 (MCP Server Foundation).

### Journey 2: Future Developer Onboarding

**Persona:** A new developer (or Ziutus returning after months away) opening the project for the first time.

**Opening Scene:** The developer opens README.md and CLAUDE.md to understand the project's purpose and current state.

**Rising Action:** Documentation describes current architecture, active endpoints (18 in API Gateway, matching server.py and Lambda implementations), and target vision (MCP server + Obsidian vault). CloudFormation templates are tagged for cost tracking. All resources follow consistent patterns (SSM parameters, parameterized names, REST conventions). No documentation references non-existent endpoints or dead code.

**Resolution:** The developer understands the project, its active features, and its strategic direction without encountering confusing dead references, broken endpoints, or inconsistent patterns.

### Journey Requirements Summary

| Journey | Capabilities Required |
|---------|----------------------|
| Developer Cleanup | Remove `/ai_ask` endpoint from server.py, Lambda, API GW, Frontend |
| Developer Cleanup | Preserve `ai_ask()` function (used by youtube_processing.py) |
| Developer Cleanup | Remove `/translate` endpoint from Lambda, API GW, Frontend |
| Developer Cleanup | Remove `/infra/ip-allow` endpoint from API GW, delete Lambda function |
| Developer Cleanup | Remove `ai_describe_image()` dead code from library/ai.py |
| Developer Cleanup | Add Project and Environment tags to all CF resources |
| Developer Cleanup | Replace `{{resolve:ssm:...}}` with AWS::SSM::Parameter::Value<String> |
| Developer Cleanup | Parameterize hardcoded Lambda name in Step Function |
| Developer Cleanup | Fix ApiDeployment pattern to force redeployment |
| Developer Cleanup | Fix Lambda typo `secrutity` → `security` |
| Developer Cleanup | Review `/website_delete` GET method for REST compliance |
| Developer Cleanup | Verify zero stale references (grep + semantic review) |
| Future Onboarding | Clear documentation with current state and vision |
| Future Onboarding | No stale references to removed endpoints or dead code |
| Future Onboarding | Consistent CF patterns across all templates |

## Web App Technical Context

Brownfield web application: React 18 SPA (CloudFront + S3) + Flask REST API (API Gateway + Lambda) + PostgreSQL 17 with pgvector (RDS). Sprint 3 removes endpoints and dead code — impacts both backend and frontend.

**Key constraint:** `api-gw-app.yaml` currently at 51164 bytes (under 51200 byte inline limit after Sprint 2 cleanup). Removing 3 endpoints will further reduce size. Direct `aws cloudformation deploy --template-file` workflow applies (no S3 packaging needed).

**Critical dependency:** `ai_ask()` function in `library/ai.py` is called by `youtube_processing.py:290` for AI summary generation. The `/ai_ask` endpoint must be removed but the underlying function must remain intact. Future MCP Server implementation may replace this dependency when Claude Desktop takes over AI summary generation.

**Broken endpoint:** `/translate` endpoint already broken — backend module `library.translate` does not exist. Removal is cleanup of non-functional code.

**Frontend impact:** React frontend (`useManageLLM.js`) contains two functions referencing removed endpoints: `handleCorrectUsingAI()` (calls `/ai_ask`) at line 456, `handleTranslate()` (calls `/translate`) at line 375. Both must be removed or disabled.

**REST compliance review:** `/website_delete` currently uses GET method for destructive operation. Review requires evaluating switch to DELETE method and potential impact on frontend DELETE request handling.

## Risk Mitigation

**Technical Risks:**
- *Accidental removal of `ai_ask()` function* — Mitigated by explicit preservation requirement in story, code review verification, grep pattern for `youtube_processing.py` usage
- *Frontend breaking after endpoint removal* — Mitigated by removing React hook functions (`handleCorrectUsingAI`, `handleTranslate`) and testing against live API
- *Lambda typo fix before CF update* — Mitigated by two-step process: rename Lambda in AWS first, then update CF template
- *`/website_delete` REST change breaks frontend* — Mitigated by review-only requirement (no implementation without documented impact analysis)

**Resource Risks:**
- *Context loss between sessions* — Mitigated by detailed story files and BMad Method tracking
- *Incomplete reference cleanup* — Mitigated by grep verification + semantic review (numeric counts, package names, terminology)
- *CloudFormation validation failures* — Mitigated by cfn-lint validation before every deployment

**Process Risks:**
- *Retro action items not tracked* — Mitigated by adding retro commitments to sprint-status.yaml
- *Documentation review gaps* — Mitigated by 2-round review requirement for documentation changes

## Functional Requirements

### Endpoint Removal — `/ai_ask`

- FR1: Developer can remove `/ai_ask` endpoint from `backend/server.py`
- FR2: Developer can remove `/ai_ask` endpoint from `infra/aws/serverless/app-server-internet/lambda_function.py`
- FR3: Developer can remove `/ai_ask` endpoint definition from `infra/aws/cloudformation/templates/api-gw-app.yaml`
- FR4: Developer can remove or disable `handleCorrectUsingAI()` function from `web_interface_react/src/hooks/useManageLLM.js`
- FR5: Developer can verify `ai_ask()` function in `backend/library/ai.py` remains intact and is called by `backend/imports/youtube_processing.py`

### Endpoint Removal — `/translate`

- FR6: Developer can remove `/translate` endpoint from `infra/aws/serverless/app-server-internet/lambda_function.py`
- FR7: Developer can remove `/translate` endpoint definition from `infra/aws/cloudformation/templates/api-gw-app.yaml`
- FR8: Developer can remove or disable `handleTranslate()` function from `web_interface_react/src/hooks/useManageLLM.js`
- FR9: Developer can verify backend module `library.translate` does not exist (endpoint already broken)

### Endpoint Removal — `/infra/ip-allow`

- FR10: Developer can remove `/infra/ip-allow` endpoint definition from `infra/aws/cloudformation/templates/api-gw-app.yaml`
- FR11: Developer can delete or archive Lambda function `infra-allow-ip-in-secrutity-group` from AWS account
- FR12: Developer can verify zero frontend references to `/infra/ip-allow` endpoint

### Dead Code Removal

- FR13: Developer can remove `ai_describe_image()` function from `backend/library/ai.py`
- FR14: Developer can verify `ai_describe_image()` has zero callers across entire codebase

### CloudFormation Improvements — Tagging

- FR15: Developer can add `Project` tag to all resources across all CloudFormation templates
- FR16: Developer can add `Environment` tag to all resources across all CloudFormation templates
- FR17: Developer can verify tags enable filtering in AWS Cost Explorer

### CloudFormation Improvements — SSM Pattern

- FR18: Developer can replace `{{resolve:ssm:...}}` with `AWS::SSM::Parameter::Value<String>` in `infra/aws/cloudformation/templates/sqs-to-rds-step-function.yaml`
- FR19: Developer can verify updated template passes cfn-lint validation with zero errors

### CloudFormation Improvements — Lambda Parameterization

- FR20: Developer can parameterize hardcoded Lambda function name `lenie-sqs-to-db` in `sqs-to-rds-step-function.yaml` DefinitionSubstitutions
- FR21: Developer can verify parameterized Lambda name resolves correctly in Step Function definition

### CloudFormation Improvements — ApiDeployment Fix

- FR22: Developer can fix ApiDeployment pattern in `api-gw-app.yaml` to force redeployment when RestApi Body changes
- FR23: Developer can verify API Gateway redeploys automatically without manual `aws apigateway create-deployment` command

### CloudFormation Improvements — Lambda Typo Fix

- FR24: Developer can rename Lambda function `infra-allow-ip-in-secrutity-group` to `infra-allow-ip-in-security-group` in AWS account
- FR25: Developer can update `api-gw-app.yaml` to reference corrected Lambda function name
- FR26: Developer can verify API Gateway integration references correct Lambda function after deployment

### CloudFormation Improvements — REST Compliance Review

- FR27: Developer can review `/website_delete` GET method in `api-gw-app.yaml`
- FR28: Developer can document REST-compliant alternative (DELETE method) with frontend impact analysis
- FR29: Developer can document decision (implement now, defer, or reject) based on frontend change scope

### Reference Cleanup

- FR30: Developer can verify zero stale references to `/ai_ask` endpoint across entire codebase
- FR31: Developer can verify zero stale references to `/translate` endpoint across entire codebase
- FR32: Developer can verify zero stale references to `/infra/ip-allow` endpoint across entire codebase
- FR33: Developer can verify zero stale references to `ai_describe_image()` function across entire codebase
- FR34: Developer can verify all modified CloudFormation templates pass cfn-lint validation with zero errors
- FR35: Developer can verify API Gateway endpoint count in documentation reflects actual count after removal

## Non-Functional Requirements

### Reliability & Safety

- NFR1: Existing API Gateway endpoints (all except `/ai_ask`, `/translate`, `/infra/ip-allow`) continue to function correctly after template modification and redeployment
- NFR2: `ai_ask()` function in `library/ai.py` remains operational and callable by `youtube_processing.py` after `/ai_ask` endpoint removal
- NFR3: No actively used code, endpoints, or functions are removed — only confirmed-unused or broken resources
- NFR4: All cleanup operations preserve rollback capability through version control (git) and CloudFormation stack operations
- NFR5: Frontend application loads and functions after React hook modifications (`handleCorrectUsingAI`, `handleTranslate` removed or disabled)

### IaC Quality & Validation

- NFR6: All modified CloudFormation templates pass cfn-lint validation with zero errors before deployment
- NFR7: All CloudFormation resources include Project and Environment tags for cost allocation tracking
- NFR8: CloudFormation templates use consistent patterns: `AWS::SSM::Parameter::Value<String>` instead of `{{resolve:ssm:...}}`, parameterized Lambda names instead of hardcoded values
- NFR9: ApiDeployment resource triggers redeployment automatically when RestApi Body changes (no manual `aws apigateway create-deployment` required)
- NFR10: Codebase-wide search (grep + semantic review) confirms zero stale references to removed endpoints, dead code, or incorrect numeric counts

### Documentation Quality

- NFR11: API Gateway endpoint count in CLAUDE.md and README.md matches actual deployed count with zero discrepancies
- NFR12: No documentation file references removed endpoints (`/ai_ask`, `/translate`, `/infra/ip-allow`) or dead code (`ai_describe_image()`)
- NFR13: CloudFormation improvement decisions (implement, defer, or reject) are documented with rationale for future reference
