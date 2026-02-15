---
stepsCompleted:
  - step-01-init
  - step-01b-continue
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
inputDocuments:
  - docs/index.md
  - docs/project-overview.md
  - docs/architecture-backend.md
  - docs/architecture-web_interface_react.md
  - docs/architecture-web_chrome_extension.md
  - docs/architecture-infra.md
  - docs/api-contracts-backend.md
  - docs/data-models-backend.md
  - docs/integration-architecture.md
  - docs/component-inventory-web_interface_react.md
  - docs/source-tree-analysis.md
  - docs/development-guide.md
  - docs/CI_CD.md
  - docs/CI_CD_Tools.md
  - docs/CircleCI.md
  - docs/GitLabCI.md
  - docs/Jenkins.md
  - docs/Docker_Local.md
  - docs/AWS_Infrastructure.md
  - docs/AWS_Amplify_Deployment.md
  - docs/AWS_EC2_Runner_Setup.md
  - docs/AWS_Troubleshooting.md
  - docs/EC2_AMI_Backup_Pipeline.md
  - docs/Code_Quality.md
  - docs/Python_Dependencies.md
  - docs/VM_Setup.md
  - docs/API_Usage.md
documentCounts:
  briefs: 0
  research: 0
  brainstorming: 0
  projectDocs: 27
workflowType: 'prd'
classification:
  projectType: 'web_app'
  domain: 'general'
  complexity: 'medium'
  projectContext: 'brownfield'
discoveryInProgress:
  focus: 'infrastructure-refactoring'
  scope: 'AWS CloudFormation full IaC coverage for DEV environment'
  detectedProjectType: 'web_app'
  detectedDomain: 'general'
  detectedComplexity: 'medium'
  projectContext: 'brownfield'
  openQuestions: []
  userStatedGoals:
    - 'All AWS resources for the project must have CloudFormation templates'
    - 'Focus on IaC coverage only (cross-account migration deferred)'
  resolvedQuestions:
    - question: 'Which AWS resources lack CloudFormation templates?'
      answer: 'Identified via MCP + docs: Lambda Layers (3), DynamoDB cache tables (3), S3 lenie-s3-tmp (active, needs rename to lenie-dev-website-content), S3 lenie-dev-app-web, CloudFront ETIQTXICZBECA, Amplify Apps (3), SNS rds-monitor-sns + ses-monitoring, SES lenie-ai.eu root domain'
    - question: 'Migration scenario?'
      answer: 'Deferred - focus only on CloudFormation IaC coverage for now'
  legacyResourcesToRemove:
    - 'Lambda lenie_2_internet_tmp (temporary copy)'
    - 'Lambda lenie-url-add (replaced by lenie-dev-url-add)'
    - 'S3 lenie-s3-web-test (test bucket)'
    - 'CloudFront E19SWSRXVWFGJQ (test distribution, origin: lenie-s3-web-test)'
    - 'API Gateway pir31ejsf2 lenie_chrome_extension (old version)'
  activeResourcesNeedingCFTemplates:
    - 'API Gateway 1bkc3kz7c9 lenie_split — active main API, default endpoint for web_interface_react and web_add_url_react (no CF template)'
  futureConsiderations:
    - 'Migrate Lambda secrets from plaintext env vars to SSM Parameter Store (cheaper than Secrets Manager) - separate PRD'
    - 'Cross-account migration support'
---

# Product Requirements Document - lenie-server-2025

**Author:** Ziutus
**Date:** 2026-02-13

## Executive Summary

Project Lenie is a personal AI assistant for collecting, managing, and searching data using LLMs. Its AWS infrastructure spans 30+ resources across Lambda, API Gateway, DynamoDB, S3, RDS, SQS, CloudFront, SES, and Step Functions — most managed via CloudFormation templates, but ~16 resources currently lack IaC coverage.

**Goal:** Achieve 100% CloudFormation template coverage for all DEV environment AWS resources. Every resource used by Project Lenie must be deployable from code — eliminating the risk of configuration loss and enabling environment recreation from templates alone.

