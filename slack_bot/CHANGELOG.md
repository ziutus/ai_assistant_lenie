# Changelog

All notable changes to the Lenie Slack Bot will be documented in this file.

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
