"""Unit tests for src.commands module."""

from unittest.mock import MagicMock, patch

from src.api_client import ApiConnectionError, ApiError, ApiResponseError
from src.commands import (
    DOCUMENT_TYPES,
    _handle_add,
    _handle_check,
    _handle_count,
    _handle_info,
    _handle_version,
    register_commands,
)



# --- Helpers ---


def _make_mock_client() -> MagicMock:
    return MagicMock()


def _make_ack_respond() -> tuple[MagicMock, MagicMock]:
    return MagicMock(), MagicMock()


# --- Task 5.1: Test /lenie-version success ---


class TestHandleVersion:
    def test_success(self):
        client = _make_mock_client()
        client.get_version.return_value = {
            "app_version": "0.3.13.0",
            "app_build_time": "2026.01.23 04:04",
        }
        ack, respond = _make_ack_respond()

        _handle_version(ack, respond, client)

        ack.assert_called_once()
        respond.assert_called_once()
        text = respond.call_args[1]["text"]
        assert "0.3.13.0" in text
        assert "2026.01.23 04:04" in text

    def test_ack_called_before_respond(self):
        """Verify ack() is called before respond() — Slack 3-second timeout requirement."""
        client = _make_mock_client()
        client.get_version.return_value = {
            "app_version": "1.0.0",
            "app_build_time": "2026-01-01",
        }
        call_order = []
        ack = MagicMock(side_effect=lambda: call_order.append("ack"))
        respond = MagicMock(side_effect=lambda **kw: call_order.append("respond"))

        _handle_version(ack, respond, client)

        assert call_order == ["ack", "respond"]

    # --- Task 5.2: Test /lenie-version with ApiConnectionError ---

    def test_connection_error(self):
        client = _make_mock_client()
        client.get_version.side_effect = ApiConnectionError("timeout")
        ack, respond = _make_ack_respond()

        _handle_version(ack, respond, client)

        ack.assert_called_once()
        text = respond.call_args[1]["text"]
        assert "Backend unreachable" in text
        assert "lenie-ai-server" in text

    # --- Task 5.3: Test /lenie-version with ApiResponseError ---

    def test_response_error(self):
        client = _make_mock_client()
        client.get_version.side_effect = ApiResponseError("bad", status_code=502, response_body="error")
        ack, respond = _make_ack_respond()

        _handle_version(ack, respond, client)

        ack.assert_called_once()
        text = respond.call_args[1]["text"]
        assert "Unexpected response from backend" in text
        assert "502" in text

    def test_generic_api_error(self):
        client = _make_mock_client()
        client.get_version.side_effect = ApiError("something broke")
        ack, respond = _make_ack_respond()

        _handle_version(ack, respond, client)

        ack.assert_called_once()
        text = respond.call_args[1]["text"]
        assert "An error occurred" in text
        assert "something broke" in text

    def test_missing_keys_in_version_response(self):
        """KeyError from missing dict keys should respond with error, not crash."""
        client = _make_mock_client()
        client.get_version.return_value = {"status": "success"}  # missing app_version, app_build_time
        ack, respond = _make_ack_respond()

        _handle_version(ack, respond, client)

        ack.assert_called_once()
        text = respond.call_args[1]["text"]
        assert "Unexpected response from backend" in text

    def test_response_error_logs_warning(self):
        client = _make_mock_client()
        client.get_version.side_effect = ApiResponseError("bad", status_code=502, response_body="error")
        ack, respond = _make_ack_respond()

        with patch("src.commands.logger") as mock_logger:
            _handle_version(ack, respond, client)
            mock_logger.warning.assert_called_once()


# --- Task 5.4: Test /lenie-count success ---