**Scope:** Create ~11 new CF templates, remove 5 legacy AWS resources, migrate S3 bucket `lenie-s3-tmp` → `lenie-dev-website-content`, clean unused monitoring code (CloudWatch RUM, Cognito) from the React frontend, and document the complete deployment order.

**Out of scope (deferred to future PRDs):** Cross-account migration, Amplify replacement, SSM Parameter Store secret migration, multi-environment parameterization, CI/CD template validation.

## Success Criteria

### User Success

- Developer can recreate the DEV environment from CloudFormation templates — deployment order is documented, full automation is not required
- Every AWS resource used by Project Lenie has a corresponding CloudFormation template
- No "silent" manually-created resources outside of IaC code

### Business Success

- AWS infrastructure is fully described in code — reduced risk of configuration loss
- Clean AWS account — legacy resources removed, reducing noise and potential costs
- Clean frontend codebase — unused monitoring code removed (CloudWatch RUM, Cognito)

### Technical Success

- 0 AWS resources for Project Lenie without a CloudFormation template (DEV environment)
- 0 legacy resources remaining on the AWS account
- S3 bucket `lenie-s3-tmp` migrated to `lenie-dev-website-content` with all references updated across Lambdas, CF templates, and environment variables
- Frontend code cleaned of `aws-rum-web` dependency and Cognito Identity Pool references

### Measurable Outcomes

- Resources without CF templates: from ~16 → 0
- Legacy resources: from 5 → 0
- `deploy.ini`: all DEV templates uncommented and functional
- Frontend bundle size reduced by removing `aws-rum-web` package

## Product Scope

### MVP — This PRD

1. **New CloudFormation templates** (~11 templates):
   - Lambda Layers (3): `lenie_all_layer`, `lenie_openai`, `psycopg2_new_layer`
   - DynamoDB cache tables (3): `lenie_cache_ai_query`, `lenie_cache_language`, `lenie_cache_translation`
   - S3 `lenie-dev-website-content` (rename from `lenie-s3-tmp` + data migration)
   - S3 `lenie-dev-app-web` (frontend hosting bucket)
   - CloudFront distribution for `app.dev.lenie-ai.eu` (ID: `ETIQTXICZBECA`)
   - SNS topics (2): `rds-monitor-sns`, `ses-monitoring`
   - SES root domain `lenie-ai.eu`
   - API Gateway main application API (ID: `1bkc3kz7c9`, name: `lenie_split`)

2. **Legacy resource removal** (5 resources):
   - Lambda `lenie_2_internet_tmp` (temporary copy)
   - Lambda `lenie-url-add` (replaced by CF-managed `lenie-dev-url-add`)
   - S3 `lenie-s3-web-test` (test bucket)
   - CloudFront `E19SWSRXVWFGJQ` (test distribution)
   - API Gateway `pir31ejsf2` (`lenie_chrome_extension`, old version)

3. **Frontend code cleanup**:
   - Remove `aws-rum-web` from `authorizationContext.js` and `package.json`
   - Remove Cognito Identity Pool ID and `bootstrapRum()` function
   - Remove associated CloudWatch RUM configuration

4. **Deployment documentation**:
   - Documented deployment order for all CF templates in DEV environment
   - Updated `deploy.ini` with correct template list

### Future Phases

See "Project Scoping & Phased Development" section for detailed Phase 2 (Growth) and Phase 3 (Expansion) roadmap.

## User Journeys

### Journey 1: Developer recreates DEV environment after account reset

Ziutus, an experienced developer, needs to recreate the DEV environment after an AWS account reset. He opens `infra/aws/cloudformation/` and finds a complete set of templates. He reads `deploy.ini` and sees a documented deployment order. He runs `deploy.sh` for successive layers: first networking (VPC, Security Groups), then storage (S3, DynamoDB), compute (Lambda Layers, Lambdas), API (API Gateway), and finally orchestration (Step Functions). After 30-40 minutes of manual layer-by-layer deployment, the entire DEV infrastructure is operational. The frontend on CloudFront serves the React SPA, API Gateway routes to Lambdas, and the Step Function processes the SQS queue.

