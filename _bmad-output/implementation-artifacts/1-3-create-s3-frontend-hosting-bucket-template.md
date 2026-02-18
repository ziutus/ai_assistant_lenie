# Story 1.3: Create S3 Frontend Hosting Bucket Template

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer,
I want to deploy the frontend hosting S3 bucket (`lenie-dev-app-web`) via a CloudFormation template,
so that the frontend hosting bucket is managed by IaC and can be recreated from code.

## Acceptance Criteria

1. **Given** the Gen 2+ canonical template pattern and the existing `lenie-dev-app-web` bucket (CF import strategy)
   **When** developer creates template `s3-app-web.yaml`
   **Then** the template defines an S3 bucket matching the live resource configuration exactly

2. **And** the bucket has `DeletionPolicy: Retain` (required for CF import)

3. **And** the bucket has server-side encryption enabled per NFR1

4. **And** the bucket blocks public access (CloudFront OAC will provide access) per NFR4

5. **And** the template exports bucket name, ARN, and domain name via SSM Parameters at:
   - `/${ProjectCode}/${Environment}/s3/app-web/name`
   - `/${ProjectCode}/${Environment}/s3/app-web/arn`
   - `/${ProjectCode}/${Environment}/s3/app-web/domain-name`

6. **And** the template uses `ProjectCode` + `Environment` parameters with standard tags (`Environment`, `Project`)

7. **And** parameter file `parameters/dev/s3-app-web.json` is created

8. **And** the template validates successfully with `aws cloudformation validate-template`

9. **And** the bucket is imported into CloudFormation via `create-change-set --change-set-type IMPORT`

10. **And** drift detection confirms no configuration difference between template and live resource

## Tasks / Subtasks

