---
stepsCompleted: [1, 2, 3, 4, 5, 6, 7, 8]
lastStep: 8
status: 'complete'
completedAt: '2026-02-13'
sprint4:
  stepsCompleted: [2, 3, 4, 5, 6, 7, 8]
  lastStep: 8
  status: 'complete'
  startedAt: '2026-02-19'
  completedAt: '2026-02-19'
inputDocuments:
  - _bmad-output/planning-artifacts/prd.md
  - _bmad-output/planning-artifacts/prd-validation-report.md
  - docs/index.md
  - docs/project-overview.md
  - docs/architecture-backend.md
  - docs/architecture-web_interface_react.md
  - docs/architecture-web_chrome_extension.md
  - docs/architecture-infra.md
  - docs/integration-architecture.md
  - docs/api-contracts-backend.md
  - docs/data-models-backend.md
workflowType: 'architecture'
project_name: 'lenie-server-2025'
user_name: 'Ziutus'
date: '2026-02-13'
---

# Architecture Decision Document

_This document builds collaboratively through step-by-step discovery. Sections are appended as we work through each architectural decision together._

## Project Context Analysis

### Requirements Overview

**Functional Requirements:**
28 FRs organized in 7 capability groups:
1. **IaC Template Coverage (FR1-FR8):** Create CloudFormation templates for ~11 uncovered AWS resources (3 DynamoDB cache tables, 3 Lambda Layers, 2 S3 buckets, CloudFront distribution, 2 SNS topics, SES root domain, API Gateway main application API)
2. **Cross-Stack Integration (FR9-FR11):** All new templates must export resource identifiers via SSM Parameter Store and consume cross-stack values via SSM — no hardcoded ARNs
3. **S3 Bucket Migration (FR12-FR15):** Migrate `lenie-s3-tmp` → `lenie-dev-website-content` with data preservation and multi-location reference updates (CF templates, Lambda env vars, local .env)
4. **Legacy Resource Cleanup (FR16-FR18):** Remove 5 legacy AWS resources (2 Lambdas, 1 S3 bucket, 1 CloudFront distribution, 1 API Gateway) following documented dependency order
5. **Frontend Code Maintenance (FR19-FR21):** Remove unused `aws-rum-web` dependency and Cognito Identity Pool references from React frontend
6. **Deployment Orchestration (FR22-FR24):** Complete and document `deploy.ini` with all DEV templates in correct deployment order
7. **Template Consistency (FR25-FR28):** Enforce `ProjectCode` + `Environment` parameter pattern, `${ProjectCode}-${Environment}-<description>` naming, standard tags, and prod-conditional features

**Non-Functional Requirements:**
14 NFRs in 3 categories:
- **Security (NFR1-NFR5):** S3 encryption (SSE-S3/KMS), DynamoDB encryption at rest, no hardcoded secrets, public access blocked by default, Lambda Layer sharing limited to same account
- **Compatibility (NFR6-NFR10):** Deployable via existing `deploy.sh`, no modifications to existing stacks, `validate-template` passes, supports stack updates (not just create), zero-downtime S3 migration
- **Maintainability (NFR11-NFR14):** Self-documenting templates (filename + Description field), SSM Parameter Store paths (not CF Exports), consistent parameter naming across new templates, self-contained templates

**Scale & Complexity:**

- Primary domain: Infrastructure as Code (CloudFormation)
- Complexity level: Medium (brownfield, single developer, single environment)
- Estimated architectural components: ~11 new CF templates + deployment documentation + cleanup procedures
- Project context: Brownfield — codifying existing infrastructure, not creating new application architecture

### Technical Constraints & Dependencies

1. **Existing 8-layer deployment model** — new templates must slot into the correct layer:
   - Layer 4 (Storage): DynamoDB cache tables, S3 buckets, SNS topics
   - Layer 5 (Compute): Lambda Layers
   - Layer 6 (API): API Gateway main application
   - Layer 8 (Email & CDN): SES root domain, CloudFront distribution

2. **SSM Parameter Store convention** — path pattern `/${ProjectCode}/${Environment}/<resource-path>` is mandatory for all cross-stack references. CloudFormation Exports are NOT used.

3. **Naming convention split** — newer templates use `ProjectCode`, older use `ProjectName`. New templates MUST use `ProjectCode`. No refactoring of existing templates in this scope.

4. **deploy.ini + deploy.sh** — existing orchestration mechanism. New templates must be registered in correct order. Script itself is not modified.

5. **No NAT Gateway** — Lambda split (VPC for DB, public for internet) is a cost decision that constrains API Gateway template design.

6. **Single AWS account, DEV environment only** — no multi-account, no multi-environment parameterization in this phase.

### Cross-Cutting Concerns Identified

1. **SSM Parameter Store consistency** — every new template must both export its key identifiers AND consume dependencies via SSM. Inconsistent usage breaks cross-stack integration.
2. **Security defaults** — encryption at rest, public access blocking, no hardcoded secrets. Must be applied uniformly across all new templates.
3. **Template parameter standardization** — `ProjectCode` (default: `lenie`), `Environment` (AllowedValues: dev, qa, prod), standard tags (`Environment`, `Project`). All new templates share this pattern.
4. **Deployment ordering** — templates have layer dependencies. Incorrect ordering in `deploy.ini` causes deployment failures. Documentation must capture the complete dependency graph.
5. **Reference update coordination** — S3 migration requires synchronized updates across CF templates, Lambda environment variables, and local `.env` files. Partial updates break the content flow.

## Starter Template Evaluation

### Primary Technology Domain

Infrastructure as Code (AWS CloudFormation) — brownfield project codifying existing AWS resources. No traditional application "starter template" applies; instead, the established template patterns serve as the canonical foundation for new templates.

### Existing Template Pattern Analysis

**Two template generations coexist in the codebase:**

| Aspect | Generation 1 (older) | Generation 2 (newer) |
|--------|---------------------|---------------------|
| Parameter naming | `stage` or `ProjectName` | `ProjectCode` + `Environment` |
| Environment values | dev, qas, prd | dev, qa, qa2, qa3, prod |
| Output mechanism | Mix of SSM and CF Exports | CF Exports (despite SSM being preferred) |
| SSM path pattern | `/lenie/${stage}/...` (hardcoded project) | Not used for outputs |
| Tags | Inconsistent | `Environment`, `Project` |
| Encryption | Varies | SSE with KMS |
| Prod conditions | Absent | `IsProduction` condition for PITR, etc. |
| Descriptions | Polish/English mix | English |

**Examples:**
- Gen 1: `s3.yaml`, `env-setup.yaml`, `sqs-documents.yaml`, `sqs-application-errors.yaml`, `ses.yaml`
- Gen 2: `dynamodb-documents.yaml`

### Selected Pattern: Generation 2+ (Canonical Template)

New templates will follow an enhanced Generation 2 pattern that resolves the SSM vs CF Exports inconsistency:

**Rationale:** Generation 2 (`dynamodb-documents.yaml`) is the most recent and best-structured pattern, but must be extended to use SSM Parameter Store for outputs (per PRD FR9-FR10, NFR12) instead of CF Exports.

**Canonical Template Structure:**

```yaml
AWSTemplateFormatVersion: '2010-09-09'
Description: '<resource-description> for Project Lenie'

Parameters:
  ProjectCode:
    Type: String
    Default: lenie
  Environment:
    Type: String
    Default: dev
    AllowedValues: [dev, qa, qa2, qa3, prod]
    Description: Environment name

Conditions:
  IsProduction: !Or
    - !Equals [!Ref Environment, prod]
    - !Equals [!Ref Environment, qa]
    - !Equals [!Ref Environment, qa2]
    - !Equals [!Ref Environment, qa3]

Resources:
  # Resource definitions...
  # Resource naming: ${ProjectCode}-${Environment}-<description>

  # SSM Parameter exports (NOT CF Exports)
  <Resource>NameParameter:
    Type: AWS::SSM::Parameter
    Properties:
      Name: !Sub '/${ProjectCode}/${Environment}/<resource-path>/name'
      Type: String
      Value: !Ref <Resource>
      Description: '<description>'

  <Resource>ArnParameter:
    Type: AWS::SSM::Parameter
    Properties:
      Name: !Sub '/${ProjectCode}/${Environment}/<resource-path>/arn'
      Type: String
      Value: !GetAtt <Resource>.Arn
      Description: '<description>'
```

Tags (on all taggable resources):
```yaml
Tags:
  - Key: Environment
    Value: !Ref Environment
  - Key: Project
    Value: !Ref ProjectCode
```

**Architectural Decisions Established by Pattern:**

