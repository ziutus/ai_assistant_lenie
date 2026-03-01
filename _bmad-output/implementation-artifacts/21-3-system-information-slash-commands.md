# Story 21.3: System Information Slash Commands

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **user**,
I want to type `/lenie-version` and `/lenie-count` in Slack,
So that I can check system status quickly without opening the web UI.

## Acceptance Criteria

1. **Given** the bot is connected and backend is running
   **When** user types `/lenie-version`
   **Then** bot responds with backend version and build timestamp in the same channel within 3 seconds

2. **Given** the bot is connected and backend is running
   **When** user types `/lenie-count`
   **Then** bot responds with total document count and breakdown by type (webpage, youtube, link, etc.)

3. **Given** the backend is unreachable
   **When** user types `/lenie-version` or `/lenie-count`
   **Then** bot responds with user-friendly error message: "Backend unreachable (connection timeout). Check if lenie-ai-server is running."

4. **Given** the bot is connected
   **When** backend returns unexpected response format
   **Then** bot logs a warning and responds with "Unexpected response from backend" (no crash)

**Covers:** FR4, FR5, FR6 (partial), FR7, FR18-FR20 | NFR1, NFR16

## Tasks / Subtasks

- [x] Task 1: Register slash commands in main.py (AC: #1, #2)
  - [x] 1.1: Import `register_commands(app, cfg)` from `commands.py` in `main.py`
  - [x] 1.2: Call `register_commands(app, cfg)` after `App()` creation but before `handler.connect()`
  - [x] 1.3: Verify bot starts and connects with commands registered

- [x] Task 2: Implement `/lenie-version` handler (AC: #1, #3, #4)
  - [x] 2.1: Create `handle_version(ack, respond, client)` function — call `ack()` immediately, then `client.get_version()`
  - [x] 2.2: Format success response: "Version: {app_version}\nBuild: {app_build_time}"
  - [x] 2.3: Catch `ApiConnectionError` → respond with "Backend unreachable (connection timeout). Check if lenie-ai-server is running."
  - [x] 2.4: Catch `ApiResponseError` → log warning, respond with "Unexpected response from backend (HTTP {status_code})"
  - [x] 2.5: Catch generic `ApiError` → respond with "An error occurred: {message}"

- [x] Task 3: Implement `/lenie-count` handler (AC: #2, #3, #4)
  - [x] 3.1: Create `handle_count(ack, respond, client)` function — call `ack()` immediately
  - [x] 3.2: Call `client.get_count("ALL")` for total count
  - [x] 3.3: Call `client.get_count(type)` for each document type: webpage, youtube, link, movie, text_message, text
  - [x] 3.4: Format response with total and per-type breakdown (skip types with 0 count)
  - [x] 3.5: Same error handling as Task 2 (ApiConnectionError, ApiResponseError, ApiError)

- [x] Task 4: Create `register_commands()` function in commands.py (AC: #1, #2)
  - [x] 4.1: Create `register_commands(app: App, cfg: Config) -> None`
  - [x] 4.2: Inside, create `LenieApiClient` via `create_client(cfg)`
  - [x] 4.3: Register `@app.command("/lenie-version")` with closure over client
  - [x] 4.4: Register `@app.command("/lenie-count")` with closure over client

- [x] Task 5: Write unit tests for commands.py (AC: all)
  - [x] 5.1: Test `/lenie-version` success — mocked `get_version()` returns version data, verify `ack()` called first, verify `respond()` message format
  - [x] 5.2: Test `/lenie-version` with `ApiConnectionError` — verify user-friendly error message
  - [x] 5.3: Test `/lenie-version` with `ApiResponseError` — verify warning logged, error response
  - [x] 5.4: Test `/lenie-count` success — mocked `get_count()` returns counts, verify formatted response
  - [x] 5.5: Test `/lenie-count` with `ApiConnectionError` — verify error message
  - [x] 5.6: Test `/lenie-count` with zero-count types — verify they are omitted from response
  - [x] 5.7: Test `register_commands()` — verify commands are registered on app object
  - [x] 5.8: Target >80% coverage for `commands.py`

- [x] Task 6: Code quality verification (NFR11, NFR12)
  - [x] 6.1: Run `ruff check slack_bot/` — zero warnings
  - [x] 6.2: Verify type hints on all public functions
  - [x] 6.3: Run full test suite — zero regressions

## Dev Notes

### Critical Architecture Constraints

- **Module separation** (NFR14): `commands.py` handles Slack interaction logic ONLY. All HTTP communication goes through `LenieApiClient` from `api_client.py`. Never call `requests` directly from `commands.py`.
- **`ack()` first** (NFR1): Slack requires acknowledgment within 3 seconds. Call `ack()` BEFORE any API calls to the backend. Use `respond()` for the actual response.
- **Error isolation** (NFR16, NFR19): Backend failures must NEVER crash the bot or disconnect from Slack. Every handler wraps API calls in `try/except ApiError`.
- **No secrets in responses** (NFR6): Never include API keys, tokens, or internal URLs in Slack messages.
- **ZERO code dependencies on `backend/`** (NFR8): Import only from `src.api_client` and `src.config`.

### Backend API Response Formats

**`GET /version`** (no auth required):
```json
{
  "status": "success",
  "app_version": "0.3.13.0",
  "app_build_time": "2026.01.23 04:04",
  "encoding": "utf8"
}
```

**`GET /website_list?type=ALL`** (requires `x-api-key`):
```json
{
  "status": "success",
  "message": "Dane odczytane pomyślnie.",
  "encoding": "utf8",
  "websites": [...],
  "all_results_count": 1847
}
```

### Document Types (for `/lenie-count` breakdown)

Available types from `StalkerDocumentType` enum:
- `webpage` — downloaded web pages
- `youtube` — YouTube video transcripts
- `link` — saved links (not downloaded)
- `movie` — local movie files
- `text_message` — text messages/notes
- `text` — plain text documents

**Important:** `/website_list` does NOT return per-type breakdown in a single call. To get breakdown, call `get_count(type)` for each type separately (7 calls total: ALL + 6 types). Each call is lightweight (~50ms), well within the 5s timeout.

### Slack Bolt Command Pattern

```python
# Pattern for registering slash commands
def register_commands(app: App, cfg: Config) -> None:
    client = create_client(cfg)

    @app.command("/lenie-version")
    def handle_version(ack, respond):
        ack()  # Must be first! Slack 3-second timeout
        try:
            data = client.get_version()
            respond(text=f"Version: {data['app_version']}\nBuild: {data['app_build_time']}")
        except ApiConnectionError as exc:
            respond(text="Backend unreachable (connection timeout). Check if lenie-ai-server is running.")
        except ApiResponseError as exc:
            logger.warning("Unexpected response: %s", exc.message)
            respond(text=f"Unexpected response from backend (HTTP {exc.status_code})")
        except ApiError as exc:
            respond(text=f"An error occurred: {exc.message}")
```

### `/lenie-count` Response Format

```
Documents in knowledge base: 1,847 total

  webpage: 423
  youtube: 312
  link: 891
  movie: 42
  text: 179
```
Types with 0 count should be omitted. Use number formatting with thousands separator (locale-aware or simple comma).

### Error Message Templates

| Scenario | Message |
|----------|---------|
| Backend unreachable | "Backend unreachable (connection timeout). Check if lenie-ai-server is running." |
| HTTP error | "Unexpected response from backend (HTTP {status_code})" |
| Unexpected format | "Unexpected response from backend" |
| Generic error | "An error occurred: {message}" |

### Exception Hierarchy (from Story 21-2)

```python
from src.api_client import (
    ApiError,            # Base — catch-all for any API issue
    ApiConnectionError,  # Backend unreachable (timeout, DNS, network)
    ApiResponseError,    # Backend returned error (4xx, 5xx, invalid JSON)
    LenieApiClient,
    create_client,
)
```

### Testing Strategy

Run tests from the `slack_bot/` directory using project venv:

```bash
cd slack_bot && PYTHONPATH=. .venv/Scripts/python -m pytest tests/unit/test_commands.py -v
```

**Mocking pattern for Slack commands:**
- Mock `LenieApiClient` methods (not HTTP layer) — command tests should verify command logic, not API client behavior
- Use `MagicMock` for `ack` and `respond` callable objects
- Verify `ack()` is called exactly once and BEFORE `respond()`

```python
from unittest.mock import MagicMock, patch
from src.api_client import ApiConnectionError, ApiResponseError

def test_handle_version_success():
    mock_client = MagicMock()
    mock_client.get_version.return_value = {
        "app_version": "0.3.13.0",
        "app_build_time": "2026.01.23 04:04"
    }
    ack = MagicMock()
    respond = MagicMock()

    # Call handler with mocked client
    handle_version(ack, respond, mock_client)

    ack.assert_called_once()
    respond.assert_called_once()
    assert "0.3.13.0" in respond.call_args[1]["text"]
```

**Important:** The `handle_version` and `handle_count` functions should accept `client` as a parameter (injected via closure in `register_commands`) to make them testable without mocking imports.

### Previous Story Learnings (21-2 Code Review)

Key issues found and fixed during 21-2 review — avoid repeating:
1. **Always handle unexpected response formats** — `get_count()` was fixed to raise `ApiResponseError` when `all_results_count` key is missing. Your command handlers should catch this.
2. **Use `pytest.raises`** not `try/assert False/except` in tests
3. **Named constants** for magic values (e.g., `MAX_ERROR_BODY_LENGTH`)
4. **Catch-all `except requests.RequestException`** was added to api_client — commands layer should catch `ApiError` (the typed base)

### Project Structure After This Story

```
slack_bot/
├── src/
│   ├── __init__.py          # (Story 21-1) — unchanged
│   ├── config.py            # (Story 21-1) — unchanged
│   ├── main.py              # MODIFIED: import + call register_commands()
│   ├── api_client.py        # (Story 21-2) — unchanged
│   └── commands.py          # ← THIS STORY: register_commands, handle_version, handle_count
├── tests/
│   └── unit/
│       ├── test_config.py     # (Story 21-1) — unchanged
│       ├── test_main.py       # (Story 21-1) — unchanged
│       ├── test_api_client.py # (Story 21-2) — unchanged
│       └── test_commands.py   # ← THIS STORY: ~8 tests
```

### Dependencies on Other Stories

- **Story 21-1** (done): `main.py`, `config.py`, `pyproject.toml`, project structure, Socket Mode connection
- **Story 21-2** (done): `api_client.py` with `LenieApiClient`, `create_client()`, exception hierarchy, 24 tests
- **Story 21-4** (next): Will add `/lenie-add`, `/lenie-check`, `/lenie-info` to `commands.py`

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 21.3] — Story definition, acceptance criteria
- [Source: _bmad-output/implementation-artifacts/21-2-api-client-for-backend-communication.md] — API client implementation, exception hierarchy, code review findings
- [Source: backend/server.py:709-718] — `/version` endpoint implementation
- [Source: backend/server.py:291-314] — `/website_list` endpoint implementation
- [Source: backend/library/models/stalker_document_type.py] — `StalkerDocumentType` enum (6 types)
- [Source: slack_bot/src/main.py] — Entry point where commands must be registered
- [Source: slack_bot/src/api_client.py] — `LenieApiClient`, `create_client()`, exception classes

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List

- All 6 tasks completed in single implementation cycle
- 17 unit tests written covering all acceptance criteria (7 version + 7 count + 2 register + 1 types)
- Full test suite (71 tests) passes with zero regressions
- Ruff linting: zero warnings
- All public functions have correct type hints (`Callable` from `collections.abc`)
- Handler functions (`_handle_version`, `_handle_count`) accept `client` parameter for testability
- `register_commands()` creates client via closure pattern, registers both commands
- `ack()` verified to be called before `respond()` (dedicated tests for both handlers)
- Zero-count document types are correctly omitted from `/lenie-count` response
- Number formatting uses comma thousands separator (`{:,}`)
- `KeyError` handling for unexpected `get_version()` response format (AC #4)

### File List

- `slack_bot/src/commands.py` — NEW: `register_commands()`, `_handle_version()`, `_handle_count()`, `DOCUMENT_TYPES` constant (80 lines)
- `slack_bot/src/main.py` — MODIFIED: added `from src.commands import register_commands` import and `register_commands(app, cfg)` call (2 lines added)
- `slack_bot/tests/unit/test_commands.py` — NEW: 17 unit tests for all handlers, error cases, logging, registration, and document types
- `_bmad-output/implementation-artifacts/21-3-system-information-slash-commands.md` — MODIFIED: status → done, task checkboxes, Dev Agent Record, File List
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — MODIFIED: story status → done

## Senior Developer Review (AI)

**Reviewer:** Ziutus | **Date:** 2026-03-01 | **Outcome:** Approved with fixes applied

### Findings (7 total: 1 HIGH, 5 MEDIUM, 1 LOW)

**HIGH — Fixed:**
- H1: `_handle_version()` — `KeyError` on missing `app_version`/`app_build_time` dict keys escaped all `except ApiError` handlers (AC #4 violation). Same pattern as H2 from 21-2 review, explicitly warned against in Dev Notes. **Fix:** Added `except KeyError` handler with `logger.warning()` and user-friendly response.

**MEDIUM — Fixed:**
- M1: `callable` (lowercase builtin function) used as type hint instead of `Callable` from `collections.abc`. **Fix:** Added `from collections.abc import Callable` in `TYPE_CHECKING` block.
- M2: No test for `_handle_version` with missing dict keys. **Fix:** Added `test_missing_keys_in_version_response`.
- M3: No ack-before-respond test for `_handle_count` (only existed for `_handle_version`). **Fix:** Added `test_ack_called_before_respond` to `TestHandleCount`.
- M4: Tests for `ApiResponseError` didn't verify `logger.warning()` was called (Task 5.3 required it). **Fix:** Added `test_response_error_logs_warning` for both handlers.
- M5: `sprint-status.yaml` modified but not in story File List. **Fix:** Added to File List.

**LOW — Addressed:**
- L1: File List claimed "73 lines" for commands.py — actual ~80 lines post-review. **Fix:** Updated File List with correct count.

### Verification
- 17/17 command unit tests pass (was 13, +4 new)
- 71/71 full test suite passes (zero regressions)
- `ruff check`: zero warnings
- All 4 Acceptance Criteria verified as implemented

## Change Log

- 2026-03-01: Implemented `/lenie-version` and `/lenie-count` slash commands in `commands.py`. Wired `register_commands()` into `main.py`. Wrote 13 unit tests. All 67 tests pass, ruff clean. Status → review.
- 2026-03-01: **Code review fixes:** Added `KeyError` handling in `_handle_version()`, fixed `callable` → `Callable` type hints, added 4 new tests (missing keys, ack-before-respond for count, logger.warning verification ×2). 17 tests total, 71 full suite.
