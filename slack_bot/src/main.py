"""Lenie Slack Bot entry point — Socket Mode connection and startup.

Connects to Slack via Socket Mode, configures JSON structured logging,
and posts a startup confirmation message.
"""

from __future__ import annotations

import logging
import sys
from threading import Event
from typing import Any

from pythonjsonlogger import jsonlogger

from src import __version__
from src.api_client import ApiConnectionError, ApiError, LenieApiClient, create_client
from src.commands import register_commands
from src.dm_handler import register_dm_handler
from src.health_monitor import HealthMonitor
from src.mention_handler import register_mention_handler
from src.config import Config, load_config


def setup_logging() -> None:
    """Configure JSON structured logging to stdout."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        jsonlogger.JsonFormatter(
            fmt="%(asctime)s %(name)s %(levelname)s %(message)s",
        )
    )
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)


def check_backend_connectivity(client: LenieApiClient) -> None:
    """Check if the Lenie backend is reachable by calling GET /healthz."""
    logger = logging.getLogger(__name__)
    try:
        client.check_health()
    except ApiConnectionError as exc:
        logger.warning("Backend is NOT reachable: %s", exc.message)
        return
    except ApiError as exc:
        logger.warning("Backend health check failed: %s", exc.message)
        return

    try:
        data = client.get_version()
        logger.info(
            "Backend connection OK — version %s, build %s",
            data.get("app_version", "unknown"),
            data.get("app_build_time", "unknown"),
        )
    except ApiError:
        logger.info("Backend is reachable but /version endpoint unavailable")


def post_startup_message(app: Any, cfg: Config) -> None:
    """Post startup confirmation message to the configured channel."""
    channel = cfg.require("SLACK_CHANNEL_STARTUP", "#general")
    api_url = cfg.require("LENIE_API_URL", "http://lenie-ai-server:5000")
    text = f"Lenie Bot connected. Version {__version__}. Backend: {api_url}"

    try:
        app.client.chat_postMessage(channel=channel, text=text)
        logging.getLogger(__name__).info("Startup message posted to %s", channel)
    except Exception as exc:
        logging.getLogger(__name__).warning("Failed to post startup message: %s", exc)


def main() -> None:
    """Initialize config, Slack app, and start Socket Mode handler."""
    setup_logging()
    logger = logging.getLogger(__name__)

    logger.info("Lenie Slack Bot v%s starting...", __version__)

    try:
        cfg = load_config()
    except SystemExit:
        raise
    except Exception as exc:
        logger.error("Failed to load configuration: %s", exc)
        sys.exit(1)

    bot_token = cfg.require("SLACK_BOT_TOKEN")
    app_token = cfg.require("SLACK_APP_TOKEN")

    try:
        from slack_bolt import App
        from slack_bolt.adapter.socket_mode import SocketModeHandler
    except ImportError:
        logger.error("slack-bolt package is required. Install: uv sync (or pip install slack-bolt)")
        sys.exit(1)

    api_client = create_client(cfg)
    intent_enabled = cfg.get("INTENT_PARSER_ENABLED", "false").lower() == "true"
    if intent_enabled:
        logger.info("LLM intent parsing is ENABLED")

    app = App(token=bot_token)
    register_commands(app, api_client)
    register_dm_handler(app, api_client, intent_enabled=intent_enabled)
    register_mention_handler(app, api_client, intent_enabled=intent_enabled)

    handler = SocketModeHandler(app, app_token)
    handler.connect()
    logger.info("Socket Mode connection established")

    check_backend_connectivity(api_client)
    post_startup_message(app, cfg)

    # Start health monitor if enabled
    health_monitor = None
    health_enabled = cfg.get("HEALTH_CHECK_ENABLED", "false").lower() == "true"
    if health_enabled:
        health_user_id = cfg.get("HEALTH_CHECK_USER_ID", "")
        if not health_user_id:
            logger.warning("HEALTH_CHECK_ENABLED=true but HEALTH_CHECK_USER_ID not set — health monitor disabled")
        else:
            try:
                health_interval = int(cfg.get("HEALTH_CHECK_INTERVAL", "300"))
            except ValueError:
                logger.warning("HEALTH_CHECK_INTERVAL is not a valid integer, using default 300s")
                health_interval = 300
            health_monitor = HealthMonitor(
                api_client=api_client,
                slack_client=app.client,
                alert_user_id=health_user_id,
                interval=health_interval,
            )
            health_monitor.start()
            logger.info("Health monitor started (interval: %ds, user: %s)", health_interval, health_user_id)

    logger.info("Bot is running. Press Ctrl+C to stop.")
    try:
        Event().wait()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        if health_monitor is not None:
            health_monitor.stop()
        handler.close()


if __name__ == "__main__":
    main()
