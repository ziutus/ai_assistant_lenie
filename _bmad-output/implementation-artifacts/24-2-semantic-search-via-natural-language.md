# Story 24.2: Semantic Search via Natural Language

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **user**,
I want to search my knowledge base with natural language ("articles about Kubernetes security"),
so that I can find relevant documents without knowing exact titles or IDs.

## Acceptance Criteria

1. **Given** the bot is connected and embeddings exist in the database
   **When** user types `/lenie-search Kubernetes security`
   **Then** bot calls `/website_similar` and responds with top results (title, type, similarity score)

2. **Given** the bot is in a DM with LLM enabled
   **When** user sends "find articles about pgvector performance"
   **Then** LLM maps to `search` intent, bot calls `/website_similar` and returns similar documents

3. **Given** the bot is mentioned on a channel
   **When** user posts `@Lenie search Kubernetes security`
   **Then** bot responds in a thread with search results

4. **Given** no similar documents are found (cosine similarity below threshold)
   **When** user searches for an obscure topic
   **Then** bot responds: "No similar documents found for '<query>'."

5. **Given** the query is empty
   **When** user types `/lenie-search` without arguments
   **Then** bot responds with usage hint: "Usage: `/lenie-search <query>`"

6. **Given** the backend is unreachable
   **When** user types `/lenie-search <query>`
   **Then** bot responds with user-friendly error message (same pattern as other commands)

## Tasks / Subtasks

