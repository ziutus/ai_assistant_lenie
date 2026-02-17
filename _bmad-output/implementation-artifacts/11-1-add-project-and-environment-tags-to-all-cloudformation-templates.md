# Story 11.1: Add Project and Environment Tags to All CloudFormation Templates

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **developer**,
I want to add `Project` and `Environment` tags to all resources across all CloudFormation templates,
So that AWS Cost Explorer can filter costs by project and environment.

## Acceptance Criteria

1. **AC1 — Tags on all taggable resources:** Every taggable CloudFormation resource across every template in `infra/aws/cloudformation/templates/` includes both `Project` (from `!Ref ProjectCode`) and `Environment` (from `!Ref Environment`) tags. Non-taggable resources (Lambda LayerVersion, Organizations Policy, IdentityStore Group, Budget, CloudFront OAI, API Gateway Resource/Method/Deployment, Route Table associations) are documented as excluded.

2. **AC2 — Parameters standardized:** Every deployed template (listed in `deploy.ini [dev]`) has `ProjectCode` (Type: String, Default: lenie) and `Environment` (Type: String, Default: dev, AllowedValues: [dev, qa, qa2, qa3, prod]) parameters. Templates currently using `ProjectName` are renamed to `ProjectCode`; templates using `stage` are renamed to `Environment`. All `!Ref` and `!Sub` references are updated accordingly. Parameter files in `infra/aws/cloudformation/parameters/dev/` are created or updated with the new parameter values.

3. **AC3 — cfn-lint validation passes:** All modified templates pass cfn-lint validation with zero errors.

## Tasks / Subtasks

