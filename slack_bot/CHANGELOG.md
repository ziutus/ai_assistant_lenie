# Changelog

All notable changes to the Lenie Slack Bot will be documented in this file.

## [0.3.0] - 2026-03-05

### Added
- LLM intent parsing for natural language commands (Epic 24, Story 24.1)
- Backend endpoint `POST /ai_parse_intent` — classifies natural language into structured commands via LLM
- `backend/library/ai_intent_parser.py` — intent parsing logic with system prompt, JSON response validation, confidence threshold
- `slack_bot/src/intent_parser.py` — thin client calling backend endpoint, returns `ParsedIntent` dataclass
- `LenieApiClient.parse_intent()` and `search_similar()` methods
- LLM fallback chain: keyword match (instant) → LLM intent parsing → help text
- Config variables: `INTENT_PARSER_ENABLED`, `INTENT_PARSER_MODEL`
- 27 backend unit tests, 8 slack_bot intent parser tests, 8+5 handler integration tests

### Changed
- `dm_handler.register_dm_handler()` accepts `intent_enabled` parameter
- `mention_handler.register_mention_handler()` accepts `intent_enabled` parameter
- `main.py` reads `INTENT_PARSER_ENABLED` config and passes to handlers

## [0.2.0] - 2026-03-04

### Added
- Channel `@Lenie` mention support (Epic 23) — same command set as DMs, responses posted as thread replies
- `mention_handler.py` — handles `app_mention` events, strips bot mention prefix, routes to shared handlers
- Slack manifest: `app_mentions:read` OAuth scope and `app_mention` bot event subscription

### Changed
- Handler functions in `dm_handler.py` renamed from private (`_handle_*`) to public (`handle_*`) for reuse by mention handler

## [0.1.0] - 2026-02-15

### Added
- Initial release with Socket Mode connection
- Slash commands: `/lenie-version`, `/lenie-count`, `/lenie-add`, `/lenie-check`, `/lenie-info`
- DM text command handler (Epic 22) — same commands via direct messages
- Backend API client with health checks and error handling
- JSON structured logging
- Startup message posted to configured channel
