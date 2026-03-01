# Story 21.5: Slack App Manifest & Setup Documentation

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **developer**,
I want a Slack App manifest and step-by-step README,
So that I can set up the bot from scratch in under 15 minutes.

## Acceptance Criteria

1. **Given** a developer has a free Slack workspace
   **When** they import `slack-app-manifest.yaml` at api.slack.com
   **Then** the Slack App is created with correct permissions (slash commands, Socket Mode, bot scopes)

2. **Given** the README exists
   **When** a developer follows it step-by-step
   **Then** they can go from zero to working bot: create workspace, create App, configure tokens, run `docker compose --profile slack up -d`, verify with `/lenie-version`

3. **Given** Slack tokens are classified as secrets
   **When** reviewing `vars-classification.yaml`
   **Then** `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN` are listed with `classification: secret` and appropriate backend definitions

**Covers:** FR23, FR25 | NFR12

## Tasks / Subtasks

- [x] Task 1: Create Slack App manifest file (AC: #1)
  - [x] 1.1: Create `slack_bot/slack-app-manifest.yaml` with `_metadata` (major_version: 1, minor_version: 1)
  - [x] 1.2: Add `display_information` section (name: "Lenie Bot", description)
  - [x] 1.3: Add `features.bot_user` (display_name: "Lenie Bot", always_online: true)
  - [x] 1.4: Add `features.slash_commands` with all 5 commands: `/lenie-version`, `/lenie-count`, `/lenie-add`, `/lenie-check`, `/lenie-info` — each with description and usage_hint, NO url (Socket Mode)
  - [x] 1.5: Add `oauth_config.scopes.bot` with required scopes: `commands`, `chat:write`, `chat:write.public`
  - [x] 1.6: Add `settings` with `socket_mode_enabled: true`, `org_deploy_enabled: false`, `token_rotation_enabled: false`
  - [x] 1.7: Verify manifest is valid YAML (no syntax errors)

- [x] Task 2: Add Slack variables to vars-classification.yaml (AC: #3)
  - [x] 2.1: Add `slack` group to `groups` section with description "Slack bot tokens and configuration"
  - [x] 2.2: Add `SLACK_BOT_TOKEN` — type: secret, required_when: slack bot deployed, used_by: [docker]
  - [x] 2.3: Add `SLACK_APP_TOKEN` — type: secret, required_when: slack bot deployed, used_by: [docker]
  - [x] 2.4: Add `LENIE_API_URL` — type: config, required: false, default: "http://lenie-ai-server:5000", used_by: [docker]
  - [x] 2.5: Add `SLACK_CHANNEL_STARTUP` — type: config, required: false, default: "#general", used_by: [docker]

- [x] Task 3: Expand slack_bot/README.md with setup documentation (AC: #2)
  - [x] 3.1: Add "Prerequisites" section (Slack workspace, Docker, backend running)
  - [x] 3.2: Add "Step 1: Create Slack Workspace" — link to slack.com/create, brief instructions
  - [x] 3.3: Add "Step 2: Create Slack App from Manifest" — step-by-step at api.slack.com/apps, import manifest, reference `slack-app-manifest.yaml`
  - [x] 3.4: Add "Step 3: Enable Socket Mode & Get App-Level Token" — navigate to Socket Mode, generate token with `connections:write` scope, copy `xapp-...` token
  - [x] 3.5: Add "Step 4: Install App to Workspace & Get Bot Token" — navigate to OAuth & Permissions, install to workspace, copy `xoxb-...` Bot User OAuth Token
  - [x] 3.6: Add "Step 5: Configure Secrets" — add tokens to `.env` file (env backend) or Vault/SSM (vault/aws backend). Reference `docs/secrets-management.md`
  - [x] 3.7: Add "Step 6: Start the Bot" — `docker compose --profile slack up -d`, verify with `docker compose logs lenie-ai-slack-bot`
  - [x] 3.8: Add "Step 7: Verify" — type `/lenie-version` in Slack, expect version response
  - [x] 3.9: Add "Available Commands" section — table with all 5 commands, description, and usage examples
  - [x] 3.10: Add "Troubleshooting" section — common issues (wrong token, backend unreachable, Socket Mode not enabled)
  - [x] 3.11: Add "Development" section — how to run tests, lint, and develop locally

- [x] Task 4: Code quality verification
  - [x] 4.1: Validate manifest YAML syntax (e.g., `python -c "import yaml; yaml.safe_load(open(...))"`)
  - [x] 4.2: Verify vars-classification.yaml is valid YAML after edits
  - [x] 4.3: Verify README renders correctly (markdown syntax check)
  - [x] 4.4: Run existing full test suite — zero regressions (100 tests)

## Dev Notes

### Critical Architecture Constraints

- **Manifest location** (FR23): File must be at `slack_bot/slack-app-manifest.yaml` — referenced in PRD risk mitigation section.
- **Socket Mode ONLY** (PRD): Bot uses Socket Mode (outbound WebSocket), NOT HTTP endpoints. Slash commands in manifest MUST NOT have a `url` field. This is critical — if `url` is present, Slack will try HTTP delivery instead of Socket Mode.
- **No secrets in files** (NFR4): README must explain how to configure tokens via secret backend, NEVER suggest putting tokens directly in `compose.yaml` or code. Always reference `.env` or Vault/SSM.
- **ZERO code dependencies on `backend/`** (NFR8): This story creates ONLY config/doc files. No Python code changes.

### Slack App Manifest Format

The manifest uses Slack's v1 format (version 2 is for Deno SDK only). Key sections:

```yaml
_metadata:
  major_version: 1
  minor_version: 1

display_information:
  name: "Lenie Bot"
  description: "Knowledge base assistant for Lenie-AI"
  background_color: "#2c2d30"

features:
  bot_user:
    display_name: "Lenie Bot"
    always_online: true
  slash_commands:
    - command: /lenie-version
      description: "Show backend version and build info"
      should_escape: false
      # NO url field — Socket Mode delivers via WebSocket
    # ... more commands

oauth_config:
  scopes:
    bot:
      - commands          # Required for slash commands
      - chat:write        # Required for posting messages (startup message, respond)
      - chat:write.public # Required for posting to channels bot hasn't joined

settings:
  socket_mode_enabled: true
  org_deploy_enabled: false
  token_rotation_enabled: false
```

**Important:** Do NOT include `event_subscriptions` or `interactivity` sections — those are for Phase 2+ (DM events, app mentions). Adding them now would request unnecessary permissions.

### Slash Command Definitions

| Command | Description | Usage Hint |
|---------|-------------|------------|
| `/lenie-version` | Show backend version and build info | (no arguments) |
| `/lenie-count` | Show document count by type | (no arguments) |
| `/lenie-add` | Add a URL to the knowledge base | `/lenie-add <url>` |
| `/lenie-check` | Check if a URL exists in the database | `/lenie-check <url>` |
| `/lenie-info` | Get document details by ID | `/lenie-info <document_id>` |

### OAuth Bot Scopes

| Scope | Reason |
|-------|--------|
| `commands` | Required for slash command registration |
| `chat:write` | Required for `respond()` and `chat_postMessage()` (startup message) |
| `chat:write.public` | Required for posting startup message to channels bot hasn't been invited to |

**Do NOT add** `app_mentions:read`, `im:history`, `im:read`, `im:write` — those are for Phase 2/3 (Epics 22-23). Adding them now violates least-privilege principle.

### Token Types

The bot needs TWO tokens:

1. **Bot User OAuth Token** (`xoxb-...`): Used as `SLACK_BOT_TOKEN` in config. Found at OAuth & Permissions page after installing app to workspace. Grants bot scopes defined in manifest.

2. **App-Level Token** (`xapp-...`): Used as `SLACK_APP_TOKEN` in config. Generated at Basic Information > App-Level Tokens. MUST have `connections:write` scope for Socket Mode. This is NOT an OAuth token — it's for the WebSocket connection.

### vars-classification.yaml Updates

Add a new `slack` group after the `app` group:

```yaml
  slack:
    description: "Slack bot tokens and configuration"
    variables:
      SLACK_BOT_TOKEN:
        description: "Slack Bot User OAuth Token (xoxb-...)"
        type: secret
        required_when: "slack bot deployed"
        used_by: [docker]
      SLACK_APP_TOKEN:
        description: "Slack App-Level Token for Socket Mode (xapp-...)"
        type: secret
        required_when: "slack bot deployed"
        used_by: [docker]
      LENIE_API_URL:
        description: "Backend API base URL"
        type: config
        required: false
        default: "http://lenie-ai-server:5000"
        example: "http://lenie-ai-server:5000"
        used_by: [docker]
      SLACK_CHANNEL_STARTUP:
        description: "Channel for bot startup confirmation messages"
        type: config
        required: false
        default: "#general"
        example: "#lenie-bot"
        used_by: [docker]
```

### README Structure

The README should follow this structure:

```
# Lenie Slack Bot
## Prerequisites
## Setup Guide
### Step 1: Create Slack Workspace
### Step 2: Create Slack App from Manifest
### Step 3: Enable Socket Mode & Get App-Level Token
### Step 4: Install App to Workspace & Get Bot Token
### Step 5: Configure Secrets
### Step 6: Start the Bot
### Step 7: Verify
## Available Commands
## Configuration Reference
## Troubleshooting
## Development
```

**Key README guidelines:**
- Use numbered steps with clear action verbs ("Click", "Navigate to", "Copy")
- Include exact URLs where possible (e.g., `https://api.slack.com/apps`)
- Do NOT include screenshots (they become outdated) — use text descriptions of UI elements
- Reference `docs/secrets-management.md` for Vault/SSM configuration details
- Keep it under ~200 lines — comprehensive but not overwhelming

### Existing Configuration Variables in Code

From `main.py`, the bot uses these config variables:
- `SLACK_BOT_TOKEN` — via `cfg.require("SLACK_BOT_TOKEN")` (no default, required)
- `SLACK_APP_TOKEN` — via `cfg.require("SLACK_APP_TOKEN")` (no default, required)
- `SLACK_CHANNEL_STARTUP` — via `cfg.require("SLACK_CHANNEL_STARTUP", "#general")` (default: #general)
- `LENIE_API_URL` — via `cfg.require("LENIE_API_URL", "http://lenie-ai-server:5000")` (default: Docker service name)

From `api_client.py`, used via `create_client(cfg)`:
- `LENIE_API_URL` — base URL for backend
- `STALKER_API_KEY` — API key for x-api-key header (already in vars-classification.yaml under `app` group)

### Docker Compose Configuration

The `lenie-ai-slack-bot` service is already defined in `infra/docker/compose.yaml`:

```yaml
  lenie-ai-slack-bot:
    build:
      context: ../..
      dockerfile: slack_bot/Dockerfile
    profiles: ["slack"]
    env_file: .env
    depends_on:
      - lenie-ai-server
    restart: unless-stopped
```

**No changes needed to compose.yaml.** The service reads all config from `.env` (for env backend) or from Vault/SSM (for vault/aws backends — bootstrap vars in `.env`).

### Testing Strategy

This story is documentation/config only — no Python code changes. Verification:

1. **YAML validation**: Parse both `slack-app-manifest.yaml` and `vars-classification.yaml` with Python's yaml module
2. **Full test suite**: Run 100 existing tests to confirm zero regressions
3. **Manual verification**: Developer imports manifest at api.slack.com and confirms App is created correctly

```bash
# Validate YAML files
cd slack_bot && python -c "import yaml; yaml.safe_load(open('slack-app-manifest.yaml'))"
cd .. && python -c "import yaml; yaml.safe_load(open('scripts/vars-classification.yaml'))"

# Run full test suite (should still be 100 tests, zero failures)
cd slack_bot && PYTHONPATH=. .venv/Scripts/python -m pytest tests/unit/ -v
```

### Previous Story Learnings (21-4 Code Review)

Key takeaways from Sprint 7 stories:
1. **isdigit() Unicode bug** — reminded that input validation edge cases matter. For this story, ensure manifest YAML has no edge cases (e.g., special characters in descriptions).
2. **KeyError handling** — API response format assumptions are fragile. Document the expected Slack API behavior in README troubleshooting.
3. **File List accuracy** — always verify actual line counts match claims in completion notes.
4. **Test coverage** — even for non-code stories, validate that existing tests still pass after file changes.

### Project Structure After This Story

```
slack_bot/
├── slack-app-manifest.yaml  # ← NEW: Slack App configuration manifest (FR23)
├── README.md                # ← MODIFIED: Expanded with full setup guide (FR25)
├── Dockerfile               # (Story 21-1) — unchanged
├── .dockerignore             # (Story 21-1) — unchanged
├── pyproject.toml            # (Story 21-1) — unchanged
├── src/
│   ├── __init__.py           # (Story 21-1) — unchanged
│   ├── config.py             # (Story 21-1) — unchanged
│   ├── main.py               # (Story 21-3) — unchanged
│   ├── api_client.py         # (Story 21-2) — unchanged
│   └── commands.py           # (Story 21-4) — unchanged
├── tests/
│   └── unit/
│       ├── test_config.py    # (Story 21-1) — unchanged
│       ├── test_main.py      # (Story 21-1) — unchanged
│       ├── test_api_client.py # (Story 21-2) — unchanged
│       └── test_commands.py  # (Story 21-4) — unchanged

scripts/
└── vars-classification.yaml  # ← MODIFIED: Added slack group with 4 variables
```

### Dependencies on Other Stories

- **Story 21-1** (done): Project structure, Dockerfile, compose.yaml service definition, config.py
- **Story 21-2** (done): api_client.py — uses STALKER_API_KEY (already in vars-classification.yaml)
- **Story 21-3** (done): /lenie-version, /lenie-count commands
- **Story 21-4** (done): /lenie-add, /lenie-check, /lenie-info commands
- **All 5 commands implemented** — manifest references all of them

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 21.5](../../_bmad-output/planning-artifacts/epics.md) — Story definition, acceptance criteria
- [Source: _bmad-output/planning-artifacts/prd.md#Risk Mitigation](../../_bmad-output/planning-artifacts/prd.md) — Manifest location decision, risk mitigation strategy
- [Source: _bmad-output/planning-artifacts/prd.md#Technical Context](../../_bmad-output/planning-artifacts/prd.md) — Docker deployment, secrets management approach
- [Source: slack_bot/src/main.py](../src/main.py) — Config variable usage (SLACK_BOT_TOKEN, SLACK_APP_TOKEN, SLACK_CHANNEL_STARTUP, LENIE_API_URL)
- [Source: slack_bot/src/api_client.py](../src/api_client.py) — Config variable usage (LENIE_API_URL, STALKER_API_KEY)
- [Source: scripts/vars-classification.yaml](../../scripts/vars-classification.yaml) — SSOT for configuration variables
- [Source: infra/docker/compose.yaml](../../infra/docker/compose.yaml) — Docker service definition for lenie-ai-slack-bot
- [Source: docs/secrets-management.md](../../docs/secrets-management.md) — Vault/SSM setup documentation
- [Slack App Manifest Reference](https://docs.slack.dev/reference/app-manifest/) — Official Slack documentation
- [Socket Mode Documentation](https://docs.slack.dev/apis/events-api/using-socket-mode/) — Socket Mode setup guide

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

None — clean implementation with no issues encountered.

### Completion Notes List

- Created `slack_bot/slack-app-manifest.yaml` (49 lines) — Slack App Manifest v1 with all 5 slash commands, Socket Mode enabled, no `url` fields on commands, 3 bot scopes (commands, chat:write, chat:write.public). No event_subscriptions or interactivity sections (Phase 2+ only). Commands without arguments omit `usage_hint` field (avoids empty placeholder in Slack UI).
- Updated `scripts/vars-classification.yaml` — added `slack` group with 4 variables (27 new lines): SLACK_BOT_TOKEN (secret), SLACK_APP_TOKEN (secret), LENIE_API_URL (config, default: http://lenie-ai-server:5000), SLACK_CHANNEL_STARTUP (config, default: #general). Group placed between `app` and `integrations` sections.
- Expanded `slack_bot/README.md` (172 lines) — full setup guide with 7 numbered steps (workspace creation, app import, Socket Mode token, bot token, secret config, Docker start, verification), Available Commands table, Configuration Reference table, Troubleshooting section (4 common issues), Development section with cross-platform test commands (Windows + Linux/macOS). References docs/secrets-management.md for Vault/SSM. No secrets in file.
- YAML validation passed for both slack-app-manifest.yaml and vars-classification.yaml.
- Full test suite: 100 tests passed, 0 failures, 0 regressions.

### Change Log

- 2026-03-01: Story 21-5 implementation complete. Created Slack App manifest, added slack variables to vars-classification.yaml, expanded README with full setup documentation. All 4 tasks completed, all 3 ACs satisfied.
- 2026-03-01: Code review (Claude Opus 4.6). 6 issues found (3M/3L). All 3 MEDIUM fixed: removed empty usage_hint from manifest, added cross-platform test paths to README, corrected line counts in completion notes.

### File List

- `slack_bot/slack-app-manifest.yaml` — NEW: Slack App configuration manifest (49 lines)
- `slack_bot/README.md` — MODIFIED: Expanded from 12 to 172 lines with full setup guide
- `scripts/vars-classification.yaml` — MODIFIED: Added `slack` group with 4 variables (27 new lines)
- `_bmad-output/implementation-artifacts/21-5-slack-app-manifest-setup-documentation.md` — MODIFIED: Task checkboxes, Dev Agent Record, File List, Change Log, Status
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — MODIFIED: Story status ready-for-dev → in-progress → review
