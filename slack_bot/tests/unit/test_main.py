"""Unit tests for src.main module."""

import logging
from unittest.mock import MagicMock

from src.config import Config
from src.main import post_startup_message, setup_logging


class TestSetupLogging:
    """Tests for setup_logging."""

    def teardown_method(self):
        """Clean up root logger handlers."""
        logging.getLogger().handlers.clear()

    def test_configures_json_formatter(self):
        setup_logging()
        root = logging.getLogger()
        assert len(root.handlers) == 1
        assert root.handlers[0].formatter is not None

    def test_sets_info_level(self):
        setup_logging()
        root = logging.getLogger()
        assert root.level == logging.INFO


class TestPostStartupMessage:
    """Tests for post_startup_message."""

    def test_posts_message_with_version_and_backend(self):
        app = MagicMock()
        cfg = Config({"SLACK_CHANNEL_STARTUP": "#test", "LENIE_API_URL": "http://localhost:5000"})
        post_startup_message(app, cfg)
        app.client.chat_postMessage.assert_called_once()
        call_kwargs = app.client.chat_postMessage.call_args[1]
        assert call_kwargs["channel"] == "#test"
        assert "Version" in call_kwargs["text"]
        assert "http://localhost:5000" in call_kwargs["text"]

    def test_uses_default_channel(self):
        app = MagicMock()
        cfg = Config({})
        post_startup_message(app, cfg)
        call_kwargs = app.client.chat_postMessage.call_args[1]
        assert call_kwargs["channel"] == "#general"

    def test_uses_default_backend_url(self):
        app = MagicMock()
        cfg = Config({})
        post_startup_message(app, cfg)
        call_kwargs = app.client.chat_postMessage.call_args[1]
        assert "http://lenie-ai-server:5000" in call_kwargs["text"]

    def test_handles_api_error_gracefully(self):
        app = MagicMock()
        app.client.chat_postMessage.side_effect = Exception("API error")
        cfg = Config({})
        # Should not raise
        post_startup_message(app, cfg)