- [x] **Task 1: Standardize parameters and add tags — Foundation, Networking, Security (Layer 1-3)** (AC: #1, #2)
  - [x] 1.1 `env-setup.yaml` — rename `stage` → `Environment`, add `ProjectCode` param, add tags to SSM Parameter
  - [x] 1.2 `1-domain-route53.yaml` — add `ProjectCode` + `Environment` params, add `HostedZoneTags` to Route53 HostedZone
  - [x] 1.3 `vpc.yaml` — rename `ProjectName` → `ProjectCode`, add tags to VPC, Subnets, InternetGateway, RouteTable, SSM Parameters
  - [x] 1.4 `security-groups.yaml` — add `ProjectCode` + `Environment` params, add tags to SecurityGroup
  - [x] 1.5 `secrets.yaml` — rename `ProjectName` → `ProjectCode`, add tags to SecretsManager Secret

- [x] **Task 2: Standardize parameters and add tags — Storage (Layer 4)** (AC: #1, #2)
  - [x] 2.1 `s3.yaml` — rename `stage` → `Environment`, add `ProjectCode` param, add tags to S3 Bucket
  - [x] 2.2 `s3-cloudformation.yaml` — rename `ProjectName` → `ProjectCode`, add tags to S3 Bucket, SSM Parameters
  - [x] 2.3 `sqs-documents.yaml` — rename `ProjectName` → `ProjectCode`, add tags to SQS Queue, SSM Parameters
  - [x] 2.4 `sqs-application-errors.yaml` — rename `ProjectName` → `ProjectCode`, add tags to SQS Queue, SNS Topic
  - [x] 2.5 `rds.yaml` — rename `ProjectName` → `ProjectCode`, add tags to DBInstance, DBSubnetGroup, SecurityGroup

- [x] **Task 3: Standardize parameters and add tags — Compute (Layer 5)** (AC: #1, #2)
  - [x] 3.1 `lambda-layer-lenie-all.yaml` — verified: LayerVersion NOT taggable, SSM already tagged. No changes needed.
  - [x] 3.2 `lambda-layer-openai.yaml` — verified: same as 3.1. No changes needed.
  - [x] 3.3 `lambda-layer-psycopg2.yaml` — verified: same as 3.1. No changes needed.
  - [x] 3.4 `ec2-lenie.yaml` — rename `ProjectName` → `ProjectCode`, add/fix tags on EC2 Instance, SecurityGroup, IAM Role, EIP
  - [x] 3.5 `lenie-launch-template.yaml` — rename `Stage` → `Environment`, add tags to LaunchTemplate + TagSpecifications, SSM Parameters
  - [x] 3.6 `lambda-rds-start.yaml` — rename `ProjectName` → `ProjectCode`, add tags to Lambda Function, IAM Role
  - [x] 3.7 `lambda-weblink-put-into-sqs.yaml` — add `ProjectCode` + `Environment` params, add tags to Lambda Function
  - [x] 3.8 `sqs-to-rds-lambda.yaml` — rename `ProjectName` → `ProjectCode`, add tags to Lambda Function, IAM Role
  - [x] 3.9 `url-add.yaml` — add AllowedValues to Environment, add tags to Lambda Function, LogGroup, IAM Role, RestApi, ApiKey, UsagePlan

- [x] **Task 4: Standardize parameters and add tags — API, Orchestration, CDN (Layer 6-8)** (AC: #1, #2)
  - [x] 4.1 `api-gw-infra.yaml` — rename `stage` → `Environment`, add tags to RestApi, 7 Lambda Functions, IAM Role
  - [x] 4.2 `api-gw-app.yaml` — add `qa2`, `qa3` to AllowedValues, add tags to RestApi. SSM Params already tagged.
  - [x] 4.3 `api-gw-url-add.yaml` — rename `stage` → `Environment`, add `ProjectCode` param, add tags to RestApi, ApiKey, UsagePlan
  - [x] 4.4 `sqs-to-rds-step-function.yaml` — rename `ProjectName` → `ProjectCode`, add AllowedValues. Scheduler::Schedule is NOT taggable. IAM Roles, LogGroup, StateMachine already tagged.
  - [x] 4.5 `cloudfront-helm.yaml` — rename `ProjectName` → `ProjectCode`, add AllowedValues, add tags to CloudFront Distribution. Fixed pre-existing bug: `IPV6` → `IPV6Enabled`.
  - [x] 4.6 `s3-helm.yaml` — rename `ProjectName` → `ProjectCode`, add AllowedValues, add tags to S3 Bucket. CloudFront OAI is non-taggable.

- [x] **Task 5: Create and update parameter files** (AC: #2)
  - [x] 5.1 Updated existing parameter files: `env-setup.json`, `vpc.json`, `secrets.json`, `s3-cloudformation.json`, `sqs-documents.json`, `sqs-application-errors.json`, `rds.json`, `ec2-lenie.json`, `lenie-launch-template.json`, `sqs-to-rds-lambda.json`, `api-gw-infra.json`, `api-gw-url-add.json`, `sqs-to-rds-step-function.json`, `budget.json`
  - [x] 5.2 Created missing parameter files: `1-domain-route53.json`, `security-groups.json`, `s3.json`, `s3-helm.json`, `cloudfront-helm.json`, `lambda-rds-start.json`, `lambda-weblink-put-into-sqs.json`
  - [x] 5.3 All parameter files contain `ProjectCode` and `Environment` parameters

- [x] **Task 6: Run cfn-lint validation on all modified templates** (AC: #3)
  - [x] 6.1 Ran cfn-lint on each modified template individually
  - [x] 6.2 Zero errors on all templates
  - [x] 6.3 Warnings documented: `vpc.yaml` W2001 (unused VpcName param — pre-existing), `budget.yaml` W2001 (ProjectCode/Environment unused by active AccountBudget resource — used by commented-out resources)

- [x] **Task 7: Document non-taggable resources and verify Cost Explorer readiness** (AC: #1)
  - [x] 7.1 Non-taggable resources documented in Completion Notes below
  - [x] 7.2 Post-deployment step documented: activate `Project` and `Environment` as Cost Allocation Tags in AWS Billing Console

## Dev Notes

### Technical Requirements

**Scope: 25 templates need modifications, 10 are excluded.**

This story adds cost allocation tags (`Project` and `Environment`) to all taggable CloudFormation resources. It also standardizes parameter naming across all templates to use `ProjectCode` (instead of `ProjectName`) and `Environment` (instead of `stage`).

**Key principle:** For each template, the changes are:
1. Rename `ProjectName` → `ProjectCode` (if applicable) — update parameter declaration AND all `!Ref ProjectName` / `!Sub '...${ProjectName}...'` references
2. Rename `stage` → `Environment` (if applicable) — same approach
3. Add `ProjectCode` / `Environment` parameters if missing entirely
4. Add tags to every taggable resource:
```yaml
Tags:
  - Key: Environment
    Value: !Ref Environment
  - Key: Project
    Value: !Ref ProjectCode
```
5. Update or create the parameter file in `parameters/dev/`

**Template Classification (from audit):**

| Category | Count | Templates |
|----------|-------|-----------|
| Already fully tagged (Gen 2+) | 4 | dynamodb-documents, s3-app-web, s3-website-content, cloudfront-app |
| Need tags only (have correct params) | 5 | api-gw-app, url-add, lambda-layer-lenie-all*, lambda-layer-openai*, lambda-layer-psycopg2* |
| Need param rename + tags (ProjectName) | 13 | vpc, rds, s3-cloudformation, s3-helm, cloudfront-helm, ec2-lenie, lenie-launch-template, lambda-rds-start, sqs-to-rds-lambda, sqs-documents, sqs-application-errors, secrets, sqs-to-rds-step-function |
| Need param rename + tags (stage) | 4 | env-setup, api-gw-infra, api-gw-url-add, s3 |
| Need new params + tags (no params) | 3 | 1-domain-route53, lambda-weblink-put-into-sqs, security-groups |
| Excluded (non-taggable/org-level) | 6 | organization, identityStore, scp-block-all, scp-block-sso-creation, scp-only-allowed-reginos, budget |

*Lambda layer templates: `AWS::Lambda::LayerVersion` does NOT support the `Tags` property in CloudFormation. SSM Parameters in these templates are already tagged. These templates need verification only, not changes.

### Architecture Compliance

**Gen 2+ Canonical Template Pattern (from architecture.md):**
- Parameters section order: `ProjectCode`, `Environment` first, then resource-specific
- `IsProduction` condition if applicable (not required for this story — only add if template already has conditions)
- Tags on all taggable resources: `Environment` (from `!Ref Environment`), `Project` (from `!Ref ProjectCode`)
- SSM Parameter exports always last in Resources section

**Parameter Renaming Impact:**
- Renaming `ProjectName` → `ProjectCode` changes all `!Ref` and `!Sub` references in the template
- Renaming `stage` → `Environment` changes all `!Ref` and `!Sub` references
- Parameter files must also be updated (ParameterKey names change)
- Deployed stacks will need a stack update with the new parameter names provided
- **CRITICAL:** Verify that resource naming (`!Sub '${ProjectCode}-${Environment}-...'`) produces the SAME resource names as before (e.g., `lenie-dev-...`). Since default values are the same, names should be identical.

**CloudFormation Tag Property Variations:**
- Most resources: `Tags` property with `Key`/`Value` pairs
- `AWS::Route53::HostedZone`: uses `HostedZoneTags` (not `Tags`) with same Key/Value format
- `AWS::EC2::VPC`, `AWS::EC2::Subnet`, etc.: standard `Tags` property — can include `Name` tag alongside Project/Environment
- `AWS::AutoScaling::LaunchConfiguration`: uses `Tags` property (not applicable here)

**Resources that do NOT support Tags in CloudFormation:**
- `AWS::Lambda::LayerVersion` — no Tags property
- `AWS::Organizations::Policy` — no Tags property
- `AWS::Organizations::Organization` — no Tags property
- `AWS::IdentityStore::Group` — no Tags property
- `AWS::Budgets::Budget` — no Tags property
- `AWS::CloudFront::CloudFrontOriginAccessIdentity` — no Tags property
- `AWS::ApiGateway::Resource` — no Tags property
- `AWS::ApiGateway::Method` — no Tags property
- `AWS::ApiGateway::Deployment` — no Tags property
- `AWS::EC2::VPCGatewayAttachment` — no Tags property
- `AWS::EC2::Route` — no Tags property
- `AWS::EC2::SubnetRouteTableAssociation` — no Tags property

### Library / Framework Requirements

- **cfn-lint**: Use for template validation after changes. Available via `pip install cfn-lint` or as a Docker container. Run: `cfn-lint templates/<name>.yaml`
- **No new libraries needed** — this is purely CloudFormation template editing

### File Structure Notes

All templates are in: `infra/aws/cloudformation/templates/`
All parameter files are in: `infra/aws/cloudformation/parameters/dev/`

**Parameter file format (standard):**
```json
[
  {"ParameterKey": "ProjectCode", "ParameterValue": "lenie"},
  {"ParameterKey": "Environment", "ParameterValue": "dev"}
]
```

**7 templates currently lack parameter files** and need new ones created:
- `1-domain-route53.json`
- `security-groups.json`
- `s3.json`
- `s3-helm.json`
- `cloudfront-helm.json`
- `lambda-rds-start.json`
- `lambda-weblink-put-into-sqs.json`

### Testing Requirements

- **cfn-lint validation** on all modified templates — zero errors required
- **No unit tests** — this story is CloudFormation-only, no backend/frontend code changes
- **No integration tests** — template deployment is verified via cfn-lint, actual deployment is a separate step
- **Regression check:** Ensure parameter renaming produces identical resource names (same default values → same output)

### Previous Story Intelligence

**From Epic 10 stories (10-1 through 10-4):**
- Story 10-3 (in review) modified `api-gw-app.yaml` — removed `/infra/ip-allow` endpoint. Working tree may have uncommitted changes. Story 11.1 must work on top of these changes.
- Story 10-3 also deleted Lambda `infra-allow-ip-in-secrutity-group` from AWS. This impacts Story 11.4 (Lambda typo fix) — resolved by deletion (Path A).
- Story 10-4 modified `backend/library/ai.py` — removed `ai_describe_image()` dead code. No impact on this story.

**From Sprint 1 retrospective (epic-1-6-retro):**
- cfn-lint validation is critical — run it before marking any template change complete
- Template file naming convention: `<service>-<resource-description>.yaml` (lowercase, hyphens)
- Parameter files must match template names exactly

### Git Intelligence

**Recent commits (relevant patterns):**
```
7d06ee5 chore: remove ai_describe_image() dead code
db4181f chore: remove /translate endpoint
6af45b9 chore: remove /ai_ask endpoint
```
- Commit message pattern: `chore:` prefix for cleanup/maintenance work
- This story fits the `chore:` category

**Unstaged changes in working tree:**
- `infra/aws/cloudformation/templates/api-gw-app.yaml` — from story 10-3
- `infra/aws/cloudformation/apigw/lenie-split-export.json` — from story 10-3

### Project Structure Notes

- All changes are within `infra/aws/cloudformation/` directory
- No backend, frontend, or Lambda code changes
- No documentation updates needed (CLAUDE.md already documents the tagging convention)
- deploy.ini does NOT need changes (no new templates added or removed)

### References

- [Source: _bmad-output/planning-artifacts/architecture.md#Starter Template Evaluation] — Gen 2+ canonical template pattern with tag requirements
- [Source: _bmad-output/planning-artifacts/architecture.md#Implementation Patterns & Consistency Rules] — Enforcement guidelines for tags
- [Source: _bmad-output/planning-artifacts/epics.md#Story 11.1] — Original story definition with ACs
- [Source: _bmad-output/planning-artifacts/epics.md#Requirements Inventory] — FR15, FR16, FR17 coverage
- [Source: infra/aws/cloudformation/CLAUDE.md] — Template overview and deployment documentation

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

None — all changes passed cfn-lint validation on first attempt (except pre-existing `IPV6` → `IPV6Enabled` bug in cloudfront-helm.yaml).

### Completion Notes List

1. **Non-taggable CloudFormation resources excluded from tagging:**
   - `AWS::Lambda::LayerVersion` — no Tags property (3 templates: lambda-layer-lenie-all, lambda-layer-openai, lambda-layer-psycopg2)
   - `AWS::Organizations::Organization` — no Tags property (organization.yaml)
   - `AWS::Organizations::Policy` — no Tags property (scp-block-all, scp-block-sso-creation, scp-only-allowed-reginos)
   - `AWS::IdentityStore::Group`, `AWS::IdentityStore::GroupMembership` — no Tags property (identityStore.yaml)
   - `AWS::Budgets::Budget` — no Tags property (budget.yaml)
   - `AWS::CloudFront::CloudFrontOriginAccessIdentity` — no Tags property (s3-helm.yaml)
   - `AWS::Scheduler::Schedule` — no Tags property (sqs-to-rds-step-function.yaml)
   - `AWS::ApiGateway::Resource`, `AWS::ApiGateway::Method`, `AWS::ApiGateway::Deployment` — no Tags property
   - `AWS::EC2::VPCGatewayAttachment`, `AWS::EC2::Route`, `AWS::EC2::SubnetRouteTableAssociation` — no Tags property (vpc.yaml)
   - `AWS::S3::BucketPolicy` — no Tags property

2. **Additional fix: `budget.yaml`** — renamed `Stage` → `Environment` (was missed in initial story scope under "Excluded" category). Added AllowedValues. Updated parameter file.

3. **Pre-existing bug fixed: `cloudfront-helm.yaml`** — `IPV6` property renamed to correct `IPV6Enabled` (cfn-lint error E3002).

4. **Pre-existing warning: `sqs-documents.yaml`** — removed unnecessary `!Sub` on plain string description (no interpolation needed).

5. **Post-deployment step:** After deploying updated stacks, activate `Project` and `Environment` as **Cost Allocation Tags** in AWS Billing Console → Cost Allocation Tags → User-Defined Cost Allocation Tags.

6. **cfn-lint warnings (pre-existing, not introduced by this story):**
   - `vpc.yaml` — W2001: Parameter `VpcName` not used
   - `budget.yaml` — W2001: Parameters `ProjectCode` and `Environment` not used (only active resource `AccountBudget` doesn't reference them; commented-out resources do)
   - **Note:** `budget.yaml` W2001 for `ProjectCode`/`Environment` is now resolved — `AccountBudget` references them via `BudgetName: !Sub "${ProjectCode}-${Environment}-monthly-budget"` (fixed in code review round 2).

7. **Code review fixes — HIGH/MEDIUM (2026-02-17):**
   - `api-gw-infra.yaml:116` — Fixed hardcoded `lenie` in S3Key for RdsStopFunction (`S3Key: !Sub lenie-${Environment}-rds-stop.zip` → `S3Key: !Sub ${ProjectCode}-${Environment}-rds-stop.zip`). All other 6 Lambda S3Keys in the same file already used `${ProjectCode}` correctly.
   - `api-gw-infra.yaml:251` — Removed unnecessary `!Sub` on plain string `"Infrastructure management API"` (cfn-lint W1020).
   - File List count corrected from "25 files" to "23 files".

8. **Code review fixes — LOW / pre-existing hardcoded values (2026-02-17):**
   - **SSM paths `/lenie/` → `/${ProjectCode}/`** in 6 templates:
     - `env-setup.yaml` — SSM Parameter Name
     - `s3-cloudformation.yaml` — SSM Parameter Name
     - `sqs-documents.yaml` — 2 SSM Parameter Names + fixed inconsistent YAML indentation on SQSUrlParameter
     - `lambda-rds-start.yaml` — IAM policy Resource ARN + Lambda env var `DB_ID`
     - `sqs-to-rds-step-function.yaml` — EventBridge Scheduler Input JSON (QueueUrl, DbInstanceIdentifier)
   - **ImportValue parameterization** in 2 templates:
     - `ec2-lenie.yaml` — `!ImportValue 'lenie-dev-publicSubnet1'` → `Fn::ImportValue: !Sub '${ProjectCode}-${Environment}-publicSubnet1'` (same for vpcId)
     - `sqs-to-rds-step-function.yaml` — `!ImportValue lenie-problems-dlq-arn` → `Fn::ImportValue: !Sub '${ProjectCode}-${Environment}-problems-dlq-arn'`
   - **Export name fix:**
     - `sqs-application-errors.yaml` — Export `${ProjectCode}-problems-dlq-arn` → `${ProjectCode}-${Environment}-problems-dlq-arn` (was missing `${Environment}`)
   - **S3Bucket hardcoded → SSM resolve** in 4 templates:
     - `lambda-rds-start.yaml` — `lenie-2025-dev-cloudformation` → `{{resolve:ssm:/${ProjectCode}/${Environment}/s3/cloudformation/name}}`
     - `url-add.yaml` — `lenie-dev-cloudformation` → same SSM resolve pattern
     - `sqs-to-rds-lambda.yaml` — `lenie-dev-cloudformation` → same SSM resolve pattern
     - `lambda-weblink-put-into-sqs.yaml` — `lenie-2025-dev-cloudformation` → same SSM resolve pattern; S3Key `lenie-dev-url-add.zip` → `${ProjectCode}-${Environment}-url-add.zip`
   - **Resource name parameterization** in 2 templates:
     - `url-add.yaml` — FunctionName, S3Key, BUCKET_NAME, S3 ARN in IAM policy, API name, ApiKey name, UsagePlan name — all changed from `lenie-dev-*` to `!Sub '${ProjectCode}-${Environment}-*'`
     - `sqs-to-rds-lambda.yaml` — FunctionName, S3Key — changed from `lenie-dev-*` to `!Sub '${ProjectCode}-${Environment}-*'`
   - **Not fixed (remaining pre-existing debt):**
     - `url-add.yaml` — SQS URL and ARN with hardcoded account ID `008971653395` and queue `lenie_websites` (legacy queue, not managed by this project's CF templates)
     - `sqs-to-rds-step-function.yaml:51` — SQS ARN with hardcoded `lenie_websites` queue name
     - `sqs-to-rds-step-function.yaml:61` — Lambda function ARN `lenie-sqs-to-db` (name mismatch with actual FunctionName)
     - `sqs-to-rds-lambda.yaml` — hardcoded subnet IDs, security group ID, RDS hostname, DB credentials, Lambda layer ARNs with account IDs
     - `lambda-weblink-put-into-sqs.yaml:22` — hardcoded test IAM Role ARN from different account (`049706517731` instead of `008971653395`)
   - **Next sprint item:** S3 bucket name unification — `s3-cloudformation.yaml` creates `${ProjectCode}-2025-${Environment}-cloudformation` but canonical pattern is `${ProjectCode}-${Environment}-cloudformation` (without `2025`). Rename bucket to remove `2025` and update all references.
   - **Deployment note:** Export name change in `sqs-application-errors.yaml` requires coordinated deployment — update `sqs-to-rds-step-function.yaml` first (remove old ImportValue), then update `sqs-application-errors.yaml` export, then re-deploy step-function with new ImportValue. Alternatively, delete and recreate both stacks.

9. **Code review round 2 — LOW fixes (2026-02-17):**
   - `sqs-application-errors.yaml` — extracted hardcoded email `krzysztof@lenie-ai.eu` to `AlertEmail` parameter; updated parameter file with value
   - `budget.yaml` — replaced generic `"My Monthly Cost Budget"` with `!Sub "${ProjectCode}-${Environment}-monthly-budget"`
   - `secrets.yaml` — replaced hardcoded `"lenie"` username with `${ProjectCode}` reference in `!Sub` block
   - **cfn-lint verification (v1.44.0):** All 4 templates modified in round 2 (`lambda-weblink-put-into-sqs.yaml`, `sqs-application-errors.yaml`, `budget.yaml`, `secrets.yaml`) pass with zero errors and zero warnings.

### File List

**Templates modified (23 files):**
- `infra/aws/cloudformation/templates/env-setup.yaml`
- `infra/aws/cloudformation/templates/1-domain-route53.yaml`
- `infra/aws/cloudformation/templates/vpc.yaml`
- `infra/aws/cloudformation/templates/security-groups.yaml`
- `infra/aws/cloudformation/templates/secrets.yaml`
- `infra/aws/cloudformation/templates/s3.yaml`
- `infra/aws/cloudformation/templates/s3-cloudformation.yaml`
- `infra/aws/cloudformation/templates/sqs-documents.yaml`
- `infra/aws/cloudformation/templates/sqs-application-errors.yaml`
- `infra/aws/cloudformation/templates/rds.yaml`
- `infra/aws/cloudformation/templates/ec2-lenie.yaml`
- `infra/aws/cloudformation/templates/lenie-launch-template.yaml`
- `infra/aws/cloudformation/templates/lambda-rds-start.yaml`
- `infra/aws/cloudformation/templates/lambda-weblink-put-into-sqs.yaml`
- `infra/aws/cloudformation/templates/sqs-to-rds-lambda.yaml`
- `infra/aws/cloudformation/templates/url-add.yaml`
- `infra/aws/cloudformation/templates/api-gw-infra.yaml`
- `infra/aws/cloudformation/templates/api-gw-app.yaml`
- `infra/aws/cloudformation/templates/api-gw-url-add.yaml`
- `infra/aws/cloudformation/templates/sqs-to-rds-step-function.yaml`
- `infra/aws/cloudformation/templates/cloudfront-helm.yaml`
- `infra/aws/cloudformation/templates/s3-helm.yaml`
- `infra/aws/cloudformation/templates/budget.yaml`

**Templates verified (no changes needed — 3 files):**
- `infra/aws/cloudformation/templates/lambda-layer-lenie-all.yaml`
- `infra/aws/cloudformation/templates/lambda-layer-openai.yaml`
- `infra/aws/cloudformation/templates/lambda-layer-psycopg2.yaml`

**Templates excluded (org-level/non-taggable — 5 files):**
- `infra/aws/cloudformation/templates/organization.yaml`
- `infra/aws/cloudformation/templates/identityStore.yaml`
- `infra/aws/cloudformation/templates/scp-block-all.yaml`
- `infra/aws/cloudformation/templates/scp-block-sso-creation.yaml`
- `infra/aws/cloudformation/templates/scp-only-allowed-reginos.yaml`

**Already compliant (no changes needed — 4 files):**
- `infra/aws/cloudformation/templates/dynamodb-documents.yaml`
- `infra/aws/cloudformation/templates/s3-app-web.yaml`
- `infra/aws/cloudformation/templates/s3-website-content.yaml`
- `infra/aws/cloudformation/templates/cloudfront-app.yaml`

**Parameter files updated (14 files):**
- `infra/aws/cloudformation/parameters/dev/env-setup.json`
- `infra/aws/cloudformation/parameters/dev/vpc.json`
- `infra/aws/cloudformation/parameters/dev/secrets.json`
- `infra/aws/cloudformation/parameters/dev/s3-cloudformation.json`
- `infra/aws/cloudformation/parameters/dev/sqs-documents.json`
- `infra/aws/cloudformation/parameters/dev/sqs-application-errors.json`
- `infra/aws/cloudformation/parameters/dev/rds.json`
- `infra/aws/cloudformation/parameters/dev/ec2-lenie.json`
- `infra/aws/cloudformation/parameters/dev/lenie-launch-template.json`
- `infra/aws/cloudformation/parameters/dev/sqs-to-rds-lambda.json`
- `infra/aws/cloudformation/parameters/dev/api-gw-infra.json`
- `infra/aws/cloudformation/parameters/dev/api-gw-url-add.json`
- `infra/aws/cloudformation/parameters/dev/sqs-to-rds-step-function.json`
- `infra/aws/cloudformation/parameters/dev/budget.json`

**Parameter files created (7 files):**
- `infra/aws/cloudformation/parameters/dev/1-domain-route53.json`
- `infra/aws/cloudformation/parameters/dev/security-groups.json`
- `infra/aws/cloudformation/parameters/dev/s3.json`
- `infra/aws/cloudformation/parameters/dev/s3-helm.json`
- `infra/aws/cloudformation/parameters/dev/cloudfront-helm.json`
- `infra/aws/cloudformation/parameters/dev/lambda-rds-start.json`
- `infra/aws/cloudformation/parameters/dev/lambda-weblink-put-into-sqs.json`
