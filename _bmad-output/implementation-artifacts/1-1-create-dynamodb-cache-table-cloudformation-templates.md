# Story 1.1: Create DynamoDB Cache Table CloudFormation Templates

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer,
I want to deploy the three DynamoDB cache tables (`lenie_cache_ai_query`, `lenie_cache_language`, `lenie_cache_translation`) via individual CloudFormation templates,
so that these storage resources are fully covered by IaC and can be recreated from code.

## Acceptance Criteria

1. **Given** the Gen 2+ canonical template pattern from Architecture document
   **When** developer creates templates `dynamodb-cache-ai-query.yaml`, `dynamodb-cache-language.yaml`, `dynamodb-cache-translation.yaml`
   **Then** each template defines a DynamoDB table matching the live resource configuration exactly (table name, key schema, billing mode, attributes)

2. **And** each template includes `DeletionPolicy: Retain` on the primary DynamoDB table resource (required for CF import)

3. **And** each template exports table name and ARN via SSM Parameters at:
   - `/${ProjectCode}/${Environment}/dynamodb/cache-<name>/name`
   - `/${ProjectCode}/${Environment}/dynamodb/cache-<name>/arn`

4. **And** each template uses `ProjectCode` + `Environment` parameters with standard tags (`Environment`, `Project`)

5. **And** each template includes `IsProduction` condition for DynamoDB PITR (Point-in-Time Recovery)

6. **And** each template has encryption at rest enabled (KMS) per NFR2

7. **And** parameter files are created:
   - `parameters/dev/dynamodb-cache-ai-query.json`
   - `parameters/dev/dynamodb-cache-language.json`
   - `parameters/dev/dynamodb-cache-translation.json`

8. **And** each template validates successfully with `aws cloudformation validate-template`

9. **And** each table is imported into CloudFormation via `create-change-set --change-set-type IMPORT`

## Tasks / Subtasks