- **Language & Format:** YAML (consistent with all existing templates)
- **Parameter convention:** `ProjectCode` (default: `lenie`) + `Environment` (5 allowed values)
- **Cross-stack communication:** SSM Parameter Store with path `/${ProjectCode}/${Environment}/<resource-path>`
- **Security defaults:** Encryption at rest (KMS), public access blocked where applicable
- **Tagging:** `Environment` + `Project` tags on all taggable resources
- **Prod conditions:** `IsProduction` condition for features like DynamoDB PITR, S3 versioning
- **Naming:** `${ProjectCode}-${Environment}-<description>` (hyphens for AWS names, underscores for DynamoDB tables)
- **Deployment:** Via existing `deploy.sh` script, registered in `deploy.ini`
- **Template descriptions:** English, self-explanatory

**Note:** This pattern is the first implementation decision — all ~11 new templates must follow it consistently.

## Core Architectural Decisions

### Decision Priority Analysis

**Critical Decisions (Block Implementation):**
1. Template granularity: Separate template per resource
2. Canonical template pattern: Generation 2+ with SSM Parameter Store exports
3. API Gateway strategy: Update `api-gw-app.yaml` from live AWS export, CF import
4. CloudFront S3 access: OAC (Origin Access Control), not legacy OAI
5. Existing resource strategy: Mix — CF import for stateful (DynamoDB, S3), recreate for stateless (Lambda Layers)
6. Lambda Layer versioning: Layer ARN (with version) exported via SSM Parameter, consumed by Lambda templates

**Important Decisions (Shape Architecture):**
7. SNS topics `rds-monitor-sns` and `ses-monitoring` — removed from scope, added to legacy cleanup
8. SES identities (`lenie-ai.eu`, `dev.lenie-ai.eu`) — removed from scope, added to legacy cleanup. Existing `ses.yaml` template to be removed from repo and `deploy.ini`

**Deferred Decisions (Post-MVP):**
- CI/CD template validation (cfn-lint, cfn-guard in pipeline)
- Multi-environment parameterization (dev/qa/prod from single template set)
- Migration of existing templates from Gen 1 → Gen 2+ pattern
- Replacement of CF Exports with SSM Parameters in existing templates

### Scope Changes from PRD

| Aspect | PRD Original | After Architecture Decisions |
|--------|-------------|------------------------------|
| New CF templates | ~11 | ~8 (removed: 2 SNS, 1 SES) |
| Legacy resources to remove | 5 | 9 (+2 SNS topics, +2 SES identities) |
| FR5 (SNS templates) | In scope | Removed — resources deleted |
| FR6 (SES root domain) | In scope | Removed — resources deleted |
| `ses.yaml` | Keep | Remove from repo and deploy.ini |

### Template Organization

**Decision:** One template per resource (not grouped).

**Rationale:** Maximizes isolation — each template can be deployed, updated, or rolled back independently. Consistent with existing `dynamodb-documents.yaml` (single resource) pattern. Reduces blast radius of changes.

**New templates (8):**

| Template | Layer | Resource | Strategy |
|----------|-------|----------|----------|
| `dynamodb-cache-ai-query.yaml` | 4. Storage | DynamoDB `lenie_cache_ai_query` | CF import |
| `dynamodb-cache-language.yaml` | 4. Storage | DynamoDB `lenie_cache_language` | CF import |
| `dynamodb-cache-translation.yaml` | 4. Storage | DynamoDB `lenie_cache_translation` | CF import |
| `s3-website-content.yaml` | 4. Storage | S3 `lenie-dev-website-content` | Recreate (new name) |
| `s3-app-web.yaml` | 4. Storage | S3 `lenie-dev-app-web` | CF import |
| `lambda-layer-lenie-all.yaml` | 5. Compute | Lambda Layer `lenie_all_layer` | Recreate |
| `lambda-layer-openai.yaml` | 5. Compute | Lambda Layer `lenie_openai` | Recreate |
| `lambda-layer-psycopg2.yaml` | 5. Compute | Lambda Layer `psycopg2_new_layer` | Recreate |

**Additionally updated (not new):**
| `api-gw-app.yaml` | 6. API | API Gateway `lenie_split` | Update from live + CF import |
| `cloudfront-app.yaml` | 8. CDN | CloudFront `ETIQTXICZBECA` | CF import |

Total physical template files: 10 (8 new + 2 updated/new for API GW and CloudFront).

### API Gateway Strategy

**Decision:** Update existing `api-gw-app.yaml` to match live AWS configuration, then CF import.

**Rationale:** Live AWS configuration is the source of truth. The existing template may be outdated. Export live config via `aws apigateway get-export --rest-api-id 1bkc3kz7c9 --stage-name dev --export-type oas30`, reconcile with template, import resource into CF stack.

**Execution sequence:**
1. Export live API Gateway configuration (OpenAPI 3.0) as a reference document
2. Inspect live resources: `aws apigateway get-resources`, `get-method`, `get-integration` for each endpoint
3. Build/update CF template manually based on live inspection (OpenAPI export alone is not a direct CF input)
4. Compare with existing `api-gw-app.yaml` and reconcile
5. Use `aws cloudformation create-change-set --change-set-type IMPORT` to adopt
6. Verify stack matches live API — no drift

### CloudFront Access Control

**Decision:** Use OAC (Origin Access Control) for new CloudFront distribution.

**Rationale:** OAC is the AWS-recommended approach, replacing legacy OAI. Better support for SSE-KMS encryption, more granular permissions, actively maintained. Existing `cloudfront-helm.yaml` uses OAI but new templates should follow current best practices.

**Implementation phasing:** Phase 1: Import existing CloudFront distribution with its current access configuration (likely OAI) — CF import requires exact match with live state. Phase 2: Update to OAC via CF stack update after successful import and drift verification.

### Existing Resource Management

**Decision:** Mix strategy based on resource state.

| Resource Type | Strategy | Rationale |
|--------------|----------|-----------|
| DynamoDB cache tables (3) | CF import | Contain cache data (non-critical but avoidable loss) |
| S3 `lenie-dev-app-web` | CF import | Contains deployed frontend files |
| S3 `lenie-dev-website-content` | Recreate | New name (migration from `lenie-s3-tmp`) |
| Lambda Layers (3) | Recreate | Stateless — new version created on each deploy anyway |
| CloudFront `ETIQTXICZBECA` | CF import | Complex config, avoid recreation risk |
| API Gateway `lenie_split` | CF import | Complex config (13+ endpoints), must preserve API ID |

### Lambda Layer Versioning

**Decision:** Layer ARN (including version number) exported via SSM Parameter Store.

**SSM path pattern:**
- `/${ProjectCode}/${Environment}/lambda/layers/<layer-name>/arn` — full ARN with version

**Workflow:** Deploy layer template → SSM updated with new ARN → update consuming Lambda stacks → Lambdas pick up new layer version.

### Legacy Resource Cleanup (Updated)

**Total: 9 resources to remove (was 5 in PRD)**

