# Story 6.1: Update deploy.ini and Document Deployment Order

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer,
I want to see the complete, ordered list of all DEV CloudFormation templates in `deploy.ini` with clear layer documentation,
so that I can recreate the entire DEV environment by following the documented deployment order.

## Acceptance Criteria

1. **Given** all new templates from Epics 1, 2, and 4 have been created and verified
   **When** developer updates `deploy.ini`
   **Then** all new templates are added to the `[dev]` section at the correct position within their deployment layer (FR24):
   - Layer 4 (Storage): `dynamodb-cache-ai-query.yaml`, `dynamodb-cache-language.yaml`, `dynamodb-cache-translation.yaml`, `s3-website-content.yaml`, `s3-app-web.yaml`
   - Layer 5 (Compute): `lambda-layer-lenie-all.yaml`, `lambda-layer-openai.yaml`, `lambda-layer-psycopg2.yaml`
   - Layer 8 (CDN): `cloudfront-app.yaml`

2. **Given** the updated `deploy.ini`
   **When** developer reviews the file
   **Then** the `ses.yaml` entry is NOT present (already removed in Epic 5)
   **And** all previously commented-out valid DEV templates are uncommented
   **And** layer boundaries are documented with comments (e.g., `; --- Layer 4: Storage ---`)
   **And** the complete template list is visible in `deploy.ini` (FR22)

3. **Given** the documented deployment order in `deploy.ini`
   **When** developer deploys the entire DEV environment by running templates in order via `deploy.sh`
   **Then** the deployment order respects all layer dependencies: Foundation -> Networking -> Security -> Storage -> Compute -> API -> Orchestration -> CDN (FR23)
   **And** no modifications to `deploy.sh` script are required (NFR6)

## Tasks / Subtasks

