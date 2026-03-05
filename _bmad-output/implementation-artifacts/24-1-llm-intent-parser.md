# Story 24.1: LLM Intent Parser

Status: done

## Story

As a **user**,
I want to ask the bot questions in natural language ("how many articles do I have?"),
so that I don't need to remember specific command syntax.

## Acceptance Criteria

1. **Given** the bot is in a DM and LLM is configured, **When** user sends "how many articles do I have?", **Then** LLM interprets intent as `count` command, bot responds with document count.

2. **Given** the bot is in a DM, **When** user sends "do I already have this link? https://example.com", **Then** LLM interprets intent as `check` command with URL, bot responds with found/not-found.

3. **Given** the LLM service is unreachable, **When** user sends a natural language message, **Then** bot falls back to direct text parsing (Epic 22 logic) and responds or shows help.

4. **Given** the LLM cannot determine intent, **When** user sends ambiguous message, **Then** bot responds: "I'm not sure what you mean. Available commands: version, count, check, add, info".

**Covers:** FR12, FR13 | NFR3, NFR9

## Tasks / Subtasks

- [x] Task 1: Add `/ai_parse_intent` backend endpoint (AC: #1, #2, #3, #4)
  - [x] 1.1 Create `backend/library/ai_intent_parser.py` — system prompt + LLM call via existing `ai.py` → returns structured JSON `{command, args, confidence}`
  - [x] 1.2 Add `POST /ai_parse_intent` route in `server.py` — accepts `{text: str}`, returns `{command, args, confidence}` or `{command: "unknown"}`
  - [x] 1.3 Add unit tests for intent parser (prompt construction, response parsing, edge cases)
  - [x] 1.4 Add `INTENT_PARSER_MODEL` and `INTENT_PARSER_ENABLED` to `vars-classification.yaml`

- [x] Task 2: Add `intent_parser.py` to slack_bot (AC: #1, #2, #3, #4)
  - [x] 2.1 Create `slack_bot/src/intent_parser.py` — calls backend `/ai_parse_intent`, returns `ParsedIntent` dataclass
  - [x] 2.2 Add `parse_intent()` and `search_similar()` methods to `LenieApiClient` in `api_client.py`
  - [x] 2.3 Unit tests for intent_parser module (success, fallback, timeout)

- [x] Task 3: Integrate intent parsing into DM handler (AC: #1, #2, #3)
  - [x] 3.1 Modify `dm_handler.py`: if keyword match fails AND intent parsing enabled → call intent parser → route to command handler
  - [x] 3.2 Preserve existing keyword matching as primary path (zero latency for explicit commands)
  - [x] 3.3 Unit tests for DM handler with intent parsing (keyword match, LLM fallback, LLM failure fallback)

- [x] Task 4: Integrate intent parsing into mention handler (AC: #1, #2, #3)
  - [x] 4.1 Modify `mention_handler.py`: same fallback-to-LLM pattern as DM handler
  - [x] 4.2 Thread responses preserved for LLM-parsed commands
  - [x] 4.3 Unit tests for mention handler with intent parsing

- [x] Task 5: Configuration and documentation (AC: #3)
  - [x] 5.1 Add config vars to `vars-classification.yaml`
  - [x] 5.2 Update `slack_bot/README.md` with LLM intent parsing section
  - [x] 5.3 Bump version to 0.3.0 in `slack_bot/src/__init__.py`, update CHANGELOG.md

## Dev Notes

### Architecture Decision: Backend Endpoint vs Direct LLM Call

**Recommended: New backend endpoint `/ai_parse_intent`** (Option A).

Rationale:
- Reuses existing `backend/library/ai.py` multi-provider LLM routing (OpenAI, Bedrock, Vertex AI, Bielik)
- No LLM config duplication in slack_bot — backend already has `OPENAI_API_KEY`, `LLM_PROVIDER`, model vars
- Slack bot stays a thin REST client (established pattern from Epics 21-23)
- Single place to tune prompts, change models, add caching
- Follows NFR8: "Bot communicates exclusively via HTTP REST API"

**Do NOT:**
- Add `openai` dependency to slack_bot
- Duplicate LLM provider routing logic
- Store LLM API keys in slack_bot config

### Intent Parser Design

**System prompt approach** — send a system prompt defining available commands and expected JSON output, then user's natural language text as the user message.

Available commands to map to:
| Command | Args | Example natural language |
|---------|------|------------------------|
| `version` | none | "what version is running?" |
| `count` | none | "how many articles do I have?" |
| `check` | `{url: str}` | "do I already have this link? https://..." |
| `add` | `{url: str, type?: str}` | "save this article https://..." |
| `info` | `{id: int}` | "show me document 42" |
| `search` | `{query: str}` | "find articles about Kubernetes" (Story 24.2) |
| `unknown` | none | ambiguous or unrelated text |

**Response format** (JSON):
```json
{
  "command": "check",
  "args": {"url": "https://example.com"},
  "confidence": 0.95
}
```

**Confidence threshold:** If confidence < 0.5, treat as `unknown` and show help text.

**Model recommendation:** Default to `Bielik-11B-v2.3-Instruct` (CloudFerro — prepaid package already purchased, supports Polish natively). If Bielik proves insufficient for intent classification accuracy during testing, fall back to `gpt-4o-mini` or `amazon.nova-micro`. Intent parsing is a simple classification task; start with the model that's already paid for.

### Fallback Chain (Critical)

```
User message
  → 1. Keyword match (existing dm_handler/mention_handler logic) — instant, no LLM cost
  → 2. If no keyword match AND INTENT_PARSER_ENABLED=true:
       → Call POST /ai_parse_intent {text: message}
       → If success + confidence >= 0.5: route to command handler
       → If success + confidence < 0.5: show "I'm not sure..." + help
  → 3. If LLM unreachable (timeout, error): show help text (Epic 22 fallback)
```

**CRITICAL:** Existing keyword commands MUST work identically with or without LLM. LLM is an additive fallback, not a replacement.

### Existing Code to Reuse (Do NOT Reinvent)

| What | Where | How to use |
|------|-------|-----------|
| LLM multi-provider router | `backend/library/ai.py` → `ai_ask()` | Call from new intent parser module |
| OpenAI client | `backend/library/api/openai/openai_my.py` → `OpenAIClient` | Used internally by `ai_ask()` |
| Bedrock client | `backend/library/api/aws/bedrock_ask.py` | Used internally by `ai_ask()` |
| API client pattern | `slack_bot/src/api_client.py` → `LenieApiClient` | Add `parse_intent()` method |
| DM command handlers | `slack_bot/src/dm_handler.py` → `handle_*()` functions | Reuse after intent parsing |
| Error hierarchy | `slack_bot/src/api_client.py` → `ApiError`, `ApiConnectionError` | Handle LLM endpoint errors |
| Config loading | `backend/library/config_loader.py` → `get_config()` | Load `INTENT_PARSER_MODEL`, `INTENT_PARSER_ENABLED` |

### Config Variables to Add

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `INTENT_PARSER_ENABLED` | config | `false` | Enable/disable LLM intent parsing |
| `INTENT_PARSER_MODEL` | config | `Bielik-11B-v2.3-Instruct` | LLM model for intent classification (Bielik default, fallback: gpt-4o-mini) |

Add to `scripts/vars-classification.yaml` under the `llm` group.

### Project Structure Notes

**New files:**
- `backend/library/ai_intent_parser.py` — intent parsing logic (system prompt, response parsing)
- `backend/tests/unit/test_ai_intent_parser.py` — unit tests
- `slack_bot/src/intent_parser.py` — thin wrapper calling backend endpoint

**Modified files:**
- `backend/server.py` — add `POST /ai_parse_intent` route
- `slack_bot/src/api_client.py` — add `parse_intent()` method
- `slack_bot/src/dm_handler.py` — add LLM fallback after keyword mismatch
- `slack_bot/src/mention_handler.py` — add LLM fallback after keyword mismatch
- `slack_bot/src/__init__.py` — version bump to 0.3.0
- `slack_bot/CHANGELOG.md` — add v0.3.0 entry
- `scripts/vars-classification.yaml` — add INTENT_PARSER_ENABLED, INTENT_PARSER_MODEL

### Testing Requirements

**Backend tests** (`backend/tests/unit/test_ai_intent_parser.py`):
- System prompt construction
- JSON response parsing (valid, malformed, empty)
- Confidence threshold logic
- Unknown command handling
- Model selection from config

**Slack bot tests** (`slack_bot/tests/unit/test_intent_parser.py`):
- Successful intent parsing via API client
- API timeout fallback (returns None → keyword help text shown)
- API error fallback (ApiConnectionError → keyword help text shown)

**Slack bot handler tests** (update existing):
- `test_dm_handler.py`: keyword match still works, LLM fallback when no keyword match, LLM disabled path
- `test_mention_handler.py`: same patterns as DM handler tests

**Run tests:**
```bash
# Backend
cd backend && PYTHONPATH=. uvx pytest tests/unit/test_ai_intent_parser.py -v

# Slack bot
cd slack_bot && PYTHONPATH=. .venv/Scripts/python -m pytest tests/unit/ -v
```

### Security Notes

- `/ai_parse_intent` endpoint MUST require `x-api-key` header (same as all other endpoints)
- Never log raw user text at INFO level (could contain sensitive URLs/data) — use DEBUG
- LLM system prompt must not leak internal architecture details in responses
- Sanitize LLM JSON response before processing (prevent injection via crafted LLM output)

### Performance Notes

- Keyword matching is instant (< 1ms) — always try first
- LLM call adds 0.5-2s latency — only used when keyword match fails
- Use cheapest viable model (`gpt-4o-mini`: ~$0.15/1M input tokens)
- Consider adding response caching in backend for repeated queries (future optimization, NOT in scope)

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Epic 24]
- [Source: _bmad-output/planning-artifacts/prd.md — FR12, FR13, NFR3, NFR9]
- [Source: backend/library/ai.py — LLM router pattern]
- [Source: slack_bot/src/dm_handler.py — current command parsing]
- [Source: slack_bot/src/api_client.py — API client pattern]
- [Source: scripts/vars-classification.yaml — config variable SSOT]

## Dev Agent Record

### Agent Model Used
Claude Opus 4.6

### Debug Log References
- boto3 import cascade: `ai_intent_parser.py` initially had top-level `from library.ai import ai_ask` which triggered boto3 import in test env. Fixed with lazy imports inside `parse_intent()`.
- `@patch` decorator failure: `library/` has no `__init__.py`, so `@patch("library.ai.ai_ask")` failed. Fixed using `patch.dict(sys.modules, {...})`.

### Completion Notes List
- All 5 tasks completed successfully
- 27 backend unit tests (test_ai_intent_parser.py) — all passing
- 214 slack_bot unit tests — all passing (8 intent_parser, 9 dm_handler intent, 5 mention_handler intent, rest existing)
- Ruff linting clean for both backend and slack_bot
- Lazy imports used in `ai_intent_parser.py` to avoid cascading heavy dependencies (boto3, openai) in test environment
- `_route_intent()` helper maps ParsedIntent args to existing handler function signatures

### Code Review Fixes (2026-03-05)
- **H1**: Removed unused `CONFIDENCE_THRESHOLD` import from `server.py` (ruff F401)
- **H2**: Removed unused `client` parameter from `_route_intent()`, added type hints
- **M1**: Added "not yet available" message for LLM-parsed commands without handlers (e.g. `search`)
- **M3**: Added input length limit (2000 chars) and documented prompt injection limitation in `ai_intent_parser.py`
- **M4**: Added test for unimplemented command scenario (`test_llm_unimplemented_command_shows_not_available`)

### File List

**New files:**
- `backend/library/ai_intent_parser.py` — intent parsing logic with system prompt, JSON response validation, confidence threshold
- `backend/tests/unit/test_ai_intent_parser.py` — 27 unit tests (19 response parsing + 8 integration with mocked LLM)
- `slack_bot/src/intent_parser.py` — thin client calling backend `/ai_parse_intent`, returns `ParsedIntent` dataclass
- `slack_bot/tests/unit/test_intent_parser.py` — 8 unit tests

**Modified files:**
- `backend/server.py` — added `POST /ai_parse_intent` endpoint, gated by `INTENT_PARSER_ENABLED`
- `scripts/vars-classification.yaml` — added `INTENT_PARSER_ENABLED` and `INTENT_PARSER_MODEL` under `llm` group
- `slack_bot/src/api_client.py` — added `parse_intent()` and `search_similar()` methods to `LenieApiClient`
- `slack_bot/src/dm_handler.py` — added `intent_enabled` parameter, `_route_intent()` helper, LLM fallback chain
- `slack_bot/src/mention_handler.py` — added `intent_enabled` parameter, LLM fallback chain with thread_ts preservation
- `slack_bot/src/main.py` — reads `INTENT_PARSER_ENABLED` config, passes `intent_enabled` to handlers
- `slack_bot/src/__init__.py` — version bumped from `0.2.0` to `0.3.0`
- `slack_bot/CHANGELOG.md` — added v0.3.0 entry
- `slack_bot/README.md` — added LLM Intent Parsing section, updated config reference and project structure
- `slack_bot/tests/unit/test_dm_handler.py` — added `TestDmIntentParsing` class (8 tests)
- `slack_bot/tests/unit/test_mention_handler.py` — added `TestMentionIntentParsing` class (5 tests)

