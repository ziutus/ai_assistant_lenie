"""Unit tests for src.main module."""

import logging
from unittest.mock import MagicMock

from src.api_client import ApiConnectionError, ApiError
from src.config import Config
from src.main import check_backend_connectivity, post_startup_message, setup_logging


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


class TestCheckBackendConnectivity:
    """Tests for check_backend_connectivity."""

    def test_logs_success_with_version_info(self, caplog):
        client = MagicMock()
        client.check_health.return_value = {"status": "OK"}
        client.get_version.return_value = {
            "app_version": "0.3.13.0",
            "app_build_time": "2026.01.23 04:04",
        }
        with caplog.at_level(logging.INFO):
            check_backend_connectivity(client)
        assert "Backend connection OK" in caplog.text
        assert "0.3.13.0" in caplog.text
        assert "2026.01.23 04:04" in caplog.text

    def test_logs_warning_on_connection_error(self, caplog):
        client = MagicMock()
        client.check_health.side_effect = ApiConnectionError("Connection refused")
        with caplog.at_level(logging.WARNING):
            check_backend_connectivity(client)
        assert "Backend is NOT reachable" in caplog.text
        assert "Connection refused" in caplog.text

    def test_logs_warning_on_health_api_error(self, caplog):
        client = MagicMock()
        client.check_health.side_effect = ApiError("Internal error")
        with caplog.at_level(logging.WARNING):
            check_backend_connectivity(client)
        assert "Backend health check failed" in caplog.text
        assert "Internal error" in caplog.text

    def test_does_not_raise_on_connection_error(self):
        client = MagicMock()
        client.check_health.side_effect = ApiConnectionError("timeout")
        # Should not raise
        check_backend_connectivity(client)

    def test_health_ok_but_version_fails_logs_info(self, caplog):
        """Backend reachable via /healthz but /version returns error."""
        client = MagicMock()
        client.check_health.return_value = {"status": "OK"}
        client.get_version.side_effect = ApiError("non-JSON response")
        with caplog.at_level(logging.INFO):
            check_backend_connectivity(client)
        assert "Backend is reachable but /version endpoint unavailable" in caplog.text

    def test_does_not_call_version_if_health_fails(self):
        client = MagicMock()
        client.check_health.side_effect = ApiConnectionError("timeout")
        check_backend_connectivity(client)
        client.get_version.assert_not_called()


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
