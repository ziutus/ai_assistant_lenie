# Story 11.5: REST Compliance Review for `/website_delete`

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **developer**,
I want to review the `/website_delete` GET method and document a REST-compliant alternative,
so that a decision is made and documented for future reference.

## Acceptance Criteria

1. **AC1 — Current implementation documented:** A review document is created that describes the current `/website_delete` implementation across all layers: API Gateway (GET + POST defined in `api-gw-app.yaml:190-260`), Flask backend (`server.py:610`, GET only), Lambda handler (`lambda_function.py:221`, path-based routing), and frontend (`useManageLLM.js`, two `axios.get()` calls: `handleDeleteDocument` and `handleDeleteDocumentNext`).

2. **AC2 — REST-compliant alternative documented:** The review document describes a REST-compliant alternative using HTTP DELETE method, including: (a) API Gateway template change (replace `get:` with `delete:` on `/website_delete` path), (b) Flask route change (`methods=['DELETE']`), (c) Lambda handler change (if any — currently path-based, method-agnostic), (d) frontend change (`axios.get()` → `axios.delete()`), (e) integration test change (`self.app.get()` → `self.app.delete()`).

3. **AC3 — Frontend impact analysis complete:** The review document quantifies the frontend change scope: exactly 2 function calls in `useManageLLM.js` (`handleDeleteDocument` at line ~477, `handleDeleteDocumentNext` at line ~413) need `axios.get` changed to `axios.delete`. No other frontend files reference `/website_delete`.

4. **AC4 — Decision documented with rationale:** A decision is recorded (implement now, defer to future sprint, or reject) with clear rationale based on: (a) change scope (number of files and lines affected), (b) risk assessment (breaking change for any callers), (c) benefit (REST compliance, API safety — prevents accidental deletion via browser URL bar or link prefetch), (d) alignment with project priorities.

5. **AC5 — No code changes if decision is "defer" or "reject":** If the decision is not "implement now", the current GET method continues to function unchanged. The review document is the only deliverable.

## Tasks / Subtasks