**Reveals requirements:** Complete CF templates, documented deployment order, cross-stack references (SSM exports), DEV environment parameterization.

### Journey 2: Developer adds new Lambda function to existing stack

Ziutus writes a new Lambda for a new endpoint. He looks at existing CF templates as a pattern — sees how `sqs-to-rds-lambda.yaml` defines a function with layers and VPC. He copies the pattern, modifies it, adds it to `deploy.ini`. Deploys — the Lambda connects to existing resources via SSM Parameter Store imports. No need to manually look up ARNs.

**Reveals requirements:** Consistent patterns across templates, SSM exports for key ARNs and identifiers, clear naming convention.

### Journey 3: Developer cleans up legacy resources

Ziutus reviews the AWS account and sees resources that don't match any CF template. He opens the README and finds a "Legacy resources" section with a list of resources to remove and the correct order (first CloudFront, then S3, then Lambda, finally API Gateway). He removes them manually or via CLI. After cleanup, every resource on the account has a corresponding CF template.

**Reveals requirements:** Documented legacy resource list, removal order (dependencies), post-cleanup validation.

### Journey 4: Developer migrates S3 bucket with data

Ziutus needs to move data from `lenie-s3-tmp` to a new bucket `lenie-dev-website-content`. He creates the new bucket via CF template, copies data with `aws s3 sync`, updates references in the `url-add.yaml` template, Lambda environment variables, and local `.env`. He tests the flow — Chrome extension sends a URL, Lambda saves content to the new bucket. Everything works, the old bucket can be deleted.

**Reveals requirements:** CF template for new S3 bucket, data migration procedure, reference updates across multiple locations (CF templates, Lambda env, local .env).

### Journey Requirements Summary

| Journey | Required Capabilities |
|---------|----------------------|
| 1. Recreate DEV | Complete CF templates, deployment docs, cross-stack references |
| 2. Add new Lambda | Consistent template patterns, SSM exports, naming conventions |
| 3. Legacy cleanup | Legacy resource documentation, removal order, validation |
| 4. S3 migration | New CF template, migration procedure, multi-location reference updates |

## Technical Architecture Requirements

### Architecture Overview

The web app architecture determines the infrastructure shape: static SPA hosting (S3 + CloudFront), REST API (API Gateway + Lambda), persistent storage (RDS + DynamoDB), and asynchronous processing (SQS + Step Functions). Every component must have a corresponding CloudFormation template.

### Technical Architecture Considerations

#### Template Organization Pattern

Existing templates follow a layered deployment model with dependencies flowing top-down:

| Layer | Templates | Dependencies |
|-------|-----------|-------------|
| 1. Foundation | `env-setup`, `budget`, `1-domain-route53` | None |
| 2. Networking | `vpc`, `security-groups` | Foundation |
| 3. Security | `secrets` | Networking |
| 4. Storage | `s3`, `s3-cloudformation`, `dynamodb-*`, `rds` | Networking, Security |
| 5. Compute | Lambda Layers, `lambda-*`, `sqs-to-rds-lambda` | Storage |
| 6. API | `api-gw-app`, `api-gw-infra`, `api-gw-url-add` | Compute |
| 7. Orchestration | `sqs-to-rds-step-function` | Compute, API |
| 8. Email & CDN | `ses`, CloudFront, SNS | Foundation |

New templates must be placed in the correct layer and added to `deploy.ini` in the proper order.

#### Cross-Stack Communication via SSM Parameter Store

The project uses SSM Parameters as the primary mechanism for cross-stack references, following the path convention `/${ProjectName}/${Environment}/<resource-path>`. Key exports include VPC ID, subnet IDs, S3 bucket names, and Lambda runtime version. New templates **must** export any values that other stacks might need (e.g., the new S3 `lenie-dev-website-content` bucket name should be exported for Lambda templates that reference it).

