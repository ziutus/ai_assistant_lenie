# Story 10.3: Remove `/infra/ip-allow` Endpoint

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **developer**,
I want to remove the `/infra/ip-allow` endpoint from API Gateway and delete its Lambda function from AWS,
So that the unused infrastructure endpoint and its Lambda are cleaned up.

## Acceptance Criteria

1. **AC1 — API Gateway definition removed:** The `/infra/ip-allow` path definition (POST + OPTIONS) in `infra/aws/cloudformation/templates/api-gw-app.yaml` (lines 920-970) is deleted. The API Gateway template no longer includes the `/infra/ip-allow` path. After removal, the template has 18 paths (10 app + 8 infra). The template passes cfn-lint validation with zero errors.

2. **AC2 — Lambda function deleted from AWS:** The Lambda function `infra-allow-ip-in-secrutity-group` is deleted from the AWS account. The Resource Deletion Checklist was followed: (1) code references checked — only `api-gw-app.yaml` line 934, (2) active state verified — function exists in AWS but is unused, (3) dependency chain reviewed — no downstream callers. Lambda code is already archived in git at `archive/infra-allow-ip-in-security-group`.

3. **AC3 — Zero frontend references verified:** A codebase-wide search confirms zero references to `/infra/ip-allow` in any frontend JavaScript/JSX source files. (Already confirmed during analysis — no `useIpAllow` hook or similar exists.)

4. **AC4 — Stale export file cleaned up:** The stale reference to `/infra/ip-allow` in `infra/aws/cloudformation/apigw/lenie-split-export.json` is either removed (delete the path block) or the file is documented as historical/stale.

5. **AC5 — Cross-story impact documented:** Story 11.4 (Lambda typo fix `secrutity` → `security`) is resolved by Path A: Lambda deleted — FR24-FR26 satisfied by removal. This outcome is noted for sprint tracking.

## Tasks / Subtasks