class TestHandleCount:
    def test_success(self):
        client = _make_mock_client()
        # ALL returns 1847, individual types return various counts
        counts = {"ALL": 1847, "webpage": 423, "youtube": 312, "link": 891, "movie": 42, "text_message": 0, "text": 179}
        client.get_count.side_effect = lambda t: counts[t]
        ack, respond = _make_ack_respond()

        _handle_count(ack, respond, client)

        ack.assert_called_once()
        text = respond.call_args[1]["text"]
        assert "1,847" in text
        assert "webpage: 423" in text
        assert "youtube: 312" in text
        assert "link: 891" in text
        assert "movie: 42" in text
        assert "text: 179" in text

    # --- Task 5.6: Test /lenie-count with zero-count types ---

    def test_zero_count_types_omitted(self):
        client = _make_mock_client()
        counts = {"ALL": 10, "webpage": 10, "youtube": 0, "link": 0, "movie": 0, "text_message": 0, "text": 0}
        client.get_count.side_effect = lambda t: counts[t]
        ack, respond = _make_ack_respond()

        _handle_count(ack, respond, client)

        text = respond.call_args[1]["text"]
        assert "webpage: 10" in text
        assert "youtube" not in text
        assert "link" not in text
        assert "movie" not in text
        assert "text_message" not in text
        # "text" could match "text:" so check precisely
        lines = text.strip().split("\n")
        type_lines = [line.strip() for line in lines if line.strip().startswith(("webpage", "youtube", "link", "movie", "text_message", "text:"))]
        assert len(type_lines) == 1
        assert "webpage" in type_lines[0]

    # --- Task 5.5: Test /lenie-count with ApiConnectionError ---

    def test_connection_error(self):
        client = _make_mock_client()
        client.get_count.side_effect = ApiConnectionError("timeout")
        ack, respond = _make_ack_respond()

        _handle_count(ack, respond, client)

        ack.assert_called_once()
        text = respond.call_args[1]["text"]
        assert "Backend unreachable" in text

    def test_response_error(self):
        client = _make_mock_client()
        client.get_count.side_effect = ApiResponseError("bad", status_code=500, response_body="error")
        ack, respond = _make_ack_respond()

        _handle_count(ack, respond, client)

        ack.assert_called_once()
        text = respond.call_args[1]["text"]
        assert "Unexpected response from backend" in text
        assert "500" in text

    def test_generic_api_error(self):
        client = _make_mock_client()
        client.get_count.side_effect = ApiError("count failed")
        ack, respond = _make_ack_respond()

        _handle_count(ack, respond, client)

        ack.assert_called_once()
        text = respond.call_args[1]["text"]
        assert "An error occurred" in text
        assert "count failed" in text

    def test_ack_called_before_respond(self):
        """Verify ack() is called before respond() for /lenie-count — NFR1."""
        client = _make_mock_client()
        counts = {"ALL": 5, "webpage": 5, "youtube": 0, "link": 0, "movie": 0, "text_message": 0, "text": 0}
        client.get_count.side_effect = lambda t: counts[t]
        call_order = []
        ack = MagicMock(side_effect=lambda: call_order.append("ack"))
        respond = MagicMock(side_effect=lambda **kw: call_order.append("respond"))

        _handle_count(ack, respond, client)

        assert call_order == ["ack", "respond"]

    def test_response_error_logs_warning(self):
        client = _make_mock_client()
        client.get_count.side_effect = ApiResponseError("bad", status_code=500, response_body="error")
        ack, respond = _make_ack_respond()

        with patch("src.commands.logger") as mock_logger:
            _handle_count(ack, respond, client)
            mock_logger.warning.assert_called_once()


# --- Task 5.7: Test register_commands() ---


class TestRegisterCommands:
    def test_registers_version_and_count_commands(self):
        app = MagicMock()
        client = _make_mock_client()

        register_commands(app, client)

        # Verify app.command was called for both slash commands
        command_calls = [c for c in app.command.call_args_list]
        registered = {c.args[0] for c in command_calls}
        assert "/lenie-version" in registered
        assert "/lenie-count" in registered

    def test_uses_provided_client(self):
        app = MagicMock()
        client = _make_mock_client()

        register_commands(app, client)

        # Should register commands without creating a new client
        assert app.command.call_count == 5


# --- Task 5.1-5.3: Test /lenie-add ---