#### Known Inconsistency: `ProjectCode` vs `ProjectName`

Newer templates use the parameter name `ProjectCode` while older ones use `ProjectName`. Both default to `lenie`. New templates in this PRD should use `ProjectCode` (the newer convention) for consistency going forward. Existing templates should not be refactored as part of this PRD — that is a separate cleanup task.

#### Naming Convention

Resources follow the pattern `${ProjectCode}-${Environment}-<resource-description>` with hyphens for AWS resource names (S3 buckets, Lambda functions, stacks) and underscores for DynamoDB tables and internal identifiers. New templates should follow this existing convention.

#### Environment Parameterization

Templates support multiple environments via:
- `Parameters` section with `Environment` (AllowedValues: dev, qa, prod, etc.)
- `Conditions` for prod-specific features (e.g., DynamoDB PITR)
- Separate parameter files in `parameters/{env}/` directory
- Stack names follow `lenie-{env}-{resource}` pattern

This PRD targets DEV environment only. Parameter files for other environments are not required.

### Implementation Considerations

#### New Template Placement

All new templates go in `infra/aws/cloudformation/templates/`:

| New Template | Layer | Key Dependencies |
|-------------|-------|-----------------|
| `lambda-layers.yaml` (or 3 separate) | 5. Compute | `s3-cloudformation` (code artifacts bucket) |
| `dynamodb-cache-*.yaml` (3 tables) | 4. Storage | None (standalone) |
| `s3-website-content.yaml` | 4. Storage | None |
| `s3-app-web.yaml` | 4. Storage | None |
| `cloudfront-app.yaml` | 8. CDN | `s3-app-web` |
| `sns-monitoring.yaml` | 4. Storage | None |
| `ses-root-domain.yaml` | 8. Email | `1-domain-route53` |
| `api-gw-main.yaml` | 6. API | Compute layer Lambdas |

#### deploy.ini Integration

All new templates must be added to the `[dev]` section of `deploy.ini` in deployment order. Currently most entries are commented out — this PRD requires uncommenting all valid DEV templates and adding new ones in the correct position.

#### S3 Bucket Migration Procedure

The rename from `lenie-s3-tmp` to `lenie-dev-website-content` requires:
1. Create new bucket via CF template
2. `aws s3 sync s3://lenie-s3-tmp s3://lenie-dev-website-content`
3. Update `url-add.yaml` template (environment variable reference)
4. Update Lambda `sqs-weblink-put-into` configuration
5. Update local `.env` (`AWS_S3_WEBSITE_CONTENT` variable)
6. Verify flow end-to-end
7. Delete old bucket

#### Legacy Resource Removal Order

Removal must respect dependencies:
1. CloudFront `E19SWSRXVWFGJQ` (depends on S3 origin)
2. S3 `lenie-s3-web-test` (CloudFront origin removed first)
3. Lambda `lenie_2_internet_tmp` (no dependents)
4. Lambda `lenie-url-add` (replaced by `lenie-dev-url-add`)
5. API Gateway `pir31ejsf2` (no dependents after Lambda removal)

## Project Scoping & Phased Development

### MVP Strategy & Philosophy

**MVP Approach:** Problem-Solving MVP — eliminate the risk of configuration loss by ensuring every AWS resource has a CloudFormation template. The MVP does not introduce new application features; it codifies the existing infrastructure state.

**Resource Requirements:** Single developer (Ziutus). No additional team members needed. Requires AWS account access with CloudFormation, S3, Lambda, API Gateway, DynamoDB, SNS, SES, and CloudFront permissions.

### MVP Feature Set (Phase 1)

**Core User Journeys Supported:**
- Journey 1 (Recreate DEV) — primary driver, requires all templates to exist
- Journey 3 (Legacy cleanup) — removes noise, validates completeness
- Journey 4 (S3 migration) — prerequisite for clean naming convention

**Must-Have Capabilities:**

