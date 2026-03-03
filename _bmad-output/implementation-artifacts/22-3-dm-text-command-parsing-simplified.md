# Story 22.3: DM Text Command Parsing (Simplified)

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **user**,
I want to send commands as plain text messages in a direct message with the bot (e.g., "version", "add https://...", "check https://...", "info 1234"),
So that I can interact with the knowledge base without remembering slash command syntax.

## Acceptance Criteria

1. **Given** the bot is connected and user is in a DM with it
   **When** user sends "version"
   **Then** bot responds with the same version info as `/lenie-version`

2. **Given** the bot is in a DM
   **When** user sends "add https://example.com/article"
   **Then** bot calls `POST /url_add` and responds with confirmation (same as `/lenie-add`)

3. **Given** the bot is in a DM
   **When** user sends "check https://example.com/article"
   **Then** bot responds with found/not-found (same as `/lenie-check`)

4. **Given** the bot is in a DM
   **When** user sends "info 1234"
   **Then** bot responds with document details (same as `/lenie-info`)

5. **Given** the bot is in a DM
   **When** user sends "count"
   **Then** bot responds with document count breakdown (same as `/lenie-count`)

6. **Given** the bot is in a DM
   **When** user sends unrecognized text (e.g., "hello" or "asdf")
   **Then** bot responds with a help message listing available commands

**Covers:** FR8, FR9 | NFR1, NFR18

**Out of scope (Epic 21 retro decision):**
- Bare URL detection with confirmation prompt ("Did you want to add this URL?") — requires conversational state, deferred to future epic
- Channel message handling (Epic 23 scope)
- Natural language / LLM intent parsing (Epic 24 scope)

## Tasks / Subtasks

