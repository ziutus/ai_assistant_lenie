# Story 25.1: Scheduled Health Checks & Proactive Alerts

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **system administrator (single user)**,
I want the Slack bot to periodically check backend health and proactively alert me via DM when infrastructure problems occur,
so that I am immediately aware of failures without having to manually query the system.

## Acceptance Criteria

1. **Scheduled health checks run on a configurable interval** (default: 5 minutes)
   - Given the Slack bot is running
   - When the configured interval elapses
   - Then the bot executes health checks against the backend API
   - And health checks do NOT block normal Slack event handling (commands, DMs, mentions)

2. **Backend API reachability is monitored**
   - Given a scheduled health check runs
   - When the bot calls `GET /healthz` on the backend
   - Then the result is recorded as `healthy` (2xx response) or `down` (timeout/connection error/non-2xx)

3. **Database connectivity is monitored**
   - Given a scheduled health check runs
   - When the bot calls a DB-dependent endpoint (`GET /version` or `GET /website_list?type=ALL`)
   - Then the result confirms the database is reachable through the backend

4. **Bot sends DM alert on new failure**
   - Given a health check detects a failure (transition from `healthy` → `down`)
   - When the failure is new (not previously reported and still unresolved)
   - Then the bot sends a direct message to the configured user with:
     - Affected component name
     - Failure reason in plain language (no stack traces)
     - Timestamp of the failed check
     - Actionable suggestion (e.g., "Check if lenie-ai-server container is running on NAS")

5. **Alert deduplication prevents alert fatigue**
   - Given an alert was sent for a specific failure
   - When the same health check fails again before recovery
   - Then no duplicate alert is sent
   - And when the failure resolves, a recovery notification IS sent

6. **Recovery notification on resolution**
   - Given a component was in `down` state and an alert was sent
   - When the health check succeeds again (transition from `down` → `healthy`)
   - Then the bot sends a recovery DM with:
     - Component name
     - Recovery timestamp
     - Approximate downtime duration

7. **Health check does not crash the bot**
   - Given the backend is completely unreachable
   - When the health check runs
   - Then the bot catches all exceptions gracefully
   - And remains connected to Slack and responsive to user commands

8. **Configuration via environment variables**
   - `HEALTH_CHECK_ENABLED` (default: `false`) — enable/disable scheduled checks
   - `HEALTH_CHECK_INTERVAL` (default: `300` seconds / 5 minutes)
   - `HEALTH_CHECK_USER_ID` — Slack user ID to receive alerts (required if enabled)
   - All variables managed via `unified_config_loader` (Vault/SSM/env)

## Tasks / Subtasks