- [x] Task 1: Add `/lenie-search` slash command handler (AC: #1, #4, #5, #6)
  - [x] 1.1 Add `handle_search(ack, command, client_instance)` to `slack_bot/src/commands.py`
  - [x] 1.2 Register `/lenie-search` slash command in `commands.py` via `register_commands()`
  - [x] 1.3 Format results as Slack message (title, URL, type, similarity %)
  - [x] 1.4 Handle empty query with usage hint
  - [x] 1.5 Handle empty results with "No similar documents found" message
  - [x] 1.6 Handle backend errors with user-friendly message
  - [x] 1.7 Unit tests for search command handler (10 tests)

- [x] Task 2: Add `search` command to DM handler (AC: #2, #4, #5, #6)
  - [x] 2.1 Add `handle_search(say, client, args_str)` function to `dm_handler.py`
  - [x] 2.2 Register "search" in DM commands dict in `register_dm_handler()`
  - [x] 2.3 `_route_intent()` already wired for search (from Story 24-1); now routes to real handler
  - [x] 2.4 Unit tests for DM search command (9 tests: 7 handler + 2 routing)

- [x] Task 3: Add `search` command to mention handler (AC: #3, #4, #5, #6)
  - [x] 3.1 Register "search" in mention commands dict in `register_mention_handler()`
  - [x] 3.2 Thread response works for search results (verified by tests)
  - [x] 3.3 Unit tests for mention search command (4 tests: 3 routing + 1 intent)

- [x] Task 4: Create shared search result formatter (AC: #1, #4)
  - [x] 4.1 Created `slack_bot/src/search_formatter.py` with `format_search_results()` function
  - [x] 4.2 Include: result number, title (or URL if no title), document type, similarity percentage
  - [x] 4.3 Limit display to top 5 results (configurable via `SEARCH_RESULTS_LIMIT` env var, default 5)
  - [x] 4.4 Unit tests for formatter (13 tests)

- [x] Task 5: Update Slack App manifest and documentation (AC: all)
  - [x] 5.1 Add `/lenie-search` to `slack_bot/slack-app-manifest.yaml`
  - [x] 5.2 Update help text in `dm_handler.py` (shared via HELP_TEXT, used by mention_handler too)
  - [x] 5.3 Update `slack_bot/README.md` with search command documentation
  - [x] 5.4 Bump slack_bot version to 0.4.0

## Dev Notes

### Architecture & Implementation Patterns

- **Backend endpoint is FULLY IMPLEMENTED**: `POST /website_similar` accepts `{"search": "<query>", "limit": N}` and returns `{"status": "success", "websites": [...]}` with pgvector cosine similarity search
- **API client method EXISTS**: `slack_bot/src/api_client.py:134` — `search_similar(query, limit=5)` already calls `/website_similar`
- **Intent parser already recognizes "search"**: `backend/library/ai_intent_parser.py` has `search` in `allowed_commands` with extraction of `{query: str}` arg
- **No new backend code needed** — this story is purely Slack bot integration work

### Key Code Patterns to Follow

Follow the EXACT patterns established in Story 24-1 and Epic 21-23:

1. **Slash command handler pattern** — see `commands.py` existing handlers (e.g., `handle_info`):
   ```python
   def handle_search(ack, command, client_instance):
       ack()
       query = command.get("text", "").strip()
       if not query:
           command["respond"](text="Usage: `/lenie-search <query>`")
           return
       # ... call client_instance.search_similar(query) ...
   ```

2. **DM command handler pattern** — see `dm_handler.py` existing handlers:
   - Commands dict maps string → handler function: `{"search": handle_search, ...}`
   - Handler signature: `def handle_search(say, args_str)`

3. **Mention handler pattern** — see `mention_handler.py`:
   - Same commands dict pattern as DM handler
   - Responses go to thread (already handled by mention handler framework)

4. **Error handling pattern** — all commands use try/except around API calls with user-friendly messages:
   ```python
   except LenieApiError as e:
       say(text=f"Error searching: {e.user_message}")
   ```

5. **Intent routing** — `_route_intent()` in `dm_handler.py` (line 180+) must be updated to handle `search` command with `intent.args.get("query", "")` as parameter

### Result Formatting

The `/website_similar` response contains objects with these fields (from `stalker_web_documents_db_postgresql.py:get_similar()`):
- `website_id` — document ID
- `title` — document title (may be None)
- `url` — document URL
- `document_type` — type (webpage, youtube, link, movie)
- `similarity` — cosine similarity score (0.0–1.0)
- `language` — document language
- `text` — embedded text chunk (don't display — too long)

**Recommended Slack format:**
```
Found 3 results for "Kubernetes security":

1. *Kubernetes Security Best Practices* (webpage, 87%)
   https://example.com/k8s-security

2. *CKS Exam Prep Guide* (link, 72%)
   https://example.com/cks-guide

3. *K8s Network Policies* (youtube, 65%)
   https://youtube.com/watch?v=abc123
```

### Critical Implementation Details

- **`api_client.search_similar()` returns `list[dict]`** — already implemented, returns `data.get("websites", [])` (line 137)
- **Similarity is a float 0.0–1.0** — multiply by 100 and format as percentage for display
- **Default limit is 5** in `api_client.search_similar()` — keep this as default, make configurable
- **Minimum similarity threshold is 0.30** (30%) — set in backend `get_similar()`, no need to override
- **SQL injection warning**: `get_similar()` in `stalker_web_documents_db_postgresql.py` uses f-string interpolation (tracked in B-86) — this is a known issue, do NOT fix in this story
- **The `text` field in results can be very large** — do NOT include it in Slack messages

### Testing Standards

- Follow existing test patterns in `slack_bot/tests/unit/`
- Mock `api_client.search_similar()` in all tests — no real backend
- Test cases: valid query, empty query, no results, backend error, large result set
- Use `pytest` with `PYTHONPATH=.` from `slack_bot/` directory
- All tests must pass `ruff check` (line-length=120)

### Project Structure Notes

- All changes in `slack_bot/` directory — no backend changes needed
- New files: none expected (add to existing modules)
- Modified files:
  - `slack_bot/src/commands.py` — add search slash command handler
  - `slack_bot/src/dm_handler.py` — add search to DM commands, update `_route_intent()`, update help text
  - `slack_bot/src/mention_handler.py` — add search to mention commands, update help text
  - `slack_bot/src/main.py` — register `/lenie-search` slash command
  - `slack_bot/slack-app-manifest.yaml` — add `/lenie-search` command definition
  - `slack_bot/README.md` — document search command
  - `slack_bot/pyproject.toml` — version bump to 0.4.0
  - `slack_bot/tests/unit/test_commands.py` — search command tests
  - `slack_bot/tests/unit/test_dm_handler.py` — DM search tests
  - `slack_bot/tests/unit/test_mention_handler.py` — mention search tests

### Previous Story Intelligence (24-1)

From Story 24-1 (LLM Intent Parser) implementation:
- Intent parser system prompt already includes `search` command with `{query: str}` arg
- Fallback chain: keyword match → LLM parse → help text — search must be added to keyword matching
- `_route_intent()` currently handles: `check` (with URL arg), `add` (with URL arg), `info` (with ID arg) — add `search` (with query arg)
- DM handler line ~204: unrecognized intents fall through to `handler(say, "")` — search must be explicitly routed
- Code review found issues with unused imports and dead params — be thorough with cleanup
- 214 total slack_bot tests after 24-1 — maintain test count growth pattern

### Git Intelligence

Recent commits show:
- `027dac3` — feat: add LLM intent parser with Bielik v3.0 support (Epic 24, Story 24-1)
- `c9d01c5` — feat: add channel @mention support for Slack bot (Epic 23)
- Pattern: feature commits use `feat: <description> (Epic N, Story N-M)` format

### References

- [Source: `slack_bot/src/api_client.py`#search_similar — lines 134-137]
- [Source: `slack_bot/src/commands.py` — existing slash command patterns]
- [Source: `slack_bot/src/dm_handler.py`#_route_intent — lines 180-208]
- [Source: `slack_bot/src/mention_handler.py` — mention command registration]
- [Source: `backend/server.py`#search_similar — `/website_similar` endpoint, lines 433-469]
- [Source: `backend/library/stalker_web_documents_db_postgresql.py`#get_similar — pgvector query, lines 194-248]
- [Source: `backend/library/ai_intent_parser.py` — search in allowed_commands]
- [Source: `_bmad-output/planning-artifacts/epics.md`#Story 24.2 — requirements]
- [Source: `_bmad-output/implementation-artifacts/24-1-llm-intent-parser.md` — previous story learnings]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

None — clean implementation with no debug issues.

### Completion Notes List

- Created shared `search_formatter.py` module with `format_search_results()` and configurable `SEARCH_RESULTS_LIMIT`
- Added `_handle_search()` slash command handler in `commands.py` following existing patterns (ack, respond, error handling)
- Added `handle_search()` DM handler in `dm_handler.py` with same error handling pattern
- Registered "search" in both DM and mention handler command dicts
- `_route_intent()` already had search routing from Story 24-1 — now routes to real handler instead of "not yet available"
- Updated HELP_TEXT to include `search <query>` command
- Added `/lenie-search` to Slack app manifest
- Updated README with search command, LLM example, config reference, project structure
- Bumped version to 0.4.0
- 250 total tests (36 new: 10 commands, 9 DM, 4 mention, 13 formatter), all passing
- Ruff linting clean

### File List

- `slack_bot/src/search_formatter.py` — NEW: shared search result formatter
- `slack_bot/src/commands.py` — MODIFIED: added `_handle_search()`, registered `/lenie-search`
- `slack_bot/src/dm_handler.py` — MODIFIED: added `handle_search()`, registered in commands dict, updated HELP_TEXT
- `slack_bot/src/mention_handler.py` — MODIFIED: imported `handle_search`, registered in commands dict
- `slack_bot/src/__init__.py` — MODIFIED: version bump 0.3.0 → 0.4.0
- `slack_bot/slack-app-manifest.yaml` — MODIFIED: added `/lenie-search` command definition
- `slack_bot/README.md` — MODIFIED: added search command docs, config reference, project structure
- `slack_bot/tests/unit/test_search_formatter.py` — NEW: 13 unit tests for formatter
- `slack_bot/tests/unit/test_commands.py` — MODIFIED: 10 search tests, updated registration tests
- `slack_bot/tests/unit/test_dm_handler.py` — MODIFIED: 9 search tests, updated help/intent tests
- `slack_bot/tests/unit/test_mention_handler.py` — MODIFIED: 4 search tests
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — MODIFIED: status update
- `_bmad-output/implementation-artifacts/24-2-semantic-search-via-natural-language.md` — MODIFIED: task completion