class TestHandleAdd:
    def test_success(self):
        """5.1: Mocked add_url(), verify response format with document_id."""
        client = _make_mock_client()
        client.add_url.return_value = {"status": "success", "document_id": 42}
        ack, respond = _make_ack_respond()
        command = {"text": "https://example.com/article"}

        _handle_add(ack, respond, client, command)

        ack.assert_called_once()
        client.add_url.assert_called_once_with("https://example.com/article")
        text = respond.call_args[1]["text"]
        assert "42" in text
        assert "link" in text
        assert "Added to knowledge base" in text

    def test_empty_url(self):
        """5.2: Empty URL — verify usage hint response."""
        client = _make_mock_client()
        ack, respond = _make_ack_respond()
        command = {"text": ""}

        _handle_add(ack, respond, client, command)

        ack.assert_called_once()
        text = respond.call_args[1]["text"]
        assert "Usage:" in text
        assert "/lenie-add" in text
        client.add_url.assert_not_called()

    def test_no_text_key(self):
        """Empty command dict — verify usage hint response."""
        client = _make_mock_client()
        ack, respond = _make_ack_respond()
        command = {}

        _handle_add(ack, respond, client, command)

        ack.assert_called_once()
        text = respond.call_args[1]["text"]
        assert "Usage:" in text

    def test_connection_error(self):
        """5.3: Backend unreachable — verify error message."""
        client = _make_mock_client()
        client.add_url.side_effect = ApiConnectionError("timeout")
        ack, respond = _make_ack_respond()
        command = {"text": "https://example.com/article"}

        _handle_add(ack, respond, client, command)

        ack.assert_called_once()
        text = respond.call_args[1]["text"]
        assert "Backend unreachable" in text

    def test_response_error(self):
        client = _make_mock_client()
        client.add_url.side_effect = ApiResponseError("bad", status_code=500, response_body="error")
        ack, respond = _make_ack_respond()
        command = {"text": "https://example.com/article"}

        _handle_add(ack, respond, client, command)

        text = respond.call_args[1]["text"]
        assert "Unexpected response from backend" in text
        assert "500" in text

    def test_generic_api_error(self):
        client = _make_mock_client()
        client.add_url.side_effect = ApiError("add failed")
        ack, respond = _make_ack_respond()
        command = {"text": "https://example.com/article"}

        _handle_add(ack, respond, client, command)

        text = respond.call_args[1]["text"]
        assert "An error occurred" in text
        assert "add failed" in text

    def test_ack_called_before_respond(self):
        """5.10: Verify ack() called before respond() for /lenie-add."""
        client = _make_mock_client()
        client.add_url.return_value = {"status": "success", "document_id": 1}
        call_order = []
        ack = MagicMock(side_effect=lambda: call_order.append("ack"))
        respond = MagicMock(side_effect=lambda **kw: call_order.append("respond"))
        command = {"text": "https://example.com"}

        _handle_add(ack, respond, client, command)

        assert call_order == ["ack", "respond"]

    def test_response_error_logs_warning(self):
        """5.11: Verify logger.warning() called for ApiResponseError."""
        client = _make_mock_client()
        client.add_url.side_effect = ApiResponseError("bad", status_code=500, response_body="error")
        ack, respond = _make_ack_respond()
        command = {"text": "https://example.com"}

        with patch("src.commands.logger") as mock_logger:
            _handle_add(ack, respond, client, command)
            mock_logger.warning.assert_called_once()

    def test_missing_keys_in_response(self):
        """5.12: KeyError handling — missing document_id in response."""
        client = _make_mock_client()
        client.add_url.return_value = {"status": "success"}  # missing document_id
        ack, respond = _make_ack_respond()
        command = {"text": "https://example.com"}

        _handle_add(ack, respond, client, command)

        ack.assert_called_once()
        text = respond.call_args[1]["text"]
        assert "Unexpected response from backend" in text


# --- Task 5.4-5.6: Test /lenie-check ---