- [x] Task 1: Create `src/health_monitor.py` module (AC: #1, #2, #3, #7)
  - [x] 1.1: Define `HealthStatus` enum (`healthy`, `down`) and `ComponentState` dataclass (component name, status, last_check, last_alert_sent)
  - [x] 1.2: Implement `HealthMonitor` class with state tracking per component
  - [x] 1.3: Implement `check_backend_api()` — calls `client.check_health()` (GET /healthz)
  - [x] 1.4: Implement `check_database_connectivity()` — calls `client.get_version()` (GET /version, requires DB)
  - [x] 1.5: Implement `run_all_checks()` — executes all checks, returns list of state changes
  - [x] 1.6: Wrap all check methods in try/except to prevent crashes (AC #7)

- [x] Task 2: Implement alert delivery (AC: #4, #5, #6)
  - [x] 2.1: Implement `send_alert(component, reason, suggestion)` — DM via Slack `chat.postMessage` to `HEALTH_CHECK_USER_ID`
  - [x] 2.2: Implement `send_recovery(component, downtime_duration)` — recovery DM
  - [x] 2.3: Implement state-transition-based deduplication (only alert on `healthy→down`, only recover on `down→healthy`)
  - [x] 2.4: Format messages with user-friendly text (FR18/FR20 patterns from dm_handler.py)

- [x] Task 3: Implement scheduler integration (AC: #1, #8)
  - [x] 3.1: Add `threading.Timer` based recurring execution (stdlib, no new dependency)
  - [x] 3.2: Ensure scheduler runs in background thread (daemon timer, does not block Socket Mode event loop)
  - [x] 3.3: Add graceful shutdown (cancel timer on SIGTERM/SIGINT via KeyboardInterrupt handler in main.py)

- [x] Task 4: Integrate into `src/main.py` (AC: #8)
  - [x] 4.1: Read `HEALTH_CHECK_ENABLED`, `HEALTH_CHECK_INTERVAL`, `HEALTH_CHECK_USER_ID` from config
  - [x] 4.2: If enabled, create `HealthMonitor` instance and start scheduler after Socket Mode connect
  - [x] 4.3: Add shutdown hook to stop scheduler

- [x] Task 5: Add environment variables to configuration (AC: #8)
  - [x] 5.1: Add `HEALTH_CHECK_ENABLED`, `HEALTH_CHECK_INTERVAL`, `HEALTH_CHECK_USER_ID` to `scripts/vars-classification.yaml`
  - [x] 5.2: Add variables to `slack-app-manifest.yaml` documentation comment (if applicable) — N/A, manifest does not list env vars

- [x] Task 6: Unit tests (all ACs)
  - [x] 6.1: Test `HealthMonitor` state tracking — initial state, healthy→down transition, down→healthy transition
  - [x] 6.2: Test alert deduplication — no duplicate alerts for same ongoing failure
  - [x] 6.3: Test recovery notification — sent only on down→healthy transition
  - [x] 6.4: Test graceful error handling — check doesn't crash on ConnectionError, Timeout
  - [x] 6.5: Test scheduler start/stop lifecycle
  - [x] 6.6: Test configuration loading — enabled/disabled, default values

## Dev Notes

### Architecture Patterns & Constraints

- **Slack Bot runs on Docker/NAS only** (Socket Mode = persistent process, not serverless). Scheduler fits naturally.
- **Existing health check at startup**: `main.py:check_backend_connectivity()` calls `client.check_health()` + `client.get_version()`. Reuse this pattern.
- **API client already has health methods**: `api_client.py` provides `check_health()` (GET /healthz) and `get_version()` (GET /version). No new API endpoints needed.
- **5-second timeout on all API calls** (NFR3) — health checks inherit this timeout from `api_client.py`.
- **NFR16**: Bot MUST remain running and connected to Slack even when backend is unreachable. Health check failures must never crash the process.
- **NFR17**: Slack Bolt SDK auto-reconnect handles Socket Mode disconnections. Health monitor must not interfere.

### Implementation Guidance

- **Scheduler choice**: Prefer `threading.Timer` (stdlib) over `APScheduler` to avoid adding a new dependency. Recurring timer pattern:
  ```python
  def _schedule_next(self):
      self._timer = threading.Timer(self.interval, self._run_and_reschedule)
      self._timer.daemon = True
      self._timer.start()
  ```
- **State tracking**: In-memory dict keyed by component name. No persistence needed — state resets on restart (acceptable for single-container deployment).
- **DM delivery**: Use Slack Web API `client.chat_postMessage(channel=user_id, text=...)`. The bot already has `chat:write` scope.
- **Alert format**: Follow existing error message patterns from `dm_handler.py` and `mention_handler.py` (plain text, no stack traces, actionable suggestions).
- **Deduplication**: Track previous state per component. Only send alert when state transitions (not on every failed check). This is simpler and more reliable than cooldown timers.

### Error Handling Patterns (from existing codebase)

```python
# From dm_handler.py / mention_handler.py
try:
    client.check_health()
except ApiConnectionError:
    # Backend unreachable — record as "down"
except ApiResponseError as exc:
    # Backend returned error — record as "down" with status code
except ApiError as exc:
    # Unexpected — record as "down"
```

### Project Structure Notes

- New file: `slack_bot/src/health_monitor.py` — health monitoring logic + scheduler
- Modified file: `slack_bot/src/main.py` — integration (config reading, monitor start/stop)
- New test file: `slack_bot/tests/unit/test_health_monitor.py`
- Modified file: `scripts/vars-classification.yaml` — new env vars
- **No changes to backend** — all monitoring uses existing API endpoints

### References

- [Source: `_bmad-output/planning-artifacts/archive/prd-sprint5-slack-bot-2026-03-04.md` — FR15, FR16, FR17, NFR16, NFR17]
- [Source: `slack_bot/src/main.py` — `check_backend_connectivity()` startup health check pattern]
- [Source: `slack_bot/src/api_client.py` — `check_health()`, `get_version()`, exception hierarchy]
- [Source: `slack_bot/src/dm_handler.py` — error handling and message formatting patterns]
- [Source: `slack_bot/pyproject.toml` — current dependencies (no APScheduler)]
- [Source: `CLAUDE.md` — Slack Bot Docker deployment, Socket Mode, config_loader]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

None — all tests passed on first run.

### Completion Notes List

- Implemented `HealthMonitor` class in `slack_bot/src/health_monitor.py` with:
  - `HealthStatus` enum (healthy/down) and `ComponentState` dataclass for per-component state tracking
  - `check_backend_api()` — calls GET /healthz via existing `api_client.check_health()`
  - `check_database_connectivity()` — calls GET /version via existing `api_client.get_version()`
  - `run_all_checks()` — runs all checks and returns state transitions (component, old→new status)
  - `send_alert()` / `send_recovery()` — DM delivery via Slack `chat.postMessage`
  - `process_transitions()` — dispatches alerts on healthy→down, recovery on down→healthy
  - State-transition-based deduplication — no duplicate alerts for ongoing failures
  - `threading.Timer` based scheduler with daemon threads (stdlib, no new dependencies)
  - Graceful error handling — all exceptions caught, monitor never crashes the bot
- Integrated into `main.py` — reads config, starts monitor after Socket Mode connect, stops on shutdown
- Added 3 env vars to `vars-classification.yaml`: HEALTH_CHECK_ENABLED, HEALTH_CHECK_INTERVAL, HEALTH_CHECK_USER_ID
- 33 new unit tests covering all ACs (state tracking, deduplication, recovery, error handling, scheduler lifecycle)
- 283 total tests pass, 0 regressions, ruff clean

**Code Review Fixes (2026-03-10):**
- H1: Fixed recovery downtime calculation — uses `down_since` instead of `last_alert_sent`; transition tuples now include `down_since` field
- H2: Fixed `test_alert_deduplication_via_run_all_checks` — now properly calls `process_transitions` on first transitions and asserts `chat_postMessage` call count
- M1: Protected `HEALTH_CHECK_INTERVAL` parsing against `ValueError` with fallback to 300s default
- M2: Added interval validation in `HealthMonitor.__init__` — raises `ValueError` for zero/negative interval
- M3: `down_since` field now properly consumed in recovery flow (resolved by H1 fix)
- 4 new tests added: interval validation (2), recovery downtime calculation (2)
- 287 total tests pass, 0 regressions, ruff clean

### Change Log

- 2026-03-10: Story 25.1 implemented — scheduled health checks with proactive Slack alerts
- 2026-03-10: Code review — 5 issues fixed (2H/3M), 4 new tests added

### File List

- `slack_bot/src/health_monitor.py` — NEW: health monitoring module (HealthStatus, ComponentState, HealthMonitor)
- `slack_bot/src/main.py` — MODIFIED: health monitor integration (config reading, start/stop)
- `slack_bot/tests/unit/test_health_monitor.py` — NEW: 37 unit tests for health monitoring
- `scripts/vars-classification.yaml` — MODIFIED: added HEALTH_CHECK_ENABLED, HEALTH_CHECK_INTERVAL, HEALTH_CHECK_USER_ID
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — MODIFIED: story status updated