- [x] **Task 1: Document current `/website_delete` implementation** (AC: #1)
  - [x] 1.1 Document API Gateway definition: GET + POST methods in `api-gw-app.yaml:190-260`, both route to `lenie_2_db` Lambda
  - [x] 1.2 Document Flask route: `server.py:610` — `methods=['GET']`, ID from `request.args.get('id')`
  - [x] 1.3 Document Lambda handler: `lambda_function.py:221` — path-based routing, ID from `queryStringParameters['id']`
  - [x] 1.4 Document frontend calls: `useManageLLM.js` — two `axios.get()` calls passing `id` as query param
  - [x] 1.5 Document integration test: `test_website_crud.py:62` — `self.app.get(f"/website_delete?id={id}")`

- [x] **Task 2: Design REST-compliant alternative** (AC: #2)
  - [x] 2.1 Define API Gateway change: replace `get:` with `delete:` method on `/website_delete` path (keep CORS `options:`)
  - [x] 2.2 Define Flask route change: `methods=['DELETE']` instead of `methods=['GET']`
  - [x] 2.3 Evaluate Lambda handler impact: path-based routing is method-agnostic — no Lambda code change needed
  - [x] 2.4 Define frontend change: `axios.get()` → `axios.delete()` in both functions
  - [x] 2.5 Define test change: `self.app.get()` → `self.app.delete()` in integration test
  - [x] 2.6 Consider alternative: rename path from `/website_delete` to `/website/{id}` with DELETE method (full REST) vs. minimal change (keep path, change method only)

- [x] **Task 3: Perform frontend impact analysis** (AC: #3)
  - [x] 3.1 Confirm exactly 2 call sites in `useManageLLM.js` (no other files)
  - [x] 3.2 Verify Chrome extension does not call `/website_delete`
  - [x] 3.3 Assess backward compatibility: callers that still use GET after migration would get 405 Method Not Allowed

- [x] **Task 4: Make and document decision** (AC: #4, #5)
  - [x] 4.1 Evaluate change scope: ~6 files, ~10 lines changed
  - [x] 4.2 Evaluate risk: low (single developer, no external API consumers, all callers identified)
  - [x] 4.3 Evaluate benefit: REST compliance, prevents accidental deletion via browser URL/link prefetch
  - [x] 4.4 Record decision with rationale in the story file
  - [x] 4.5 If "implement now" — create follow-up implementation tasks; if "defer"/"reject" — document why

## Dev Notes

### The Situation

This is a **documentation and decision story** — not a code change story. The primary deliverable is a review document analyzing the REST compliance of the `/website_delete` endpoint and recording a decision about whether to change the HTTP method from GET to DELETE.

The `/website_delete` endpoint currently uses HTTP GET for a destructive operation (deleting a document from the database). This violates REST conventions where GET should be safe and idempotent (no side effects). The REST-standard approach is to use the HTTP DELETE method for resource deletion.

**Why this matters:**
- **Browser link prefetch:** Some browsers pre-fetch GET URLs found on a page — a prefetched `/website_delete?id=123` link would silently delete the document
- **Crawler safety:** Web crawlers follow GET links by default; DELETE endpoints are never followed
- **API contract clarity:** GET implies "read", DELETE implies "destroy" — using GET for deletion confuses API consumers
- **Caching:** HTTP proxies and CDNs may cache GET responses; a cached delete response would be incorrect

### Scope: Documentation-Only (Unless Decision is "Implement Now")

**Expected code changes: 0 files** (review/decision document only).

If the decision is "implement now", the actual code changes would be a **separate follow-up story** (not this story) touching:

| File | Change | Lines |
|------|--------|-------|
| `api-gw-app.yaml:191` | `get:` → `delete:` | ~1 line |
| `api-gw-app.yaml:211-230` | Remove redundant `post:` block | ~20 lines removed |
| `server.py:610` | `methods=['GET']` → `methods=['DELETE']` | 1 line |
| `lambda_function.py` | No change needed (path-based routing, method-agnostic) | 0 lines |
| `useManageLLM.js:413` | `axios.get(` → `axios.delete(` | 1 line |
| `useManageLLM.js:477` | `axios.get(` → `axios.delete(` | 1 line |
| `test_website_crud.py:62` | `self.app.get(` → `self.app.delete(` | 1 line |
| `api-contracts-backend.md:57` | `GET /website_delete` → `DELETE /website_delete` | 1 line |
| `apigw/lenie-split-export.json:63-97` | Re-export from API Gateway after method change (exported OpenAPI definition) | N/A (re-export) |
| `docs/architecture-backend.md:114` | Update `website_delete` reference in Document CRUD endpoint list | 1 line |
| `docs/component-inventory-web_interface_react.md:70` | Update `/website_delete` reference in `useManageLLM` hook description | 1 line |
| `web_interface_react/CLAUDE.md:113` | `GET /website_delete` → `DELETE /website_delete` in endpoint table | 1 line |
| `backend/tests/CLAUDE.md:83` | `GET /website_delete` → `DELETE /website_delete` in test table | 1 line |
| `infra/aws/serverless/CLAUDE.md:184` | `/website_delete (GET)` → `/website_delete (DELETE)` in comparison table | 1 line |
| `infra/aws/README.md:254,520` | Update `GET` → `DELETE` method for `/website_delete` (2 references) | 2 lines |

**Total if implemented:** ~12 files, ~13 lines changed, ~20 lines removed, 1 file re-exported.

### Current Implementation Deep Dive

**API Gateway (`api-gw-app.yaml:190-260`):**
- Defines both `get:` and `post:` methods on `/website_delete` path
- Both methods route to `lenie_2_db` Lambda via `aws_proxy` integration
- CORS `options:` method also defined
- The `post:` method is never called by any frontend code — it's dead config

**Flask Backend (`server.py:610-639`):**
```python
@app.route('/website_delete', methods=['GET'])
def website_delete():
    link_id = int(request.args.get('id'))
    # ... delete logic ...
```
- Accepts only GET
- ID passed as query parameter `?id=<int>`
- Returns `{status, message, encoding}` JSON

**Lambda Handler (`lambda_function.py:221-246`):**
- Path-based routing: `if event['path'] == '/website_delete':`
- Extracts ID from `event['queryStringParameters']['id']`
- Does NOT convert to int (unlike Flask) — **pre-existing technical debt**: a non-numeric `id` parameter would bypass the Lambda's type check and may cause unexpected behavior deeper in `StalkerWebDocumentDB`. This should be addressed in the follow-up implementation story or tracked as a separate bug fix.
- Method-agnostic: does not check `event['httpMethod']`

**Frontend (`useManageLLM.js`):**
- `handleDeleteDocumentNext` (line ~413): `axios.get(apiUrl + '/website_delete', {params: {id: website.id}})`
- `handleDeleteDocument` (line ~477): `axios.get(apiUrl + '/website_delete', {params: {id: website_id}})`
- Both use `x-api-key` header for auth

**Integration Test (`test_website_crud.py:62`):**
- `self.app.get(f"/website_delete?id={example_data['id']}")`

**Exported API Gateway Definition (`apigw/lenie-split-export.json:63-97`):**
- Exported OpenAPI definition also references `/website_delete` with `get`, `post`, and `options` methods
- This is a console-exported reference copy, not a CloudFormation input — would need re-exporting after any method change

**Chrome Extension (`web_chrome_extension/`):**
- Does NOT call `/website_delete` — only uses `POST /url_add`

### Two Migration Approaches

**Approach A — Minimal Change (change method only):**
- Keep path as `/website_delete`
- Change HTTP method from GET to DELETE
- Pros: smallest change, lowest risk
- Cons: path still contains the verb "delete" (non-RESTful URL design)

**Approach B — Full REST (change path and method):**
- Change path from `/website_delete?id=X` to `/website/{id}` with DELETE method
- Pros: fully REST-compliant URL design
- Cons: much larger change scope — API Gateway path parameter routing, Lambda path extraction, Flask route with `<int:id>`, frontend URL construction, documentation updates. Would affect all layers significantly.

**Recommendation for review:** Approach A (minimal change) if implementing, because Approach B is a much larger refactor that touches the entire API surface design and is better suited for a future "API redesign" initiative.

### Architecture Compliance

**Gen 2+ canonical template pattern:** Not directly applicable — this story makes no CloudFormation template changes. If the decision is "implement now", the follow-up implementation story would modify `api-gw-app.yaml` within the existing OpenAPI Body definition (changing `get:` to `delete:` at line 191). This is a method-level change within the existing template structure, not a structural template change.

**REST conventions (industry standard):**
- GET: Safe, idempotent, cacheable — retrieves a resource without side effects
- POST: Not idempotent — creates a resource or triggers processing
- PUT: Idempotent — replaces a resource entirely
- PATCH: Not necessarily idempotent — partially updates a resource
- DELETE: Idempotent — removes a resource

Current `/website_delete` using GET violates the safety guarantee of GET.

**Project API patterns:**
The project's API does not follow strict REST resource naming — endpoints use action-based paths (`/website_list`, `/website_get`, `/website_save`, `/website_delete`) rather than resource-based paths (`/websites`, `/websites/{id}`). This is a project-wide pattern, not specific to this endpoint. Changing only the HTTP method (Approach A) is consistent with the project's current naming convention.

**cfn-lint validation:** If `api-gw-app.yaml` is modified in a follow-up story, cfn-lint must pass with zero errors before committing (NFR6).

### Technical Requirements

**This story requires NO technical tools or commands.** It is a review and documentation task.

**If the decision leads to a follow-up implementation story, that story would need:**

Verification commands:
```bash
# After changing method to DELETE — verify API Gateway template
cfn-lint infra/aws/cloudformation/templates/api-gw-app.yaml

# After Flask route change — verify endpoint responds to DELETE
curl -X DELETE "http://localhost:5000/website_delete?id=1" -H "x-api-key: <key>"

# Verify GET returns 405 Method Not Allowed
curl -X GET "http://localhost:5000/website_delete?id=1" -H "x-api-key: <key>"
# Expected: 405

# Run integration tests
cd backend && PYTHONPATH=. uvx pytest tests/integration/test_website_crud.py -v
```

### Library / Framework Requirements

No libraries or dependencies involved. This is a documentation-only story.

If the follow-up implementation story is created:
- `axios` already supports `axios.delete()` — no new dependencies
- Flask already supports `methods=['DELETE']` — no new dependencies
- API Gateway OpenAPI spec supports `delete:` method — no extensions needed

### File Structure Requirements

**Files to CREATE (1 file — the review content is embedded in this story file):**
```
_bmad-output/implementation-artifacts/
└── 11-5-rest-compliance-review-for-website-delete.md   [THIS FILE] Review document with decision
```

**Files NOT to touch:**
```
infra/aws/cloudformation/templates/api-gw-app.yaml       [NO CHANGE] Review only — no template edits
backend/server.py                                         [NO CHANGE] Review only — no route edits
infra/aws/serverless/lambdas/app-server-db/lambda_function.py  [NO CHANGE]
web_interface_react/src/modules/shared/hooks/useManageLLM.js   [NO CHANGE]
backend/tests/integration/test_website_crud.py            [NO CHANGE]
```

### Testing Requirements

**No automated tests needed.** This is a documentation story — the deliverable is the review document and decision, not code.

**Verification checklist:**
1. Review document covers all 4 layers (API GW, Flask, Lambda, frontend)
2. REST-compliant alternative is described with specific file:line references
3. Frontend impact analysis quantifies exactly 2 call sites
4. Decision is recorded with rationale
5. If decision is "defer"/"reject" — zero code changes made

### Previous Story Intelligence

**From Story 11.4 (done) — Resolve Lambda Function Name Typo:**
- Verification-only story pattern — similar to this story (review + document, minimal code changes)
- Demonstrates that "documentation stories" are valid deliverables in the project
- Code review found 4 issues (0 HIGH, 1 MEDIUM, 3 LOW) — all related to documentation accuracy, not code
- Sprint status transition: `backlog → review` (not `ready-for-dev → in-progress → review`)
- Key learning: be precise about status transitions in File List section

**From Story 11.3 (done) — Fix ApiDeployment Pattern:**
- `api-gw-app.yaml` was significantly restructured: `ApiStage` separated from `ApiDeployment` for proper redeployment support
- Auto-redeployment hook added to `deploy.sh` (creates new API Gateway deployment after stack update)
- cfn-lint v1.44.0 used for validation, zero errors
- Commit prefix: `chore:` for infrastructure maintenance
- The current `api-gw-app.yaml` structure (as of commit `7f82301`) is the baseline for this review

**From Story 10.3 (done) — Remove `/infra/ip-allow` Endpoint:**
- Demonstrated the pattern of removing an endpoint from `api-gw-app.yaml` — the `get:`, `post:`, and `options:` blocks were all removed together
- Resource Deletion Checklist followed: (1) code references checked, (2) active state verified, (3) dependency chain reviewed
- Same checklist methodology applies to this review (checking all callers before recommending a method change)

**Key insight for this story:** The project has established a pattern of thorough cross-layer analysis before making API Gateway changes. This story follows that same pattern — analyze all layers first, then decide.

### Git Intelligence

**Recent commits (last 5):**
```
7f82301 chore: complete stories 10-3 and 11-3 with code review fixes
4e790af chore: add __pycache__/ to .gitignore
4a11307 chore: replace resolve:ssm with SSM Parameter types and parameterize Lambda name in step function
21391f3 docs: update story 11.1 with code review round 2 results and cfn-lint verification
2005495 chore: parameterize hardcoded values in sqs-application-errors, budget, and secrets templates
```

**Relevant observations:**
- All recent commits use `chore:` or `docs:` prefix — consistent with infrastructure maintenance work
- `api-gw-app.yaml` was last modified in commit `7f82301` (Story 10.3/11.3 code review fixes)
- No code changes expected from this story, so no new commit unless `sprint-status.yaml` is updated

### Project Structure Notes

- This story is documentation-only — no new files, no structural changes
- The review content is embedded in this story file (no separate review document needed)
- Aligns with Epic 11's goal of "documented REST compliance decisions" (FR27, FR28, FR29)
- The decision outcome (implement/defer/reject) will be referenced by Story 12.2 (CloudFormation Validation and Documentation Update) which requires "all decisions documented with rationale"

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 11.5] — Story definition with acceptance criteria (FR27, FR28, FR29)
- [Source: infra/aws/cloudformation/templates/api-gw-app.yaml:190-260] — Current `/website_delete` endpoint definition (GET + POST + OPTIONS)
- [Source: backend/server.py:610-639] — Flask route definition (`methods=['GET']`)
- [Source: infra/aws/serverless/lambdas/app-server-db/lambda_function.py:221-246] — Lambda handler (path-based routing)
- [Source: web_interface_react/src/modules/shared/hooks/useManageLLM.js:409-506] — Frontend `axios.get()` calls (2 functions)
- [Source: backend/tests/integration/test_website_crud.py:62] — Integration test using `self.app.get()`
- [Source: docs/api-contracts-backend.md:57-60] — API documentation listing `GET /website_delete`
- [Source: infra/aws/cloudformation/apigw/lenie-split-export.json:63-97] — Exported API Gateway OpenAPI definition (`get`, `post`, `options` on `/website_delete`)
- [Source: docs/architecture-backend.md:114] — Backend architecture doc referencing `website_delete` in Document CRUD list
- [Source: docs/component-inventory-web_interface_react.md:70] — Frontend component inventory referencing `/website_delete` in `useManageLLM` hook
- [Source: _bmad-output/planning-artifacts/architecture.md#Implementation Patterns] — Enforcement guidelines, cfn-lint validation requirement
- [Source: _bmad-output/implementation-artifacts/11-4-resolve-lambda-function-name-typo.md] — Previous story pattern (verification/documentation story)

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6 (claude-opus-4-6)

### Debug Log References

- API Gateway template verified: `api-gw-app.yaml:190-260` — `get:` (line 191), `post:` (line 211), `options:` (line 231) on `/website_delete` path
- Flask route verified: `server.py:610` — `@app.route('/website_delete', methods=['GET'])`
- Lambda handler verified: `lambda_function.py:221` — path-based routing, method-agnostic
- Frontend verified: `useManageLLM.js:413-414` (`handleDeleteDocumentNext`) and `useManageLLM.js:477-478` (`handleDeleteDocument`) — both `axios.get()`
- Integration test verified: `test_website_crud.py:62` — `self.app.get(f"/website_delete?id={example_data['id']}")`
- Chrome extension verified: `grep -r "website_delete" web_chrome_extension/` — zero matches
- CORS `Access-Control-Allow-Methods` already includes `DELETE` in the allowed list (line 255)
- Exported API GW definition verified: `apigw/lenie-split-export.json:63-97` — `get`, `post`, `options` on `/website_delete`
- Documentation files verified: `architecture-backend.md:114`, `component-inventory-web_interface_react.md:70` — both reference `website_delete`
- Lambda int conversion gap classified as pre-existing technical debt (lambda_function.py:227)

### Decision Record

**Decision: DEFER to future sprint**

**Rationale:**

1. **Change scope (small):** ~8 files, ~8 lines changed, ~20 lines removed (dead `post:` block), 1 file re-exported. The change itself is straightforward — Approach A (change HTTP method only, keep path) is the recommended approach.

2. **Risk (low):** Single developer project, zero external API consumers, all callers identified (2 frontend functions, 1 integration test, 1 Flask route, 1 Lambda handler, 1 API GW definition). The API requires `x-api-key` authentication, which mitigates the browser prefetch and crawler risks significantly.

3. **Benefit (real but not urgent):**
   - REST compliance improves API contract clarity
   - Prevents theoretical browser prefetch deletion (mitigated by API key requirement)
   - Removes dead `post:` config from API Gateway
   - However: no external consumers means the compliance benefit is primarily for code quality, not API safety

4. **Alignment with project priorities (not aligned with Sprint 3):** Sprint 3 focuses on CloudFormation template improvements and code cleanup. Changing the HTTP method is an application-level change that crosses backend, frontend, Lambda, and API Gateway layers — better suited for a future "API Quality Improvements" sprint.

5. **Recommended future sprint placement:** When the project undertakes API design improvements (potentially alongside Story B.3: Rename Legacy Lambda Functions), the DELETE method change can be bundled with other API cleanup work for a coordinated deployment.

6. **Follow-up scope reminder:** The follow-up implementation story should explicitly include these as separate tasks: (a) change GET→DELETE, (b) remove the dead `post:` block at `api-gw-app.yaml:211-230`, (c) add `int()` conversion for `id` parameter in Lambda handler at `lambda_function.py:227`, (d) re-export `apigw/lenie-split-export.json` after API Gateway changes, (e) update 7 documentation files (`api-contracts-backend.md`, `architecture-backend.md`, `component-inventory-web_interface_react.md`, `web_interface_react/CLAUDE.md`, `backend/tests/CLAUDE.md`, `infra/aws/serverless/CLAUDE.md`, `infra/aws/README.md`), (f) return 404 instead of 200 for deletion of non-existent document (both Flask and Lambda).

### Pre-existing Technical Debt Identified

The following items were discovered during this review and should be addressed in the follow-up implementation story (or tracked as separate bug fixes):

| Item | Location | Severity | Description |
|------|----------|----------|-------------|
| Missing `int()` conversion | `lambda_function.py:227` | Medium | Lambda handler does not convert `id` query parameter to int — a non-numeric value would propagate to `StalkerWebDocumentDB` |
| Dead `post:` method block | `api-gw-app.yaml:211-230` | Low | POST method on `/website_delete` is defined in API Gateway but never called by any frontend code — dead configuration |
| 200 for non-existent resource | `server.py:625-631`, `lambda_function.py:232-238` | Low | DELETE of non-existent document returns HTTP 200 with "Page doesn't exist in database" — should return 404 Not Found per REST convention |

**Per AC5:** Decision is "defer" — zero code changes made. The current GET method continues to function unchanged.

### Completion Notes List

- **Task 1**: All 5 layers verified against source code. Implementation matches Dev Notes exactly: API GW has GET+POST+OPTIONS, Flask accepts GET only, Lambda is method-agnostic, frontend uses `axios.get()` in 2 locations, integration test uses `self.app.get()`.
- **Task 2**: REST-compliant alternative fully designed. Approach A (change method only) recommended over Approach B (full REST with path change). CORS already supports DELETE method — no CORS changes needed.
- **Task 3**: Frontend impact analysis confirmed: exactly 2 call sites in `useManageLLM.js`, zero in Chrome extension, zero in other frontend files. Backward compatibility impact: GET would return 405 after migration.
- **Task 4**: Decision is DEFER. Rationale documented in Decision Record section above. No follow-up implementation tasks created — change will be included in a future API quality sprint.

### Change Log

- 2026-02-17: Implementation complete — review document created with current implementation analysis, REST-compliant alternative design, frontend impact analysis, and DEFER decision with rationale.
- 2026-02-17: Code review fixes — added `lenie-split-export.json` to analysis (M1), classified Lambda int conversion gap as technical debt (M2), added 2 missing documentation files to scope (L1), explicit follow-up scope reminder in Decision Record (L2), clarified co-mingled sprint-status changes in File List (L3).
- 2026-02-17: Code review round 2 — fixed File List sprint-status transition to include final `done` state (M1), corrected Decision Record file count from ~6 to ~8 (L1), added "Pre-existing Technical Debt Identified" table for Lambda int conversion and dead `post:` block (L2, L3), added status transition history to Change Log (L4).
- 2026-02-17: Status transitions: backlog → done (committed in `cda9fd9`).
- 2026-02-17: Code review round 3 — 4 issues found (1 HIGH, 1 MEDIUM, 2 LOW), all fixed. Story file committed (was untracked). Follow-up scope expanded from ~8 to ~12 files (4 missing CLAUDE.md/README.md refs). Added 200-for-non-existent to technical debt table. File List starting state corrected.

### File List

- `_bmad-output/implementation-artifacts/11-5-rest-compliance-review-for-website-delete.md` — this story file (review document with embedded decision)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — modified (11-5: backlog → done; committed in `cda9fd9`)

## Senior Developer Review — Round 3 (AI)

**Reviewer:** Claude Opus 4.6 | **Date:** 2026-02-17 | **Outcome:** Approved with fixes applied

### AC Verification

| AC | Result | Method |
|----|--------|--------|
| AC1 — Implementation documented | PASS | All 5 file:line refs independently verified against source |
| AC2 — REST alternative documented | PASS | Approach A/B described with per-layer changes |
| AC3 — Frontend impact analysis | PASS | Grep confirms exactly 2 call sites, zero in Chrome extension |
| AC4 — Decision with rationale | PASS | DEFER with 6-point rationale |
| AC5 — No code changes | PASS | Zero modified source files |

### Issues Found and Fixed

| # | Severity | Issue | Fix |
|---|----------|-------|-----|
| 1 | HIGH | Story file (the primary deliverable — review document with DEFER decision) was untracked (`??`) in git, never committed. Previous reviews missed this. | Staged and committed with this review |
| 2 | MEDIUM | Follow-up scope listed 3 doc files (~8 total), but grep `GET.*website_delete` across `*.md` found 4 more: `web_interface_react/CLAUDE.md:113`, `backend/tests/CLAUDE.md:83`, `infra/aws/serverless/CLAUDE.md:184`, `infra/aws/README.md:254,520`. Actual scope ~12 files. | Added 4 files to scope table, updated total from ~8 to ~12, updated Decision Record item (e) from 3 to 7 doc files |
| 3 | LOW | File List starting state `ready-for-dev` doesn't match committed starting state `backlog` in `cda9fd9` | Corrected to `backlog → done` |
| 4 | LOW | REST compliance review doesn't note that both Flask (`server.py:625`) and Lambda (`lambda_function.py:232`) return 200 for deletion of non-existent document (should be 404) | Added to Pre-existing Technical Debt table and Decision Record follow-up scope item (f) |

### Notes

- All 5 ACs independently verified — the review document is thorough and accurate
- File:line references all verified against current source code
- Decision (DEFER) is well-reasoned with clear rationale
- Two previous review rounds improved the document significantly
- The recurring "story file not committed" pattern (also seen in Story 11-4) suggests a workflow gap where sprint-status gets committed but deliverable files don't