class TestHandleCheck:
    def test_url_found(self):
        """5.4: Mocked check_url() returns doc dict, verify formatted response."""
        client = _make_mock_client()
        client.check_url.return_value = {
            "id": 123,
            "url": "https://example.com/article",
            "document_type": "webpage",
            "document_state": "URL_ADDED",
            "created_at": "2026-01-15 10:30:45",
        }
        ack, respond = _make_ack_respond()
        command = {"text": "https://example.com/article"}

        _handle_check(ack, respond, client, command)

        ack.assert_called_once()
        client.check_url.assert_called_once_with("https://example.com/article")
        text = respond.call_args[1]["text"]
        assert "Found in database (ID: 123)" in text
        assert "webpage" in text
        assert "URL_ADDED" in text
        assert "2026-01-15 10:30:45" in text

    def test_url_not_found(self):
        """5.5: Mocked check_url() returns None, verify 'Not found' message."""
        client = _make_mock_client()
        client.check_url.return_value = None
        ack, respond = _make_ack_respond()
        command = {"text": "https://example.com/new"}

        _handle_check(ack, respond, client, command)

        ack.assert_called_once()
        text = respond.call_args[1]["text"]
        assert "Not found in database." in text

    def test_empty_url(self):
        """5.6: Empty URL — verify usage hint."""
        client = _make_mock_client()
        ack, respond = _make_ack_respond()
        command = {"text": "  "}

        _handle_check(ack, respond, client, command)

        ack.assert_called_once()
        text = respond.call_args[1]["text"]
        assert "Usage:" in text
        assert "/lenie-check" in text
        client.check_url.assert_not_called()

    def test_connection_error(self):
        client = _make_mock_client()
        client.check_url.side_effect = ApiConnectionError("timeout")
        ack, respond = _make_ack_respond()
        command = {"text": "https://example.com"}

        _handle_check(ack, respond, client, command)

        ack.assert_called_once()
        text = respond.call_args[1]["text"]
        assert "Backend unreachable" in text

    def test_response_error(self):
        client = _make_mock_client()
        client.check_url.side_effect = ApiResponseError("bad", status_code=502, response_body="error")
        ack, respond = _make_ack_respond()
        command = {"text": "https://example.com"}

        _handle_check(ack, respond, client, command)

        ack.assert_called_once()
        text = respond.call_args[1]["text"]
        assert "Unexpected response from backend" in text
        assert "502" in text

    def test_generic_api_error(self):
        client = _make_mock_client()
        client.check_url.side_effect = ApiError("check failed")
        ack, respond = _make_ack_respond()
        command = {"text": "https://example.com"}

        _handle_check(ack, respond, client, command)

        ack.assert_called_once()
        text = respond.call_args[1]["text"]
        assert "An error occurred" in text
        assert "check failed" in text

    def test_ack_called_before_respond(self):
        """5.10: Verify ack() called before respond() for /lenie-check."""
        client = _make_mock_client()
        client.check_url.return_value = None
        call_order = []
        ack = MagicMock(side_effect=lambda: call_order.append("ack"))
        respond = MagicMock(side_effect=lambda **kw: call_order.append("respond"))
        command = {"text": "https://example.com"}

        _handle_check(ack, respond, client, command)

        assert call_order == ["ack", "respond"]

    def test_response_error_logs_warning(self):
        """5.11: Verify logger.warning() called for ApiResponseError."""
        client = _make_mock_client()
        client.check_url.side_effect = ApiResponseError("bad", status_code=502, response_body="error")
        ack, respond = _make_ack_respond()
        command = {"text": "https://example.com"}

        with patch("src.commands.logger") as mock_logger:
            _handle_check(ack, respond, client, command)
            mock_logger.warning.assert_called_once()

    def test_missing_keys_in_response(self):
        """5.12: KeyError handling — missing keys in check_url response."""
        client = _make_mock_client()
        client.check_url.return_value = {"id": 123}  # missing document_type, document_state, created_at
        ack, respond = _make_ack_respond()
        command = {"text": "https://example.com"}

        _handle_check(ack, respond, client, command)

        ack.assert_called_once()
        text = respond.call_args[1]["text"]
        assert "Unexpected response from backend" in text


# --- Task 5.7-5.9: Test /lenie-info ---