- [x] Task 1: Inspect live DynamoDB cache tables (AC: #1)
  - [x] 1.1: Run `aws dynamodb describe-table --table-name lenie_cache_ai_query` and capture full configuration
  - [x] 1.2: Run `aws dynamodb describe-table --table-name lenie_cache_language` and capture full configuration
  - [x] 1.3: Run `aws dynamodb describe-table --table-name lenie_cache_translation` and capture full configuration
  - [x] 1.4: Document key schema, attribute definitions, billing mode, GSIs (if any), and encryption settings for each table

- [x] Task 2: Create CloudFormation templates (AC: #1-#6)
  - [x] 2.1: Create `infra/aws/cloudformation/templates/dynamodb-cache-ai-query.yaml` matching live config exactly
  - [x] 2.2: Create `infra/aws/cloudformation/templates/dynamodb-cache-language.yaml` matching live config exactly
  - [x] 2.3: Create `infra/aws/cloudformation/templates/dynamodb-cache-translation.yaml` matching live config exactly
  - [x] 2.4: Verify each template follows canonical Gen 2+ pattern (Parameters → Conditions → Resources → SSM exports)

- [x] Task 3: Create parameter files (AC: #7)
  - [x] 3.1: Create `infra/aws/cloudformation/parameters/dev/dynamodb-cache-ai-query.json`
  - [x] 3.2: Create `infra/aws/cloudformation/parameters/dev/dynamodb-cache-language.json`
  - [x] 3.3: Create `infra/aws/cloudformation/parameters/dev/dynamodb-cache-translation.json`

- [x] Task 4: Validate templates (AC: #8)
  - [x] 4.1: Run `aws cloudformation validate-template --template-body file://templates/dynamodb-cache-ai-query.yaml`
  - [x] 4.2: Run `aws cloudformation validate-template --template-body file://templates/dynamodb-cache-language.yaml`
  - [x] 4.3: Run `aws cloudformation validate-template --template-body file://templates/dynamodb-cache-translation.yaml`

- [x] Task 5: Import tables into CloudFormation (AC: #9)
  - [x] 5.1: Create import change set for `lenie_cache_ai_query`
  - [x] 5.2: Create import change set for `lenie_cache_language`
  - [x] 5.3: Create import change set for `lenie_cache_translation`
  - [x] 5.4: Execute each change set and verify import success
  - [x] 5.5: Run drift detection to confirm no configuration differences

## Dev Notes

### Critical Architecture Constraints

**MUST follow Gen 2+ Canonical Template Pattern:**

```yaml
AWSTemplateFormatVersion: '2010-09-09'
Description: '<description> for Project Lenie'

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

Resources:
  # Primary resource with DeletionPolicy: Retain (for CF import)
  # SSM Parameter exports (always LAST in Resources)

# NO Outputs section — use SSM Parameters instead
```

### DynamoDB-Specific Requirements

- **Table names use underscores** (not hyphens): `lenie_cache_ai_query` — this is the existing naming convention that MUST be preserved for CF import
- **BillingMode: PAY_PER_REQUEST** — consistent with existing `dynamodb-documents.yaml` pattern
- **SSESpecification:** `SSEEnabled: true`, `SSEType: KMS` — encryption at rest per NFR2
- **PointInTimeRecoverySpecification:** Conditional on `IsProduction` — PITR enabled only for prod/qa per FR28
- **DeletionPolicy: Retain** — MANDATORY on the DynamoDB table resource (CF import requirement)
- **NO DeletionPolicy on SSM Parameter resources** — SSM Parameters can be freely recreated

### CF Import Procedure (for each table)

```bash
# Step 1: Validate template
aws cloudformation validate-template \
  --template-body file://infra/aws/cloudformation/templates/dynamodb-cache-ai-query.yaml

# Step 2: Create import change set
aws cloudformation create-change-set \
  --stack-name lenie-dev-dynamodb-cache-ai-query \
  --template-body file://infra/aws/cloudformation/templates/dynamodb-cache-ai-query.yaml \
  --parameters file://infra/aws/cloudformation/parameters/dev/dynamodb-cache-ai-query.json \
  --change-set-name import-existing-table \
  --change-set-type IMPORT \
  --resources-to-import '[{"ResourceType":"AWS::DynamoDB::Table","LogicalResourceId":"CacheAiQueryTable","ResourceIdentifier":{"TableName":"lenie_cache_ai_query"}}]'

# Step 3: Wait for change set creation
aws cloudformation wait change-set-create-complete \
  --stack-name lenie-dev-dynamodb-cache-ai-query \
  --change-set-name import-existing-table

# Step 4: Execute change set
aws cloudformation execute-change-set \
  --stack-name lenie-dev-dynamodb-cache-ai-query \
  --change-set-name import-existing-table

# Step 5: Wait for import completion
aws cloudformation wait stack-import-complete \
  --stack-name lenie-dev-dynamodb-cache-ai-query

# Step 6: Verify — detect drift
aws cloudformation detect-stack-drift \
  --stack-name lenie-dev-dynamodb-cache-ai-query
```

### SSM Parameter Path Convention

For each cache table, export name and ARN:

| Table | SSM Name Path | SSM ARN Path |
|-------|--------------|-------------|
| `lenie_cache_ai_query` | `/${ProjectCode}/${Environment}/dynamodb/cache-ai-query/name` | `/${ProjectCode}/${Environment}/dynamodb/cache-ai-query/arn` |
| `lenie_cache_language` | `/${ProjectCode}/${Environment}/dynamodb/cache-language/name` | `/${ProjectCode}/${Environment}/dynamodb/cache-language/arn` |
| `lenie_cache_translation` | `/${ProjectCode}/${Environment}/dynamodb/cache-translation/name` | `/${ProjectCode}/${Environment}/dynamodb/cache-translation/arn` |

### Naming Conventions

| Aspect | Convention | Examples |
|--------|-----------|---------|
| CF Logical Resource IDs | PascalCase | `CacheAiQueryTable`, `CacheLanguageTable`, `CacheTranslationTable` |
| SSM Parameter logical IDs | PascalCase | `CacheAiQueryTableNameParameter`, `CacheAiQueryTableArnParameter` |
| Template file names | lowercase-hyphens | `dynamodb-cache-ai-query.yaml` |
| Stack names | `{ProjectCode}-{Stage}-{FileName}` | `lenie-dev-dynamodb-cache-ai-query` |
| Description field | English | `DynamoDB cache table for AI query results for Project Lenie` |

### Enforcement Rules (from Architecture)

**ALL AGENTS MUST:**
1. Follow canonical template structure (Parameters → Conditions → Resources with SSM exports last)
2. Use SSM Parameters for all cross-stack outputs (NEVER CF Exports)
3. Use `ProjectCode` parameter (NOT `ProjectName` or `stage`)
4. Include `Environment` and `Project` tags on all taggable resources
5. Write all descriptions and comments in English
6. Use `AWS::SSM::Parameter::Value<String>` for consuming cross-stack values
7. Validate templates with `aws cloudformation validate-template` before marking work complete

**ANTI-PATTERNS (NEVER do this):**
- Hardcode AWS account IDs, ARNs, or resource names
- Use CloudFormation Exports (`Export:` / `Fn::ImportValue`)
- Mix `ProjectCode` and `ProjectName` parameter names
- Write descriptions or comments in Polish
- Skip SSM Parameter exports for resource identifiers
- Create Outputs section (use SSM Parameters instead)

### CRITICAL: Inspect Live Tables FIRST

Before writing any template, the developer MUST inspect the live DynamoDB tables using:
```bash
aws dynamodb describe-table --table-name lenie_cache_ai_query --region us-east-1
aws dynamodb describe-table --table-name lenie_cache_language --region us-east-1
aws dynamodb describe-table --table-name lenie_cache_translation --region us-east-1
```

The CF import template MUST match the live configuration **exactly**. Any mismatch will cause the import to fail. Pay special attention to:
- Key schema (partition key, sort key if any)
- Attribute definitions
- Billing mode
- GSIs (if any)
- Encryption settings
- Table class

### Existing Reference Pattern

The existing `dynamodb-documents.yaml` template (at `infra/aws/cloudformation/templates/dynamodb-documents.yaml`) is the reference for DynamoDB CF patterns. Key differences for new cache table templates:

1. **DO NOT copy the Outputs section** — use SSM Parameters instead
2. **ADD DeletionPolicy: Retain** — required for CF import (not present in reference)
3. **Keep same structure** for Parameters, Conditions, Resources
4. **Table names are FIXED** — must match live table names exactly (e.g., `lenie_cache_ai_query`, not generated)

### Parameter File Format

Each parameter file follows this exact JSON format:
```json
[
  {
    "ParameterKey": "ProjectCode",
    "ParameterValue": "lenie"
  },
  {
    "ParameterKey": "Environment",
    "ParameterValue": "dev"
  }
]
```

### Project Structure Notes

- Templates location: `infra/aws/cloudformation/templates/`
- Parameters location: `infra/aws/cloudformation/parameters/dev/`
- deploy.ini location: `infra/aws/cloudformation/deploy.ini`
- New templates should be added to deploy.ini in Layer 4 (Storage) section — but this is Story 6.1's responsibility
- Stack names will be: `lenie-dev-dynamodb-cache-ai-query`, `lenie-dev-dynamodb-cache-language`, `lenie-dev-dynamodb-cache-translation`

### References

- [Source: _bmad-output/planning-artifacts/architecture.md#Starter Template Evaluation] — Gen 2+ canonical template pattern
- [Source: _bmad-output/planning-artifacts/architecture.md#Implementation Patterns & Consistency Rules] — Naming, structure, format, process patterns
- [Source: _bmad-output/planning-artifacts/architecture.md#Core Architectural Decisions] — CF import strategy, DeletionPolicy rules
- [Source: _bmad-output/planning-artifacts/epics.md#Story 1.1] — Acceptance criteria and requirements
- [Source: _bmad-output/planning-artifacts/prd.md#IaC Template Coverage] — FR1 requirement
- [Source: _bmad-output/planning-artifacts/prd.md#Security] — NFR2 encryption requirement
- [Source: infra/aws/cloudformation/templates/dynamodb-documents.yaml] — Existing Gen 2 reference pattern
- [Source: infra/aws/cloudformation/deploy.sh] — Deployment script (stack naming, parameter discovery)
- [Source: infra/aws/cloudformation/deploy.ini] — Template registration

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6 (claude-opus-4-6)

### Debug Log References

None

### Completion Notes List

- All 3 DynamoDB tables inspected: identical schema (hash/provider composite key, PAY_PER_REQUEST, no GSIs)
- Live tables had AWS-owned default encryption; templates specify KMS per NFR2
- Two-phase CF import used: Phase 1 imports table-only template (SSM Parameters can't be in import), Phase 2 updates stack with full template adding SSM Parameters
- KMS encryption enabled via `aws dynamodb update-table` after import to resolve SSE drift
- Final drift detection: all 3 stacks IN_SYNC
- cfn-lint validation: 0 errors, 0 warnings (after adding UpdateReplacePolicy: Retain)
- AWS validate-template: all 3 passed
- Tags (Environment, Project) applied during stack update

### Code Review Fixes Applied

- [H1] Added Tags (Environment, Project) to all 6 SSM Parameter resources
- [M1] IsProduction condition updated to include qa2/qa3 (consistent with dynamodb-documents.yaml)
- [M2] Added explanatory comments on hardcoded TableName and DeletionPolicy/UpdateReplacePolicy
- [L1] AllowedValues changed to flow-style per canonical pattern
- [L2] SSM Parameter Descriptions updated with "for Project Lenie" suffix
- [L3] Added comments explaining DeletionPolicy: Retain purpose
- All 3 stacks updated and verified IN_SYNC after fixes

### File List

- `infra/aws/cloudformation/templates/dynamodb-cache-ai-query.yaml` — CF template for lenie_cache_ai_query table
- `infra/aws/cloudformation/templates/dynamodb-cache-language.yaml` — CF template for lenie_cache_language table
- `infra/aws/cloudformation/templates/dynamodb-cache-translation.yaml` — CF template for lenie_cache_translation table
- `infra/aws/cloudformation/parameters/dev/dynamodb-cache-ai-query.json` — Dev parameters
- `infra/aws/cloudformation/parameters/dev/dynamodb-cache-language.json` — Dev parameters
- `infra/aws/cloudformation/parameters/dev/dynamodb-cache-translation.json` — Dev parameters
