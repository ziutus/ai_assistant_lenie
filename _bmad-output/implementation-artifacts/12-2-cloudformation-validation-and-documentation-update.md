# Story 12.2: CloudFormation Validation and Documentation Update

Status: done

## Story

As a **developer**,
I want to validate all modified CloudFormation templates and update documentation to reflect the current state,
So that the project documentation is accurate and all templates are deployment-ready.

## Acceptance Criteria

1. **AC1 — cfn-lint passes on all templates:** All CloudFormation templates pass `cfn-lint` with zero errors.
2. **AC2 — Endpoint counts accurate:** CLAUDE.md and README.md reflect actual endpoint counts (18 in server.py, 10 in api-gw-app, 9 in api-gw-infra).
3. **AC3 — No stale references to removed endpoints:** Zero references to `/ai_ask`, `/translate`, `/infra/ip-allow`, or `ai_describe_image()` in active documentation (excluding historical context in ADRs, system-evolution.md, and _bmad-output/).
4. **AC4 — Epic 11 decisions documented:** All implement/defer/reject decisions from Epic 11 stories are documented with rationale.
5. **AC5 — Post-Sprint 3 documentation accurate:** CLAUDE.md, README.md, and infra docs reflect the current state.

## Tasks / Subtasks

- [x] **Task 1: Run cfn-lint on all CF templates** (AC: #1)
  - [x] 1.1 Run `uvx cfn-lint infra/aws/cloudformation/templates/*.yaml`
  - [x] 1.2 Verify zero errors (warnings acceptable)
  - Results: Zero errors. 5 warnings (W8001 unused IsProduction condition in 4 templates, W2001 unused VpcName parameter in vpc.yaml) — all pre-existing, not related to Sprint 3 changes.

- [x] **Task 2: Verify endpoint counts in documentation** (AC: #2)
  - [x] 2.1 Verify server.py has 18 endpoints (counted 19 routes including root `/`, 18 per convention excluding root)
  - [x] 2.2 Verify CLAUDE.md (root), README.md, backend/CLAUDE.md all say "18 endpoints" for server.py — confirmed correct
  - [x] 2.3 Fix `infra/aws/CLAUDE.md:49` — "3 APIs with 20+ endpoints" updated to "2 active REST APIs: app 10 + infra 9 endpoints, plus Chrome ext API"
  - [x] 2.4 Verify `infra/aws/cloudformation/CLAUDE.md` API Gateway table — already updated in consolidation commit (api-gw-app: 10 endpoints, api-gw-infra: 9 endpoints)

- [x] **Task 3: Verify no stale endpoint references** (AC: #3)
  - [x] 3.1 Grep for `/ai_ask`, `/translate`, `/infra/ip-allow`, `ai_describe_image` in all active docs
  - [x] 3.2 Results: Zero stale references in active code/docs. All occurrences are historical context (ADR-005, system-evolution.md, _bmad-output/ artifacts).

- [x] **Task 4: Verify Epic 11 decisions are documented** (AC: #4)
  - [x] 4.1 Story 11-5 (REST compliance for /website_delete): Decision is DEFER — fully documented in story file with 6-point rationale, pre-existing technical debt table, and follow-up scope.
  - [x] 4.2 Story 11-7 (SQS queue references): Decision to use project-scoped wildcard documented in story file.
  - [x] 4.3 Story 11-9 (Lambda function name mismatch): Decision to align to CF-defined name documented in story file.
  - [x] 4.4 All other Epic 11 stories (11-1 through 11-4, 11-6, 11-8, 11-10) were implementation stories with no deferred decisions.

- [x] **Task 5: Final documentation accuracy review** (AC: #5)
  - [x] 5.1 Verified docs/api-contracts-backend.md says "18 endpoints" — correct
  - [x] 5.2 Verified docs/source-tree-analysis.md says "18 endpoints" — correct
  - [x] 5.3 Verified docs/project-overview.md says "18 endpoints" — correct
  - [x] 5.4 Verified docs/index.md says "18 endpoints" — correct
  - [x] 5.5 Verified infra/aws/serverless/CLAUDE.md endpoint mapping table — correct (no removed endpoints)
  - [x] 5.6 Verified web_interface_react/CLAUDE.md — no stale references

## Dev Notes

### cfn-lint Results (all templates)

```
W8001 Condition IsProduction not used — lambda-layer-lenie-all.yaml, lambda-layer-openai.yaml, lambda-layer-psycopg2.yaml, s3-app-web.yaml
W2001 Parameter VpcName not used — vpc.yaml
```

All warnings are pre-existing conditions for multi-environment support (IsProduction will be used when prod environment is added). No errors.

### Documentation State Summary (Post-Sprint 3)

| Document | Endpoint Count | Status |
|----------|---------------|--------|
| CLAUDE.md (root) | 18 (server.py) | Correct |
| README.md | 18 (server.py) | Correct |
| backend/CLAUDE.md | 18 (server.py) | Correct |
| docs/api-contracts-backend.md | 18 (server.py) | Correct |
| docs/source-tree-analysis.md | 18 (server.py) | Correct |
| docs/project-overview.md | 18 (server.py) | Correct |
| docs/index.md | 18 (server.py) | Correct |
| infra/aws/CLAUDE.md | 2 active APIs (10+9) | Fixed in this story |
| infra/aws/cloudformation/CLAUDE.md | app:10, infra:9 | Fixed in API GW consolidation |

### Epic 11 Decision Summary

| Story | Decision | Rationale |
|-------|----------|-----------|
| 11-1 Tags | Implemented | All templates tagged |
| 11-2 SSM pattern | Implemented | Zero `{{resolve:ssm:` remaining |
| 11-3 ApiDeployment | Implemented | Separate deployment resource + auto-redeploy hook |
| 11-4 Lambda name typo | Implemented | Verified naming consistency |
| 11-5 REST /website_delete | **DEFER** | Low risk, not aligned with Sprint 3 scope. Follow-up: ~12 files when API quality sprint happens. |
| 11-6 SQS-to-RDS parameterization | Implemented | Infrastructure values parameterized |
| 11-7 Legacy queue references | Implemented | Project-scoped wildcard chosen over exact name |
| 11-8 Fn::ImportValue→SSM | Implemented | DLQ ARN via SSM parameter |
| 11-9 Lambda name mismatch | Implemented | Aligned to CF-defined name (Option B) |
| 11-10 Stage logging/tracing | Implemented | StageDescription with INFO logging, X-Ray, metrics |

## File List

- `_bmad-output/implementation-artifacts/12-2-cloudformation-validation-and-documentation-update.md` — this story file (created)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — 12-2: backlog → done
- `infra/aws/CLAUDE.md` — fixed API Gateway description (line 49)
