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

## Configuration Reference

| Variable | Type | Required | Default | Description |
|----------|------|----------|---------|-------------|
| `SLACK_BOT_TOKEN` | secret | Yes (when bot deployed) | — | Bot User OAuth Token (`xoxb-...`) |
| `SLACK_APP_TOKEN` | secret | Yes (when bot deployed) | — | App-Level Token for Socket Mode (`xapp-...`) |
| `LENIE_API_URL` | config | No | `http://lenie-ai-server:5000` | Backend API base URL |
| `SLACK_CHANNEL_STARTUP` | config | No | `#general` | Channel for bot startup messages |
| `STALKER_API_KEY` | secret | Yes | — | API key for backend authentication |

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
│   └── commands.py          # Slash command handlers
└── tests/
    └── unit/
        ├── test_config.py
        ├── test_main.py
        ├── test_api_client.py
        └── test_commands.py
```
