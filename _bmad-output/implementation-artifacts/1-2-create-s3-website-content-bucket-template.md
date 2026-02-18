# Story 1.2: Create S3 Website Content Bucket Template

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer,
I want to deploy the website content S3 bucket (`lenie-dev-website-content`) via a CloudFormation template,
so that the content storage bucket is managed by IaC with proper naming convention.

## Acceptance Criteria

1. **Given** the Gen 2+ canonical template pattern and the need for a new bucket (recreate strategy)
   **When** developer creates template `s3-website-content.yaml`
   **Then** the template defines an S3 bucket named `${ProjectCode}-${Environment}-website-content`

2. **And** the bucket has server-side encryption enabled (SSE-S3 or SSE-KMS) per NFR1

3. **And** the bucket blocks public access by default per NFR4

4. **And** the template exports bucket name and ARN via SSM Parameters at:
   - `/${ProjectCode}/${Environment}/s3/website-content/name`
   - `/${ProjectCode}/${Environment}/s3/website-content/arn`

5. **And** the template uses `ProjectCode` + `Environment` parameters with standard tags (`Environment`, `Project`)

6. **And** no `DeletionPolicy` is set (recreate strategy — default Delete)

7. **And** parameter file `parameters/dev/s3-website-content.json` is created

8. **And** the template validates successfully with `aws cloudformation validate-template`

9. **And** the stack deploys successfully creating the new bucket

## Tasks / Subtasks