| # | Capability | Rationale |
|---|-----------|-----------|
| 1 | DynamoDB cache table templates (3) | Standalone, no dependencies — quick wins |
| 2 | SNS monitoring topic templates (2) | Standalone, used by existing error notifications |
| 3 | S3 `lenie-dev-website-content` template + data migration | Active bucket used by Lambdas, blocks other work if naming stays inconsistent |
| 4 | S3 `lenie-dev-app-web` template | Frontend hosting bucket |
| 5 | Lambda Layer templates (3) | Required by all app Lambda functions |
| 6 | SES root domain `lenie-ai.eu` template | Email functionality dependency |
| 7 | CloudFront `app.dev.lenie-ai.eu` template | Frontend delivery, depends on S3 app-web |
| 8 | API Gateway `lenie_split` template | Most complex — main application API with 13+ endpoints |
| 9 | Legacy resource removal (5 resources) | Clean account, reduce confusion |
| 10 | Frontend cleanup (aws-rum-web, Cognito) | Remove dead code, reduce bundle size |
| 11 | `deploy.ini` update + deployment order documentation | Ties everything together for Journey 1 |

**Suggested Implementation Order:** Items 1-2 first (standalone, low risk), then 3-6 (storage and compute layer), then 7-8 (most complex, highest dependency), then 9-10 (cleanup), finally 11 (documentation).

### Post-MVP Features

**Phase 2 (Growth):**
- Replace Amplify Apps with S3 + CloudFront + authentication mechanism (panel access control)
- Migrate Lambda secrets from plaintext env vars to SSM Parameter Store
- CF template validation in CI/CD pipeline (cfn-lint, cfn-guard)

**Phase 3 (Expansion):**
- Multi-environment parameterization (dev/qa/prod from single template set)
- Cross-account AWS migration support
- Full deployment automation (single script recreates entire environment)
- GitOps — automatic infrastructure deployment from CI/CD on merge to main

### Risk Mitigation Strategy

**Technical Risks:**

| Risk | Impact | Mitigation |
|------|--------|-----------|
| API Gateway import to CF is complex (13+ endpoints, CORS, Lambda integrations) | High | Use existing `api-gw-app.yaml` as pattern; consider generating from current API Gateway export |
| CloudFront distribution CF template may differ from manual config | Medium | Export current distribution config via AWS CLI before writing template |
| S3 data migration could lose files or break references | Medium | Use `aws s3 sync` (not move), verify before deleting old bucket, test end-to-end flow |
| Lambda Layer version pinning — CF creates new versions | Low | Accept new version numbers; update references in Lambda templates |

**Operational Risks:**

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Deploying CF template for existing resource causes conflict | High | Use `--no-execute-changeset` first to preview; for existing resources consider `import` |
| Legacy resource removal breaks something unexpected | Medium | Verify no references exist (code search + CloudTrail) before removal |
| `deploy.ini` ordering mistake causes deployment failure | Low | Test deployment order in sequence; document dependencies |

**Resource Risks:**
- Single developer — no team dependency risk, but also no review safety net
- Mitigation: Use `cfn-lint` validation before deployment even if CI/CD integration is Phase 2
- Minimum viable: Even if only the templates are created (without deploy.ini update), the IaC coverage goal is met

## Functional Requirements

### IaC Template Coverage

- FR1: Developer can deploy each of the three DynamoDB cache tables (`lenie_cache_ai_query`, `lenie_cache_language`, `lenie_cache_translation`) via individual CloudFormation templates
- FR2: Developer can deploy each of the three Lambda Layers (`lenie_all_layer`, `lenie_openai`, `psycopg2_new_layer`) via CloudFormation templates
- FR3: Developer can deploy the website content S3 bucket (`lenie-dev-website-content`) via a CloudFormation template
- FR4: Developer can deploy the frontend hosting S3 bucket (`lenie-dev-app-web`) via a CloudFormation template
- FR5: Developer can deploy both SNS monitoring topics (`rds-monitor-sns`, `ses-monitoring`) via CloudFormation templates
- FR6: Developer can deploy the SES root domain identity (`lenie-ai.eu`) with DKIM configuration via a CloudFormation template
- FR7: Developer can deploy the CloudFront distribution for `app.dev.lenie-ai.eu` via a CloudFormation template
- FR8: Developer can deploy the main application API Gateway (`lenie_split`, 13+ endpoints with CORS and Lambda integrations) via a CloudFormation template