- [x] Task 1: Inspect live S3 bucket and review reference templates (AC: #1)
  - [x] 1.1: Inspect live `lenie-dev-app-web` bucket configuration (encryption, public access block, versioning, tags, policy, website config, CORS, logging, location)
  - [x] 1.2: Review `s3-website-content.yaml` for latest Gen 2+ S3 canonical pattern (Story 1.2)
  - [x] 1.3: Review `dynamodb-cache-ai-query.yaml` for CF import pattern and two-phase import procedure (Story 1.1)
  - [x] 1.4: Document exact live bucket configuration to match in template

- [x] Task 2: Create CloudFormation template (AC: #1-#6)
  - [x] 2.1: Create `infra/aws/cloudformation/templates/s3-app-web.yaml` following Gen 2+ canonical pattern
  - [x] 2.2: Verify bucket resource matches live configuration exactly (encryption AES256 with BucketKey, PublicAccessBlock all 4 true, no versioning, hardcoded bucket name for import)
  - [x] 2.3: Add `DeletionPolicy: Retain` and `UpdateReplacePolicy: Retain` on the S3 bucket resource
  - [x] 2.4: Verify SSM Parameter exports with correct paths, tags, and descriptions

- [x] Task 3: Create parameter file (AC: #7)
  - [x] 3.1: Create `infra/aws/cloudformation/parameters/dev/s3-app-web.json`

- [x] Task 4: Validate template (AC: #8)
  - [x] 4.1: Run `aws cloudformation validate-template --template-body file://templates/s3-app-web.yaml`

- [x] Task 5: Import bucket into CloudFormation (AC: #9)
  - [x] 5.1: Phase 1 — Create import change set for `AWS::S3::Bucket` resource only (SSM Parameters cannot be included in import)
  - [x] 5.2: Execute import change set and wait for completion
  - [x] 5.3: Phase 2 — Update stack to add SSM Parameter exports (bucket name, ARN, domain name)
  - [x] 5.4: Wait for update completion

- [x] Task 6: Verify import and detect drift (AC: #10)
  - [x] 6.1: Run `aws cloudformation detect-stack-drift` and verify IN_SYNC
  - [x] 6.2: Verify SSM Parameters created at correct paths
  - [x] 6.3: Verify all 3 SSM Parameter values match expected bucket name, ARN, and domain name

## Dev Notes

### Critical Architecture Constraints

**This is a CF IMPORT strategy — NOT recreate.** The bucket `lenie-dev-app-web` already exists and contains deployed frontend files. The template MUST match the live resource configuration exactly for the import to succeed.

**MUST follow Gen 2+ Canonical Template Pattern (with Story 1.1 code review fixes applied):**

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
    - !Equals [!Ref Environment, qa2]
    - !Equals [!Ref Environment, qa3]

Resources:
  # Primary resource with DeletionPolicy: Retain (required for CF import)
  # SSM Parameter exports (always LAST in Resources, with Tags)

# NO Outputs section — use SSM Parameters instead
```

### Live Bucket Configuration (Inspected 2026-02-13)

**MUST match this configuration exactly for CF import to succeed:**

| Property | Live Value |
|----------|-----------|
| BucketName | `lenie-dev-app-web` |
| Region | us-east-1 |
| Encryption | SSE-S3 (AES256), BucketKeyEnabled: true |
| PublicAccessBlock | All 4 settings: true |
| Versioning | Not enabled (Suspended is NOT the same — do NOT set VersioningConfiguration at all) |
| Tags | None (Tags will be added during Phase 2 stack update) |
| Website Hosting | Not enabled |
| CORS | Not configured |
| Logging | Not enabled |
| Bucket Policy | CloudFront OAC pattern (see below) |

### Live Bucket Policy (CloudFront OAC)

```json
{
  "Version": "2008-10-17",
  "Id": "PolicyForCloudFrontPrivateContent",
  "Statement": [
    {
      "Sid": "AllowCloudFrontServicePrincipal",
      "Effect": "Allow",
      "Principal": {
        "Service": "cloudfront.amazonaws.com"
      },
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::lenie-dev-app-web/*",
      "Condition": {
        "StringEquals": {
          "AWS:SourceArn": "arn:aws:cloudfront::008971653395:distribution/ETIQTXICZBECA"
        }
      }
    }
  ]
}
```

**IMPORTANT:** The bucket policy is an `AWS::S3::BucketPolicy` resource (separate from the bucket). `AWS::S3::BucketPolicy` is NOT importable into CloudFormation. The bucket policy will be added during Phase 2 stack update (after bucket import).

**The CloudFront distribution ARN in the policy references a specific distribution ID (`ETIQTXICZBECA`).** Since the CloudFront template doesn't exist yet (Story 4.1), accept the distribution ID as a template parameter with default value `ETIQTXICZBECA`. Use `!Sub` with `${AWS::AccountId}` to avoid hardcoding the account ID.

### S3-Specific Requirements for CF Import

- **BucketName:** Hardcoded `lenie-dev-app-web` — MUST match live name exactly (CF import requirement). Do NOT use `!Sub` parameterization.
- **BucketEncryption:** SSE-S3 (`AES256`) with `BucketKeyEnabled: true` — MUST match live config exactly
- **PublicAccessBlockConfiguration:** ALL four settings `true` — matches live config
- **VersioningConfiguration:** Do NOT include this property at all — live bucket has versioning not enabled (which is different from `Suspended`). Including `Status: Suspended` would cause drift.
- **DeletionPolicy: Retain** — MANDATORY on the S3 bucket resource (CF import requirement)
- **UpdateReplacePolicy: Retain** — recommended for imported stateful resources (cfn-lint requires this per Story 1.1 learning)
- **Tags:** Will be added during Phase 2 update — live bucket has no tags, so Phase 1 import template must NOT include tags to avoid drift. Phase 2 adds `Environment` + `Project` tags.

### Two-Phase CF Import Procedure (Learned from Story 1.1)

**Phase 1: Import bucket (primary resource only)**

SSM Parameters and BucketPolicy CANNOT be included in CF import change sets. Phase 1 template contains ONLY the S3 bucket resource definition.

```bash
# Step 1: Validate Phase 1 template (bucket-only)
aws cloudformation validate-template \
  --template-body file://infra/aws/cloudformation/templates/s3-app-web.yaml

# Step 2: Create import change set
aws cloudformation create-change-set \
  --stack-name lenie-dev-s3-app-web \
  --template-body file://infra/aws/cloudformation/templates/s3-app-web.yaml \
  --parameters file://infra/aws/cloudformation/parameters/dev/s3-app-web.json \
  --change-set-name import-existing-bucket \
  --change-set-type IMPORT \
  --resources-to-import '[{"ResourceType":"AWS::S3::Bucket","LogicalResourceId":"AppWebBucket","ResourceIdentifier":{"BucketName":"lenie-dev-app-web"}}]' \
  --region us-east-1

# Step 3: Wait for change set
aws cloudformation wait change-set-create-complete \
  --stack-name lenie-dev-s3-app-web \
  --change-set-name import-existing-bucket \
  --region us-east-1

# Step 4: Execute change set
aws cloudformation execute-change-set \
  --stack-name lenie-dev-s3-app-web \
  --change-set-name import-existing-bucket \
  --region us-east-1

# Step 5: Wait for import completion
aws cloudformation wait stack-import-complete \
  --stack-name lenie-dev-s3-app-web \
  --region us-east-1
```

**Phase 2: Add SSM Parameters, BucketPolicy, and Tags**

After successful import, update the stack with the full template that includes SSM Parameters, BucketPolicy resource, and Tags on the bucket.

```bash
# Step 6: Update stack with full template
aws cloudformation update-stack \
  --stack-name lenie-dev-s3-app-web \
  --template-body file://infra/aws/cloudformation/templates/s3-app-web.yaml \
  --parameters file://infra/aws/cloudformation/parameters/dev/s3-app-web.json \
  --region us-east-1

# Step 7: Wait for update
aws cloudformation wait stack-update-complete \
  --stack-name lenie-dev-s3-app-web \
  --region us-east-1

# Step 8: Detect drift
aws cloudformation detect-stack-drift \
  --stack-name lenie-dev-s3-app-web \
  --region us-east-1
```

**IMPORTANT: The template file must be modified between Phase 1 and Phase 2.** Phase 1 template has bucket-only. Phase 2 template adds SSM Parameters, BucketPolicy, and Tags. The developer must:
1. Create Phase 1 template (bucket-only, no tags)
2. Import
3. Update the same template file to add SSM Parameters, BucketPolicy, and Tags
4. Update stack

### SSM Parameter Path Convention

| Attribute | SSM Path |
|-----------|----------|
| Bucket Name | `/${ProjectCode}/${Environment}/s3/app-web/name` |
| Bucket ARN | `/${ProjectCode}/${Environment}/s3/app-web/arn` |
| Domain Name | `/${ProjectCode}/${Environment}/s3/app-web/domain-name` |

Note: Domain name export is additional compared to Story 1.2. Use `!GetAtt AppWebBucket.DomainName` for the S3 bucket domain name. This value will be consumed by the CloudFront template in Story 4.1.

### SSM Parameter Tags (MANDATORY)

From Story 1.1 code review (H1 fix): ALL SSM Parameters must have Tags:
```yaml
Tags:
  Environment: !Ref Environment
  Project: !Ref ProjectCode
```

Note: SSM Parameter `Tags` uses map format (not list-of-objects format like S3 bucket tags).

### SSM Parameter Description Pattern

From Story 1.1 code review (L2 fix): Include "for Project Lenie" suffix:
```yaml
Description: 'S3 app-web bucket name for Project Lenie'
```

### Naming Conventions

| Aspect | Convention | This Story |
|--------|-----------|------------|
| CF Logical Resource ID | PascalCase | `AppWebBucket` |
| BucketPolicy logical ID | PascalCase | `AppWebBucketPolicy` |
| SSM Parameter logical IDs | PascalCase | `AppWebBucketNameParameter`, `AppWebBucketArnParameter`, `AppWebBucketDomainNameParameter` |
| Template file name | lowercase-hyphens | `s3-app-web.yaml` |
| Stack name | `{ProjectCode}-{Stage}-{FileName}` | `lenie-dev-s3-app-web` |
| Bucket name | hardcoded (CF import) | `lenie-dev-app-web` |
| Description field | English | `S3 bucket for frontend hosting for Project Lenie` |

### Key Differences from Story 1.2 (S3 Website Content)

| Aspect | Story 1.2 (website-content) | Story 1.3 (app-web) |
|--------|---------------------------|---------------------|
| Strategy | Recreate (new resource) | CF import (existing resource) |
| DeletionPolicy | None (default Delete) | Retain (required for import) |
| UpdateReplacePolicy | None | Retain |
| BucketName | Parameterized (`!Sub`) | Hardcoded `lenie-dev-app-web` (must match live) |
| Deployment | Regular `create-stack` | Import change set (`--change-set-type IMPORT`) |
| Drift detection | Not needed | Required after import |
| BucketKey | Not set | `BucketKeyEnabled: true` (match live) |
| Versioning | Conditional (IsProduction) | Not included (live has no versioning) |
| BucketPolicy | None | CloudFront OAC policy |
| SSM exports | 2 (name, arn) | 3 (name, arn, domain-name) |
| Two-phase import | Not applicable | Required (Phase 1: bucket, Phase 2: SSM + policy + tags) |

### Key Differences from Story 1.1 (DynamoDB CF Import)

| Aspect | Story 1.1 (DynamoDB) | Story 1.3 (S3) |
|--------|---------------------|----------------|
| Resource type | AWS::DynamoDB::Table | AWS::S3::Bucket |
| Additional resources | None | AWS::S3::BucketPolicy (OAC access) |
| Two-phase import reason | SSM Parameters can't be imported | SSM Parameters AND BucketPolicy can't be imported |
| Phase 2 additions | SSM Parameters + Tags | SSM Parameters + BucketPolicy + Tags |
| Drift resolution | KMS encryption update needed | Should be clean if template matches live exactly |

### Lessons from Story 1.1 (CF Import — MUST Apply)

Two-phase import was successfully used for DynamoDB tables. ALL these lessons apply to this story:

1. **Phase 1 template = primary resource only** — SSM Parameters cannot be included in CF import change sets. BucketPolicy is also NOT importable.
2. **Phase 2 adds supporting resources** — Update stack to add SSM Parameters, BucketPolicy, and Tags
3. **UpdateReplacePolicy: Retain** required by cfn-lint for imported resources
4. **Drift may occur if encryption settings don't match** — match BucketKeyEnabled: true exactly
5. **cfn-lint validation**: Run if available (not installed in current environment)
6. **All code review fixes from Story 1.1 pre-applied** (H1: SSM tags, M1: IsProduction with qa2/qa3, L1: flow-style AllowedValues, L2: description suffix, L3: explanatory comments)

### Lessons from Story 1.2 (S3 Template)

1. **`ssm get-parameter` may fail** even though parameters exist — use `describe-parameters` as fallback verification
2. **SSE-S3 (AES256) is acceptable** for non-sensitive data per NFR1
3. **Conditional versioning NOT applicable here** — live bucket has no versioning, don't add it

### BucketPolicy Template Strategy

The live bucket has a CloudFront OAC bucket policy. Since the CloudFront template doesn't exist yet (Story 4.1), the distribution ID must be accepted as a parameter:

```yaml
Parameters:
  CloudFrontDistributionId:
    Type: String
    Default: ETIQTXICZBECA
    Description: CloudFront distribution ID for OAC bucket policy

Resources:
  AppWebBucketPolicy:
    Type: AWS::S3::BucketPolicy
    Properties:
      Bucket: !Ref AppWebBucket
      PolicyDocument:
        Version: '2008-10-17'
        Id: PolicyForCloudFrontPrivateContent
        Statement:
          - Sid: AllowCloudFrontServicePrincipal
            Effect: Allow
            Principal:
              Service: cloudfront.amazonaws.com
            Action: s3:GetObject
            Resource: !Sub '${AppWebBucket.Arn}/*'
            Condition:
              StringEquals:
                AWS:SourceArn: !Sub 'arn:aws:cloudfront::${AWS::AccountId}:distribution/${CloudFrontDistributionId}'
```

**NOTE:** When Story 4.1 is implemented, the `CloudFrontDistributionId` parameter can be changed to consume from SSM Parameter (`AWS::SSM::Parameter::Value<String>`). For now, a simple string parameter with default value is sufficient.

### What This Story Does NOT Include

- **CloudFront distribution template** — that is Story 4.1
- **Migrating data** — bucket already has correct content (deployed frontend)
- **Updating deploy.ini** — that is Story 6.1
- **Changing the bucket name** — CF import preserves existing name

This story ONLY creates the template, parameter file, imports the existing bucket, and verifies drift-free state.

### Enforcement Rules (from Architecture)

**ALL AGENTS MUST:**
1. Follow canonical template structure (Parameters -> Conditions -> Resources with SSM exports last)
2. Use SSM Parameters for all cross-stack outputs (NEVER CF Exports)
3. Use `ProjectCode` parameter (NOT `ProjectName` or `stage`)
4. Include `Environment` and `Project` tags on ALL taggable resources (including SSM Parameters)
5. Write all descriptions and comments in English
6. Use `AWS::SSM::Parameter::Value<String>` for consuming cross-stack values
7. Validate templates with `aws cloudformation validate-template` before marking work complete

**ANTI-PATTERNS (NEVER do this):**
- Hardcode AWS account IDs, ARNs, or resource names (use `${AWS::AccountId}` for account ID)
- Use CloudFormation Exports (`Export:` / `Fn::ImportValue`)
- Mix `ProjectCode` and `ProjectName` parameter names
- Write descriptions or comments in Polish
- Skip SSM Parameter exports for resource identifiers
- Create Outputs section (use SSM Parameters instead)
- Include VersioningConfiguration when live bucket has versioning not enabled (causes drift)

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
    "ParameterKey": "CloudFrontDistributionId",
    "ParameterValue": "ETIQTXICZBECA"
  }
]
```

### Project Structure Notes

- Templates location: `infra/aws/cloudformation/templates/`
- Parameters location: `infra/aws/cloudformation/parameters/dev/`
- deploy.ini location: `infra/aws/cloudformation/deploy.ini`
- New template should be added to deploy.ini in Layer 4 (Storage) — but that is Story 6.1's responsibility
- Stack name: `lenie-dev-s3-app-web`

### References

- [Source: _bmad-output/planning-artifacts/architecture.md#Starter Template Evaluation] — Gen 2+ canonical template pattern
- [Source: _bmad-output/planning-artifacts/architecture.md#Implementation Patterns & Consistency Rules] — Naming, structure, format, process patterns
- [Source: _bmad-output/planning-artifacts/architecture.md#Core Architectural Decisions] — CF import strategy for S3 app-web
- [Source: _bmad-output/planning-artifacts/architecture.md#CloudFront Access Control] — OAC pattern for S3 bucket policy
- [Source: _bmad-output/planning-artifacts/epics.md#Story 1.3] — Acceptance criteria and requirements
- [Source: _bmad-output/planning-artifacts/prd.md#IaC Template Coverage] — FR4 requirement
- [Source: _bmad-output/planning-artifacts/prd.md#Security] — NFR1 (S3 encryption), NFR4 (public access block)
- [Source: infra/aws/cloudformation/templates/s3-website-content.yaml] — Latest Gen 2+ S3 pattern (Story 1.2)
- [Source: infra/aws/cloudformation/templates/dynamodb-cache-ai-query.yaml] — CF import reference pattern (Story 1.1)
- [Source: _bmad-output/implementation-artifacts/1-1-create-dynamodb-cache-table-cloudformation-templates.md] — CF import learnings, two-phase procedure, code review fixes
- [Source: _bmad-output/implementation-artifacts/1-2-create-s3-website-content-bucket-template.md] — S3 template learnings, SSM Parameter verification issues
- [Source: infra/aws/cloudformation/deploy.sh] — Deployment script (stack naming, parameter discovery)
- [Source: Live AWS inspection 2026-02-13] — Bucket encryption (AES256+BucketKey), PublicAccessBlock (4/4), no versioning, no tags, OAC bucket policy

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List

- Task 1: Inspected live bucket via CloudFormation Cloud Control API. Confirmed: BucketName=lenie-dev-app-web, SSE-S3 AES256 with BucketKeyEnabled=true, PublicAccessBlock all 4 true, OwnershipControls=BucketOwnerEnforced, no versioning, no tags. Reviewed s3-website-content.yaml (Gen 2+ pattern) and dynamodb-cache-ai-query.yaml (CF import pattern with two-phase procedure). Found existing partial Phase 1 template and parameter file from previous session.
- Task 2: Created full CloudFormation template following Gen 2+ canonical pattern. Phase 1 (bucket-only) used for import, Phase 2 added SSM Parameters (3: name, arn, domain-name), BucketPolicy (CloudFront OAC with parameterized distribution ID), and Tags (Environment, Project). cfn-lint passed with 2 acceptable warnings (unused IsProduction condition, policy version 2008-10-17 matching live).
- Task 3: Created parameter file with ProjectCode=lenie, Environment=dev, CloudFrontDistributionId=ETIQTXICZBECA.
- Task 4: Validated template with both cfn-lint (0 errors, 2 warnings) and AWS CLI validate-template (success).
- Task 5: Two-phase CF import executed. Phase 1: Import change set for S3 bucket — IMPORT_COMPLETE. Phase 2 first attempt failed because existing bucket policy conflicted (error: "The bucket policy already exists on bucket lenie-dev-app-web"). Resolved by deleting existing bucket policy before retry. Phase 2 retry: UPDATE_COMPLETE — SSM Parameters, BucketPolicy, and Tags all created successfully.
- Task 6: Drift detection returned IN_SYNC with 0 drifted resources. All 3 SSM Parameters verified: /lenie/dev/s3/app-web/name=lenie-dev-app-web, /lenie/dev/s3/app-web/arn=arn:aws:s3:::lenie-dev-app-web, /lenie/dev/s3/app-web/domain-name=lenie-dev-app-web.s3.amazonaws.com.

### Change Log

- 2026-02-13: Created S3 app-web CloudFormation template, imported existing bucket, added SSM Parameters, BucketPolicy (OAC), and Tags via two-phase import procedure.
- 2026-02-14: Code review fixes applied — M1: Updated BucketPolicy version from '2008-10-17' to '2012-10-17'; M2: Added DenyInsecureTransport statement (cfn-guard S3_BUCKET_SSL_REQUESTS_ONLY); L1: Added explanatory comment for OwnershipControls. Stack updated and drift verified IN_SYNC.

## Senior Developer Review (AI)

**Review Date:** 2026-02-14
**Reviewer:** Claude Opus 4.6 (code-review workflow)
**Review Outcome:** Approve (with fixes applied)

### Summary

All 10 Acceptance Criteria verified as implemented. All 6 tasks (16 subtasks) confirmed complete. No git vs story discrepancies found. cfn-guard compliance check identified 6 rule violations, 2 applicable and fixed.

### Action Items

- [x] [M1] Update BucketPolicy version from '2008-10-17' to '2012-10-17' [s3-app-web.yaml:60] — FIXED
- [x] [M2] Add DenyInsecureTransport statement for SSL-only enforcement [s3-app-web.yaml:73-82] — FIXED
- [x] [L1] Add explanatory comment for OwnershipControls [s3-app-web.yaml:45] — FIXED
- [ ] [L2] IsProduction condition unused (accepted — canonical pattern consistency) [s3-app-web.yaml:18-23]
- [ ] [L3] S3 access logging not configured (accepted — matches live config, not critical for dev) [s3-app-web.yaml]

### File List

- infra/aws/cloudformation/templates/s3-app-web.yaml (new)
- infra/aws/cloudformation/parameters/dev/s3-app-web.json (new)
