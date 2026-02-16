# Story 10.1: Remove `/ai_ask` Endpoint

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **developer**,
I want to remove the `/ai_ask` endpoint from backend, Lambda, API Gateway, and frontend,
So that the API surface contains only active endpoints while preserving the `ai_ask()` function used by `youtube_processing.py`.

## Acceptance Criteria

1. **AC1 — Backend endpoint removed:** The `/ai_ask` route in `backend/server.py` (lines 539-594) is deleted. The Flask app no longer exposes `/ai_ask`. No other routes are affected.

2. **AC2 — Lambda handler removed:** The `/ai_ask` handler block in `infra/aws/serverless/lambdas/app-server-internet/lambda_function.py` (lines 181-234) is deleted. The Lambda function no longer handles `/ai_ask` requests. All other handlers (`/website_download_text_content`, `/ai_embedding_get`, `/translate`) continue to function.

3. **AC3 — API Gateway definition removed:** The `/ai_ask` path definition (POST + OPTIONS) in `infra/aws/cloudformation/templates/api-gw-app.yaml` (lines 563-613) is deleted. The API Gateway template no longer includes the `/ai_ask` path.

4. **AC4 — Frontend function removed:** `handleCorrectUsingAI()` in `web_interface_react/src/modules/shared/hooks/useManageLLM.js` (lines 452-489) is deleted. The "Correct using AI" button is removed from `InputsForAllExceptLink.jsx`. All page components (webpage, youtube, movie) no longer destructure or pass `handleCorrectUsingAI`. The React frontend loads and functions without errors.

5. **AC5 — `ai_ask()` function preserved:** The `ai_ask()` function in `backend/library/ai.py` (lines 39-94) remains intact and unmodified. `backend/imports/youtube_processing.py` (line 290) successfully imports and calls `ai_ask()` without errors. All AI provider integrations (OpenAI, Bedrock, Vertex, CloudFerro) remain operational.

6. **AC6 — Documentation updated:** All documentation files referencing `/ai_ask` as an endpoint are updated: `docs/api-contracts-backend.md`, `docs/architecture-backend.md`, `docs/architecture-web_interface_react.md`, `docs/component-inventory-web_interface_react.md`, `backend/CLAUDE.md`, `infra/aws/serverless/CLAUDE.md`. Endpoint counts are decremented to reflect removal.

7. **AC7 — Unused frontend constants cleaned up:** `ai_correct_query` and `llm_simple_jobs_model_name` constants in `web_interface_react/src/modules/shared/constants/variables.js` are removed (confirmed used only by `handleCorrectUsingAI`).

## Tasks / Subtasks