class TestHandleInfo:
    def test_success(self):
        """5.7: Mocked get_document() returns doc, verify formatted response."""
        client = _make_mock_client()
        client.get_document.return_value = {
            "id": 123,
            "title": "Article Title",
            "document_type": "webpage",
            "document_state": "URL_ADDED",
            "created_at": "2026-01-15 10:30:45",
        }
        ack, respond = _make_ack_respond()
        command = {"text": "123"}

        _handle_info(ack, respond, client, command)

        ack.assert_called_once()
        client.get_document.assert_called_once_with(123)
        text = respond.call_args[1]["text"]
        assert "Document #123" in text
        assert "Article Title" in text
        assert "webpage" in text
        assert "URL_ADDED" in text
        assert "2026-01-15 10:30:45" in text

    def test_non_numeric_id(self):
        """5.8: Non-numeric ID — verify usage hint."""
        client = _make_mock_client()
        ack, respond = _make_ack_respond()
        command = {"text": "abc"}

        _handle_info(ack, respond, client, command)

        ack.assert_called_once()
        text = respond.call_args[1]["text"]
        assert "Usage:" in text
        assert "/lenie-info" in text
        assert "numeric ID required" in text
        client.get_document.assert_not_called()

    def test_empty_input(self):
        """Empty input — verify usage hint."""
        client = _make_mock_client()
        ack, respond = _make_ack_respond()
        command = {"text": ""}

        _handle_info(ack, respond, client, command)

        ack.assert_called_once()
        text = respond.call_args[1]["text"]
        assert "Usage:" in text

    def test_unicode_digit_input(self):
        """Unicode digits (e.g., superscript ²) must not crash — usage hint instead."""
        client = _make_mock_client()
        ack, respond = _make_ack_respond()
        command = {"text": "\u00b2"}  # superscript 2

        _handle_info(ack, respond, client, command)

        ack.assert_called_once()
        text = respond.call_args[1]["text"]
        assert "Usage:" in text
        assert "numeric ID required" in text
        client.get_document.assert_not_called()

    def test_connection_error(self):
        """5.9: Backend unreachable — verify error message."""
        client = _make_mock_client()
        client.get_document.side_effect = ApiConnectionError("timeout")
        ack, respond = _make_ack_respond()
        command = {"text": "123"}

        _handle_info(ack, respond, client, command)

        ack.assert_called_once()
        text = respond.call_args[1]["text"]
        assert "Backend unreachable" in text

    def test_response_error(self):
        client = _make_mock_client()
        client.get_document.side_effect = ApiResponseError("bad", status_code=404, response_body="not found")
        ack, respond = _make_ack_respond()
        command = {"text": "999"}

        _handle_info(ack, respond, client, command)

        text = respond.call_args[1]["text"]
        assert "Unexpected response from backend" in text
        assert "404" in text

    def test_generic_api_error(self):
        client = _make_mock_client()
        client.get_document.side_effect = ApiError("info failed")
        ack, respond = _make_ack_respond()
        command = {"text": "123"}

        _handle_info(ack, respond, client, command)

        text = respond.call_args[1]["text"]
        assert "An error occurred" in text
        assert "info failed" in text

    def test_ack_called_before_respond(self):
        """5.10: Verify ack() called before respond() for /lenie-info."""
        client = _make_mock_client()
        client.get_document.return_value = {
            "id": 1, "title": "T", "document_type": "link",
            "document_state": "URL_ADDED", "created_at": "2026-01-01",
        }
        call_order = []
        ack = MagicMock(side_effect=lambda: call_order.append("ack"))
        respond = MagicMock(side_effect=lambda **kw: call_order.append("respond"))
        command = {"text": "1"}

        _handle_info(ack, respond, client, command)

        assert call_order == ["ack", "respond"]

    def test_response_error_logs_warning(self):
        """5.11: Verify logger.warning() called for ApiResponseError."""
        client = _make_mock_client()
        client.get_document.side_effect = ApiResponseError("bad", status_code=500, response_body="error")
        ack, respond = _make_ack_respond()
        command = {"text": "123"}

        with patch("src.commands.logger") as mock_logger:
            _handle_info(ack, respond, client, command)
            mock_logger.warning.assert_called_once()

    def test_missing_keys_in_response(self):
        """5.12: KeyError handling — missing keys in get_document response."""
        client = _make_mock_client()
        client.get_document.return_value = {"id": 123}  # missing title, document_type, etc.
        ack, respond = _make_ack_respond()
        command = {"text": "123"}

        _handle_info(ack, respond, client, command)

        ack.assert_called_once()
        text = respond.call_args[1]["text"]
        assert "Unexpected response from backend" in text


# --- Task 5.13: Test register_commands() registers all 5 commands ---


class TestRegisterCommandsAll:
    def test_registers_all_five_commands(self):
        """5.13: Verify all 5 commands registered (2 from 21-3 + 3 new)."""
        app = MagicMock()
        client = _make_mock_client()

        register_commands(app, client)

        command_calls = [c for c in app.command.call_args_list]
        registered = {c.args[0] for c in command_calls}
        assert registered == {
            "/lenie-version",
            "/lenie-count",
            "/lenie-add",
            "/lenie-check",
            "/lenie-info",
        }


class TestDocumentTypes:
    def test_all_types_present(self):
        expected = {"webpage", "youtube", "link", "movie", "text_message", "text"}
        assert set(DOCUMENT_TYPES) == expected