- [x] **Task 1: Remove `/infra/ip-allow` from API Gateway CloudFormation template** (AC: #1)
  - [x] 1.1 Delete the `/infra/ip-allow` path block (POST + OPTIONS) in `infra/aws/cloudformation/templates/api-gw-app.yaml` (lines 920-970)
  - [x] 1.2 Validate template with cfn-lint after removal — must pass with 0 errors
  - [x] 1.3 Verify no other resources reference the removed `/infra/ip-allow` path or `infra-allow-ip-in-secrutity-group` Lambda within the template
  - [x] 1.4 Count remaining paths: expect 18 (10 app + 8 infra)

- [x] **Task 2: Delete Lambda function from AWS** (AC: #2)
  - [x] 2.1 Follow Resource Deletion Checklist: (1) code references — only `api-gw-app.yaml` (being removed in Task 1), (2) active state — function exists in AWS, (3) dependency chain — no callers
  - [x] 2.2 Delete Lambda function `infra-allow-ip-in-secrutity-group` from AWS using `aws lambda delete-function --function-name infra-allow-ip-in-secrutity-group`
  - [x] 2.3 Verify deletion: `aws lambda get-function --function-name infra-allow-ip-in-secrutity-group` should return ResourceNotFoundException
  - [x] 2.4 Confirm Lambda code remains archived in git at `archive/infra-allow-ip-in-security-group` branch

- [x] **Task 3: Verify zero frontend and backend references** (AC: #3)
  - [x] 3.1 `grep -r "ip-allow"` across `web_interface_react/` — must return ZERO results
  - [x] 3.2 `grep -r "ip-allow"` across `backend/` — must return ZERO results
  - [x] 3.3 `grep -r "infra-allow-ip"` across entire codebase — only planning artifacts and archive references should remain

- [x] **Task 4: Clean up stale API Gateway export** (AC: #4)
  - [x] 4.1 Remove `/infra/ip-allow` path block from `infra/aws/cloudformation/apigw/lenie-split-export.json` (line 380+)
  - [x] 4.2 Verify JSON remains valid after edit

- [x] **Task 5: Codebase-wide verification and documentation** (AC: #1-5)
  - [x] 5.1 `grep -r "ip-allow"` across entire codebase — review results: only planning artifacts should remain
  - [x] 5.2 `grep -r "secrutity"` across entire codebase — only planning artifacts and `infra/aws/serverless/CLAUDE.md` archive table should remain
  - [x] 5.3 Semantic review: count paths in `api-gw-app.yaml` — verify 18 paths (10 app + 8 infra)
  - [x] 5.4 Verify no active documentation (CLAUDE.md, README.md, docs/*.md) references `/infra/ip-allow` as an active endpoint
  - [x] 5.5 Note for sprint tracking: Story 11.4 (Lambda typo fix) is resolved by Path A (Lambda deleted)

## Dev Notes

### Technical Requirements

**SIMPLEST STORY IN EPIC 10 — Minimal code change scope:**
- The `/infra/ip-allow` endpoint does NOT exist in Flask `backend/server.py` — it is an API-Gateway-only endpoint
- The `/infra/ip-allow` endpoint does NOT exist in any Lambda function source code — it invokes a standalone Lambda `infra-allow-ip-in-secrutity-group` directly via API Gateway integration
- There are ZERO frontend references — no React hook, no button, no component calls this endpoint
- The ONLY code change is removing lines 920-970 from `api-gw-app.yaml`

**What the Lambda function does (for context — being deleted):**
- Lambda `infra-allow-ip-in-secrutity-group` adds the caller's IP to a hardcoded Security Group (`sg-0929bfcae31074fb8`) on RDP port 3389
- Uses AWS Lambda Powertools, runtime python3.12
- Function has typo in name (`secrutity` instead of `security`)
- Function is unused — not needed for RDP access
- Lambda code already archived in git at `archive/infra-allow-ip-in-security-group` (Sprint 2 cleanup)

**API Gateway template (`api-gw-app.yaml`) — target lines:**
- Lines 920-970: `/infra/ip-allow` path with POST method + OPTIONS CORS mock integration
- Line 934: Lambda invocation URI referencing `infra-allow-ip-in-secrutity-group`
- After removal: 18 paths remain (10 app + 8 infra):
  - App (10): `/website_list`, `/website_get`, `/website_save`, `/website_delete`, `/website_is_paid`, `/website_get_next_to_correct`, `/website_similar`, `/website_split_for_embedding`, `/website_download_text_content`, `/ai_embedding_get`
  - Infra (8): `/infra/database/start`, `/infra/database/stop`, `/infra/database/status`, `/infra/vpn_server/start`, `/infra/vpn_server/stop`, `/infra/vpn_server/status`, `/infra/sqs/size`, `/infra/git-webhooks`

**Cross-story impact — Epic 11 Story 11.4 (Lambda typo fix):**
- Story 11.4 has two paths: Path A (Lambda deleted → typo fix moot) or Path B (Lambda archived → rename needed)
- This story triggers **Path A**: deleting the Lambda from AWS means FR24-FR26 are satisfied by removal
- No rename operation needed — the misspelled function ceases to exist

**AWS Lambda deletion — manual operation:**
- Command: `aws lambda delete-function --function-name infra-allow-ip-in-secrutity-group --region eu-central-1`
- This is an AWS-side operation, not a code change
- The function name has the typo `secrutity` — use the EXACT misspelled name in the delete command
- Verify: `aws lambda get-function --function-name infra-allow-ip-in-secrutity-group --region eu-central-1` should return `ResourceNotFoundException`

### Architecture Compliance

**Resource Deletion Checklist (from Epic 7/8 retro — MANDATORY):**
Before removing any resource, verify:
1. **Code references checked** — `grep -r "ip-allow"` and `grep -r "infra-allow-ip"` across codebase: only `api-gw-app.yaml` (line 920, 934) and stale `lenie-split-export.json` (line 380) reference this endpoint in active code
2. **Active state verified** — Lambda function `infra-allow-ip-in-secrutity-group` exists in AWS but is confirmed unused (hardcoded security group for RDP, not needed)
3. **Dependency chain reviewed** — no downstream callers: no backend route, no frontend hook, no other Lambda references this function

**API Gateway template modification rules:**
- After stories 10-1 and 10-2, the template already had `/ai_ask` and `/translate` removed
- Removing `/infra/ip-allow` further reduces the template (removes ~50 lines)
- CORS OPTIONS mock integration for `/infra/ip-allow` must also be removed (not just the POST method)
- After removal, run cfn-lint validation
- Template uses OpenAPI 3.0 inline Body definition — the path block is self-contained within the `paths:` section

**Semantic review requirement (from Epic 8/9 retro):**
- After removal, verify path count in `api-gw-app.yaml` = 18
- No active documentation references `/infra/ip-allow` — confirmed during analysis. Documentation update scope is ZERO for active docs (CLAUDE.md, README.md, docs/*.md)
- Flask endpoint count (18 in server.py) is NOT affected — this endpoint was never in Flask

**CloudFormation validation:**
- Run cfn-lint on modified `api-gw-app.yaml` before committing

### Library & Framework Requirements

**No new libraries or dependencies required.** This story is purely removal/deletion.

**No libraries affected.** Unlike stories 10-1 and 10-2, there are no Lambda handler changes, no React hook changes, and no Flask route changes. The only code change is YAML path removal in the CloudFormation template.

**Dependencies NOT to remove:**
- All other `/infra/*` Lambda integrations in `api-gw-app.yaml` remain untouched
- The archived Lambda code in git stays in `archive/infra-allow-ip-in-security-group` branch

### File Structure Requirements

**Files to MODIFY (2 files):**

```
infra/aws/cloudformation/templates/
└── api-gw-app.yaml                                   [MOD] Remove /infra/ip-allow path definition (lines 920-970)

infra/aws/cloudformation/apigw/
└── lenie-split-export.json                            [MOD] Remove /infra/ip-allow path block (line 380+) — stale export file cleanup
```

**AWS-side operation (not a code change):**

```
AWS Lambda:
└── infra-allow-ip-in-secrutity-group                  [DELETE] Delete function from AWS account
```

**Files to NOT TOUCH:**

```
backend/server.py                                      [NO CHANGE] /infra/ip-allow never existed here
backend/library/*.py                                   [NO CHANGE] No backend code involved
web_interface_react/src/**/*                            [NO CHANGE] Zero frontend references
infra/aws/serverless/lambdas/**/*                      [NO CHANGE] Lambda code already archived
infra/aws/serverless/CLAUDE.md                         [NO CHANGE] Archive table already correct
CLAUDE.md (root)                                       [NO CHANGE] No /infra/ip-allow references
README.md                                              [NO CHANGE] No /infra/ip-allow references
docs/*.md                                              [NO CHANGE] No /infra/ip-allow references
```

**No files created or deleted in the repository.** All changes are modifications to existing files (YAML path removal + JSON cleanup). The Lambda deletion is an AWS-side operation.

### Testing Requirements

**Automated tests:**
- Run `pytest backend/tests/` — all existing tests must pass (no regressions, though no backend code is changed)
- No new test files required (this is infrastructure cleanup, not feature work)

**Manual verification checklist:**

1. **CloudFormation template validation:**
   - `cfn-lint infra/aws/cloudformation/templates/api-gw-app.yaml` — must pass with zero errors

2. **AWS Lambda deletion verification:**
   - `aws lambda get-function --function-name infra-allow-ip-in-secrutity-group --region eu-central-1` — must return ResourceNotFoundException

3. **Codebase-wide grep verification:**
   - `grep -r "ip-allow"` — only planning artifacts and this story file should remain
   - `grep -r "infra-allow-ip"` — only planning artifacts, archive references, and `infra/aws/serverless/CLAUDE.md` archive table
   - `grep -r "secrutity"` — only planning artifacts and `infra/aws/serverless/CLAUDE.md` archive table

4. **Semantic review:**
   - Count paths in `api-gw-app.yaml` `paths:` section — verify 18 (10 app + 8 infra)
   - Verify Flask endpoint count in docs unchanged (18 in server.py)
   - Verify no active docs reference `/infra/ip-allow`

5. **JSON validity:**
   - Verify `lenie-split-export.json` is valid JSON after edit

### Previous Story Intelligence (from Stories 10-1 and 10-2)

**Key learnings from previous stories:**
- Story 10-1 refactored Lambda `if` chains to `if/elif/else` — NOT relevant here (no Lambda source changes)
- Story 10-1 and 10-2 both required touching 10-13 documentation files — this story requires ZERO doc file changes (confirmed: no active docs reference `/infra/ip-allow`)
- Story 10-2 found stale `/ai_ask` references in `infra/aws/README.md` from 10-1 — watch for similar missed references
- Code review in 10-1 found 6 issues, 10-2 found 6 issues — this story has much smaller scope, expect fewer issues
- Both 10-1 and 10-2 had "19 paths" in `api-gw-app.yaml` semantic review — after this story: 18 paths
- Pre-existing test failures: 16 passed, 6 failed in unit tests (markdown/transcript tests — not regressions)
- Pre-existing ruff errors: 67 errors (all pre-existing)

**Commit message convention:** `chore: remove /infra/ip-allow endpoint from API Gateway and delete Lambda`

### Git Intelligence

**Recent commits (post stories 10-1 and 10-2):**

| Commit | Description | Relevance |
|--------|-------------|-----------|
| `db4181f` | chore: remove /translate endpoint from Lambda, API Gateway, and frontend | **HIGH** — same pattern (API GW path removal) |
| `6af45b9` | chore: remove /ai_ask endpoint from backend, Lambda, API Gateway, and frontend | **HIGH** — same pattern (API GW path removal) |
| `eae71f0` | docs: complete Sprint 2 — cleanup, vision, documentation | LOW |

**Key pattern:** Single commit for all changes, commit type `chore`, all changes in same commit.

### Project Structure Notes

- All modifications align with existing project structure — no new paths, modules, or naming introduced
- CloudFormation template remains in existing location: `infra/aws/cloudformation/templates/api-gw-app.yaml`
- Stale export file cleanup: `infra/aws/cloudformation/apigw/lenie-split-export.json` (historical OpenAPI export)
- No frontend or backend structure changes
- No conflicts or variances detected with existing conventions

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Epic 10, Story 10.3] — Story definition, acceptance criteria, BDD scenarios
- [Source: _bmad-output/planning-artifacts/prd.md#Endpoint Removal — /infra/ip-allow] — FR10-FR12 requirements
- [Source: _bmad-output/planning-artifacts/prd.md#CF Improvements — Lambda Typo] — FR24-FR26 (resolved by Path A: Lambda deleted)
- [Source: _bmad-output/planning-artifacts/architecture.md#Implementation Patterns] — Resource Deletion Checklist, CF validation rules
- [Source: _bmad-output/planning-artifacts/architecture.md#Enforcement Guidelines] — AI Agent MUST rules for CF templates
- [Source: _bmad-output/implementation-artifacts/10-1-remove-ai-ask-endpoint.md] — Previous story patterns and learnings
- [Source: _bmad-output/implementation-artifacts/10-2-remove-translate-endpoint.md] — Previous story patterns and learnings
- [Source: infra/aws/cloudformation/templates/api-gw-app.yaml:920-970] — `/infra/ip-allow` path definition (POST + OPTIONS)
- [Source: infra/aws/cloudformation/templates/api-gw-app.yaml:934] — Lambda URI `infra-allow-ip-in-secrutity-group`
- [Source: infra/aws/cloudformation/apigw/lenie-split-export.json:380] — Stale export with `/infra/ip-allow` reference
- [Source: infra/aws/serverless/CLAUDE.md:98] — Lambda archive table entry with function details

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6 (claude-opus-4-6)

### Debug Log References

### Completion Notes List

- Ultimate context engine analysis completed — comprehensive developer guide created
- Story created on 2026-02-16 by BMad create-story workflow
- Simplest story in Epic 10: only 2 files to modify + 1 AWS-side Lambda deletion
- 5 acceptance criteria defined with specific file locations and line numbers
- 5 tasks with 16 subtasks mapped to acceptance criteria
- Key insight: ZERO frontend/backend code changes needed — endpoint only in API Gateway template
- Lambda code already archived in git (Sprint 2) — only AWS-side deletion remains
- Cross-story impact: Story 11.4 (Lambda typo fix) resolved by Path A (Lambda deleted)
- Previous stories 10-1 and 10-2 intelligence integrated
- Implementation completed on 2026-02-16:
  - Removed /infra/ip-allow path block (POST + OPTIONS, ~51 lines) from api-gw-app.yaml
  - cfn-lint validation passed with 0 errors, 0 warnings
  - Verified 18 remaining paths (10 app + 8 infra)
  - Lambda function `infra-allow-ip-in-secrutity-group` already deleted from AWS (ResourceNotFoundException confirmed)
  - Lambda code archived in git history (commit 476855b)
  - Removed /infra/ip-allow block from stale lenie-split-export.json, JSON validity confirmed
  - Codebase-wide grep: zero references in active code; only planning artifacts remain
  - Zero references in frontend (web_interface_react/) and backend (backend/)
  - No active documentation changes required
  - Unit tests: 16 passed, 6 failed (all pre-existing failures, no regressions)
  - Story 11.4 (Lambda typo fix) resolved by Path A: Lambda deleted from AWS

### Implementation Plan

- Removed /infra/ip-allow path definition from API Gateway CloudFormation template
- Confirmed Lambda function already deleted from AWS
- Cleaned up stale reference in lenie-split-export.json
- Verified zero codebase references outside planning artifacts

## Change Log

- 2026-02-16: Removed /infra/ip-allow endpoint from API Gateway template and cleaned up stale export file. Lambda function confirmed already deleted from AWS. Story 11.4 resolved by Path A.
- 2026-02-17: Code review (adversarial) — Found api-gw-app.yaml change was already committed in d2b3992 with misleading commit message. Updated File List to reflect actual git state. Only lenie-split-export.json remains uncommitted. All ACs verified: path count 18, JSON valid, zero active code references.

### File List

**Modified (committed in d2b3992 — bundled with environment unification commit):**
- `infra/aws/cloudformation/templates/api-gw-app.yaml` — Removed /infra/ip-allow path block (POST + OPTIONS, ~51 lines)

**Modified (uncommitted):**
- `infra/aws/cloudformation/apigw/lenie-split-export.json` — Removed /infra/ip-allow path block from stale export

**AWS-side:**
- Lambda `infra-allow-ip-in-secrutity-group` — Already deleted (confirmed ResourceNotFoundException)

**Note:** The api-gw-app.yaml change was inadvertently committed in `d2b3992` ("chore: unify environment definitions") along with unrelated changes. The commit message does not mention the ip-allow removal, making this change untraceable via `git log --grep`.