- [x] **Task 1: Remove `/ai_ask` route from Flask backend** (AC: #1)
  - [x] 1.1 Delete the `@app.route('/ai_ask', methods=['POST'])` function in `backend/server.py` (lines 539-594)
  - [x] 1.2 Verify `import library.ai` on line 10 is still needed (NO — removed unused import)
  - [x] 1.3 Run `python -c "import server"` or equivalent to confirm no import errors

- [x] **Task 2: Remove `/ai_ask` handler from Lambda function** (AC: #2)
  - [x] 2.1 Delete the `if event['path'] == '/ai_ask':` block in `infra/aws/serverless/lambdas/app-server-internet/lambda_function.py` (lines 181-234)
  - [x] 2.2 Verify remaining handlers (`/website_download_text_content`, `/ai_embedding_get`, `/translate`) are intact
  - [x] 2.3 Verify `import library.ai` is still needed in Lambda (NO — removed unused import + llm_simple_jobs_model)

- [x] **Task 3: Remove `/ai_ask` from API Gateway CloudFormation template** (AC: #3)
  - [x] 3.1 Delete the `/ai_ask` path block (POST + OPTIONS) in `infra/aws/cloudformation/templates/api-gw-app.yaml` (lines 563-613)
  - [x] 3.2 Validate template with cfn-lint after removal — passed with 0 errors, 0 warnings
  - [x] 3.3 Verify no other resources reference the removed `/ai_ask` path within the template

- [x] **Task 4: Remove frontend `handleCorrectUsingAI` and UI button** (AC: #4, #7)
  - [x] 4.1 Delete `handleCorrectUsingAI()` function from `web_interface_react/src/modules/shared/hooks/useManageLLM.js` (lines 452-489)
  - [x] 4.2 Remove `handleCorrectUsingAI` from the hook's return object (line 601)
  - [x] 4.3 Remove `ai_correct_query` and `llm_simple_jobs_model_name` imports from `useManageLLM.js` (lines 5-6)
  - [x] 4.4 Remove `ai_correct_query` constant definition from `web_interface_react/src/modules/shared/constants/variables.js` (lines 3-4)
  - [x] 4.5 Remove `llm_simple_jobs_model_name` constant definition from `variables.js` (line 2)
  - [x] 4.6 Remove "Correct using AI" button from `web_interface_react/src/modules/shared/components/SharedInputs/InputsForAllExceptLink.jsx` (lines 42-48)
  - [x] 4.7 Remove `handleCorrectUsingAI` prop from `InputsForAllExceptLink` component destructuring (line 7)
  - [x] 4.8 Remove `handleCorrectUsingAI` destructure + prop passing in `webpage.jsx` (lines 56, 77)
  - [x] 4.9 Remove `handleCorrectUsingAI` destructure + prop passing in `youtube.jsx` (lines 55, 75)
  - [x] 4.10 Remove `handleCorrectUsingAI` destructure + prop passing in `movie.jsx` (lines 55, 75)

- [x] **Task 5: Verify `ai_ask()` function is preserved** (AC: #5)
  - [x] 5.1 Confirm `ai_ask()` in `backend/library/ai.py` (lines 39-94) is untouched
  - [x] 5.2 Confirm `from library.ai import ai_ask` in `backend/library/youtube_processing.py` (line 13) works
  - [x] 5.3 Run unit tests: `pytest backend/tests/unit/` — 16 passed, 6 pre-existing failures (no regressions)

- [x] **Task 6: Update documentation** (AC: #6)
  - [x] 6.1 Remove `/ai_ask` entry from `docs/api-contracts-backend.md` (lines 121-126)
  - [x] 6.2 Update `docs/architecture-backend.md` — remove `/ai_ask` references
  - [x] 6.3 Update `docs/architecture-web_interface_react.md` — remove `handleCorrectUsingAI` references
  - [x] 6.4 Update `docs/component-inventory-web_interface_react.md` — remove references
  - [x] 6.5 Update `backend/CLAUDE.md` — decrement endpoint count (19→18), remove `/ai_ask` from endpoint list
  - [x] 6.6 Update `infra/aws/serverless/CLAUDE.md` — remove `/ai_ask` from Lambda endpoint mapping
  - [x] 6.7 (additional) Update root `CLAUDE.md`, `web_interface_react/CLAUDE.md`, `README.md`, `docs/index.md`, `docs/project-overview.md`, `docs/source-tree-analysis.md`, `docs/project-parts.json` — 13 files total

## Dev Notes

### Technical Requirements

**CRITICAL SAFETY CONSTRAINT — `ai_ask()` function preservation:**
- The `/ai_ask` **endpoint** (HTTP route) is being removed, but the underlying `ai_ask()` **function** in `backend/library/ai.py` MUST remain intact
- `ai_ask()` is called by `backend/imports/youtube_processing.py` at line 290 for AI summary generation of YouTube documents
- `ai_ask()` is also used by 4 test scripts in `backend/test_code/` (non-critical but still functional)
- The function supports 6+ LLM models across 4 providers (OpenAI, AWS Bedrock, CloudFerro Bielik, Google Vertex AI)
- **Verification:** After removal, confirm `from library.ai import ai_ask` still works and `youtube_processing.py` can call it

**Endpoint removal scope:**
- Flask backend: `server.py` route `/ai_ask` (POST) — the route function is named `ai_ask()` which shadows the library function name locally. Removing the route removes only the Flask wrapper, not the library function
- Lambda: `app-server-internet/lambda_function.py` handler block — note this Lambda **ignores** the `model` parameter from request and always uses `llm_simple_jobs_model` environment variable (differs from Flask implementation)
- API Gateway: `api-gw-app.yaml` path `/ai_ask` with POST method + OPTIONS CORS preflight — both must be removed
- Frontend: `handleCorrectUsingAI()` function + "Correct using AI" button across 3 page types (webpage, youtube, movie)

**Lambda `import library.ai` must be retained:**
- The Lambda `app-server-internet` still needs `import library.ai` because `/ai_embedding_get` endpoint uses `library.ai` functions
- Only the `/ai_ask` handler block (lines 181-234) is removed, not the import

**Frontend constant cleanup:**
- `ai_correct_query` (Polish prompt for punctuation correction) — used ONLY by `handleCorrectUsingAI` — safe to remove
- `llm_simple_jobs_model_name` (`"gpt-4o-2024-05-13"`) — used ONLY by `handleCorrectUsingAI` — safe to remove
- Both defined in `web_interface_react/src/modules/shared/constants/variables.js`

### Architecture Compliance

**Resource Deletion Checklist (from Epic 7/8 retro — MANDATORY):**
Before removing any resource, verify:
1. **Code references checked** — grep entire codebase for `ai_ask` as endpoint path (not function name)
2. **Active state verified** — the `/ai_ask` endpoint is active in AWS API Gateway but confirmed unused by end users
3. **Dependency chain reviewed** — `ai_ask()` function has downstream callers (`youtube_processing.py`), but the HTTP endpoint does not

**API Gateway template (`api-gw-app.yaml`) modification rules:**
- Template currently at ~51164 bytes (under 51200 byte inline limit) — removing `/ai_ask` will further reduce size
- After removal, `aws cloudformation deploy --template-file` workflow still applies (no S3 packaging needed)
- The template uses OpenAPI 3.0 inline Body definition — the `/ai_ask` path block is self-contained within the `paths:` section
- CORS OPTIONS mock integration for `/ai_ask` must also be removed (not just the POST method)

**Semantic review requirement (from Epic 8/9 retro):**
- After code changes, verify numeric counts in documentation match reality (e.g., "19 endpoints" in CLAUDE.md must be decremented)
- Verify no orphaned references to `handleCorrectUsingAI` in any JSX files
- Verify `api-gw-app.yaml` path count matches what is documented

**CloudFormation validation:**
- Run cfn-lint on modified `api-gw-app.yaml` before committing
- The template must continue to pass `aws cloudformation validate-template` after `/ai_ask` path removal

### Library & Framework Requirements

**No new libraries or dependencies required.** This story is purely removal/deletion of existing code.

**Libraries/frameworks affected (existing — no version changes):**

| Component | Framework | Impact |
|-----------|-----------|--------|
| `backend/server.py` | Flask (Python) | Remove one `@app.route` decorated function — no Flask configuration changes |
| `lambda_function.py` | AWS Lambda (Python) | Remove one `if event['path']` handler block — no Lambda runtime changes |
| `api-gw-app.yaml` | CloudFormation (YAML) | Remove path from OpenAPI 3.0 inline Body — no template format changes |
| `useManageLLM.js` | React 18 + axios | Remove one async function + axios.post call — no dependency changes |
| `InputsForAllExceptLink.jsx` | React 18 | Remove one `<button>` element — no component API changes |
| `variables.js` | JavaScript (constants) | Remove 2 exported constants — no module system changes |

**Dependencies NOT to remove:**
- `axios` — still used by many other API calls in the frontend
- `library.ai` import in both `server.py` and `lambda_function.py` — still used by other endpoints
- `library.api.openai`, `library.api.aws.bedrock_ask`, etc. — still used by `ai_ask()` function (preserved)
- `formik` — still used by all page components for form state management

### File Structure Requirements

**Files to MODIFY (10 files):**

```
backend/
├── server.py                                              [MOD] Remove /ai_ask route (lines 539-594)

infra/aws/
├── serverless/lambdas/app-server-internet/
│   └── lambda_function.py                                 [MOD] Remove /ai_ask handler (lines 181-234)
├── cloudformation/templates/
│   └── api-gw-app.yaml                                   [MOD] Remove /ai_ask path definition (lines 563-613)

web_interface_react/src/modules/shared/
├── hooks/
│   └── useManageLLM.js                                    [MOD] Remove handleCorrectUsingAI + imports + export
├── constants/
│   └── variables.js                                       [MOD] Remove ai_correct_query + llm_simple_jobs_model_name
├── components/SharedInputs/
│   └── InputsForAllExceptLink.jsx                         [MOD] Remove "Correct using AI" button + prop
├── pages/
│   ├── webpage.jsx                                        [MOD] Remove handleCorrectUsingAI destructure + prop
│   ├── youtube.jsx                                        [MOD] Remove handleCorrectUsingAI destructure + prop
│   └── movie.jsx                                          [MOD] Remove handleCorrectUsingAI destructure + prop

docs/
├── api-contracts-backend.md                               [MOD] Remove /ai_ask endpoint entry
```

**Files to UPDATE (documentation — 5 files):**

```
docs/
├── architecture-backend.md                                [MOD] Remove /ai_ask references
├── architecture-web_interface_react.md                    [MOD] Remove handleCorrectUsingAI references
├── component-inventory-web_interface_react.md             [MOD] Remove references
backend/
├── CLAUDE.md                                              [MOD] Decrement endpoint count, remove /ai_ask
infra/aws/serverless/
├── CLAUDE.md                                              [MOD] Remove /ai_ask from endpoint mapping
```

**Files to NOT TOUCH (critical preservation):**

```
backend/library/ai.py                                      [NO CHANGE] ai_ask() function MUST remain
backend/imports/youtube_processing.py                      [NO CHANGE] Calls ai_ask() — must keep working
backend/library/models/ai_response.py                      [NO CHANGE] AiResponse class used by ai_ask()
backend/test_code/webdocument_bielik_*.py                  [NO CHANGE] Test scripts using ai_ask()
backend/test_code/embeddings_search.py                     [NO CHANGE] Test script using ai_ask()
```

**No files created or deleted.** All changes are modifications to existing files (code removal + documentation updates).

### Testing Requirements

**Automated tests:**
- Run `pytest backend/tests/` — all existing unit and integration tests must pass
- No new test files required (this is code removal, not feature addition)

**Manual verification checklist:**

1. **Backend import verification:**
   - `python -c "from backend.library.ai import ai_ask; print('OK')"` — confirms `ai_ask()` function is importable
   - `python -c "from backend.imports.youtube_processing import process_youtube_url; print('OK')"` — confirms youtube processing chain works

2. **CloudFormation template validation:**
   - `cfn-lint infra/aws/cloudformation/templates/api-gw-app.yaml` — must pass with zero errors
   - `aws cloudformation validate-template --template-body file://infra/aws/cloudformation/templates/api-gw-app.yaml` — must succeed

3. **Frontend build verification:**
   - `cd web_interface_react && npm run build` — must complete without errors
   - Verify no warnings about missing imports or undefined references to `handleCorrectUsingAI`

4. **Codebase-wide grep verification:**
   - `grep -r "ai_ask" --include="*.py" --include="*.js" --include="*.jsx" --include="*.yaml" --include="*.md"` — review results:
     - `backend/library/ai.py` — EXPECTED (function definition preserved)
     - `backend/imports/youtube_processing.py` — EXPECTED (function caller)
     - `backend/test_code/*.py` — EXPECTED (test scripts)
     - Any other hits — INVESTIGATE (potential stale reference)
   - `grep -r "handleCorrectUsingAI"` — must return ZERO results
   - `grep -r "ai_correct_query"` — must return ZERO results
   - `grep -r "llm_simple_jobs_model_name"` — must return ZERO results

5. **Semantic review:**
   - Count endpoints in `api-gw-app.yaml` paths section — verify documentation matches
   - Check CLAUDE.md endpoint count statement matches actual count

### Git Intelligence

**Recent commit patterns (last 10 commits):**

| Commit | Description | Relevance |
|--------|-------------|-----------|
| `eae71f0` | docs: complete Sprint 2 — cleanup, vision, documentation | HIGH — documentation update pattern to follow |
| `b08d197` | chore: replace pytube with pytubefix | LOW — dependency change |
| `9603466` | docs: add manual execution steps for SQS Step Function | LOW — docs pattern |
| `1bb77be` | chore: update Step Function schedule/timezone | LOW — CF template change |
| `9170a90` | docs: add implementation readiness report | LOW — sprint planning |
| `8e4b38e` | chore: remove unused AWS resources, configs, dependencies | HIGH — removal pattern to follow |
| `a25bf06` | feat: add CF templates for DynamoDB cache + S3 | MEDIUM — CF template creation pattern |

**Key patterns from recent work:**
- **Commit message convention:** `type: description` format (docs, chore, feat)
- **Removal pattern (from `8e4b38e`):** Previous Sprint 1-2 established the pattern for removing unused resources — verify references first, then remove code, then update documentation
- **Documentation update pattern (from `eae71f0`):** Documentation is updated in the same commit as the code change, not separately
- **Recommended commit message for this story:** `chore: remove /ai_ask endpoint from backend, Lambda, API Gateway, and frontend`

### Project Structure Notes

- All modifications align with unified project structure — no new paths, modules, or naming introduced
- Frontend follows existing modular pattern: `modules/shared/hooks/`, `modules/shared/components/`, `modules/shared/pages/`
- CloudFormation template remains in existing location: `infra/aws/cloudformation/templates/api-gw-app.yaml`
- No conflicts or variances detected with existing conventions

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Epic 10, Story 10.1] — Story definition, acceptance criteria, BDD scenarios
- [Source: _bmad-output/planning-artifacts/prd.md#Endpoint Removal — /ai_ask] — FR1-FR5 requirements
- [Source: _bmad-output/planning-artifacts/prd.md#Risk Mitigation] — Accidental removal of ai_ask() function risk
- [Source: _bmad-output/planning-artifacts/architecture.md#Implementation Patterns] — Resource Deletion Checklist, CF validation rules
- [Source: _bmad-output/planning-artifacts/architecture.md#Enforcement Guidelines] — AI Agent MUST rules for CF templates
- [Source: backend/server.py:539-594] — Flask `/ai_ask` route definition
- [Source: backend/library/ai.py:39-94] — `ai_ask()` function (PRESERVE)
- [Source: backend/imports/youtube_processing.py:13,290] — `ai_ask()` caller (PRESERVE)
- [Source: infra/aws/serverless/lambdas/app-server-internet/lambda_function.py:181-234] — Lambda handler
- [Source: infra/aws/cloudformation/templates/api-gw-app.yaml:563-613] — API GW path definition
- [Source: web_interface_react/src/modules/shared/hooks/useManageLLM.js:452-489,601] — Frontend hook function + export
- [Source: web_interface_react/src/modules/shared/components/SharedInputs/InputsForAllExceptLink.jsx:7,42-48] — UI button
- [Source: web_interface_react/src/modules/shared/constants/variables.js:2-4] — Constants to remove
- [Source: web_interface_react/src/modules/shared/pages/webpage.jsx:56,77] — Page component reference
- [Source: web_interface_react/src/modules/shared/pages/youtube.jsx:55,75] — Page component reference
- [Source: web_interface_react/src/modules/shared/pages/movie.jsx:55,75] — Page component reference
- [Source: docs/api-contracts-backend.md:121-126] — API documentation entry
- [Source: docs/architecture-backend.md] — Backend architecture references
- [Source: docs/architecture-web_interface_react.md] — Frontend architecture references
- [Source: docs/component-inventory-web_interface_react.md] — Component inventory references

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6 (claude-opus-4-6)

### Debug Log References

- No debug issues encountered during implementation

### Implementation Plan

- Removed `/ai_ask` HTTP endpoint from Flask backend, Lambda handler, and API Gateway CloudFormation template
- Removed frontend `handleCorrectUsingAI` function, "Correct using AI" button, and associated constants
- Preserved `ai_ask()` library function in `backend/library/ai.py` (used by `youtube_processing.py`)
- Cleaned up unused imports: `import library.ai` in server.py, `import library.ai` and `llm_simple_jobs_model` in Lambda
- Updated 13 documentation files (endpoint counts 19→18, removed all `/ai_ask` references)
- cfn-lint validation passed on modified API Gateway template

### Completion Notes List

- Ultimate context engine analysis completed — comprehensive developer guide created
- Story created on 2026-02-16 by BMad create-story workflow
- 15 source files analyzed across backend, Lambda, CloudFormation, frontend, and documentation
- 7 acceptance criteria defined with specific file locations and line numbers
- 6 tasks with 27 subtasks mapped to acceptance criteria
- CRITICAL safety constraint documented: ai_ask() function in library/ai.py MUST be preserved
- Implementation completed on 2026-02-16 by Claude Opus 4.6
- All 6 tasks / 27 subtasks completed successfully
- ai_ask() function verified preserved and importable by youtube_processing.py
- Unit tests: 16 passed, 6 pre-existing failures (no regressions introduced)
- Codebase grep: zero stale references in source code; only planning artifacts retain historical references
- Additional cleanup: removed unused `import library.ai` from server.py and Lambda, removed unused `llm_simple_jobs_model` from Lambda
- Code review completed on 2026-02-16 by Claude Opus 4.6 — 6 issues found (1 HIGH, 3 MEDIUM, 2 LOW), all 6 fixed

### File List

**Modified (code — 10 files):**
- backend/server.py — removed `/ai_ask` route and unused `import library.ai`
- infra/aws/serverless/lambdas/app-server-internet/lambda_function.py — removed `/ai_ask` handler, unused `import library.ai`, unused `llm_simple_jobs_model`; [review fix] removed unused `backend_type` variable and commented-out dead code; [review fix] refactored `if` chains to `if/elif/else` for path routing
- infra/aws/cloudformation/templates/api-gw-app.yaml — removed `/ai_ask` path block (POST + OPTIONS)
- web_interface_react/src/modules/shared/hooks/useManageLLM.js — removed `handleCorrectUsingAI`, imports, export
- web_interface_react/src/modules/shared/constants/variables.js — removed `ai_correct_query`, `llm_simple_jobs_model_name`
- web_interface_react/src/modules/shared/components/SharedInputs/InputsForAllExceptLink.jsx — removed button and prop
- web_interface_react/src/modules/shared/pages/webpage.jsx — removed destructure and prop; [review fix] corrected document_type initialValue "youtube"→"webpage"
- web_interface_react/src/modules/shared/pages/youtube.jsx — removed destructure and prop; [review fix] added missing `handleRemoveNotNeededText` prop
- web_interface_react/src/modules/shared/pages/movie.jsx — removed destructure and prop; [review fix] added missing `handleRemoveNotNeededText` prop

**Modified (documentation — 13 files):**
- docs/api-contracts-backend.md — removed `/ai_ask` section, updated counts; [review fix] removed phantom `/website_exist` endpoint; [review fix] corrected endpoint count to 19 (matching actual routes)
- docs/architecture-backend.md — removed endpoint reference, updated counts
- docs/architecture-web_interface_react.md — removed `handleCorrectUsingAI` reference
- docs/component-inventory-web_interface_react.md — removed references
- docs/source-tree-analysis.md — updated endpoint counts
- docs/project-overview.md — updated endpoint counts
- docs/project-parts.json — updated endpoint count
- docs/index.md — updated endpoint counts
- backend/CLAUDE.md — updated endpoint count (19→18), removed `/ai_ask`; [review fix] removed phantom `/website_exist` from Metadata row
- infra/aws/serverless/CLAUDE.md — removed `/ai_ask` from endpoint mapping
- web_interface_react/CLAUDE.md — removed `/ai_ask` references
- CLAUDE.md (root) — updated endpoint count, removed references
- README.md — updated endpoint count

**Not modified (preserved — verified intact):**
- backend/library/ai.py — `ai_ask()` function preserved
- backend/library/youtube_processing.py — `from library.ai import ai_ask` preserved

## Change Log

- 2026-02-16: Removed `/ai_ask` endpoint from backend (Flask), Lambda (app-server-internet), API Gateway (CloudFormation template), and frontend (React). Removed associated constants and UI button. Updated 13 documentation files. Preserved `ai_ask()` library function for internal use.
- 2026-02-16: [Code Review] Fixed 6 issues: (1) webpage.jsx document_type "youtube"→"webpage", (2) removed phantom `/website_exist` from docs, (3) added missing `handleRemoveNotNeededText` prop to youtube.jsx/movie.jsx, (4) removed unused `backend_type` + dead code from Lambda, (5) refactored Lambda `if` chains to `if/elif/else`, (6) corrected api-contracts endpoint count to 19.
