# Story 12.1: Codebase-Wide Stale Reference Verification

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **developer**,
I want to verify zero stale references to removed endpoints and dead code across the entire codebase,
so that no orphaned references cause confusion or runtime errors.

## Acceptance Criteria

1. **AC1 — Zero stale `/ai_ask` endpoint references:** Codebase-wide search (grep + semantic review) confirms zero stale references to `/ai_ask` as an endpoint. Legitimate uses of `ai_ask()` function (in `ai.py`, `youtube_processing.py`) are confirmed intact and NOT removed.

2. **AC2 — Zero stale `/translate` endpoint references:** Codebase-wide search confirms zero stale references to `/translate` endpoint across all code, templates, and documentation.

3. **AC3 — Zero stale `/infra/ip-allow` references:** Codebase-wide search confirms zero stale references to `/infra/ip-allow` endpoint AND zero references to `infra-allow-ip-in-secrutity-group` (misspelled Lambda name) in active code/templates (historical archive documentation is acceptable).

4. **AC4 — Zero stale `ai_describe_image` references:** Codebase-wide search confirms zero references to `ai_describe_image` function in any active code.

5. **AC5 — Semantic review completed:** Beyond grep searches, a semantic review verifies:
   - API Gateway endpoint count in ALL documentation files matches the actual count (18)
   - No documentation file references removed endpoints or dead code
   - Package names, terminology, and numeric counts are consistent across CLAUDE.md, README.md, backend/CLAUDE.md, docs/, and infra/ documentation

6. **AC6 — All issues fixed:** Any stale references or inconsistencies discovered during verification are corrected (documentation updated, files cleaned up, counts fixed).

## Tasks / Subtasks

