# Lenie Slack Bot

Optional Slack bot module for the Lenie-AI knowledge management system. Provides slash commands for interacting with the knowledge base directly from Slack.

## Prerequisites

- A Slack workspace (free tier is sufficient)
- Docker and Docker Compose installed
- Lenie-AI backend running (the `lenie-ai-server` service)

## Setup Guide

### Step 1: Create Slack Workspace

If you don't have a Slack workspace yet:

1. Go to [slack.com/create](https://slack.com/create)
2. Follow the prompts to create a new workspace
3. Verify your email address

### Step 2: Create Slack App from Manifest

1. Go to [api.slack.com/apps](https://api.slack.com/apps)
2. Click **Create New App**
3. Select **From an app manifest**
4. Choose your workspace from the dropdown
5. Select **YAML** format
6. Paste the contents of [`slack-app-manifest.yaml`](slack-app-manifest.yaml) from this directory
7. Click **Next**, review the summary, then click **Create**

### Step 3: Enable Socket Mode & Get App-Level Token

1. In your app settings, navigate to **Socket Mode** in the left sidebar
2. Toggle **Enable Socket Mode** to ON (it should already be enabled from the manifest)
3. Navigate to **Basic Information** in the left sidebar
4. Scroll down to **App-Level Tokens**
5. Click **Generate Token and Scopes**
6. Name the token (e.g., "socket-mode")
7. Add the `connections:write` scope
8. Click **Generate**
9. Copy the token — it starts with `xapp-` — this is your `SLACK_APP_TOKEN`

### Step 4: Install App to Workspace & Get Bot Token

1. Navigate to **OAuth & Permissions** in the left sidebar
2. Click **Install to Workspace**
3. Review the permissions and click **Allow**
4. Copy the **Bot User OAuth Token** — it starts with `xoxb-` — this is your `SLACK_BOT_TOKEN`

### Step 5: Configure Secrets

Add the tokens to your secret backend:

**For `.env` backend** (default):

Add to your `infra/docker/.env` file:

```
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_APP_TOKEN=xapp-your-app-token
```

**For Vault or AWS SSM backends:**

See [docs/secrets-management.md](../docs/secrets-management.md) for instructions on storing secrets in Vault or AWS SSM Parameter Store.

### Step 6: Start the Bot

```bash
cd infra/docker
docker compose --profile slack up -d
```

Check the logs to verify successful startup:

```bash
docker compose logs lenie-ai-slack-bot
```

You should see a message like: `Lenie Bot started successfully` and a startup message posted to the configured Slack channel.

### Step 7: Verify

1. Open your Slack workspace
2. Type `/lenie-version` in any channel
3. The bot should respond with the backend version and build info

## Available Commands

| Command | Description | Usage |
|---------|-------------|-------|
| `/lenie-version` | Show backend version and build info | `/lenie-version` |
| `/lenie-count` | Show document count by type | `/lenie-count` |
| `/lenie-add` | Add a URL to the knowledge base | `/lenie-add https://example.com` |
| `/lenie-check` | Check if a URL exists in the database | `/lenie-check https://example.com` |
| `/lenie-info` | Get document details by ID | `/lenie-info 42` |
| `/lenie-search` | Semantic search in knowledge base | `/lenie-search Kubernetes security` |

## LLM Intent Parsing

The bot supports natural language command recognition via LLM. When enabled, if a message doesn't match any keyword command, the bot calls the backend `/ai_parse_intent` endpoint to classify the user's intent.

**Fallback chain:**
1. Keyword match (instant, no LLM cost) — always tried first
2. LLM intent parsing (0.5-2s latency) — only when keyword fails and `INTENT_PARSER_ENABLED=true`
3. Help text — shown when LLM returns "unknown" or is unreachable

**Examples of natural language that works with intent parsing:**
- "how many articles do I have?" → `count` command
- "do I already have this link? https://example.com" → `check` command
- "save this article https://example.com" → `add` command
- "show me document 42" → `info` command
- "find articles about pgvector performance" → `search` command

To enable, set `INTENT_PARSER_ENABLED=true` in your configuration. The default model is `Bielik-11B-v2.3-Instruct` (CloudFerro); override with `INTENT_PARSER_MODEL`.

## Configuration Reference

| Variable | Type | Required | Default | Description |
|----------|------|----------|---------|-------------|
| `SLACK_BOT_TOKEN` | secret | Yes (when bot deployed) | — | Bot User OAuth Token (`xoxb-...`) |
| `SLACK_APP_TOKEN` | secret | Yes (when bot deployed) | — | App-Level Token for Socket Mode (`xapp-...`) |
| `LENIE_API_URL` | config | No | `http://lenie-ai-server:5000` | Backend API base URL |
| `SLACK_CHANNEL_STARTUP` | config | No | `#general` | Channel for bot startup messages |
| `STALKER_API_KEY` | secret | Yes | — | API key for backend authentication |
| `INTENT_PARSER_ENABLED` | config | No | `false` | Enable LLM intent parsing for natural language commands |
| `INTENT_PARSER_MODEL` | config | No | `Bielik-11B-v2.3-Instruct` | LLM model for intent classification |
| `SEARCH_RESULTS_LIMIT` | config | No | `5` | Max number of search results to display |

## Troubleshooting

**Bot doesn't respond to slash commands:**
- Verify Socket Mode is enabled in your app settings
- Check that `SLACK_APP_TOKEN` starts with `xapp-` and has `connections:write` scope
- Check that `SLACK_BOT_TOKEN` starts with `xoxb-`
- Review logs: `docker compose logs lenie-ai-slack-bot`

**"Backend unreachable" error:**
- Verify the backend is running: `docker compose ps`
- Check that `LENIE_API_URL` points to the correct backend address
- Inside Docker network, use `http://lenie-ai-server:5000` (the service name)

**Socket Mode connection fails:**
- Regenerate the App-Level Token with `connections:write` scope
- Ensure your firewall allows outbound WebSocket connections

**Slash commands not appearing in Slack:**
- Reinstall the app: OAuth & Permissions → Install to Workspace
- Verify the manifest was imported correctly — check under Features → Slash Commands

## Development

### Running Tests

```bash
cd slack_bot

# Windows
PYTHONPATH=. .venv/Scripts/python -m pytest tests/unit/ -v

# Linux / macOS
PYTHONPATH=. .venv/bin/python -m pytest tests/unit/ -v
```

### Linting

Run from the **project root** directory:

```bash
uvx ruff check slack_bot/
```

### Project Structure

```
slack_bot/
├── slack-app-manifest.yaml  # Slack App configuration manifest
├── README.md                # This file
├── Dockerfile
├── .dockerignore
├── pyproject.toml
├── src/
│   ├── __init__.py
│   ├── config.py            # Configuration loader wrapper
│   ├── main.py              # App entry point (Socket Mode)
│   ├── api_client.py        # Backend API client
│   ├── commands.py          # Slash command handlers
│   ├── dm_handler.py        # DM text command handler
│   ├── mention_handler.py   # Channel @mention handler
│   ├── intent_parser.py     # LLM intent parser client
│   └── search_formatter.py  # Shared search result formatter
└── tests/
    └── unit/
        ├── test_config.py
        ├── test_main.py
        ├── test_api_client.py
        ├── test_commands.py
        ├── test_dm_handler.py
        ├── test_mention_handler.py
        └── test_intent_parser.py
```