- [x] Task 1: Update Slack App manifest for DM event support (AC: #1-#6)
  - [x] 1.1: Add `im:history` to `oauth_config.scopes.bot` in `slack-app-manifest.yaml`
  - [x] 1.2: Add `settings.event_subscriptions.bot_events` with `message.im` event
  - [x] 1.3: Add a note in the manifest comments that the Slack App must be reinstalled after manifest update (or update via api.slack.com App Manifest page)

- [x] Task 2: Create DM message handler module (AC: #1-#6)
  - [x] 2.1: Create `slack_bot/src/dm_handler.py` with `register_dm_handler(app: App, client: LenieApiClient)` function
  - [x] 2.2: Add `@app.event("message")` listener inside `register_dm_handler()`
  - [x] 2.3: Filter: only DM messages (`event.get("channel_type") == "im"`), skip non-DM
  - [x] 2.4: Skip bot's own messages (`event.get("bot_id")` is set) to prevent infinite loops
  - [x] 2.5: Skip message subtypes (edits, deletes, etc.) — only process regular user messages (`event.get("subtype") is None`)
  - [x] 2.6: Parse text: first word → command keyword (case-insensitive via `.lower()`), remaining text → arguments

- [x] Task 3: Implement DM command routing and handlers (AC: #1-#5)
  - [x] 3.1: Create dispatch dict mapping command keywords to handler functions
  - [x] 3.2: "version" → call `client.get_version()`, format response identical to `/lenie-version`, send via `say()`
  - [x] 3.3: "count" → call `client.get_count()` for ALL + per-type, format identical to `/lenie-count`, send via `say()`
  - [x] 3.4: "add \<url\> [type]" → validate URL present, validate type in `_VALID_TYPES`, call `client.add_url()`, format identical to `/lenie-add`, send via `say()`
  - [x] 3.5: "check \<url\>" → validate URL present, call `client.check_url()`, format identical to `/lenie-check`, send via `say()`
  - [x] 3.6: "info \<id\>" → validate numeric ID (`int()` conversion, not `str.isdigit()`), call `client.get_document()`, format identical to `/lenie-info`, send via `say()`
  - [x] 3.7: Apply error handling pattern for each handler: try/except `ApiConnectionError`, `ApiResponseError`, `ApiError`, `KeyError` → user-friendly messages via `say()`

- [x] Task 4: Implement help message for unrecognized text (AC: #6)
  - [x] 4.1: "help" command → list all available commands with brief description and usage examples
  - [x] 4.2: Unrecognized text → same help message (e.g., "I didn't understand that. Available commands: ...")
  - [x] 4.3: Empty message text → help message

- [x] Task 5: Register DM handler in main.py (AC: #1-#6)
  - [x] 5.1: Import `register_dm_handler` from `src.dm_handler`
  - [x] 5.2: Call `register_dm_handler(app, api_client)` after `register_commands(app, api_client)` in `main()`

- [x] Task 6: Write unit tests for DM handler (AC: #1-#6)
  - [x] 6.1: Create `slack_bot/tests/unit/test_dm_handler.py`
  - [x] 6.2: Test text command parsing: "version", "add https://example.com", "add https://example.com webpage", "check https://example.com", "info 1234", "count", "help", "unknown"
  - [x] 6.3: Test each DM command handler with mocked `LenieApiClient` and mocked `say` callable
  - [x] 6.4: Test error handling for each command (ApiConnectionError, ApiResponseError, ApiError, KeyError)
  - [x] 6.5: Test DM filtering: non-DM messages ignored (`channel_type != "im"`), bot messages ignored (`bot_id` present), message subtypes ignored (`subtype` present)
  - [x] 6.6: Test edge cases: empty text, whitespace only, case variations ("VERSION", "Version", "VeRsIoN")
  - [x] 6.7: Test "add" with invalid type → error message with valid types list
  - [x] 6.8: Test "info" with non-numeric ID → usage hint

- [x] Task 7: Run validations and linting (AC: #1-#6)
  - [x] 7.1: Run slack_bot tests: `cd slack_bot && PYTHONPATH=. .venv/Scripts/python -m pytest tests/unit/ -v` — 167 passed
  - [x] 7.2: Run ruff linter: `uvx ruff check slack_bot/` — All checks passed
  - [x] 7.3: Run backend tests for regressions: `cd backend && PYTHONPATH=. uvx pytest tests/unit/ -v` — 24 passed, 6 pre-existing failures (unrelated to this story), 5 skipped

## Dev Notes

### Scope & Approach

This story adds DM text command parsing as a NEW capability alongside existing slash commands. The existing slash command handlers in `commands.py` are NOT modified — DM handling is implemented in a separate module `dm_handler.py`.

**Core pattern:** User sends plain text in DM → bot parses first word as command → routes to handler → calls same `api_client` methods → formats response → sends via `say()`.

**Key architectural decision:** DM handlers are independent from slash handlers. Response formatting will be similar (same text output) but NOT shared via extracted helpers. Rationale: keeping handlers independent avoids risk of breaking the stable, tested slash command code (108 tests). The error handling boilerplate (~8 lines per handler) is acceptable duplication for 5 commands — extraction can happen in a future refactoring story if command count grows.

### Slack Bolt Event Handling Pattern

DM messages arrive as `message` events with `channel_type == "im"`. The handler signature differs from slash commands:

```python
# Slash command handler (existing):
@app.command("/lenie-version")
def handle(ack, respond):
    ack()          # Must call within 3 seconds
    respond(text="...")  # Reply to slash command

# DM message handler (new):
@app.event("message")
def handle(event, say, logger):
    say(text="...")  # Reply in the DM channel
```

**Critical differences:**
- NO `ack()` call needed for message events (only slash commands have 3-second deadline)
- Use `say()` instead of `respond()` — `say()` posts a new message in the channel
- `event` dict contains `text`, `channel`, `channel_type`, `user`, `bot_id`, `subtype`

### Slack App Manifest Changes REQUIRED

The current manifest (`slack-app-manifest.yaml`) lacks DM event support. **Two changes are required:**

1. **Add `im:history` bot scope** — required to receive DM messages
2. **Add `message.im` event subscription** — tells Slack to send DM message events to the bot

```yaml
# Add to oauth_config.scopes.bot:
- im:history

# Add new section under settings:
settings:
  event_subscriptions:
    bot_events:
      - message.im
```

**After updating the manifest:** The Slack App must be reinstalled to the workspace (or updated via api.slack.com → App Manifest page) for new scopes to take effect. This is a ONE-TIME manual step.

### Bot Self-Message Prevention

When the bot sends a reply via `say()`, Slack delivers a `message` event for the bot's own message. Without filtering, this creates an infinite loop. **Filter pattern:**

```python
if event.get("bot_id"):
    return  # Skip bot's own messages
if event.get("subtype"):
    return  # Skip message edits, deletes, thread broadcasts, etc.
```

### Command Parsing Strategy

Simple first-word dispatch (case-insensitive):

| User Text | Command | Arguments |
|-----------|---------|-----------|
| `version` | version | (none) |
| `count` | count | (none) |
| `add https://example.com` | add | `https://example.com` |
| `add https://example.com youtube` | add | `https://example.com youtube` |
| `check https://example.com` | check | `https://example.com` |
| `info 1234` | info | `1234` |
| `help` | help | (none) |
| `hello` | (unknown) | → help message |
| (empty) | (empty) | → help message |

**Parse logic:** `text.strip().split(maxsplit=1)` → `[command, args_str]`. Command `.lower()` for case-insensitive matching.

### Help Message Content

When user sends unrecognized text or "help":

```
Available commands:
  version  — Show backend version and build info
  count    — Show document count by type
  add <url> [type]  — Add a URL to the knowledge base
  check <url>  — Check if a URL exists in the database
  info <id>  — Get document details by ID
  help     — Show this help message

Types: webpage, youtube, link, movie, text_message, text (default: webpage)
```

### Existing Code to Reuse (NO modification)

| File | What to Reuse | How |
|------|--------------|-----|
| `src/api_client.py` | `LenieApiClient` methods | Import and call directly |
| `src/api_client.py` | Exception hierarchy | Import `ApiConnectionError`, `ApiResponseError`, `ApiError` |
| `src/commands.py` | `DOCUMENT_TYPES`, `_VALID_TYPES` | Import constants |
| `src/main.py` | App initialization | Add `register_dm_handler()` call after `register_commands()` |

### Files to Create/Modify

| File | Action | Description |
|------|--------|-------------|
| `slack_bot/src/dm_handler.py` | NEW | DM message event handler with text command parsing |
| `slack_bot/src/main.py` | MODIFY | Import + call `register_dm_handler(app, api_client)` (2 lines) |
| `slack_bot/slack-app-manifest.yaml` | MODIFY | Add `im:history` scope + `message.im` event subscription |
| `slack_bot/tests/unit/test_dm_handler.py` | NEW | Unit tests for DM handler |

### Testing Strategy

1. **Test runner:** `cd slack_bot && PYTHONPATH=. .venv/Scripts/python -m pytest tests/unit/ -v` (NOT `uvx pytest`)
2. **Mocking pattern:** Mock `LenieApiClient` methods (return dicts), mock `say` callable, create fake `event` dicts
3. **Expected test count:** ~30-40 new tests (5 commands x 5-6 scenarios + parsing + filtering)
4. **Existing tests:** 108 slack_bot tests must continue to pass (no modification to existing code)
5. **Ruff:** `uvx ruff check slack_bot/` must pass with 0 warnings (line-length=120)

### Error Handling Pattern (same as slash commands)

```python
try:
    data = client.some_method()
    say(text=f"formatted {data['key']}")
except ApiConnectionError:
    say(text="Backend unreachable (connection timeout). Check if lenie-ai-server is running.")
except ApiResponseError as exc:
    logger.warning("Unexpected response from backend: %s", exc.message)
    say(text=f"Unexpected response from backend (HTTP {exc.status_code})")
except ApiError as exc:
    say(text=f"An error occurred: {exc.message}")
except KeyError as exc:
    logger.warning("Unexpected response format: missing key %s", exc)
    say(text="Unexpected response from backend")
```

### Previous Story Intelligence

**From Story 22-1 (NAS Deployment):**
- All 5 slash commands verified on NAS against real backend — field names match
- Bot stays connected when backend down (Socket Mode independent of HTTP)
- `register_commands()` closure pattern is stable — do NOT modify

**From Story 22-2 (API Response Fixes):**
- `get_list()` now uses parameterized SQL queries (no injection)
- `project` filter bug fixed, 8 new backend tests added
- All API field names confirmed correct: `app_version`, `app_build_time`, `document_id`, `id`, `document_type`, `document_state`, `created_at`, `title`, `all_results_count`

**From Epic 21 Retrospective:**
- Error handling boilerplate (~8 lines) duplicated across 5 handlers — acceptable, extract when command count grows
- Test runner: `.venv/Scripts/python -m pytest`, NOT `uvx pytest`
- `register_commands()` closure pattern is stable
- Bare URL detection with confirmation removed from scope (conversational state deferred)

### Git Intelligence

Current branch: `feat/22-3-dm-text-command-parsing` (based on latest main)

Recent relevant commits:
- `3284ab8` — code review fixes for Story 22.2
- `71a6f9e` — Merge PR #56 (fix/slack-bot-add-type-and-check-url)
- `068a58f` — fix project filter column bug
- `0e7d3aa` — NAS deployment (Story 22.1)

### Project Structure Notes

- `slack_bot/` is a standalone project with its own `pyproject.toml`, `Dockerfile`, `.venv`
- Module separation: `commands.py` (slash handlers) / `api_client.py` (HTTP) / `config.py` (config) / `dm_handler.py` (NEW: DM handlers)
- All source in `slack_bot/src/`, tests in `slack_bot/tests/unit/`
- Import pattern: `from src.api_client import ...`, `from src.commands import DOCUMENT_TYPES`
- Ruff linting: `line-length=120`, consistent with backend

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 22.3] — Story definition, acceptance criteria
- [Source: _bmad-output/implementation-artifacts/epic-21-retro-2026-03-02.md] — Deployment-first rationale, DM scope removal
- [Source: _bmad-output/implementation-artifacts/22-1-nas-deployment-end-to-end-verification.md] — NAS deployment learnings
- [Source: _bmad-output/implementation-artifacts/22-2-backend-api-response-fixes-conditional.md] — API fix details
- [Source: slack_bot/src/commands.py] — 5 slash command handlers, error pattern, `DOCUMENT_TYPES`
- [Source: slack_bot/src/api_client.py] — HTTP client, exception hierarchy, `LenieApiClient`
- [Source: slack_bot/src/main.py] — Entry point, `register_commands()` call, Socket Mode init
- [Source: slack_bot/slack-app-manifest.yaml] — Current manifest (needs `im:history` + `message.im`)

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

No issues encountered during implementation.

### Completion Notes List

- Implemented DM text command parsing as a new module `dm_handler.py`, independent from existing slash commands
- All 5 commands (version, count, add, check, info) route through dispatch dict with case-insensitive parsing
- Help message shown for "help" command, unrecognized text, and empty messages
- Bot self-message prevention via `bot_id` check; message subtypes (edits, deletes) filtered out
- Slack App manifest updated with `im:history` scope and `message.im` event subscription
- 59 new unit tests cover all commands, error handling, DM filtering, edge cases, and command parsing
- Full slack_bot test suite: 167 passed (108 existing + 59 new)
- Ruff linting: All checks passed
- Backend tests: 24 passed, 6 pre-existing failures (unrelated markdown/transcript tests), 5 skipped

### Implementation Plan

Simple first-word dispatch pattern: `text.strip().split(maxsplit=1)` → `[command, args_str]`. Command `.lower()` for case-insensitive matching. Dispatch dict maps command keywords to lambda handlers that call the appropriate `_handle_*` function. Error handling follows same pattern as slash commands (ApiConnectionError, ApiResponseError, ApiError, KeyError).

### File List

| File | Action | Description |
|------|--------|-------------|
| `slack_bot/src/dm_handler.py` | NEW | DM message event handler with text command parsing and routing |
| `slack_bot/src/main.py` | MODIFIED | Added import + call to `register_dm_handler(app, api_client)` |
| `slack_bot/slack-app-manifest.yaml` | MODIFIED | Added `im:history` scope + `message.im` event subscription + reinstall note |
| `slack_bot/tests/unit/test_dm_handler.py` | NEW | 62 unit tests for DM handler (59 original + 4 new URL validation - 1 duplicate removed) |

## Change Log

- 2026-03-03: Story 22.3 implemented — DM text command parsing with 5 commands (version, count, add, check, info), help message, and 59 unit tests
- 2026-03-03: Code review (AI) — 7 issues found (0H/3M/4L), all M fixed: removed unused logger param shadowing (M1), added URL format validation for add/check commands (M2), fixed stale branch name in Dev Notes (M3), removed duplicate test (L4). Tests: 170 passed. Status → done.
