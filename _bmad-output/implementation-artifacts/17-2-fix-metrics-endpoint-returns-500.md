# Story 17.2: Fix Metrics Endpoint Returns 500

Status: done

## Story

As a **developer**,
I want the `/metrics` endpoint to return a valid response instead of HTTP 500,
so that Kubernetes health monitoring and Prometheus scraping work correctly.

## Acceptance Criteria

1. **Given** a GET request to `/metrics`
   **When** the server processes the request
   **Then** the server returns HTTP 200 with a valid response body (not 500)

2. **Given** the `/metrics` endpoint is a Prometheus metrics stub
   **When** implementing the fix
   **Then** the endpoint returns a minimal valid Prometheus text format response
   **And** the Content-Type is `text/plain; charset=utf-8`

3. **Given** the endpoint currently has an empty `pass` body
   **When** the fix is applied
   **Then** at minimum it returns basic application info metrics (e.g., `lenie_app_info{version="0.3.13.0"} 1`)

4. **Given** existing health check endpoints (`/healthz`, `/startup`, `/readiness`, `/liveness`)
   **When** the `/metrics` fix is deployed
   **Then** no existing endpoints are affected

## Tasks / Subtasks

- [x] Task 1: Fix `/metrics` endpoint in `backend/server.py` (AC: #1, #2, #3)
  - [x] Replace `pass` with a return statement
  - [x] Return minimal Prometheus exposition format with `text/plain` content type
  - [x] Include at least `lenie_app_info` gauge with version label
- [x] Task 2: Add unit test for `/metrics` endpoint (AC: #1, #4)
  - [x] Test returns HTTP 200
  - [x] Test response contains expected metric name
  - [x] Test Content-Type header

## Dev Notes

### Current Code (server.py:695-697)

```python
@app.route('/metrics', methods=['GET'])
def kubernetes_metrics():
    pass
```

The function body is `pass`, which in Flask causes the view to return `None`. Flask then raises a `TypeError: The view function did not return a valid response`, resulting in HTTP 500.

### Minimal Fix

```python
@app.route('/metrics', methods=['GET'])
def kubernetes_metrics():
    from flask import Response
    metrics = "# HELP lenie_app_info Application information\n"
    metrics += "# TYPE lenie_app_info gauge\n"
    metrics += 'lenie_app_info{version="0.3.13.0"} 1\n'
    return Response(metrics, mimetype='text/plain; charset=utf-8')
```

### Key Constraints

- This is a **stub** endpoint — keep it minimal, do NOT add a full Prometheus client library
- The endpoint is **server.py only** — not implemented in Lambda (and not needed there)
- The version string `0.3.13.0` is defined in `backend/server.py` — check for existing version variable
- `Response` is already imported from Flask in the file
- Prometheus text format: each metric has `# HELP`, `# TYPE`, then `metric_name{labels} value`

### Project Structure Notes

- File: `backend/server.py` (lines 695-697)
- Tests: `backend/tests/unit/` — follow existing test patterns
- This endpoint does NOT exist in Lambda — no AWS changes needed

### References

- [Source: backend/server.py:695-697 — current broken endpoint]
- [Source: backend/server.py:689-691 — /healthz pattern for reference]
- [Source: docs/infrastructure-metrics.md — /metrics listed as server.py-only endpoint]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

- RED phase: All 3 tests failed with `TypeError: The view function for 'kubernetes_metrics' did not return a valid response` (HTTP 500)
- GREEN phase: All 3 tests passed after fix
- Existing unit tests: 16 passed, 3 skipped (metrics tests in minimal env), 6 pre-existing failures (not related to this change)
- Ruff linting: All checks passed

### Completion Notes List

- Added `Response` to Flask imports in server.py (was not previously imported despite Dev Notes stating otherwise)
- Replaced `pass` body with Prometheus exposition format response using `APP_VERSION` variable (dynamic, not hardcoded)
- Created unit test file with mocked psycopg2 and environment variables to allow testing without database
- Test file gracefully skips when Flask dependencies are unavailable (compatible with minimal `uvx pytest` runs)
- No changes to any existing endpoints — only `/metrics` handler modified

### File List

- `backend/server.py` — Modified: added `Response` import, fixed `/metrics` endpoint
- `backend/tests/unit/test_metrics_endpoint.py` — New: unit tests for `/metrics` endpoint (5 tests)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — Modified: story status tracking

## Senior Developer Review (AI)

- **Review date:** 2026-02-22
- **Review outcome:** Approve with changes (auto-fixed)
- **Reviewer model:** Claude Opus 4.6

### Action Items

- [x] [M1] Add regression test for `/healthz` endpoint (AC #4)
- [x] [L1] Strengthen metric content assertions (verify `# HELP`, `# TYPE`, version label)
- [x] [M2] Document sys.modules mocking limitation in test file comment
- [x] [L2] Add `sprint-status.yaml` to File List
- [x] [L3] Noted: `/metrics` requires `x-api-key` auth — pre-existing design, not regression

## Change Log

- 2026-02-22: Fixed `/metrics` endpoint to return valid Prometheus text format response instead of HTTP 500. Added unit tests.
- 2026-02-22: Code review fixes — added healthz regression test, strengthened Prometheus format assertions, documented test isolation constraint.