| # | Resource | Type | Rationale |
|---|----------|------|-----------|
| 1 | `E19SWSRXVWFGJQ` | CloudFront | Test distribution |
| 2 | `lenie-s3-web-test` | S3 | Test bucket |
| 3 | `lenie_2_internet_tmp` | Lambda | Temporary copy |
| 4 | `lenie-url-add` | Lambda | Replaced by CF-managed `lenie-dev-url-add` |
| 5 | `pir31ejsf2` | API Gateway | Old `lenie_chrome_extension` |
| 6 | `rds-monitor-sns` | SNS Topic | Dead subscription (Lambda doesn't exist) |
| 7 | `ses-monitoring` | SNS Topic | Not referenced by any code |
| 8 | `lenie-ai.eu` | SES Identity | Root domain — not used by application |
| 9 | `dev.lenie-ai.eu` | SES Identity | Subdomain — not used by application |

**Removal also includes:**
- Delete `ses.yaml` template from `infra/aws/cloudformation/templates/`
- Remove `ses.yaml` entry from `deploy.ini`

### Decision Impact Analysis

**Implementation Sequence:**
1. DynamoDB cache tables (standalone, CF import — quick wins)
2. Lambda Layers (recreate — needed before API Gateway update)
3. S3 `lenie-dev-website-content` (recreate, then data migration from `lenie-s3-tmp`)
4. S3 `lenie-dev-app-web` (CF import)
5. CloudFront `app.dev.lenie-ai.eu` (CF import, depends on S3 app-web)
6. API Gateway `api-gw-app.yaml` update (most complex — export, reconcile, import)
7. Legacy resource removal (after all templates verified)
8. Frontend cleanup (aws-rum-web, Cognito)
9. `deploy.ini` update + deployment order documentation

**Cross-Component Dependencies:**
- Lambda Layers → must be deployed before any Lambda template update (layers provide ARN via SSM)
- S3 `lenie-dev-website-content` → must exist before updating `url-add.yaml` Lambda env var reference
- CloudFront → depends on S3 `lenie-dev-app-web` existing
- API Gateway → depends on Lambda Layers being deployed (references layer ARNs)
- Legacy cleanup → must happen after all new templates are verified working

## Implementation Patterns & Consistency Rules

### Critical Conflict Points Identified

7 areas where AI agents could make different choices when writing CloudFormation templates for this project.

### Naming Patterns

**CF Logical Resource IDs:**
- PascalCase, descriptive, no environment prefix
- Pattern: `<ResourceType><Purpose>`
- Examples: `CacheAiQueryTable`, `WebsiteContentBucket`, `LeniAllLayer`
- Anti-pattern: `MyDynamoDBTable`, `lenie-dev-cache-table`, `Table1`

**SSM Parameter Paths:**
- Pattern: `/${ProjectCode}/${Environment}/<service>/<resource-name>/<attribute>`
- Service names: `dynamodb`, `s3`, `lambda`, `cloudfront`, `apigateway`
- Attribute names: `name`, `arn`, `url`, `id`
- Examples:
  - `/${ProjectCode}/${Environment}/dynamodb/cache-ai-query/arn`
  - `/${ProjectCode}/${Environment}/s3/website-content/name`
  - `/${ProjectCode}/${Environment}/lambda/layers/lenie-all/arn`
  - `/${ProjectCode}/${Environment}/cloudfront/app/domain-name`
- Anti-pattern: `/lenie/dev/MyTable/ARN` (hardcoded project, PascalCase path)

**Template File Naming:**
- Pattern: `<service>-<resource-description>.yaml`
- Lowercase, hyphens between words
- Examples: `dynamodb-cache-ai-query.yaml`, `s3-website-content.yaml`, `lambda-layer-lenie-all.yaml`
- Anti-pattern: `DynamoDB_cache.yaml`, `my-new-template.yaml`

### Structure Patterns

**Template Section Ordering (mandatory):**
```yaml
AWSTemplateFormatVersion: '2010-09-09'
Description: '...'

Parameters:
  # ProjectCode, Environment first, then resource-specific

Conditions:
  # IsProduction first, then others

Resources:
  # 1. Primary resource(s)
  # 2. Supporting resources (policies, roles)
  # 3. SSM Parameter exports (always last in Resources)

# No Outputs section — use SSM Parameters instead
```

**DeletionPolicy:**
- CF import resources: `DeletionPolicy: Retain` on the primary resource (required for import)
- Recreated resources: No DeletionPolicy (default: Delete)
- SSM Parameters: Never add DeletionPolicy

**Indentation:** 2 spaces (consistent with all existing templates)

**Comments:**
- Language: English only
- Style: `# Single line comment` above the resource/property
- Use comments only for non-obvious decisions, not for describing what CF does

### Format Patterns

**Description Field:**
- Pattern: `<Resource description> for Project Lenie`
- Language: English
- Examples: `DynamoDB cache table for AI query results for Project Lenie`
- Anti-pattern: `Template do utworzenia tabeli DynamoDB` (Polish)

**SSM Parameter Consumption:**
- Use `AWS::SSM::Parameter::Value<String>` parameter type for consuming SSM values
- NOT `{{resolve:ssm:...}}` dynamic references (harder to debug, not visible in change sets)
- Example:
```yaml
Parameters:
  S3BucketName:
    Type: AWS::SSM::Parameter::Value<String>
    Default: '/${ProjectCode}/${Environment}/s3/website-content/name'
```

**Tag Values:**
- `Environment`: Value from `!Ref Environment` parameter
- `Project`: Value from `!Ref ProjectCode` parameter
- No additional tags unless resource-specific need

### Process Patterns

**CF Import Procedure (for stateful resources):**
1. Write template matching live resource configuration exactly
2. Add `DeletionPolicy: Retain` to primary resource
3. Validate: `aws cloudformation validate-template --template-body file://template.yaml`
4. Create import change set: `aws cloudformation create-change-set --change-set-type IMPORT --resources-to-import`
5. Review and execute change set
6. Verify no drift: `aws cloudformation detect-stack-drift`

**Validation Before Commit:**
- Run `aws cloudformation validate-template` locally before committing
- cfn-lint in CI/CD is deferred (Phase 2) but local usage is encouraged

**Parameter Files:**
- Create `parameters/dev/<template-name>.json` for each new template
- Standard format:
```json
[
  {"ParameterKey": "ProjectCode", "ParameterValue": "lenie"},
  {"ParameterKey": "Environment", "ParameterValue": "dev"}
]
```

**deploy.ini Entry:**
- Uncommented for DEV: `templates/<template-name>.yaml`
- Position: within the correct layer group, after dependencies

### Enforcement Guidelines

**All AI Agents MUST:**
1. Follow the canonical template structure (Parameters → Conditions → Resources with SSM exports last)
2. Use SSM Parameters for all cross-stack outputs (never CF Exports)
3. Use `ProjectCode` parameter (not `ProjectName` or `stage`)
4. Include `Environment` and `Project` tags on all taggable resources
5. Write all descriptions and comments in English
6. Use `AWS::SSM::Parameter::Value<String>` for consuming cross-stack values
7. Validate templates with `aws cloudformation validate-template` before marking work complete

**Anti-Patterns (NEVER do this):**
- Hardcode AWS account IDs, ARNs, or resource names
- Use CloudFormation Exports (`Export:` / `Fn::ImportValue`)
- Mix `ProjectCode` and `ProjectName` parameter names
- Write descriptions or comments in Polish
- Skip SSM Parameter exports for resource identifiers
- Create Outputs section (use SSM Parameters instead)

## Project Structure & Boundaries

### Complete Directory Structure (Changes Only)

Files to create (NEW), modify (MOD), or delete (DEL):

```
infra/aws/cloudformation/
├── deploy.ini                                          [MOD] Add new templates, remove ses.yaml
├── deploy.sh                                           [NO CHANGE]
├── templates/
│   ├── dynamodb-cache-ai-query.yaml                    [NEW] DynamoDB lenie_cache_ai_query
│   ├── dynamodb-cache-language.yaml                    [NEW] DynamoDB lenie_cache_language
│   ├── dynamodb-cache-translation.yaml                 [NEW] DynamoDB lenie_cache_translation
│   ├── s3-website-content.yaml                         [NEW] S3 lenie-dev-website-content
│   ├── s3-app-web.yaml                                 [NEW] S3 lenie-dev-app-web
│   ├── lambda-layer-lenie-all.yaml                     [NEW] Lambda Layer lenie_all_layer
│   ├── lambda-layer-openai.yaml                        [NEW] Lambda Layer lenie_openai
│   ├── lambda-layer-psycopg2.yaml                      [NEW] Lambda Layer psycopg2_new_layer
│   ├── cloudfront-app.yaml                             [NEW] CloudFront ETIQTXICZBECA
│   ├── api-gw-app.yaml                                 [MOD] Update from live AWS export + CF import
│   ├── ses.yaml                                        [DEL] SES not used by application
│   ├── url-add.yaml                                    [MOD] Update S3 bucket reference to lenie-dev-website-content
│   └── ... (existing templates unchanged)
├── parameters/
│   └── dev/
│       ├── dynamodb-cache-ai-query.json                [NEW]
│       ├── dynamodb-cache-language.json                 [NEW]
│       ├── dynamodb-cache-translation.json              [NEW]
│       ├── s3-website-content.json                      [NEW]
│       ├── s3-app-web.json                              [NEW]
│       ├── lambda-layer-lenie-all.json                  [NEW]
│       ├── lambda-layer-openai.json                     [NEW]
│       ├── lambda-layer-psycopg2.json                   [NEW]
│       ├── cloudfront-app.json                          [NEW]
│       └── ... (existing parameter files unchanged)
└── apigw/
    └── lenie-split-export.json                         [NEW] Live API Gateway export (reference)

web_interface_react/
├── src/
│   └── authorizationContext.js                         [MOD] Remove aws-rum-web, Cognito
├── package.json                                        [MOD] Remove aws-rum-web dependency

infra/aws/README.md                                     [MOD] Update legacy resources section
```

**File count summary:**
- New files: 18 (9 templates + 9 parameter files)
- Modified files: 5 (deploy.ini, api-gw-app.yaml, url-add.yaml, authorizationContext.js, package.json)
- Deleted files: 1 (ses.yaml)

### Requirements to Structure Mapping

| FR Group | Files Affected |
|----------|---------------|
| FR1 (DynamoDB cache) | `dynamodb-cache-ai-query.yaml`, `dynamodb-cache-language.yaml`, `dynamodb-cache-translation.yaml` + parameter files |
| FR2 (Lambda Layers) | `lambda-layer-lenie-all.yaml`, `lambda-layer-openai.yaml`, `lambda-layer-psycopg2.yaml` + parameter files |
| FR3 (S3 website-content) | `s3-website-content.yaml` + parameter file |
| FR4 (S3 app-web) | `s3-app-web.yaml` + parameter file |
| FR7 (CloudFront) | `cloudfront-app.yaml` + parameter file |
| FR8 (API Gateway) | `api-gw-app.yaml` (update) |
| FR9-FR11 (Cross-stack) | SSM Parameter resources in each new template |
| FR12-FR15 (S3 migration) | `s3-website-content.yaml`, `url-add.yaml` (MOD), local `.env` |
| FR16-FR18 (Legacy cleanup) | AWS CLI operations (no file changes except README.md) |
| FR19-FR21 (Frontend cleanup) | `authorizationContext.js`, `package.json` |
| FR22-FR24 (deploy.ini) | `deploy.ini` |
| FR25-FR28 (Consistency) | All new templates follow canonical pattern |

### Architectural Boundaries

**Template Boundaries:**
Each template is self-contained and communicates only via SSM Parameter Store:
```
Template A ──writes──> SSM Parameter ──reads──> Template B
```

No template directly references another template's resources. All cross-stack integration is mediated by SSM.

**Layer Dependency Boundaries:**
```
Layer 4 (Storage)         → No dependencies on other new templates
  ├── DynamoDB cache (×3)   Independent, deployable in any order
  ├── S3 website-content     Independent
  └── S3 app-web             Independent

Layer 5 (Compute)         → Depends on Layer 4 (S3 cloudformation bucket for code)
  └── Lambda Layers (×3)    Independent of each other

Layer 6 (API)             → Depends on Layer 5 (Lambda Layers via SSM)
  └── api-gw-app.yaml       References layer ARNs from SSM

Layer 8 (CDN)             → Depends on Layer 4 (S3 app-web)
  └── cloudfront-app.yaml   References S3 bucket from SSM
```

**deploy.ini Target Structure (DEV section):**
```ini
[dev]
; --- Layer 1: Foundation ---
templates/env-setup.yaml
templates/budget.yaml
templates/1-domain-route53.yaml

; --- Layer 2: Networking ---
templates/vpc.yaml
templates/security-groups.yaml

; --- Layer 3: Security ---
templates/secrets.yaml

; --- Layer 4: Storage ---
templates/s3.yaml
templates/s3-cloudformation.yaml
templates/dynamodb-documents.yaml
templates/dynamodb-cache-ai-query.yaml
templates/dynamodb-cache-language.yaml
templates/dynamodb-cache-translation.yaml
templates/s3-website-content.yaml
templates/s3-app-web.yaml
templates/sqs-documents.yaml
templates/sqs-application-errors.yaml

; --- Layer 5: Compute ---
templates/lambda-layer-lenie-all.yaml
templates/lambda-layer-openai.yaml
templates/lambda-layer-psycopg2.yaml
templates/ec2-lenie.yaml
templates/lenie-launch-template.yaml
templates/lambda-rds-start.yaml
templates/lambda-weblink-put-into-sqs.yaml
templates/sqs-to-rds-lambda.yaml
templates/url-add.yaml

; --- Layer 6: API ---
templates/api-gw-infra.yaml
templates/api-gw-app.yaml
templates/api-gw-url-add.yaml

; --- Layer 7: Orchestration ---
templates/sqs-to-rds-step-function.yaml

; --- Layer 8: CDN ---
templates/cloudfront-app.yaml
templates/s3-helm.yaml
templates/cloudfront-helm.yaml
```

### Development Workflow

**For each new template, the agent workflow is:**
1. Create `templates/<name>.yaml` following canonical pattern
2. Create `parameters/dev/<name>.json` with ProjectCode + Environment
3. Validate: `aws cloudformation validate-template --template-body file://templates/<name>.yaml`
4. For CF import: match live resource config exactly, add `DeletionPolicy: Retain`
5. Add entry to `deploy.ini` in correct layer position
6. Deploy: `./deploy.sh -p lenie -s dev` (or import changeset for existing resources)
7. Verify SSM Parameters created correctly

## Architecture Validation Results

### Coherence Validation ✅

**Decision Compatibility:**
All architectural decisions work together without conflicts. The Gen 2+ canonical pattern with SSM exports is consistent with the separate-template-per-resource approach. The mix strategy (CF import for stateful, recreate for stateless) aligns with resource characteristics. Lambda Layer ARN via SSM feeds cleanly into consuming Lambda templates. OAC for CloudFront is compatible with SSE-KMS encryption on S3 (unlike legacy OAI). No contradictions detected between any decisions.

**Pattern Consistency:**
Implementation patterns fully support the architectural decisions. Naming conventions are consistent across all areas: PascalCase for CF logical IDs, lowercase-hyphens for file names, slash-delimited paths for SSM Parameters. Template structure ordering is mandatory and well-defined. Tags (`Environment` + `Project`) are uniform. The SSM Parameter consumption pattern (`AWS::SSM::Parameter::Value<String>`) is specified with examples.

**Structure Alignment:**
The project structure supports all architectural decisions. The directory layout accommodates 18 new files, 5 modifications, and 1 deletion. The `deploy.ini` target structure covers all 8 deployment layers with correct dependency ordering. Parameter files exist for each template. Integration points are mediated exclusively through SSM Parameter Store, and layer boundaries (4→5→6→8) correctly reflect resource dependencies.

### Requirements Coverage Validation ✅

**Functional Requirements Coverage:**

| FR | Status | Architectural Support |
|----|--------|----------------------|
| FR1 (DynamoDB cache ×3) | ✅ Covered | Templates: `dynamodb-cache-ai-query/language/translation.yaml` |
| FR2 (Lambda Layers ×3) | ✅ Covered | Templates: `lambda-layer-lenie-all/openai/psycopg2.yaml` |
| FR3 (S3 website-content) | ✅ Covered | Template: `s3-website-content.yaml` (recreate with new name) |
| FR4 (S3 app-web) | ✅ Covered | Template: `s3-app-web.yaml` (CF import) |
| FR5 (SNS topics) | ⬜ Removed | Architectural decision: resources to be deleted, not codified |
| FR6 (SES root domain) | ⬜ Removed | Architectural decision: resources to be deleted, not codified |
| FR7 (CloudFront) | ✅ Covered | Template: `cloudfront-app.yaml` (CF import, OAI→OAC phased) |
| FR8 (API Gateway) | ✅ Covered | Template: `api-gw-app.yaml` (update from live + CF import) |
| FR9-11 (Cross-stack SSM) | ✅ Covered | Canonical pattern includes SSM Parameter exports |
| FR12-15 (S3 migration) | ✅ Covered | New bucket template + sync procedure + reference updates |
| FR16-18 (Legacy cleanup) | ✅ Covered | Expanded from 5→9 resources with documented order |
| FR19-21 (Frontend cleanup) | ✅ Covered | Files identified: `authorizationContext.js`, `package.json` |
| FR22-24 (deploy.ini) | ✅ Covered | Target `deploy.ini` structure with all 8 layers |
| FR25-28 (Consistency) | ✅ Covered | Canonical pattern enforces all consistency rules |

**Non-Functional Requirements Coverage:**

| NFR | Status | Architectural Support |
|-----|--------|----------------------|
| NFR1 (S3 encryption) | ✅ | Canonical pattern mandates SSE-S3/KMS |
| NFR2 (DynamoDB encryption) | ✅ | KMS encryption in canonical pattern |
| NFR3 (No hardcoded secrets) | ✅ | SSM Parameter consumption pattern |
| NFR4 (S3 public access block) | ✅ | Default block, CloudFront OAC exception |
| NFR5 (Lambda Layer same account) | ✅ | No cross-account sharing configured |
| NFR6 (deploy.sh compatible) | ✅ | No script modifications required |
| NFR7 (No existing stack mods) | ✅ | Integration via SSM reads only |
| NFR8 (validate-template) | ✅ | Validation step in development workflow |
| NFR9 (Stack update support) | ✅ | Inherent in CF design |
| NFR10 (Zero-downtime S3 migration) | ✅ | New bucket created first, old stays until switch |
| NFR11 (Self-documenting) | ✅ | Naming conventions + Description field pattern |
| NFR12 (SSM not CF Exports) | ✅ | Core architectural decision |
| NFR13 (Consistent naming) | ✅ | Canonical pattern enforces ProjectCode |
| NFR14 (Self-contained) | ✅ | Architectural boundaries via SSM |

**Scope Changes Justified:**
FR5 and FR6 were removed based on evidence that the underlying AWS resources (2 SNS topics, 2 SES identities) are not used by any application code. These resources were moved to the legacy cleanup list (FR16-18), expanding it from 5 to 9 items. The net effect is fewer templates to create and a cleaner AWS account.

### Implementation Readiness Validation ✅

**Decision Completeness:**
All critical decisions are documented with rationale. The canonical template pattern includes a complete YAML code example. Consistency rules are explicit and enforceable (7 "MUST" rules + 6 "NEVER" anti-patterns). The CF import procedure is documented step-by-step. SSM path convention is specified with examples for each service type.

**Structure Completeness:**
The project structure is complete with 18 new files, 5 modifications, and 1 deletion — all annotated with [NEW], [MOD], or [DEL]. The requirements-to-structure mapping covers every FR group. Layer dependency boundaries are visualized. The target `deploy.ini` shows exact file ordering.

**Pattern Completeness:**
All 7 identified conflict points are resolved with explicit patterns. Naming conventions cover logical IDs, SSM paths, file names, and Description fields — each with examples and anti-patterns. Process patterns cover CF import, validation, parameter files, and `deploy.ini` entries. Enforcement guidelines are clear for AI agents.

### Gap Analysis Results

**Critical Gaps:** None found.

**Important Gaps (Addressed):**

1. **CloudFront OAC import phasing** — CF import requires exact match with live state. If the existing distribution uses OAI, the import must use OAI first. Migration to OAC is a post-import update. *Resolution: Added phasing note to the CloudFront Access Control decision.*

2. **API Gateway export-to-template conversion** — OpenAPI 3.0 export is not a direct CF template input. The CF template must be built manually by inspecting live API resources. *Resolution: Updated the execution sequence to clarify that `get-resources` / `get-method` / `get-integration` inspection is the primary source, not the OpenAPI export.*

**Nice-to-Have Gaps (Deferred):**

3. S3 migration runbook with exact CLI commands — useful but belongs in implementation stories, not architecture
4. Rollback procedures for failed CF imports — standard CF rollback applies; no architecture-level decision needed
5. Template testing strategy beyond `validate-template` — deferred to Phase 2 (cfn-lint, cfn-guard in CI/CD)

### Architecture Completeness Checklist

**✅ Requirements Analysis**

- [x] Project context thoroughly analyzed (brownfield IaC, single dev, DEV env)
- [x] Scale and complexity assessed (medium — ~8 new templates)
- [x] Technical constraints identified (8-layer model, SSM convention, no NAT GW)
- [x] Cross-cutting concerns mapped (SSM consistency, security defaults, naming, deploy order)

**✅ Architectural Decisions**

- [x] Critical decisions documented with rationale (6 critical + 2 important)
- [x] Technology stack fully specified (CF YAML, SSM Parameters, Gen 2+ pattern)
- [x] Integration patterns defined (SSM Parameter Store as sole cross-stack mechanism)
- [x] Implementation strategy per resource defined (import vs recreate matrix)

**✅ Implementation Patterns**

- [x] Naming conventions established (4 areas with examples + anti-patterns)
- [x] Structure patterns defined (template section ordering, DeletionPolicy rules)
- [x] Format patterns specified (Description, SSM consumption, tags)
- [x] Process patterns documented (CF import procedure, validation, deploy.ini)

**✅ Project Structure**

- [x] Complete directory structure defined (NEW/MOD/DEL annotations)
- [x] Component boundaries established (templates communicate only via SSM)
- [x] Integration points mapped (layer dependency diagram)
- [x] Requirements to structure mapping complete (FR → file table)

### Architecture Readiness Assessment

**Overall Status:** READY FOR IMPLEMENTATION

**Confidence Level:** High — all critical decisions are made, no blocking gaps remain, patterns are comprehensive with examples.

**Key Strengths:**

1. **Clear canonical pattern** — single, well-documented template pattern eliminates ambiguity for AI agents
2. **Comprehensive conflict resolution** — 7 potential conflict points identified and resolved upfront
3. **Evidence-based scope changes** — FR5/FR6 removal supported by codebase search and live AWS verification
4. **Phased approach for complex resources** — CloudFront (import then OAC) and API Gateway (inspect, build, import) have realistic execution plans
5. **Strong traceability** — every FR maps to specific files, every decision has rationale

**Areas for Future Enhancement:**

1. Migration of existing Gen 1 templates to Gen 2+ pattern (separate initiative)
2. Replacement of CF Exports with SSM Parameters in existing templates
3. CI/CD template validation (cfn-lint, cfn-guard — Phase 2)
4. Multi-environment parameterization (Phase 3)
5. Full deployment automation (single-command environment recreation — Phase 3)

### Implementation Handoff

**AI Agent Guidelines:**

- Follow the Gen 2+ canonical template pattern exactly as documented in "Starter Template Evaluation"
- Use SSM Parameter Store for ALL cross-stack communication — never CF Exports
- Respect the 7 enforcement rules and 6 anti-patterns in "Implementation Patterns & Consistency Rules"
- Check layer dependencies before adding templates to `deploy.ini`
- For CF import: match live resource configuration exactly, verify with drift detection
- Validate every template with `aws cloudformation validate-template` before marking complete

**First Implementation Priority:**

1. DynamoDB cache tables (×3) — standalone, no dependencies, CF import, quick wins
2. Lambda Layers (×3) — recreate, needed before API Gateway work
3. S3 buckets (×2) — `website-content` (recreate), `app-web` (CF import)

**Implementation Sequence (Full):**

```
Phase A (standalone):  dynamodb-cache-ai-query → dynamodb-cache-language → dynamodb-cache-translation
Phase B (compute):     lambda-layer-lenie-all → lambda-layer-openai → lambda-layer-psycopg2
Phase C (storage):     s3-website-content (recreate) → s3-app-web (CF import)
Phase D (CDN):         cloudfront-app (CF import, then OAC update)
Phase E (API):         api-gw-app (inspect live, build template, CF import)
Phase F (migration):   S3 data sync lenie-s3-tmp → lenie-dev-website-content, update references
Phase G (cleanup):     Legacy resource removal (9 resources in dependency order)
Phase H (frontend):    Remove aws-rum-web, Cognito from React code
Phase I (docs):        Update deploy.ini, README.md
```

---

# Sprint 4 — AWS Infrastructure Consolidation & Tooling

_Continuation of architecture decisions for Sprint 4. Sprint 1 decisions (canonical template pattern, SSM conventions, naming, deployment workflow) remain in effect as foundational context._

## Sprint 4 — Project Context Analysis

### Requirements Overview

**Functional Requirements:**
32 FRs organized in 6 capability groups:
1. **Remove Elastic IP (FR1-FR5):** Remove ElasticIP and EIPAssociation from ec2-lenie.yaml, update Outputs to dynamic public IP, verify Route53 update via aws_ec2_route53.py. EC2 is typically stopped (started on-demand for RDS access), making idle EIP charges (~$3.65/month) pure waste.
2. **Fix Lambda Naming (FR6-FR11):** Fix FunctionName in lambda-rds-start.yaml from `${AWS::StackName}` to `${ProjectCode}-${Environment}-rds-start`, verify all other templates, update all consumers (Step Function definitions, parameter files, API GW integrations).
3. **API GW Consolidation (FR12-FR21):** Merge `/url_add` from api-gw-url-add.yaml into api-gw-app.yaml, migrate API key/usage plan/Lambda permission, update Chrome extension and add-url React app URLs, remove standalone template, verify 51200 byte limit. Most architecturally complex story.
4. **Deployment Script Safety (FR22-FR25):** Add AWS account ID display, env file name display, profile/environment/bucket display, confirmation prompt to zip_to_s3.sh.
5. **CRLF Verification (FR26-FR28):** Verify parameter file line endings, verify .gitattributes coverage, document findings.
6. **Documentation Consolidation (FR29-FR32):** Create single-source metrics file at docs/infrastructure-metrics.md, fix discrepancies across 7+ files, automated verification script.

**Non-Functional Requirements:**
15 NFRs in 4 categories:
- **Reliability & Safety (NFR1-NFR5):** Existing endpoints continue working post-consolidation (smoke test), EC2 accessible after EIP removal, no active resources removed, rollback via git+CF, client apps work with new endpoint.
- **IaC Quality (NFR6-NFR9):** cfn-lint validation passes, Lambda naming convention enforced, template under 51200 byte limit, deploy.ini order correct after template removal.
- **Operational Safety (NFR10-NFR12):** Account ID displayed before deployment, confirmation required, LF line endings enforced.
- **Documentation Quality (NFR13-NFR15):** Single source of truth for metrics, automated drift detection, all docs reflect post-consolidation state.

**Scale & Complexity:**

- Primary domain: AWS Infrastructure consolidation and operational tooling
- Complexity level: Low-Medium (brownfield modifications, single developer, single environment)
- Estimated changes: ~6 CF templates modified/removed, ~3 client files updated, ~2 scripts improved, ~7 documentation files corrected
- Project context: Brownfield — consolidating existing infrastructure, not creating new resources

### Technical Constraints & Dependencies

1. **Existing Gen 2+ canonical template pattern** from Sprint 1 — all CF modifications must maintain consistency with established conventions (ProjectCode + Environment parameters, SSM exports, standard tags).

2. **api-gw-app.yaml complexity** — 632 lines with entire OpenAPI spec inlined, hardcoded Lambda function names (`lenie_2_db`, `lenie_2_internet`), `DeletionPolicy: Retain`. Template modifications require careful handling.

3. **51200 byte CloudFormation inline limit** — api-gw-app.yaml is currently under the limit. Adding /url_add endpoint (~60 lines) must keep it within bounds. Fallback: `aws cloudformation package` for S3-based deployment.

4. **Two AWS accounts** — current production (`008971653395`, env.sh) and target migration (`049706517731`, env_lenie_2025.sh). Scripts must clearly indicate which account they target.

5. **Client app hardcoded URLs** — Chrome extension `popup.html` and add-url React app `App.js` have hardcoded API Gateway URLs that must be updated after B-14 consolidation.

6. **Implementation order matters** — B-5 (Lambda naming) before B-14 (API GW consolidation) to ensure merged template has correct references. B-14 before B-19 (documentation) to reflect post-consolidation state.

### Cross-Cutting Concerns Identified

1. **Implementation sequencing** — B-11 (deployment safety) and B-12 (CRLF) first for immediate operational benefit. B-4 (EIP) and B-5 (Lambda naming) next as independent changes. B-14 (API GW consolidation) as the main architectural work. B-19 (documentation) last to capture final state.
2. **Template modification safety** — api-gw-app.yaml has Retain policies and hardcoded values. Changes must be tested thoroughly (cfn-lint, smoke test) before deployment.
3. **Consistency with Sprint 1 architecture** — all modifications must follow the canonical Gen 2+ template pattern established in Sprint 1 architecture decisions (SSM exports, ProjectCode+Environment parameters, standard tags).
4. **Documentation accuracy chain** — B-19 depends on B-14 completion to know the final API GW structure. Creating the metrics file too early would embed incorrect counts.

## Sprint 4 — Starter Template Evaluation

### Primary Technology Domain

AWS Infrastructure modification (CloudFormation templates, bash scripts, documentation). No new application or framework — Sprint 4 modifies existing brownfield resources.

### Existing Pattern Reuse

**Decision:** Reuse the Generation 2+ canonical template pattern from Sprint 1 architecture.

**Rationale:** Sprint 4 does not create new templates from scratch. All changes modify existing templates or remove templates. The Gen 2+ pattern (ProjectCode + Environment parameters, SSM Parameter Store exports, standard tags, IsProduction condition) remains the governing standard for any template modifications.

**Sprint 4-Specific Pattern Notes:**

1. **api-gw-app.yaml** is a special case — it uses an inline OpenAPI Body specification (not the standard CF resource pattern). Modifications to this template follow the OpenAPI 3.0.1 structure within the Body, not the Gen 2+ resource pattern directly.

2. **Bash script modifications** (zip_to_s3.sh) follow existing shell scripting conventions in the project: sourcing env files, using AWS CLI, standard bash error handling.

3. **Documentation files** follow existing Markdown conventions with CLAUDE.md files per directory.

No starter template evaluation needed — all work builds on established patterns.

## Sprint 4 — Core Architectural Decisions

### Decision Priority Analysis

**Critical Decisions (Block Implementation):**
1. API Gateway consolidation approach: Inline merge of /url_add into api-gw-app.yaml OpenAPI Body
2. API key migration: Use existing api-gw-app API key, update client apps (URL + key), do not migrate ApiKey/UsagePlan CF resources
3. Lambda function rename strategy: In-place CF update (replacement) for lambda-rds-start.yaml — acceptable downtime for on-demand function

**Important Decisions (Shape Architecture):**
4. EIP removal — Outputs handling: Remove PublicIP output entirely (nothing consumes it)
5. Hardcoded Lambda names in api-gw-app.yaml (lenie_2_db, lenie_2_internet): Leave as-is — covered by future backlog item B-3 (rename-legacy-lambda-lenie-2-internet-and-db)
6. deploy.ini handling: Remove api-gw-url-add.yaml entry after manual stack deletion
7. zip_to_s3.sh confirmation pattern: Header display + --yes flag for automation bypass

**Deferred Decisions (Future Sprints):**
- B-3: Rename lenie_2_db and lenie_2_internet to ${ProjectCode}-${Environment} pattern + parameterize in api-gw-app.yaml
- B-6: Migrate api-gw-app stage to separate CF resource
- B-13: Parameterize StageDescription for multi-environment support

### API Gateway Consolidation Strategy

**Decision:** Inline merge — add /url_add path definition (POST + OPTIONS with CORS, Lambda proxy integration to lenie-dev-url-add) directly into the OpenAPI Body of api-gw-app.yaml. Add AWS::Lambda::Permission resource for the url-add Lambda function.

**Rationale:** api-gw-app.yaml is 632 lines. Adding ~60 lines for /url_add keeps it well within manageable size. The 51200 byte CloudFormation inline limit must be verified post-merge. Fallback: aws cloudformation package for S3-based deployment.

**API Key Strategy:** The /url_add endpoint inherits the existing api_key security scheme defined in api-gw-app.yaml's OpenAPI spec. No ApiKey/UsagePlan CloudFormation resources are migrated. Chrome extension and add-url React app must be updated with: (a) new endpoint URL (api-gw-app gateway), (b) existing api-gw-app API key.

**Post-Consolidation Cleanup:**
1. Verify /url_add works on consolidated gateway (smoke test)
2. Delete lenie-dev-api-gw-url-add CloudFormation stack manually
3. Remove api-gw-url-add.yaml from deploy.ini
4. Remove api-gw-url-add.yaml template file
5. Remove parameters/dev/api-gw-url-add.json parameter file

### Lambda Function Rename Strategy

**Decision:** In-place CloudFormation update for lambda-rds-start.yaml. Change FunctionName from `${AWS::StackName}-rds-start-function` to `${ProjectCode}-${Environment}-rds-start`.

**Rationale:** CloudFormation treats FunctionName change as replacement (delete old + create new). This causes brief unavailability, which is acceptable for an on-demand function (starts RDS database, used infrequently). Code re-upload via zip_to_s3.sh after stack update.

**Consumer Updates Required:**
- Verify api-gw-infra.yaml already references `${ProjectCode}-${Environment}-rds-start` (confirmed from codebase analysis — no change needed)
- Verify SqsToRdsLambdaFunctionName in sqs-to-rds-step-function.json does NOT reference this Lambda (confirmed: references sqs-to-rds-lambda, not rds-start)
- Update lambda-rds-start.json parameter file if it contains function name reference

### EIP Removal Strategy

**Decision:** Remove ElasticIP resource, EIPAssociation resource, and PublicIP output from ec2-lenie.yaml entirely.

**Rationale:** EC2 instance is typically stopped (started on-demand for RDS access). Idle EIP incurs ~$3.65/month cost. aws_ec2_route53.py already handles dynamic IP → Route53 A record update on each EC2 start. No other template, parameter, or script consumes the PublicIP output.

**Verification:** EC2 must launch with dynamic public IP via subnet's MapPublicIpOnLaunch: 'true' setting in vpc.yaml (confirmed at lines 83, 98).

### Deployment Script Safety Pattern

**Decision:** Add information header and --yes flag to zip_to_s3.sh.

**Implementation:**
- Display: sourced env file name, AWS account ID, AWS profile, environment, S3 bucket name
- Default behavior: require explicit confirmation (read -p "Continue? (y/N)")
- --yes / -y flag: bypass confirmation prompt for automation
- Display happens before any S3 upload or Lambda update operation

### Decision Impact Analysis

**Implementation Sequence:**
1. B-11 (zip_to_s3.sh safety) — independent, immediate operational benefit
2. B-12 (CRLF verification) — independent, quick verification task
3. B-4 (EIP removal) — independent, simple CF template change
4. B-5 (Lambda naming) — independent, CF replacement + code re-upload
5. B-14 (API GW consolidation) — depends on B-5 being complete (consistent naming context), most complex story
6. B-19 (Documentation consolidation) — depends on B-14 (needs final API GW state for accurate metrics)

**Cross-Component Dependencies:**
- B-5 → B-14: Lambda naming should be fixed before API GW consolidation to ensure clean state
- B-14 → B-19: Documentation must reflect post-consolidation state (2 API GWs, 11 app endpoints)
- B-11 should be first: improves safety for all subsequent deployments
- B-4, B-5 are independent of each other: can be done in parallel

## Sprint 4 — Implementation Patterns & Consistency Rules

### Critical Conflict Points Identified

4 areas where AI agents could make different choices when implementing Sprint 4 stories.

### OpenAPI Merge Pattern (B-14)

**Adding /url_add to api-gw-app.yaml OpenAPI Body:**

The /url_add endpoint must follow the exact same structure as existing endpoints in the OpenAPI Body. Key rules:

1. **Lambda integration URI format:** Use `!Sub` with inline ARN construction:
   ```yaml
   uri: !Sub "arn:aws:apigateway:${AWS::Region}:lambda:path/2015-03-31/functions/arn:aws:lambda:${AWS::Region}:${AWS::AccountId}:function:${ProjectCode}-${Environment}-url-add/invocations"
   ```
   Note: This is the only endpoint in api-gw-app.yaml that uses a parameterized Lambda name. All other endpoints use hardcoded names (lenie_2_db, lenie_2_internet) — this is intentional and will be addressed in future backlog item B-3.

2. **Security:** Include `security: [{api_key: []}]` on the POST method (same as all other endpoints).

3. **CORS OPTIONS method:** Copy the mock integration pattern from any existing endpoint's OPTIONS method. Must include `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods`, `Access-Control-Allow-Headers` response headers.

4. **Timeout:** 29000ms (matching api-gw-url-add.yaml's current timeout).

5. **Position in paths:** Add `/url_add` at the end of the paths section (after `/ai_embedding_get`).

**Anti-patterns:**
- Using `!Ref` or `Fn::GetAtt` for Lambda ARN instead of `!Sub` inline
- Changing existing endpoint definitions while adding /url_add
- Adding request/response models not present in existing endpoints
- Modifying the security scheme definition

### Lambda Permission Resource Pattern (B-14)

**Adding LambdaPermission for url-add Lambda to api-gw-app.yaml:**

```yaml
UrlAddLambdaInvokePermission:
  Type: AWS::Lambda::Permission
  Properties:
    FunctionName: !Sub '${ProjectCode}-${Environment}-url-add'
    Action: lambda:InvokeFunction
    Principal: apigateway.amazonaws.com
    SourceArn: !Sub 'arn:aws:execute-api:${AWS::Region}:${AWS::AccountId}:${LenieApi}/*/*/url_add'
```

**Key rules:**
- Logical ID: PascalCase, descriptive (`UrlAddLambdaInvokePermission`)
- FunctionName: Use `!Sub` with `${ProjectCode}-${Environment}` pattern
- SourceArn: Scope to `/url_add` path specifically (not wildcard `/*/*`)
- Place after existing Lambda permission resources in the template

### Bash Script Modification Pattern (B-11)

**Adding deployment info display and confirmation to zip_to_s3.sh:**

1. **Argument parsing:** Add `--yes` / `-y` flag parsing before `source ./env.sh`:
   ```bash
   AUTO_CONFIRM=false
   for arg in "$@"; do
     case "$arg" in
       --yes|-y) AUTO_CONFIRM=true ;;
     esac
   done
   ```

2. **Info display block:** After sourcing env file, before the function processing loop:
   ```bash
   echo "================================================"
   echo "  Deployment Target Information"
   echo "================================================"
   echo "  Env file:    ${ENV_FILE_NAME}"
   echo "  AWS Account: ${AWS_ACCOUNT_ID}"
   echo "  Profile:     ${PROFILE}"
   echo "  Environment: ${ENVIRONMENT}"
   echo "  S3 Bucket:   ${AWS_S3_BUCKET_NAME}"
   echo "================================================"
   ```

3. **Confirmation prompt:** After info display, before processing:
   ```bash
   if [ "$AUTO_CONFIRM" != "true" ]; then
     read -p "Continue with deployment? (y/N) " confirm
     if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
       echo "Deployment cancelled."
       exit 0
     fi
   fi
   ```

**Anti-patterns:**
- Changing the existing `set -e` behavior
- Adding colored output (no colors in existing scripts)
- Restructuring the existing loop or variable handling
- Adding logging to file (not in existing pattern)

### CloudFormation Resource Removal Pattern (B-4, B-14)

**Removing resources from templates:**

1. Delete the resource block entirely — no commented-out remnants
2. Delete associated outputs that reference removed resources
3. Do not add placeholder comments (e.g., `# Removed: ElasticIP`) — git history provides this
4. Do not add replacement resources unless explicitly required by a FR

**Anti-patterns:**
- Leaving commented-out resource definitions
- Adding `Condition: Never` instead of removing
- Adding `DeletionPolicy: Retain` to resources being removed from template (only needed for CF import)
- Replacing removed output with a new dynamic equivalent when nothing consumes it

### Documentation Metrics File Pattern (B-19)

**Structure for docs/infrastructure-metrics.md:**

Organize metrics by perspective (deployment target), not by resource type:

```markdown
# Infrastructure Metrics — Single Source of Truth

## Flask Server (Docker / Kubernetes)
- Endpoints: XX total (list)

## AWS Serverless (Lambda + API Gateway)
### API Gateways
- api-gw-app: XX endpoints (list)
- api-gw-infra: XX endpoints (list)
### Lambda Functions
- Total: XX (simple: X, app: X)

## CloudFormation
- Templates in deploy.ini [dev]: XX
- Total template files: XX

## Verification
Last verified: YYYY-MM-DD
```

**Anti-patterns:**
- Mixing Flask and Lambda endpoint counts in same table
- Using generated/computed values instead of explicit counts
- Duplicating metrics that should reference this file
- Creating complex scripts when a simple grep/count suffices

### Enforcement Guidelines

**All AI Agents implementing Sprint 4 MUST:**
1. Follow the OpenAPI merge pattern exactly when adding /url_add to api-gw-app.yaml
2. Use `!Sub` with `${ProjectCode}-${Environment}` for new Lambda references (not hardcoded names)
3. Remove resources cleanly without commented remnants
4. Keep bash script modifications minimal — match existing style
5. Verify template size stays under 51200 bytes after modifications
6. Run cfn-lint on modified templates before marking work complete
7. Update documentation to reflect post-consolidation state (2 API GWs, not 3)

## Sprint 4 — Project Structure & Boundaries

### Complete File Changes (Sprint 4)

Files to modify (MOD), remove (DEL), or create (NEW):

```
infra/aws/cloudformation/
├── deploy.ini                                              [MOD] Remove api-gw-url-add.yaml entry
├── templates/
│   ├── ec2-lenie.yaml                                      [MOD] Remove ElasticIP, EIPAssociation, PublicIP output
│   ├── lambda-rds-start.yaml                               [MOD] Fix FunctionName to ${ProjectCode}-${Environment}-rds-start
│   ├── api-gw-app.yaml                                     [MOD] Add /url_add endpoint (POST+OPTIONS), add LambdaPermission
│   └── api-gw-url-add.yaml                                 [DEL] Consolidated into api-gw-app.yaml
├── parameters/dev/
│   ├── lambda-rds-start.json                               [MOD] Update if references old function name
│   └── api-gw-url-add.json                                 [DEL] Template removed
└── smoke-test-url-add.sh                                   [MOD] Update endpoint URL to api-gw-app gateway (if hardcoded)

infra/aws/serverless/
├── zip_to_s3.sh                                            [MOD] Add info header, --yes flag, confirmation prompt
├── env.sh                                                  [MOD] Add AWS_ACCOUNT_ID variable if missing
└── env_lenie_2025.sh                                       [MOD] Add AWS_ACCOUNT_ID variable if missing

web_chrome_extension/
└── popup.html                                              [MOD] Update default endpoint URL to api-gw-app gateway

web_add_url_react/
└── src/App.js                                              [MOD] Update hardcoded API URL to api-gw-app gateway

docs/
└── infrastructure-metrics.md                               [NEW] Single source of truth for infrastructure counts

# Documentation files to update with correct metrics:
CLAUDE.md                                                   [MOD] Fix endpoint/template counts or reference metrics file
README.md                                                   [MOD] Update EC2 description (no EIP), API GW count (2 not 3)
backend/CLAUDE.md                                           [MOD] Fix counts if discrepant
docs/index.md                                               [MOD] Fix counts if discrepant
docs/api-contracts-backend.md                               [MOD] Fix counts if discrepant
infra/aws/CLAUDE.md                                         [MOD] Update: 2 API GWs, remove EIP mention, fix counts
infra/aws/cloudformation/CLAUDE.md                          [MOD] Remove api-gw-url-add row, update api-gw-app endpoint count

# Verification script:
scripts/verify-documentation-metrics.sh                     [NEW] Automated drift detection script
```

**File count summary:**
- New files: 2 (infrastructure-metrics.md, verify-documentation-metrics.sh)
- Modified files: ~15 (6 infra, 2 client apps, 7 documentation)
- Deleted files: 2 (api-gw-url-add.yaml, api-gw-url-add.json)

### Requirements to Structure Mapping

| FR Group | Files Affected |
|----------|---------------|
| B-4: Remove EIP (FR1-FR5) | `ec2-lenie.yaml` |
| B-5: Lambda Naming (FR6-FR11) | `lambda-rds-start.yaml`, `lambda-rds-start.json` |
| B-14: API GW Consolidation (FR12-FR21) | `api-gw-app.yaml`, `api-gw-url-add.yaml` [DEL], `api-gw-url-add.json` [DEL], `deploy.ini`, `popup.html`, `App.js`, `smoke-test-url-add.sh` |
| B-11: Script Safety (FR22-FR25) | `zip_to_s3.sh`, `env.sh`, `env_lenie_2025.sh` |
| B-12: CRLF (FR26-FR28) | `.gitattributes` (if needed), documentation |
| B-19: Documentation (FR29-FR32) | `infrastructure-metrics.md` [NEW], `verify-documentation-metrics.sh` [NEW], 7 documentation files [MOD] |

### Architectural Boundaries

**Template Boundaries:**
Sprint 4 modifies templates independently — no new cross-stack SSM dependencies are created:
- `ec2-lenie.yaml`: Resources removed, no new SSM exports
- `lambda-rds-start.yaml`: FunctionName changed, existing SSM exports unchanged
- `api-gw-app.yaml`: New endpoint added, new LambdaPermission resource, no new SSM exports

**Client App Boundaries:**
- Chrome extension (`popup.html`): Only default URL string changes — user can override in settings
- Add-URL React app (`App.js`): Hardcoded URL string changes — requires rebuild and redeploy via Amplify

**Script Boundaries:**
- `zip_to_s3.sh`: Additive changes only — new display block and flag parsing, no changes to existing packaging/upload logic

## Sprint 4 — Architecture Validation Results

### Coherence Validation ✅

**Decision Compatibility:**
All Sprint 4 architectural decisions work together without conflicts. Inline merge (B-14) with existing API key strategy is the simplest consolidation path. In-place CF replacement (B-5) is independent of API GW merge. EIP removal (B-4) has no cross-dependencies. Script safety (B-11) is purely additive. No Sprint 4 decision conflicts with Sprint 1 architecture decisions (Gen 2+ canonical pattern, SSM conventions, naming standards remain in effect).

**Pattern Consistency:**
Sprint 4 implementation patterns extend (not replace) Sprint 1 patterns. OpenAPI merge pattern matches existing api-gw-app.yaml endpoint structure. Bash script pattern matches existing project scripting style. CF resource removal pattern is clean (no remnants). Documentation pattern establishes single source of truth with verification.

**Structure Alignment:**
File changes map covers all 32 FRs and 15 NFRs. Implementation dependencies (B-5→B-14→B-19) are defined with clear rationale. No orphan files or missing references.

### Requirements Coverage Validation ✅

**Functional Requirements Coverage:**

| FR Group | Status | Architectural Support |
|----------|--------|----------------------|
| FR1-FR5 (Remove EIP) | ✅ Covered | `ec2-lenie.yaml` modification, Route53 verification via aws_ec2_route53.py |
| FR6-FR11 (Lambda naming) | ✅ Covered | `lambda-rds-start.yaml` in-place replacement, consumer verification checklist |
| FR12-FR21 (API GW consolidation) | ✅ Covered | Inline merge into api-gw-app.yaml, LambdaPermission, client URL updates, 5-step cleanup sequence |
| FR22-FR25 (Script safety) | ✅ Covered | `zip_to_s3.sh` header display + `--yes` flag pattern |
| FR26-FR28 (CRLF verification) | ✅ Covered | .gitattributes verification + documentation |
| FR29-FR32 (Documentation) | ✅ Covered | `infrastructure-metrics.md` [NEW] + `verify-documentation-metrics.sh` [NEW] + 7 documentation file updates |

**Non-Functional Requirements Coverage:**

| NFR | Status | Architectural Support |
|-----|--------|----------------------|
| NFR1 (Smoke test post-consolidation) | ✅ | smoke-test-url-add.sh executed after consolidation |
| NFR2 (EC2 accessible after EIP removal) | ✅ | Route53 dynamic update via aws_ec2_route53.py, MapPublicIpOnLaunch verified |
| NFR3 (No active resources removed) | ✅ | Only consolidated/replaced resources affected |
| NFR4 (Rollback capability) | ✅ | Git version control + CloudFormation stack operations |
| NFR5 (Client apps work) | ✅ | URL updates in popup.html and App.js |
| NFR6 (cfn-lint validation) | ✅ | Enforcement guideline for all modified templates |
| NFR7 (Lambda naming convention) | ✅ | lambda-rds-start fixed, all others verified clean |
| NFR8 (51200 byte limit) | ✅ | Size verification post-merge, S3 fallback documented |
| NFR9 (deploy.ini order) | ✅ | Entry removed after manual stack deletion |
| NFR10-NFR11 (Script display + confirmation) | ✅ | Header + --yes flag pattern |
| NFR12 (LF line endings) | ✅ | .gitattributes verification |
| NFR13-NFR15 (Documentation quality) | ✅ | Single source + verification script + post-consolidation state |

### Implementation Readiness Validation ✅

**Decision Completeness:**
All 7 architectural decisions are documented with rationale. The API GW consolidation strategy includes a 5-step cleanup sequence. Lambda rename strategy accounts for consumer verification. Implementation patterns include concrete YAML/bash code examples and anti-patterns.

**Structure Completeness:**
File changes map lists 2 new files, ~15 modifications, and 2 deletions — all annotated with [NEW], [MOD], or [DEL]. Requirements-to-structure mapping covers every FR group. Architectural boundaries (template, client app, script) are defined.

**Pattern Completeness:**
4 conflict points identified and resolved with explicit patterns: OpenAPI merge, Lambda permission, bash script modification, CF resource removal. Each includes examples and anti-patterns. Enforcement guidelines list 7 mandatory rules for AI agents.

### Gap Analysis Results

**Critical Gaps:** None found.

**Important Gaps (Addressed):**
1. **Hardcoded Lambda names in api-gw-app.yaml** — explicitly deferred to future backlog item B-3 (rename-legacy-lambda-lenie-2-internet-and-db). Sprint 4 adds /url_add with parameterized `!Sub` name, creating an intentional hybrid state. Documented in decisions.

**Minor Observations:**
1. `smoke-test-url-add.sh` may need URL update if it references the old api-gw-url-add gateway — flagged in file changes map.
2. `scripts/` directory for `verify-documentation-metrics.sh` — verify existence or create during implementation.

### Architecture Completeness Checklist

**✅ Sprint 4 Context Analysis**

- [x] 32 FRs in 6 groups analyzed for architectural implications
- [x] 15 NFRs in 4 categories mapped to architectural support
- [x] Technical constraints identified (api-gw-app complexity, 51200 limit, two AWS accounts)
- [x] Cross-cutting concerns mapped (sequencing, template safety, Sprint 1 consistency, documentation chain)

**✅ Architectural Decisions**

- [x] 7 decisions documented with rationale (3 critical, 4 important)
- [x] Deferred decisions identified with backlog references (B-3, B-6, B-13)
- [x] Implementation sequence defined with dependencies
- [x] Cross-component dependencies mapped

**✅ Implementation Patterns**

- [x] 4 conflict points identified and resolved
- [x] Code examples provided for OpenAPI merge, Lambda permission, bash script, resource removal
- [x] Anti-patterns documented for each area
- [x] 7 enforcement rules for AI agents

**✅ Project Structure**

- [x] Complete file changes map (2 new, ~15 modified, 2 deleted)
- [x] Requirements-to-structure mapping covers all FR groups
- [x] Architectural boundaries defined (template, client app, script)

### Architecture Readiness Assessment

**Overall Status:** READY FOR IMPLEMENTATION

**Confidence Level:** High — all critical decisions made, no blocking gaps, patterns are concrete with code examples.

**Key Strengths:**

1. **Clear consolidation strategy** — inline merge with existing API key eliminates migration complexity
2. **Implementation sequencing** — B-11 first (safety), B-4/B-5 parallel (independent), B-14 (main work), B-19 last (accurate metrics)
3. **Hybrid naming approach** — new /url_add uses parameterized `!Sub`, existing endpoints keep hardcoded names until B-3
4. **Safety-first design** — deployment script confirmation, smoke test verification, rollback via git+CF
5. **Strong traceability** — every FR maps to specific files, every decision has rationale, deferred items reference backlog IDs

**Areas for Future Enhancement:**

1. B-3: Rename lenie_2_db and lenie_2_internet + parameterize in api-gw-app.yaml
2. B-6: Migrate api-gw-app stage to separate CF resource
3. B-13: Parameterize StageDescription for multi-environment
4. Extract OpenAPI Body to separate file if api-gw-app.yaml grows beyond manageable size
5. CI/CD integration for documentation drift detection (currently manual script)

### Implementation Handoff

**AI Agent Guidelines:**

- Follow Sprint 1 Gen 2+ canonical template pattern for all CF modifications
- Follow Sprint 4 implementation patterns for OpenAPI merge, bash scripts, and resource removal
- Respect implementation sequence: B-11 → B-12 → B-4/B-5 → B-14 → B-19
- Verify template size (51200 byte limit) after api-gw-app.yaml modification
- Run cfn-lint and smoke-test-url-add.sh before marking B-14 complete
- Update all 7 documentation files to reflect post-consolidation state

**First Implementation Priority:**

1. B-11 (zip_to_s3.sh safety) — immediate operational benefit, zero risk
2. B-12 (CRLF verification) — quick verification task
3. B-4 (EIP removal) + B-5 (Lambda naming) — independent, can run in parallel
4. B-14 (API GW consolidation) — most complex, requires careful execution
5. B-19 (Documentation consolidation) — last, captures final state