- [x] Task 1: Restructure deploy.ini [dev] section with layer-ordered templates (AC: #1, #2)
  - [x] 1.1: Replace the current `[dev]` section with all templates organized by deployment layer
  - [x] 1.2: Add layer boundary comments (`;` prefix) for each layer group
  - [x] 1.3: Uncomment all valid DEV templates (remove leading `;`)
  - [x] 1.4: Add all 9 new templates from Epics 1, 2, 4 at the correct layer positions
  - [x] 1.5: Verify `ses.yaml` is NOT present in the file
  - [x] 1.6: Remove organization/SCP/identityStore templates from [dev] (these are account-level, not per-environment)

- [x] Task 2: Verify deploy.ini completeness and order (AC: #2, #3)
  - [x] 2.1: Cross-reference deploy.ini against the templates/ directory — every template that belongs to DEV should be listed
  - [x] 2.2: Verify layer dependency order is correct (no template references a resource from a later layer)
  - [x] 2.3: Verify parameter files exist for all new templates in `parameters/dev/`

- [x] Task 3: Update documentation (AC: #3)
  - [x] 3.1: Update `infra/aws/cloudformation/CLAUDE.md` — refresh the "Recommended Deployment Order" section to match new deploy.ini structure
  - [x] 3.2: Update `infra/aws/README.md` if needed — ensure it reflects the current template inventory

## Dev Notes

### Current State of deploy.ini

The current `[dev]` section has **all templates commented out** with `;` prefixes, in a **non-layered, disorganized order**. Templates are not grouped by deployment layer, and the 9 new templates from Epics 1-4 are missing entirely.

Key issues to fix:
1. **Missing templates (9):** `dynamodb-cache-ai-query.yaml`, `dynamodb-cache-language.yaml`, `dynamodb-cache-translation.yaml`, `s3-website-content.yaml`, `s3-app-web.yaml`, `lambda-layer-lenie-all.yaml`, `lambda-layer-openai.yaml`, `lambda-layer-psycopg2.yaml`, `cloudfront-app.yaml`
2. **All templates commented out** — they should be uncommented for DEV
3. **No layer grouping** — templates need to be ordered by deployment layer with boundary comments
4. **Organization/SCP templates mixed in** — these are account-level resources, not per-environment

### Target deploy.ini [dev] Section

Based on the Architecture document's target structure (see `architecture.md#deploy.ini Target Structure`):

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

### Templates NOT in [dev] Section

The following templates exist but are NOT per-environment (account/org level):
- `organization.yaml` — AWS Organization (deploy once)
- `identityStore.yaml` — Identity Store (deploy once)
- `scp-block-all.yaml` — Service Control Policy (deploy once)
- `scp-block-sso-creation.yaml` — Service Control Policy (deploy once)
- `scp-only-allowed-reginos.yaml` — Service Control Policy (deploy once)

The following template was removed:
- `ses.yaml` — Deleted in Story 5.1 (SES not used by application)

The following template is environment-specific but NOT for dev:
- `rds.yaml` — RDS database (deployed separately, managed lifecycle via Step Functions)

### CRITICAL: rds.yaml Decision

`rds.yaml` exists in the templates directory and IS a DEV resource, but it requires special handling:
- RDS is started/stopped on demand via Step Functions (cost optimization)
- It depends on VPC, secrets, and security groups
- It should be included in deploy.ini at Layer 4 (Storage/Database) position, AFTER `secrets.yaml`
- The developer should decide whether to include it commented or uncommented

### deploy.sh Compatibility

No changes to `deploy.sh` are needed (NFR6). The script:
- Reads templates from deploy.ini sections
- Auto-detects create vs update
- Auto-loads parameter files from `parameters/<stage>/`
- Lines with `;` prefix are skipped

### Layer Dependencies Explained

```
Layer 1 (Foundation) → No dependencies
Layer 2 (Networking) → Depends on Layer 1 (env-setup for SSM params)
Layer 3 (Security)   → Depends on Layer 2 (VPC for security groups context)
Layer 4 (Storage)    → s3-cloudformation needed before Lambda Layers
                       DynamoDB tables are independent
                       SQS queues are independent
Layer 5 (Compute)    → Lambda Layers need S3 cloudformation bucket
                       Lambdas need VPC, secrets, SQS, DynamoDB
Layer 6 (API)        → API GW needs Lambda functions
Layer 7 (Orchestration) → Step Functions need Lambdas, SQS, RDS
Layer 8 (CDN)        → CloudFront needs S3 app-web bucket
```

### Project Structure Notes

- All changes are within `infra/aws/cloudformation/` directory
- `deploy.ini` is the only file being restructured (INI format)
- Documentation updates in `CLAUDE.md` and potentially `README.md`
- No new files created — this is purely reorganization and documentation

### Architecture Compliance

- **FR22**: Complete template list visible in deploy.ini
- **FR23**: Deployment order enables full DEV environment recreation via deploy.sh
- **FR24**: New templates registered at correct position within deployment layer
- **NFR6**: No modifications to deploy.sh required

### Previous Story Intelligence

Key learnings from Stories 5.1 and 5.2:
1. **Verify before acting** — check that all referenced templates actually exist in `templates/` directory
2. **Cross-reference thoroughly** — ensure deploy.ini matches the actual file system
3. **Update documentation** — CLAUDE.md and README files must reflect changes
4. Story 5.1 already removed `ses.yaml` from both templates/ and deploy.ini

### Git Intelligence

Recent commits show:
- Documentation-heavy work (GitLab CI docs, Amplify docs, README cleanup)
- Story 5.1 completed: legacy AWS resources removed, ses.yaml deleted
- Story 5.2 completed: frontend monitoring code removed
- All Epic 1-4 work is done (templates created and deployed)

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 6.1] — Acceptance criteria (FR22, FR23, FR24)
- [Source: _bmad-output/planning-artifacts/architecture.md#deploy.ini Target Structure] — Target deploy.ini layout with all 8 layers
- [Source: _bmad-output/planning-artifacts/architecture.md#Layer Dependency Boundaries] — Layer dependency diagram
- [Source: _bmad-output/planning-artifacts/architecture.md#Implementation Patterns] — Enforcement rules for deploy.ini entries
- [Source: infra/aws/cloudformation/CLAUDE.md] — deploy.sh documentation, current deployment order
- [Source: infra/aws/cloudformation/deploy.ini] — Current state (all commented, unordered)
- [Source: _bmad-output/implementation-artifacts/5-1-remove-legacy-aws-resources.md] — ses.yaml removal confirmation
- [Source: _bmad-output/implementation-artifacts/5-2-remove-dead-frontend-monitoring-code.md] — Previous story learnings

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

No issues encountered during implementation.

### Completion Notes List

- Restructured deploy.ini [dev] section from disorganized, fully-commented list to layer-ordered, uncommented configuration with 8 deployment layers
- Added 9 new templates from Epics 1, 2, 4: dynamodb-cache-ai-query, dynamodb-cache-language, dynamodb-cache-translation, s3-website-content, s3-app-web, lambda-layer-lenie-all, lambda-layer-openai, lambda-layer-psycopg2, cloudfront-app
- Removed 5 account-level templates from [dev]: organization, identityStore, scp-block-all, scp-block-sso-creation, scp-only-allowed-reginos
- Confirmed ses.yaml is not present (removed in Story 5.1)
- Added s3.yaml (video transcription bucket) which was missing from [dev] but exists in templates/
- Included rds.yaml as commented entry with explanation (managed lifecycle via Step Functions)
- Cross-referenced all 37 templates against deploy.ini — 32 active in [dev], 5 account-level excluded, rds.yaml commented
- Verified all 27 parameter files in parameters/dev/ match templates
- Updated CLAUDE.md "Recommended Deployment Order" section with full 8-layer structure
- Updated README.md: DynamoDB table count (1→4), added cache table sections, added missing parameter file entries

### Change Log

- 2026-02-15: Story implementation complete — deploy.ini restructured, documentation updated
- 2026-02-15: Code review fixes — README.md CloudFormation count (27→38), SES CF-managed count (1→0), CLAUDE.md Templates Overview added 9 new templates (3 DynamoDB cache, 2 S3, 3 Lambda Layers, 1 CloudFront), deleted orphan parameter file api-gw-url-lenie.json

### File List

- `infra/aws/cloudformation/deploy.ini` (modified)
- `infra/aws/cloudformation/CLAUDE.md` (modified)
- `infra/aws/README.md` (modified)
- `infra/aws/cloudformation/parameters/dev/api-gw-url-lenie.json` (deleted)