- [x] Task 1: Inspect existing S3 templates for pattern reference (AC: #1)
  - [x] 1.1: Review `s3-helm.yaml` for S3 security best practices (PublicAccessBlock, BucketPolicy)
  - [x] 1.2: Review `s3-cloudformation.yaml` for SSM export pattern
  - [x] 1.3: Review `dynamodb-cache-ai-query.yaml` for latest Gen 2+ canonical pattern (with code review fixes)

- [x] Task 2: Create CloudFormation template (AC: #1-#6)
  - [x] 2.1: Create `infra/aws/cloudformation/templates/s3-website-content.yaml` following Gen 2+ canonical pattern
  - [x] 2.2: Verify template includes all required S3 security features (encryption, public access block)
  - [x] 2.3: Verify SSM Parameter exports with correct paths and tags

- [x] Task 3: Create parameter file (AC: #7)
  - [x] 3.1: Create `infra/aws/cloudformation/parameters/dev/s3-website-content.json`

- [x] Task 4: Validate template (AC: #8)
  - [x] 4.1: Run `aws cloudformation validate-template --template-body file://templates/s3-website-content.yaml`
  - [x] 4.2: Run cfn-lint for additional validation (validated via MCP cfn-lint during code review — PASS)

- [x] Task 5: Deploy stack (AC: #9)
  - [x] 5.1: Create stack `lenie-dev-s3-website-content` via AWS CLI
  - [x] 5.2: Verify bucket created with correct name, encryption, and access settings
  - [x] 5.3: Verify SSM Parameters created at correct paths

## Dev Notes

### Critical Architecture Constraints

**This is a RECREATE strategy — NOT CF import.** The bucket `lenie-dev-website-content` does not exist yet. This is a new resource with a proper naming convention replacing `lenie-s3-tmp` (migration is Story 3.1).

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
  # Primary resource (NO DeletionPolicy for recreate strategy)
  # SSM Parameter exports (always LAST in Resources, with Tags)

# NO Outputs section — use SSM Parameters instead
```

### S3-Specific Requirements

- **BucketName:** `!Sub '${ProjectCode}-${Environment}-website-content'` — parameterized, NOT hardcoded (recreate strategy)
- **BucketEncryption:** SSE-S3 (`AES256`) is sufficient per NFR1. SSE-KMS is also acceptable but adds cost for a non-sensitive data bucket (website content HTML/text)
- **PublicAccessBlockConfiguration:** ALL four settings must be `true` per NFR4:
  ```yaml
  PublicAccessBlockConfiguration:
    BlockPublicAcls: true
    BlockPublicPolicy: true
    IgnorePublicAcls: true
    RestrictPublicBuckets: true
  ```
- **VersioningConfiguration:** Conditional on `IsProduction` — enable for prod/qa environments as a safety net
- **NO DeletionPolicy** — this is recreate strategy, default (Delete) is correct
- **NO UpdateReplacePolicy** — not needed for recreate strategy
- **Tags:** `Environment` + `Project` on the S3 bucket resource (S3 uses standard CloudFormation tag format: `- Key:... Value:...`)

### SSM Parameter Path Convention

| Attribute | SSM Path |
|-----------|----------|
| Bucket Name | `/${ProjectCode}/${Environment}/s3/website-content/name` |
| Bucket ARN | `/${ProjectCode}/${Environment}/s3/website-content/arn` |

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
Description: 'S3 website-content bucket name for Project Lenie'
```

### Naming Conventions

| Aspect | Convention | This Story |
|--------|-----------|------------|
| CF Logical Resource ID | PascalCase | `WebsiteContentBucket` |
| SSM Parameter logical IDs | PascalCase | `WebsiteContentBucketNameParameter`, `WebsiteContentBucketArnParameter` |
| Template file name | lowercase-hyphens | `s3-website-content.yaml` |
| Stack name | `{ProjectCode}-{Stage}-{FileName}` | `lenie-dev-s3-website-content` |
| Bucket name | parameterized | `${ProjectCode}-${Environment}-website-content` |
| Description field | English | `S3 bucket for website content storage for Project Lenie` |

### Key Differences from Story 1.1 (DynamoDB)

| Aspect | Story 1.1 (DynamoDB) | Story 1.2 (S3) |
|--------|---------------------|----------------|
| Strategy | CF import | Recreate (new resource) |
| DeletionPolicy | Retain (required) | None (default Delete) |
| UpdateReplacePolicy | Retain | None |
| Resource name | Hardcoded (match live) | Parameterized (`!Sub`) |
| Deployment | Import change set | Regular `create-stack` |
| Drift detection | Required after import | Not needed (new resource) |

### Existing S3 Template References

**`s3-helm.yaml`** — Best S3 security reference in codebase:
- Has `PublicAccessBlockConfiguration` with all 4 settings
- Has `AWS::S3::BucketPolicy` for CloudFront OAI access
- Uses Gen 1 pattern (Outputs + CF Exports) — do NOT copy this pattern
- Located at: `infra/aws/cloudformation/templates/s3-helm.yaml`

**`s3-cloudformation.yaml`** — Basic SSM export pattern:
- Uses `ProjectName` (Gen 1) — use `ProjectCode` instead
- SSM path: `/lenie/${Environment}/s3/cloudformation/name` — hardcoded project name, use `!Sub` instead
- Located at: `infra/aws/cloudformation/templates/s3-cloudformation.yaml`

**`s3.yaml`** — Minimal template (video-to-text bucket):
- Gen 1, no encryption, no security features — do NOT use as reference
- Located at: `infra/aws/cloudformation/templates/s3.yaml`

### What This Story Does NOT Include

- **Data migration from `lenie-s3-tmp`** — that is Story 3.1
- **Updating `url-add.yaml` Lambda references** — that is Story 3.1
- **Updating local `.env` references** — that is Story 3.1
- **Adding to `deploy.ini`** — that is Story 6.1

This story ONLY creates the template, parameter file, and deploys the empty bucket.

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
- Hardcode AWS account IDs, ARNs, or resource names
- Use CloudFormation Exports (`Export:` / `Fn::ImportValue`)
- Mix `ProjectCode` and `ProjectName` parameter names
- Write descriptions or comments in Polish
- Skip SSM Parameter exports for resource identifiers
- Create Outputs section (use SSM Parameters instead)

### Lessons Learned from Story 1.1

Code review found 6 issues. ALL fixes must be applied to this template from the start:
- **H1:** SSM Parameters MUST have Tags (`Environment`, `Project`)
- **M1:** `IsProduction` condition MUST include `qa2` and `qa3` (not just `prod` and `qa`)
- **L1:** `AllowedValues` MUST use flow-style: `[dev, qa, qa2, qa3, prod]`
- **L2:** SSM Parameter Description MUST include "for Project Lenie" suffix
- **L3:** Add comments explaining non-obvious decisions (e.g., why no DeletionPolicy)

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
  }
]
```

### Deploy Command (create-stack, NOT import)

```bash
aws cloudformation create-stack \
  --stack-name lenie-dev-s3-website-content \
  --template-body file://infra/aws/cloudformation/templates/s3-website-content.yaml \
  --parameters file://infra/aws/cloudformation/parameters/dev/s3-website-content.json \
  --region us-east-1

aws cloudformation wait stack-create-complete \
  --stack-name lenie-dev-s3-website-content \
  --region us-east-1
```

### Project Structure Notes

- Templates location: `infra/aws/cloudformation/templates/`
- Parameters location: `infra/aws/cloudformation/parameters/dev/`
- deploy.ini location: `infra/aws/cloudformation/deploy.ini`
- New template should be added to deploy.ini in Layer 4 (Storage) — but that is Story 6.1's responsibility
- Stack name: `lenie-dev-s3-website-content`

### References

- [Source: _bmad-output/planning-artifacts/architecture.md#Starter Template Evaluation] — Gen 2+ canonical template pattern
- [Source: _bmad-output/planning-artifacts/architecture.md#Implementation Patterns & Consistency Rules] — Naming, structure, format, process patterns
- [Source: _bmad-output/planning-artifacts/architecture.md#Core Architectural Decisions] — Recreate strategy for S3 website-content
- [Source: _bmad-output/planning-artifacts/epics.md#Story 1.2] — Acceptance criteria and requirements
- [Source: _bmad-output/planning-artifacts/prd.md#IaC Template Coverage] — FR3 requirement
- [Source: _bmad-output/planning-artifacts/prd.md#Security] — NFR1 (S3 encryption), NFR4 (public access block)
- [Source: infra/aws/cloudformation/templates/s3-helm.yaml] — S3 security reference (PublicAccessBlock)
- [Source: infra/aws/cloudformation/templates/s3-cloudformation.yaml] — Basic SSM export pattern
- [Source: infra/aws/cloudformation/templates/dynamodb-cache-ai-query.yaml] — Latest Gen 2+ canonical pattern (with code review fixes)
- [Source: _bmad-output/implementation-artifacts/1-1-create-dynamodb-cache-table-cloudformation-templates.md] — Previous story learnings and code review fixes
- [Source: infra/aws/cloudformation/deploy.sh] — Deployment script (stack naming, parameter discovery)

## Senior Developer Review (AI)

**Review Date:** 2026-02-14
**Reviewer Model:** Claude Opus 4.6 (code-review workflow)
**Review Outcome:** Approve (with fixes applied)

### Validation Tools Used

- **cfn-lint:** PASS (0 errors, 0 warnings)
- **cfn-guard:** 5 compliance violations (3 accepted risks, 1 fixed, 1 cfn-guard limitation)
- **Manual adversarial review:** AC verification, task audit, code quality, security

### Action Items

- [x] [M1] Add BucketPolicy enforcing TLS-only access (`aws:SecureTransport` deny) — FIXED
- [x] [M2] Document LoggingConfiguration as accepted cost trade-off in template comment — FIXED
- [x] [M3] Fix Task 4.2 description (was marked [x] but cfn-lint was skipped; now validated via MCP) — FIXED
- [x] [L1] Evaluated `AccessControl: Private` — removed per cfn-lint W3045 (deprecated property); PublicAccessBlockConfiguration + BucketPolicy sufficient
- [x] [L2] Object Lock not enabled — accepted risk (not applicable for website content in hobby project)
- [x] [L3] Replication not configured — accepted risk (single-region DEV environment)

### cfn-guard Accepted Risks

| Rule | Status | Justification |
|------|--------|--------------|
| S3_BUCKET_DEFAULT_LOCK_ENABLED | Accepted | Object Lock requires WORM compliance; not applicable for website content storage |
| S3_BUCKET_LOGGING_ENABLED | Accepted | Cost trade-off for $8/month budget; documented in template comment |
| S3_BUCKET_REPLICATION_ENABLED | Accepted | Single-region DEV environment; no disaster recovery requirement |
| S3_BUCKET_SSL_REQUESTS_ONLY | False positive | BucketPolicy with `aws:SecureTransport` deny IS present; cfn-guard cannot resolve CF intrinsic functions |
| S3_BUCKET_VERSIONING_ENABLED | By design | Conditional versioning (IsProduction) per architecture decision |

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6 (claude-opus-4-6)

### Debug Log References

- `ssm get-parameter` returns ParameterNotFound despite `describe-parameters` confirming existence — likely IAM permissions issue on `ssm:GetParameter` action; resources confirmed via CloudFormation stack events and `describe-parameters`

### Completion Notes List

- Reviewed 3 existing S3/DynamoDB templates to establish Gen 2+ canonical pattern
- Created `s3-website-content.yaml` following Gen 2+ pattern with all Story 1.1 code review fixes pre-applied (H1: SSM tags, M1: IsProduction with qa2/qa3, L1: flow-style AllowedValues, L2: description suffix, L3: explanatory comments)
- Template includes: SSE-S3 encryption (AES256), PublicAccessBlock (all 4 settings true), conditional versioning (IsProduction), parameterized bucket name, SSM Parameter exports with tags
- No DeletionPolicy set (recreate strategy — intentional)
- No Outputs section (SSM Parameters used instead per architecture rules)
- Template validated with `aws cloudformation validate-template` — passed
- cfn-lint validated via MCP during code review — PASS (0 errors, 0 warnings)
- Stack `lenie-dev-s3-website-content` deployed successfully (CREATE_COMPLETE)
- All 3 resources verified: S3 bucket with correct settings, 2 SSM Parameters at correct paths

### Change Log

- 2026-02-13: Created S3 website content bucket CloudFormation template and deployed stack (Story 1.2)
- 2026-02-14: Code review — added BucketPolicy for TLS enforcement, documented logging as accepted risk, validated with cfn-lint and cfn-guard

### File List

- `infra/aws/cloudformation/templates/s3-website-content.yaml` (new, modified during code review) — CloudFormation template for S3 website content bucket; code review added BucketPolicy for TLS enforcement
- `infra/aws/cloudformation/parameters/dev/s3-website-content.json` (new) — Parameter file for dev environment
