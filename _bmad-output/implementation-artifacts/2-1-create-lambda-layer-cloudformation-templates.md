# Story 2.1: Create Lambda Layer CloudFormation Templates

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer,
I want to deploy the three Lambda Layers (`lenie_all_layer`, `lenie_openai`, `psycopg2_new_layer`) via CloudFormation templates,
so that Lambda function dependencies are managed by IaC and consistent across environments.

## Acceptance Criteria

1. **Given** the Gen 2+ canonical template pattern and the recreate strategy for stateless resources
   **When** developer creates templates `lambda-layer-lenie-all.yaml`, `lambda-layer-openai.yaml`, `lambda-layer-psycopg2.yaml`
   **Then** each template defines a Lambda Layer with compatible runtimes matching the live layer configuration

2. **And** each template references the layer code artifact in the existing S3 cloudformation bucket

3. **And** each template exports the full layer ARN (including version number) via SSM Parameter at `/${ProjectCode}/${Environment}/lambda/layers/<layer-name>/arn`

4. **And** layer sharing is limited to the same AWS account (no cross-account permissions) per NFR5

5. **And** each template uses `ProjectCode` + `Environment` parameters with standard tags (`Environment`, `Project`)

6. **And** no `DeletionPolicy` is set (recreate strategy)

7. **And** parameter files are created:
   - `parameters/dev/lambda-layer-lenie-all.json`
   - `parameters/dev/lambda-layer-openai.json`
   - `parameters/dev/lambda-layer-psycopg2.json`

8. **And** each template validates successfully with `aws cloudformation validate-template`

9. **And** each stack deploys successfully creating a new layer version

10. **And** consuming Lambda templates can reference the new layer ARN from SSM Parameter

## Tasks / Subtasks