### Cross-Stack Integration

- FR9: Each new template exports resource identifiers (ARNs, names, IDs) via SSM Parameter Store using the convention `/${ProjectCode}/${Environment}/<resource-path>`
- FR10: Each new template consumes cross-stack values via SSM Parameters, not hardcoded ARNs or resource names
- FR11: New templates can be deployed independently within their layer without modifying existing stacks

### S3 Bucket Migration

- FR12: Developer can create the replacement bucket `lenie-dev-website-content` with equivalent permissions and configuration as `lenie-s3-tmp`
- FR13: Developer can migrate all existing data from `lenie-s3-tmp` to the new bucket without data loss
- FR14: All Lambda functions, CF templates, and environment configurations reference the new bucket name after migration
- FR15: The end-to-end content flow (Chrome extension → Lambda → S3) works correctly with the new bucket

### Legacy Resource Cleanup

- FR16: Developer can identify legacy resources via a documented list with removal rationale
- FR17: Developer can remove each legacy resource following a documented dependency order
- FR18: After cleanup, no AWS resources for Project Lenie exist without a corresponding CloudFormation template

### Frontend Code Maintenance

- FR19: Frontend application builds and runs without the `aws-rum-web` package
- FR20: Frontend application functions without Cognito Identity Pool reference or `bootstrapRum()` function
- FR21: The `authorizationContext.js` contains no CloudWatch RUM initialization code

### Deployment Orchestration

- FR22: Developer can see the complete, ordered list of all DEV CloudFormation templates in `deploy.ini`
- FR23: Developer can deploy the entire DEV environment by following the documented template order using `deploy.sh`
- FR24: New templates are registered in `deploy.ini` at the correct position within their deployment layer

### Template Consistency

- FR25: New templates use the `ProjectCode` + `Environment` parameter pattern (newer convention)
- FR26: New templates follow the resource naming convention `${ProjectCode}-${Environment}-<description>`
- FR27: New templates include standard tags (`Environment`, `Project`)
- FR28: New templates include `Conditions` for prod-specific features where applicable (e.g., DynamoDB PITR)

## Non-Functional Requirements

### Security

- NFR1: All new S3 buckets have server-side encryption enabled (SSE-S3 or SSE-KMS)
- NFR2: All new DynamoDB tables have encryption at rest enabled (KMS)
- NFR3: No CloudFormation template contains hardcoded secrets, passwords, or API keys — all sensitive values are resolved via Secrets Manager or SSM Parameter Store
- NFR4: S3 buckets block public access by default unless explicitly required (e.g., frontend hosting bucket with CloudFront OAI/OAC)
- NFR5: Lambda Layer templates do not expose layer ARNs publicly — sharing is limited to the same AWS account

### Compatibility

- NFR6: All new templates are deployable via the existing `deploy.sh` script without modifications to the script itself
- NFR7: New templates do not require modifications to any existing deployed stack — they integrate via SSM Parameter Store reads
- NFR8: Templates validate successfully with `aws cloudformation validate-template` before deployment
- NFR9: Each template supports CloudFormation stack update operations (not just create) — enabling iterative changes without stack recreation
- NFR10: The S3 bucket migration does not cause downtime for the Chrome extension → Lambda → S3 content flow

### Maintainability

- NFR11: A developer unfamiliar with the project can understand each template's purpose from its filename and `Description` field
- NFR12: All cross-stack references use SSM Parameter Store paths (not CloudFormation Exports) consistent with the existing pattern
- NFR13: Template parameter names and resource naming conventions are consistent across all new templates (no mixing of `ProjectCode` vs `ProjectName`)
- NFR14: Each template is self-contained — deploying a single template does not require manual pre-steps beyond what `deploy.ini` documents