- [x] **Task 1: Grep-based stale reference search for `/ai_ask`** (AC: #1)
  - [x] 1.1 Search entire codebase for `/ai_ask` (excluding `_bmad-output/`, `node_modules/`, `.git/`)
  - [x] 1.2 **KNOWN ISSUE:** Fix `infra/aws/README.md:262` — remove `/ai_ask` row from API endpoints table
  - [x] 1.3 **KNOWN ISSUE:** Evaluate `infra/aws/cloudformation/apigw/lenie-split-export.json` — this historical API GW export contains `/ai_ask` definition (line 430). Decide: regenerate export from current API GW state, or delete the file if no longer needed
  - [x] 1.4 Verify `ai_ask()` function exists in `backend/library/ai.py` and is callable by `backend/imports/youtube_processing.py`

- [x] **Task 2: Grep-based stale reference search for `/translate`** (AC: #2)
  - [x] 2.1 Search entire codebase for `/translate` (excluding `_bmad-output/`, `node_modules/`, `.git/`)
  - [x] 2.2 **KNOWN ISSUE:** Evaluate `infra/aws/cloudformation/apigw/lenie-split-export.json` — contains `/translate` definition (line 180). Same decision as Task 1.3

- [x] **Task 3: Grep-based stale reference search for `/infra/ip-allow`** (AC: #3)
  - [x] 3.1 Search entire codebase for `/infra/ip-allow` (excluding `_bmad-output/`)
  - [x] 3.2 Search entire codebase for `infra-allow-ip-in-secrutity-group` (misspelled)
  - [x] 3.3 **NOTE:** `infra/aws/serverless/CLAUDE.md:98` contains the misspelled name in "Archived Functions" table as historical documentation — this is acceptable (describes the original AWS Lambda name). Verify context is clearly archival.

- [x] **Task 4: Grep-based stale reference search for `ai_describe_image`** (AC: #4)
  - [x] 4.1 Search entire codebase for `ai_describe_image` (excluding `_bmad-output/`)
  - [x] 4.2 Expected result: zero matches (already verified clean in pre-analysis)

- [x] **Task 5: Semantic review — endpoint counts** (AC: #5)
  - [x] 5.1 **KNOWN ISSUE:** Fix `docs/api-contracts-backend.md:7` — says "19 endpoints", should be "18 endpoints"
  - [x] 5.2 Verify `infra/aws/cloudformation/CLAUDE.md` endpoint count for `api-gw-app` (currently says "12 endpoints" — verify against actual `api-gw-app.yaml` template content)
  - [x] 5.3 Verify these files all say "18 endpoints": `CLAUDE.md` (root), `README.md`, `backend/CLAUDE.md`, `docs/index.md`, `docs/project-overview.md`, `docs/source-tree-analysis.md`
  - [x] 5.4 Count actual endpoints in `api-gw-app.yaml` RestApi Body to confirm the "18" figure is correct (Epics 10 removed `/ai_ask`, `/translate`, `/infra/ip-allow` from original 21 → should be 18)

- [x] **Task 6: Semantic review — documentation consistency** (AC: #5, #6)
  - [x] 6.1 Review `infra/aws/README.md` API endpoints table — remove rows for `/ai_ask`, `/translate`, and `/infra/ip-allow` if still present. Update total count.
  - [x] 6.2 Review `docs/api-contracts-backend.md` — verify no detailed documentation of removed endpoints exists beyond the count fix
  - [x] 6.3 Review `infra/aws/serverless/CLAUDE.md` endpoint mapping table (lines 174-191) — verify it only lists active endpoints
  - [x] 6.4 Verify `handleCorrectUsingAI` and `handleTranslate` are not referenced anywhere in active code (expected: zero matches)

- [x] **Task 7: Handle `lenie-split-export.json`** (AC: #1, #2)
  - [x] 7.1 Investigate purpose of `infra/aws/cloudformation/apigw/lenie-split-export.json` — is it used by any script, template, or documentation?
  - [x] 7.2 If used: regenerate from current API Gateway state via `aws apigateway get-export`
  - [x] 7.3 If not used (historical reference only): decide whether to delete or regenerate for accuracy

## Dev Notes

### Critical Architecture Context

**This is a verification and cleanup story — NOT a code removal story.** Epics 10 (Endpoint & Dead Code Removal) and 11 (CloudFormation Template Improvements) have already completed the actual removal work. This story verifies that ALL traces have been cleaned up and documentation is consistent.

**Scope of verification:**
- ALL files in the repository except `_bmad-output/` (planning/implementation artifacts are historical records)
- `node_modules/` and `.git/` are excluded from searches
- Both grep-based search AND semantic review are required (per NFR10)

### Pre-Analysis Findings (Current State as of 2026-02-18)

The following issues were identified during story creation analysis:

| # | Pattern | File | Line | Issue |
|---|---------|------|------|-------|
| 1 | `/ai_ask` | `infra/aws/README.md` | 262 | Stale endpoint row in API endpoints table |
| 2 | `/ai_ask` | `infra/aws/cloudformation/apigw/lenie-split-export.json` | 430 | Historical API GW export contains removed endpoint |
| 3 | `/translate` | `infra/aws/cloudformation/apigw/lenie-split-export.json` | 180 | Historical API GW export contains removed endpoint |
| 4 | `19 endpoints` | `docs/api-contracts-backend.md` | 7 | Incorrect endpoint count (should be 18) |
| 5 | `12 endpoints` | `infra/aws/cloudformation/CLAUDE.md` | 158 | Endpoint count for api-gw-app — needs verification |

**Clean areas (no action needed):**
- `ai_describe_image` — fully removed, zero references in active code
- `handleCorrectUsingAI` and `handleTranslate` — fully removed from frontend
- `/infra/ip-allow` — fully removed from all active code and templates
- Main `CLAUDE.md`, `README.md`, `backend/CLAUDE.md` — correct "18 endpoints" count
- `docs/index.md`, `docs/project-overview.md`, `docs/source-tree-analysis.md` — correct "18 endpoints"

### The `lenie-split-export.json` Decision

`infra/aws/cloudformation/apigw/lenie-split-export.json` is a historical snapshot of the API Gateway configuration. It was created during Sprint 1 (Story 4.2) as a reference document for building the `api-gw-app.yaml` template from live AWS state. It contains stale endpoint definitions (`/ai_ask`, `/translate`, `/infra/ip-allow`).

**Options:**
- **Option A — Regenerate:** Run `aws apigateway get-export --rest-api-id 1bkc3kz7c9 --stage-name v1 --export-type oas30 > lenie-split-export.json` to get current state
- **Option B — Delete:** Remove the file if it's no longer needed (the `api-gw-app.yaml` template is now the source of truth)
- **Option C — Keep as-is:** Mark it as historical with a comment/README note

**Recommendation:** Option A (regenerate) is preferred — it keeps the reference file useful for future API Gateway work while eliminating stale data.

### Project Structure Notes

- All files to modify are documentation/reference files — no code changes expected
- `infra/aws/README.md` — API endpoints table needs 3 rows removed
- `docs/api-contracts-backend.md` — endpoint count fix (19 → 18)
- `infra/aws/cloudformation/CLAUDE.md` — endpoint count verification
- `infra/aws/cloudformation/apigw/lenie-split-export.json` — regenerate or delete

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 12.1] — Story definition with acceptance criteria
- [Source: _bmad-output/planning-artifacts/epics.md#Epic 12] — Epic context (FR30-FR33)
- [Source: _bmad-output/planning-artifacts/prd.md#Reference Cleanup] — FR30-FR35 requirements
- [Source: _bmad-output/planning-artifacts/architecture.md#Implementation Patterns] — Semantic review requirement
- [Source: infra/aws/README.md:262] — Stale `/ai_ask` row in API endpoints table
- [Source: infra/aws/cloudformation/apigw/lenie-split-export.json:180,430] — Stale export with removed endpoints
- [Source: docs/api-contracts-backend.md:7] — Incorrect "19 endpoints" count
- [Source: infra/aws/cloudformation/CLAUDE.md:158] — "12 endpoints" for api-gw-app to verify

### Previous Story Intelligence

**From Story 11.10 (done) — Codify API Gateway Stage Logging and Tracing:**
- Added `StageDescription` with `MethodSettings` and `TracingEnabled` to `ApiDeployment` in `api-gw-app.yaml`
- Updated `infra/aws/cloudformation/CLAUDE.md` — manual stage configuration note replaced with CF-managed description
- Commit prefix: `chore:` for infrastructure/documentation changes
- cfn-lint validation before commit

**From Story 11.9 (review) — Reconcile Lambda Function Name Mismatch:**
- Option B chosen: align all consumers to CF-defined name `lenie-dev-sqs-to-rds-lambda`
- Stale reference grep pattern: search entire repo, exclude `_bmad-output/` historical artifacts
- Remaining references only in `_bmad-output/` completed stories — acceptable as historical records

**From Story 10.1-10.4 (done) — Endpoint & Dead Code Removal:**
- `/ai_ask` removed from server.py, Lambda, API GW template, and React frontend
- `/translate` removed from Lambda, API GW template, and React frontend
- `/infra/ip-allow` removed from API GW template, Lambda archived
- `ai_describe_image()` removed from `backend/library/ai.py`
- `handleCorrectUsingAI` and `handleTranslate` removed from `web_interface_react/src/hooks/useManageLLM.js`

**Key patterns from Epic 10/11 retros:**
- Resource Deletion Checklist: (1) check code references, (2) check active state, (3) check dependency chain
- Semantic review expanded beyond grep: verify numeric counts, package names, terminology consistency
- All story deliverables committed together (lesson from Story 11.8)

### Git Intelligence

**Recent commits (pattern to follow):**
```
03725eb chore: add B-9 backlog item for S3 bucket directory structure
4e8228b chore: use wildcard ACM cert for helm and add B-8 to backlog
e0c91b1 fix: resolve CloudFormation deployment failures and merge helm templates
ae1cfff chore: reconcile Lambda function name mismatch (Story 11-9)
d587b98 chore: add SSM Parameter for DLQ ARN and commit Story 11-8 deliverables
```

**Commit patterns:**
- Prefix: `chore:` for documentation and infrastructure changes
- Commit all story deliverables together
- cfn-lint validation before committing CF template changes

### Library / Framework Requirements

No new libraries or dependencies. This is a pure verification and documentation cleanup story.

**Tools needed:**
- `grep -rn` (or `rg`) for codebase-wide stale reference searches
- Optionally `aws apigateway get-export` if regenerating `lenie-split-export.json`
- No cfn-lint needed (no CF template code changes expected — only doc/reference file updates)

### Testing Requirements

**Verification (grep checks — the core of this story):**
```bash
# Stale reference searches (exclude _bmad-output, node_modules, .git)
grep -rn "ai_ask" --include="*.py" --include="*.js" --include="*.jsx" --include="*.yaml" --include="*.yml" --include="*.json" --include="*.md" --include="*.sh" --include="*.ini" . | grep -v "_bmad-output" | grep -v "node_modules" | grep -v ".git/"
grep -rn "/translate" . | grep -v "_bmad-output" | grep -v "node_modules" | grep -v ".git/"
grep -rn "infra/ip-allow\|infra-allow-ip" . | grep -v "_bmad-output" | grep -v "node_modules" | grep -v ".git/"
grep -rn "ai_describe_image" . | grep -v "_bmad-output" | grep -v "node_modules" | grep -v ".git/"
grep -rn "handleCorrectUsingAI\|handleTranslate" . | grep -v "_bmad-output" | grep -v "node_modules" | grep -v ".git/"
```

**Semantic verification:**
```bash
# Endpoint count consistency
grep -rn "18 endpoints\|19 endpoints\|20 endpoints\|21 endpoints" . | grep -v "_bmad-output" | grep -v "node_modules" | grep -v ".git/"
```

**Post-fix verification:**
After fixing all issues, re-run ALL grep searches above and confirm zero stale matches.

**No unit or integration tests needed** — this is a verification and documentation cleanup story.

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

None — no debugging required.

### Completion Notes List

- **Task 1 (AC1):** Searched entire codebase for `/ai_ask`. Found stale endpoint row in `infra/aws/README.md:262` — removed. Found stale entry in `lenie-split-export.json:430` — file deleted (Task 7). Verified `ai_ask()` function exists in `backend/library/ai.py:25` and is imported/used by `backend/library/youtube_processing.py:13,290`. Legitimate uses in `backend/test_code/` (experimental scripts) and `docs/architecture-backend.md:53` confirmed intact.
- **Task 2 (AC2):** Searched entire codebase for `/translate`. Zero stale references in active code/docs. Only match was in deleted `lenie-split-export.json:180`.
- **Task 3 (AC3):** Searched for `/infra/ip-allow` and `infra-allow-ip-in-secrutity-group`. Zero active references. Only match: `infra/aws/serverless/CLAUDE.md:98` in "Archived Functions" table — confirmed clearly archival context (acceptable per AC3).
- **Task 4 (AC4):** Zero references to `ai_describe_image` in any active code. Confirmed clean.
- **Task 5 (AC5):** Fixed `docs/api-contracts-backend.md:7` — "19 endpoints" → "18 endpoints" (convention: root `/` informational endpoint excluded from count). Fixed `infra/aws/cloudformation/CLAUDE.md:158` — "12 endpoints" → "18 endpoints" (actual count in api-gw-app.yaml: 10 app endpoints + 8 /infra/* endpoints = 18 total). Verified 6 files correctly state "18 endpoints": CLAUDE.md, README.md, backend/CLAUDE.md, docs/index.md, docs/project-overview.md, docs/source-tree-analysis.md. **[Review fix]** Original implementation incorrectly counted only 10 paths (missed /infra/* endpoints at lines 567-961); corrected to 18 during code review.
- **Task 6 (AC5, AC6):** Reviewed infra/aws/README.md — only `/ai_ask` was present (removed in Task 1.2); `/translate` and `/infra/ip-allow` were already absent. Reviewed docs/api-contracts-backend.md — no detailed documentation of removed endpoints beyond count. Reviewed infra/aws/serverless/CLAUDE.md endpoint mapping table — only active endpoints listed. Verified zero references to `handleCorrectUsingAI` and `handleTranslate` outside `_bmad-output/`.
- **Task 7 (AC1, AC2):** Investigated `lenie-split-export.json` — not referenced by any active script, template, or documentation. User chose Option B (delete). File deleted. The `api-gw-app.yaml` template is the authoritative source of truth.

### Change Log

- 2026-02-18: Story 12.1 implementation — codebase-wide stale reference verification and cleanup (all 7 tasks completed)
- 2026-02-18: Code review fixes — corrected api-gw-app endpoint count in CF CLAUDE.md (10→18), reordered ADRs numerically, updated File List with 3 missing files, corrected Task 5 completion note
- 2026-02-18: Adversarial code review (2nd pass) — 6 issues found (1 HIGH, 2 MEDIUM, 3 LOW). HIGH: `docs/architecture-decisions.md:208` "9 infra endpoints"→"8". MEDIUM: README `/url_add` in wrong API table, README missing `/infra/git-webhooks`. LOW: README path notation (no `/infra/` prefix, `vpn-server`→`vpn_server`), template count 35→34 (29→27 active, 1→2 commented), CF CLAUDE.md `api-gw-infra` "7 Lambdas"→"8 Lambdas", README "20+" endpoints→"19", CF CLAUDE.md `s3-helm.yaml`+`cloudfront-helm.yaml`→`helm.yaml` (post B-7 merge). All fixed.

### File List

- `infra/aws/README.md` (modified) — removed `/ai_ask` row from API endpoints table; 2nd review: removed `/url_add` from App API table, fixed Infra API paths (`/infra/` prefix, `vpn_server` underscore), added `/infra/git-webhooks`, fixed template count (35→34, 29→27 active, 1→2 commented)
- `docs/api-contracts-backend.md` (modified) — fixed endpoint count: "19 endpoints" → "18 endpoints"
- `infra/aws/cloudformation/CLAUDE.md` (modified) — fixed api-gw-app endpoint count: "12 endpoints" → "18 endpoints" (review fix: original incorrectly set to 10); 2nd review: fixed api-gw-infra "7 Lambdas" → "8 Lambdas"
- `infra/aws/cloudformation/apigw/lenie-split-export.json` (deleted) — historical API GW export with stale endpoint definitions
- `docs/architecture-decisions.md` (added) — ADR-001 through ADR-006 documenting key architectural decisions; 2nd review: fixed ADR-006 "9 infra endpoints" → "8 infra endpoints"
- `docs/system-evolution.md` (added) — system evolution narrative (embeddings, MCP pipeline, infrastructure cleanup)
- `docs/index.md` (modified) — added references to new ADR and system evolution docs
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (modified) — story status: ready-for-dev → in-progress → review
- `_bmad-output/implementation-artifacts/12-1-codebase-wide-stale-reference-verification.md` (modified) — story file updated