- [x] Task 1: Prepare Lambda Layer code artifacts in S3 (AC: #2, #9)
  - [x] 1.1: Verify S3 cloudformation bucket (`lenie-dev-cloudformation`) exists and is accessible
  - [x] 1.2: Build layer packages using existing build scripts in `infra/aws/serverless/lambda_layers/` OR download current layer code from AWS Lambda storage
  - [x] 1.3: Upload layer ZIPs to S3 bucket at `layers/lenie_all_layer.zip`, `layers/lenie_openai.zip`, `layers/psycopg2_new_layer.zip`
  - [x] 1.4: Verify all 3 ZIPs exist in S3 and are valid

- [x] Task 2: Create CloudFormation templates (AC: #1-6)
  - [x] 2.1: Create `infra/aws/cloudformation/templates/lambda-layer-lenie-all.yaml` following Gen 2+ canonical pattern
  - [x] 2.2: Create `infra/aws/cloudformation/templates/lambda-layer-openai.yaml` following Gen 2+ canonical pattern
  - [x] 2.3: Create `infra/aws/cloudformation/templates/lambda-layer-psycopg2.yaml` following Gen 2+ canonical pattern
  - [x] 2.4: Verify each template follows canonical structure: Parameters → Conditions → Resources (primary resource + SSM exports last)

- [x] Task 3: Create parameter files (AC: #7)
  - [x] 3.1: Create `infra/aws/cloudformation/parameters/dev/lambda-layer-lenie-all.json`
  - [x] 3.2: Create `infra/aws/cloudformation/parameters/dev/lambda-layer-openai.json`
  - [x] 3.3: Create `infra/aws/cloudformation/parameters/dev/lambda-layer-psycopg2.json`

- [x] Task 4: Validate templates (AC: #8)
  - [x] 4.1: Run `aws cloudformation validate-template` for lambda-layer-lenie-all.yaml
  - [x] 4.2: Run `aws cloudformation validate-template` for lambda-layer-openai.yaml
  - [x] 4.3: Run `aws cloudformation validate-template` for lambda-layer-psycopg2.yaml

- [x] Task 5: Deploy stacks and verify (AC: #9, #10)
  - [x] 5.1: Deploy `lenie-dev-lambda-layer-lenie-all` stack via `create-stack`
  - [x] 5.2: Deploy `lenie-dev-lambda-layer-openai` stack via `create-stack`
  - [x] 5.3: Deploy `lenie-dev-lambda-layer-psycopg2` stack via `create-stack`
  - [x] 5.4: Verify SSM Parameters created at correct paths with valid layer ARNs (including version numbers)
  - [x] 5.5: Verify layer ARN format is `arn:aws:lambda:us-east-1:<account>:layer:<name>:<version>`

### Review Follow-ups (AI)

- [x] [AI-Review][Med] Add `LayerCodeVersion` parameter to force layer update when S3 key stays the same [all 3 templates + parameter files]
- [x] [AI-Review][Med] Fix stale `IsProduction` canonical example in architecture.md — add qa2/qa3 [_bmad-output/planning-artifacts/architecture.md:129-131]
- [ ] [AI-Review][Med] Audit and rebuild Lambda Layer dependencies — code from 2024-07-30 may have known vulnerabilities [operational — requires layer rebuild]

## Senior Developer Review (AI)

**Review Date:** 2026-02-14
**Reviewer Model:** Claude Opus 4.6 (code-review workflow)
**Review Outcome:** Changes Requested

**Summary:** 0 High, 3 Medium, 4 Low findings. All Acceptance Criteria implemented correctly. All tasks verified against git and AWS. 2 of 3 Medium issues fixed automatically (LayerCodeVersion parameter, architecture doc update). 1 Medium issue (stale dependencies) requires operational action outside this story's scope.

### Action Items

- [x] [Med] Add `LayerCodeVersion` parameter to all 3 templates and parameter files — enables forced layer update when S3 ZIP content changes but key stays the same
- [x] [Med] Update architecture.md canonical `IsProduction` condition to include qa2 and qa3 (Epic 1 code review fix was not propagated to source-of-truth document)
- [ ] [Med] Rebuild Lambda Layer packages with current dependency versions — layer code dates from 2024-07-30 (~1.5 years old). Packages: requests, beautifulsoup4, pytube, urllib3, openai, psycopg2-binary
- [x] [Low] `IsProduction` condition defined but unused — acceptable per canonical pattern for consistency
- [x] [Low] No explicit `CompatibleArchitectures` — acceptable, x86_64 is default
- [x] [Low] Architecture doc typo `LeniAllLayer` vs correct `LenieAllLayer` — cosmetic, not blocking
- [x] [Low] Repetitive template structure — by design per architecture "one template per resource" decision

## Dev Notes

### Critical Architecture Constraints

**This is a RECREATE strategy — NOT CF import.** Lambda Layers are stateless; a new version is created on every deploy. This is fundamentally different from Epic 1 stories (which used CF import for stateful resources).

**Key differences from Epic 1:**
- No `DeletionPolicy` needed (default Delete is intentional)
- No `UpdateReplacePolicy` needed
- No two-phase import — regular `create-stack` is sufficient
- No drift detection needed — resource is newly created
- Layer code artifacts must exist in S3 BEFORE stack deployment

**MUST follow Gen 2+ Canonical Template Pattern (with all Epic 1 code review fixes pre-applied):**

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
  # Layer-specific parameters (S3 bucket and key)

Conditions:
  IsProduction: !Or
    - !Equals [!Ref Environment, prod]
    - !Equals [!Ref Environment, qa]
    - !Equals [!Ref Environment, qa2]
    - !Equals [!Ref Environment, qa3]

Resources:
  # Primary resource: AWS::Lambda::LayerVersion (no DeletionPolicy)
  # SSM Parameter exports (always LAST in Resources, with Tags)

# NO Outputs section — use SSM Parameters instead
```

### Live Lambda Layer Configuration (Inspected 2026-02-14)

All three layers share identical configuration pattern:

| Property | lenie_all_layer | lenie_openai | psycopg2_new_layer |
|----------|----------------|-------------|-------------------|
| **LayerArn** | `arn:aws:lambda:us-east-1:008971653395:layer:lenie_all_layer` | `arn:aws:lambda:us-east-1:008971653395:layer:lenie_openai` | `arn:aws:lambda:us-east-1:008971653395:layer:psycopg2_new_layer` |
| **Version** | 1 | 1 | 1 |
| **CompatibleRuntimes** | `python3.11` | `python3.11` | `python3.11` |
| **Description** | *(empty)* | *(empty)* | *(empty)* |
| **CompatibleArchitectures** | *(not set — defaults to x86_64)* | *(not set)* | *(not set)* |
| **LicenseInfo** | *(not set)* | *(not set)* | *(not set)* |
| **CodeSize** | ~1.6 MB | ~5.5 MB | ~3.0 MB |
| **Created** | 2024-07-30 | 2024-07-30 | 2024-07-30 |

**Important:** All layers are at version 1 (never updated since initial creation). Deploying via CloudFormation will create version 2+ with fresh code from S3.

### Layer Contents (from build scripts)

| Layer | Python Packages | Used By |
|-------|----------------|---------|
| `lenie_all_layer` | pytube, urllib3, requests, beautifulsoup4 | `app-server-db`, `app-server-internet` |
| `lenie_openai` | openai | `app-server-internet` |
| `psycopg2_new_layer` | psycopg2-binary | `sqs-into-rds`, `app-server-db` |

### S3 Bucket for Layer Code Artifacts

**Bucket name:** `lenie-dev-cloudformation`

**CRITICAL:** The SSM parameter `/lenie/dev/s3/cloudformation/name` does NOT currently exist (the `s3-cloudformation.yaml` stack has not been deployed or the SSM Parameter was not created). Therefore:
- Use a plain `String` parameter for the S3 bucket name — NOT `AWS::SSM::Parameter::Value<String>`
- The parameter file provides the actual bucket name directly
- When the S3 cloudformation stack is properly deployed with SSM exports, the parameter type can be upgraded to SSM reference

**S3 key convention for layer ZIPs:**

| Layer | S3 Key |
|-------|--------|
| `lenie_all_layer` | `layers/lenie_all_layer.zip` |
| `lenie_openai` | `layers/lenie_openai.zip` |
| `psycopg2_new_layer` | `layers/psycopg2_new_layer.zip` |

### How to Build Layer Code Artifacts

**Option A: Use existing build scripts (recommended — produces fresh packages)**

```bash
cd infra/aws/serverless/lambda_layers

# Source environment config
source ../env.sh

# Build each layer
./layer_create_lenie_all.sh     # Creates ZIP in tmp/
./layer_openai_2.sh             # Creates ZIP in tmp/
./layer_create_psycop2_new.sh   # Creates ZIP in tmp/

# Upload to S3 (manual step — NOT done by existing scripts)
aws s3 cp tmp/lenie_all_layer.zip s3://lenie-dev-cloudformation/layers/lenie_all_layer.zip
aws s3 cp tmp/lenie_openai.zip s3://lenie-dev-cloudformation/layers/lenie_openai.zip
aws s3 cp tmp/psycopg2_new_layer.zip s3://lenie-dev-cloudformation/layers/psycopg2_new_layer.zip
```

**NOTE:** The existing build scripts publish layers directly via `aws lambda publish-layer-version`. They do NOT upload to S3. The S3 upload is a new step required for CloudFormation-managed layers.

**NOTE:** The build scripts run `pip install --platform manylinux2014_x86_64 --only-binary=:all:` to produce Linux-compatible binary packages. This MUST be run on any OS (the `--platform` flag handles cross-platform builds).

**Option B: Download current layer code from AWS (preserves exact current state)**

```bash
# Get presigned URLs for current layer code
LENIE_ALL_URL=$(aws lambda get-layer-version --layer-name lenie_all_layer --version-number 1 --query 'Content.Location' --output text --region us-east-1)
OPENAI_URL=$(aws lambda get-layer-version --layer-name lenie_openai --version-number 1 --query 'Content.Location' --output text --region us-east-1)
PSYCOPG2_URL=$(aws lambda get-layer-version --layer-name psycopg2_new_layer --version-number 1 --query 'Content.Location' --output text --region us-east-1)

# Download
curl -o lenie_all_layer.zip "$LENIE_ALL_URL"
curl -o lenie_openai.zip "$OPENAI_URL"
curl -o psycopg2_new_layer.zip "$PSYCOPG2_URL"

# Upload to S3
aws s3 cp lenie_all_layer.zip s3://lenie-dev-cloudformation/layers/lenie_all_layer.zip
aws s3 cp lenie_openai.zip s3://lenie-dev-cloudformation/layers/lenie_openai.zip
aws s3 cp psycopg2_new_layer.zip s3://lenie-dev-cloudformation/layers/psycopg2_new_layer.zip
```

### Lambda Layer CloudFormation Resource Pattern

```yaml
Resources:
  LenieAllLayer:
    Type: AWS::Lambda::LayerVersion
    Properties:
      LayerName: lenie_all_layer
      Description: 'Lambda Layer with shared Python dependencies (requests, beautifulsoup4, pytube, urllib3) for Project Lenie'
      CompatibleRuntimes:
        - python3.11
      Content:
        S3Bucket: !Ref LayerCodeBucket
        S3Key: !Ref LayerCodeS3Key
```

**Key points:**
- `!Ref` on `AWS::Lambda::LayerVersion` returns the **LayerVersionArn** (full ARN including version number, e.g., `arn:aws:lambda:us-east-1:008971653395:layer:lenie_all_layer:2`)
- This versioned ARN is what consuming Lambda functions need
- The SSM Parameter export stores this versioned ARN

### SSM Parameter Export Convention

| Layer | SSM Path | Value (example) |
|-------|----------|----------------|
| `lenie_all_layer` | `/${ProjectCode}/${Environment}/lambda/layers/lenie-all/arn` | `arn:aws:lambda:us-east-1:008971653395:layer:lenie_all_layer:2` |
| `lenie_openai` | `/${ProjectCode}/${Environment}/lambda/layers/openai/arn` | `arn:aws:lambda:us-east-1:008971653395:layer:lenie_openai:2` |
| `psycopg2_new_layer` | `/${ProjectCode}/${Environment}/lambda/layers/psycopg2/arn` | `arn:aws:lambda:us-east-1:008971653395:layer:psycopg2_new_layer:2` |

**Note on SSM path vs AWS layer name:**
- SSM path uses **hyphens** (e.g., `lenie-all`, not `lenie_all_layer`) — consistent with architecture convention
- AWS Layer name uses **underscores** (e.g., `lenie_all_layer`) — matches existing live names, MUST be preserved

### Naming Conventions

| Aspect | Convention | Examples |
|--------|-----------|---------|
| CF Logical Resource ID | PascalCase | `LenieAllLayer`, `LenieAllLayerArnParameter` |
| Template file name | lowercase-hyphens | `lambda-layer-lenie-all.yaml` |
| Stack name | `{ProjectCode}-{Stage}-{FileName}` | `lenie-dev-lambda-layer-lenie-all` |
| Layer name (AWS) | underscores (match live) | `lenie_all_layer`, `lenie_openai`, `psycopg2_new_layer` |
| SSM path | lowercase-hyphens | `/lenie/dev/lambda/layers/lenie-all/arn` |
| Description field | English | `Lambda Layer with OpenAI SDK for Project Lenie` |

### NFR5 Compliance (Layer Sharing)

By default, `AWS::Lambda::LayerVersion` creates a layer that is ONLY accessible within the same AWS account. No `LayerPermission` resource is needed (or allowed) per NFR5. Do NOT add any `AWS::Lambda::LayerPermission` resources.

### Layer Version Update Workflow (Future Reference)

When layer dependencies need to be updated after initial deployment:
1. Build new layer ZIP with updated packages
2. Upload to S3 (same key or new key)
3. If same S3 key: force CF update by changing a parameter (e.g., timestamp) or using `deploy.sh -t` (change-set mode)
4. If new S3 key: update parameter file with new key, then update stack
5. After layer stack update: update consuming Lambda stacks to pick up new layer version from SSM

### deploy.sh Deployment Commands

```bash
cd infra/aws/cloudformation

# Deploy each layer stack (deploy.sh handles create vs update automatically)
./deploy.sh -p lenie -s dev
# OR manually:
aws cloudformation create-stack \
  --stack-name lenie-dev-lambda-layer-lenie-all \
  --template-body file://templates/lambda-layer-lenie-all.yaml \
  --parameters file://parameters/dev/lambda-layer-lenie-all.json \
  --region us-east-1

aws cloudformation wait stack-create-complete \
  --stack-name lenie-dev-lambda-layer-lenie-all \
  --region us-east-1
```

### How Consuming Templates Will Reference Layer ARNs

Existing Lambda templates (Gen 1) currently hardcode layer ARNs:
```yaml
# BEFORE (hardcoded — Gen 1 anti-pattern)
Layers:
  - arn:aws:lambda:us-east-1:008971653395:layer:lenie_all_layer:1
  - arn:aws:lambda:us-east-1:008971653395:layer:psycopg2_new_layer:1
```

After this story, consuming templates can reference via SSM:
```yaml
# AFTER (SSM reference — Gen 2+ pattern)
Parameters:
  LenieAllLayerArn:
    Type: AWS::SSM::Parameter::Value<String>
    Default: '/lenie/dev/lambda/layers/lenie-all/arn'

Resources:
  MyFunction:
    Type: AWS::Lambda::Function
    Properties:
      Layers:
        - !Ref LenieAllLayerArn
```

**NOTE:** Updating existing Lambda templates to use SSM references is NOT in scope for this story. This story only creates the layer templates and SSM exports. Lambda template migration is a separate effort.

### Lessons from Epic 1 (MUST Apply)

1. **SSM Parameter Tags are MANDATORY** — Use map format for SSM Tags (not list-of-objects):
   ```yaml
   Tags:
     Environment: !Ref Environment
     Project: !Ref ProjectCode
   ```

2. **IsProduction condition must include qa2/qa3** — 4 environments: prod, qa, qa2, qa3

3. **AllowedValues in flow-style** — `[dev, qa, qa2, qa3, prod]`

4. **Description suffix** — Include "for Project Lenie" in SSM Parameter descriptions

5. **Explanatory comments** — Add comments on non-obvious design decisions (e.g., why no DeletionPolicy)

6. **No Outputs section** — SSM Parameters replace CF Exports

7. **cfn-lint**: Run if available for additional validation (not required)

### What This Story Does NOT Include

- **Updating existing Lambda function templates** to consume layer ARNs via SSM — those are Gen 1 templates with hardcoded ARNs; migration is a separate effort
- **Modifying the layer build scripts** to add S3 upload step — the story manually uploads to S3
- **Updating deploy.ini** — that is Story 6.1's responsibility
- **Deploying consuming Lambda stacks** with new layer versions — out of scope
- **Testing Lambda functions** with new layer versions — out of scope (layer code is identical or equivalent)

### Project Structure Notes

- Templates location: `infra/aws/cloudformation/templates/`
- Parameters location: `infra/aws/cloudformation/parameters/dev/`
- Layer build scripts: `infra/aws/serverless/lambda_layers/`
- deploy.ini location: `infra/aws/cloudformation/deploy.ini`
- Stack names: `lenie-dev-lambda-layer-lenie-all`, `lenie-dev-lambda-layer-openai`, `lenie-dev-lambda-layer-psycopg2`

### Enforcement Rules (from Architecture)

**ALL AGENTS MUST:**
1. Follow canonical template structure (Parameters → Conditions → Resources with SSM exports last)
2. Use SSM Parameters for all cross-stack outputs (NEVER CF Exports)
3. Use `ProjectCode` parameter (NOT `ProjectName` or `stage`)
4. Include `Environment` and `Project` tags on ALL taggable resources (including SSM Parameters)
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
- Add `AWS::Lambda::LayerPermission` for cross-account sharing (NFR5 violation)
- Add `DeletionPolicy` on recreated stateless resources

### Parameter File Format

```json
[
  {
    "ParameterKey": "ProjectCode",
    "ParameterValue": "lenie"
  },
  {
    "ParameterKey": "Environment",
    "ParameterValue": "dev"
  },
  {
    "ParameterKey": "LayerCodeBucket",
    "ParameterValue": "lenie-dev-cloudformation"
  },
  {
    "ParameterKey": "LayerCodeS3Key",
    "ParameterValue": "layers/<layer_name>.zip"
  }
]
```

### References

- [Source: _bmad-output/planning-artifacts/architecture.md#Starter Template Evaluation] — Gen 2+ canonical template pattern
- [Source: _bmad-output/planning-artifacts/architecture.md#Implementation Patterns & Consistency Rules] — Naming, structure, format, process patterns
- [Source: _bmad-output/planning-artifacts/architecture.md#Core Architectural Decisions] — Recreate strategy for Lambda Layers, layer ARN via SSM
- [Source: _bmad-output/planning-artifacts/architecture.md#Lambda Layer Versioning] — Layer ARN (with version) exported via SSM
- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.1] — Acceptance criteria and requirements
- [Source: _bmad-output/planning-artifacts/prd.md#IaC Template Coverage] — FR2 requirement
- [Source: _bmad-output/planning-artifacts/prd.md#Security] — NFR5 (Lambda Layer sharing)
- [Source: infra/aws/cloudformation/templates/dynamodb-cache-ai-query.yaml] — Gen 2+ canonical pattern reference (Story 1.1)
- [Source: infra/aws/cloudformation/templates/s3-website-content.yaml] — Gen 2+ S3 pattern reference (Story 1.2)
- [Source: infra/aws/cloudformation/templates/sqs-to-rds-lambda.yaml] — Existing Lambda template with hardcoded layer ARNs (Gen 1)
- [Source: infra/aws/cloudformation/templates/s3-cloudformation.yaml] — S3 bucket for CF code artifacts (Gen 1, SSM path: `/lenie/${Environment}/s3/cloudformation/name`)
- [Source: infra/aws/serverless/CLAUDE.md] — Lambda Layers documentation (packages, build process)
- [Source: infra/aws/serverless/lambda_layers/layer_create_lenie_all.sh] — Build script for lenie_all_layer
- [Source: infra/aws/serverless/lambda_layers/layer_openai_2.sh] — Build script for lenie_openai
- [Source: infra/aws/serverless/lambda_layers/layer_create_psycop2_new.sh] — Build script for psycopg2_new_layer
- [Source: infra/aws/serverless/env.sh] — Environment config (account 008971653395, bucket lenie-dev-cloudformation)
- [Source: _bmad-output/implementation-artifacts/1-1-create-dynamodb-cache-table-cloudformation-templates.md] — Epic 1 learnings (SSM tags, IsProduction, comments, descriptions)
- [Source: _bmad-output/implementation-artifacts/1-3-create-s3-frontend-hosting-bucket-template.md] — Epic 1 learnings (code review fixes, two-phase import)
- [Source: Live AWS inspection 2026-02-14] — Layer runtime (python3.11), version (1), no description, no compatible architectures set

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6 (claude-opus-4-6)

### Debug Log References

None — all tasks completed without errors.

### Completion Notes List

- **Task 1**: Downloaded existing layer code from AWS Lambda (Option B — preserves exact current state). All 3 layer ZIPs uploaded to `s3://lenie-dev-cloudformation/layers/`. Sizes match expected values: lenie_all_layer (~1.6MB), lenie_openai (~5.5MB), psycopg2_new_layer (~3.0MB).
- **Task 2**: Created 3 CloudFormation templates following Gen 2+ canonical pattern with all Epic 1 code review fixes pre-applied: SSM Parameter map-format Tags, IsProduction condition with qa2/qa3, no DeletionPolicy (recreate strategy), no Outputs section, explanatory comments, "for Project Lenie" description suffix.
- **Task 3**: Created 3 parameter files with ProjectCode, Environment, LayerCodeBucket (plain String, not SSM reference), and LayerCodeS3Key parameters.
- **Task 4**: All 3 templates validated successfully with `aws cloudformation validate-template`.
- **Task 5**: All 3 stacks deployed successfully via `create-stack`. SSM Parameters verified at correct paths. Layer ARN format confirmed: `arn:aws:lambda:us-east-1:008971653395:layer:<name>:2` (version 2 — new versions created by CloudFormation).

### Change Log

- 2026-02-14: Story implementation complete. Created 3 Lambda Layer CloudFormation templates, 3 parameter files, uploaded layer code artifacts to S3, deployed all stacks, verified SSM Parameter exports.
- 2026-02-14: Code review (AI) — 7 findings (0H/3M/4L). Fixed: added `LayerCodeVersion` parameter for forced updates (M1), updated architecture.md IsProduction canonical example (M2). Remaining: stale layer dependencies audit (M3, operational). All stacks updated with new parameter.

### File List

**New files:**
- `infra/aws/cloudformation/templates/lambda-layer-lenie-all.yaml`
- `infra/aws/cloudformation/templates/lambda-layer-openai.yaml`
- `infra/aws/cloudformation/templates/lambda-layer-psycopg2.yaml`
- `infra/aws/cloudformation/parameters/dev/lambda-layer-lenie-all.json`
- `infra/aws/cloudformation/parameters/dev/lambda-layer-openai.json`
- `infra/aws/cloudformation/parameters/dev/lambda-layer-psycopg2.json`

**Modified files (code review fixes):**
- `_bmad-output/planning-artifacts/architecture.md` (IsProduction canonical example — added qa2/qa3)

**AWS resources created:**
- Stack: `lenie-dev-lambda-layer-lenie-all` (Lambda Layer `lenie_all_layer:3` + SSM `/lenie/dev/lambda/layers/lenie-all/arn`)
- Stack: `lenie-dev-lambda-layer-openai` (Lambda Layer `lenie_openai:3` + SSM `/lenie/dev/lambda/layers/openai/arn`)
- Stack: `lenie-dev-lambda-layer-psycopg2` (Lambda Layer `psycopg2_new_layer:3` + SSM `/lenie/dev/lambda/layers/psycopg2/arn`)
- S3: `s3://lenie-dev-cloudformation/layers/lenie_all_layer.zip`
- S3: `s3://lenie-dev-cloudformation/layers/lenie_openai.zip`
- S3: `s3://lenie-dev-cloudformation/layers/psycopg2_new_layer.zip`
