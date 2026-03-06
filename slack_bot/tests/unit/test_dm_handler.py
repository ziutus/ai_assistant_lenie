"""Unit tests for src.dm_handler module."""

from unittest.mock import MagicMock, patch

from src.api_client import ApiConnectionError, ApiError, ApiResponseError
from src.dm_handler import (
    HELP_TEXT,
    handle_add,
    handle_check,
    handle_count,
    handle_info,
    handle_search,
    handle_version,
    register_dm_handler,
)
from src.intent_parser import ParsedIntent


# --- Helpers ---


def _make_mock_client() -> MagicMock:
    return MagicMock()


def _make_say() -> MagicMock:
    return MagicMock()


def _make_dm_event(text: str = "", **overrides) -> dict:
    """Create a fake DM message event dict."""
    event = {
        "type": "message",
        "channel": "D123ABC",
        "channel_type": "im",
        "user": "U456DEF",
        "text": text,
        "ts": "1234567890.123456",
    }
    event.update(overrides)
    return event


# --- Test DM version handler ---


class TestDmHandleVersion:
    def test_success(self):
        client = _make_mock_client()
        client.get_version.return_value = {
            "app_version": "0.3.13.0",
            "app_build_time": "2026.01.23 04:04",
        }
        say = _make_say()

        handle_version(say, client)

        say.assert_called_once()
        text = say.call_args[1]["text"]
        assert "0.3.13.0" in text
        assert "2026.01.23 04:04" in text

    def test_connection_error(self):
        client = _make_mock_client()
        client.get_version.side_effect = ApiConnectionError("timeout")
        say = _make_say()

        handle_version(say, client)

        text = say.call_args[1]["text"]
        assert "Backend unreachable" in text
        assert "lenie-ai-server" in text

    def test_response_error(self):
        client = _make_mock_client()
        client.get_version.side_effect = ApiResponseError("bad", status_code=502, response_body="error")
        say = _make_say()

        handle_version(say, client)

        text = say.call_args[1]["text"]
        assert "Unexpected response from backend" in text
        assert "502" in text

    def test_generic_api_error(self):
        client = _make_mock_client()
        client.get_version.side_effect = ApiError("something broke")
        say = _make_say()

        handle_version(say, client)

        text = say.call_args[1]["text"]
        assert "An error occurred" in text
        assert "something broke" in text

    def test_missing_keys(self):
        client = _make_mock_client()
        client.get_version.return_value = {"status": "success"}
        say = _make_say()

        handle_version(say, client)

        text = say.call_args[1]["text"]
        assert "Unexpected response from backend" in text

    def test_response_error_logs_warning(self):
        client = _make_mock_client()
        client.get_version.side_effect = ApiResponseError("bad", status_code=502, response_body="error")
        say = _make_say()

        with patch("src.dm_handler.logger") as mock_logger:
            handle_version(say, client)
            mock_logger.warning.assert_called_once()


# --- Test DM count handler ---


class TestDmHandleCount:
    def test_success(self):
        client = _make_mock_client()
        client.get_all_counts.return_value = {
            "ALL": 1847, "webpage": 423, "youtube": 312, "link": 891, "movie": 42, "text_message": 0, "text": 179,
        }
        say = _make_say()

        handle_count(say, client)

        client.get_all_counts.assert_called_once()
        text = say.call_args[1]["text"]
        assert "1,847" in text
        assert "webpage: 423" in text
        assert "youtube: 312" in text
        assert "link: 891" in text
        assert "movie: 42" in text
        assert "text: 179" in text

    def test_zero_count_types_omitted(self):
        client = _make_mock_client()
        client.get_all_counts.return_value = {"ALL": 10, "webpage": 10}
        say = _make_say()

        handle_count(say, client)

        text = say.call_args[1]["text"]
        assert "webpage: 10" in text
        lines = text.strip().split("\n")
        type_lines = [
            line.strip()
            for line in lines
            if line.strip().startswith(("webpage", "youtube", "link", "movie", "text_message", "text:"))
        ]
        assert len(type_lines) == 1

    def test_connection_error(self):
        client = _make_mock_client()
        client.get_all_counts.side_effect = ApiConnectionError("timeout")
        say = _make_say()

        handle_count(say, client)

        text = say.call_args[1]["text"]
        assert "Backend unreachable" in text

    def test_response_error(self):
        client = _make_mock_client()
        client.get_all_counts.side_effect = ApiResponseError("bad", status_code=500, response_body="error")
        say = _make_say()

        handle_count(say, client)

        text = say.call_args[1]["text"]
        assert "Unexpected response from backend" in text
        assert "500" in text

    def test_generic_api_error(self):
        client = _make_mock_client()
        client.get_all_counts.side_effect = ApiError("count failed")
        say = _make_say()

        handle_count(say, client)

        text = say.call_args[1]["text"]
        assert "An error occurred" in text
        assert "count failed" in text


# --- Test DM add handler ---


class TestDmHandleAdd:
    def test_success_default_type(self):
        client = _make_mock_client()
        client.add_url.return_value = {"status": "success", "document_id": 42}
        say = _make_say()

        handle_add(say, client, "https://example.com/article")

        client.add_url.assert_called_once_with("https://example.com/article", url_type="webpage")
        text = say.call_args[1]["text"]
        assert "42" in text
        assert "webpage" in text
        assert "Added to knowledge base" in text

    def test_success_explicit_type(self):
        client = _make_mock_client()
        client.add_url.return_value = {"status": "success", "document_id": 99}
        say = _make_say()

        handle_add(say, client, "https://youtube.com/watch?v=abc youtube")

        client.add_url.assert_called_once_with("https://youtube.com/watch?v=abc", url_type="youtube")
        text = say.call_args[1]["text"]
        assert "99" in text
        assert "youtube" in text

    def test_invalid_url_no_scheme(self):
        client = _make_mock_client()
        say = _make_say()

        handle_add(say, client, "example.com")

        client.add_url.assert_not_called()
        text = say.call_args[1]["text"]
        assert "http://" in text or "https://" in text

    def test_invalid_url_plain_text(self):
        client = _make_mock_client()
        say = _make_say()

        handle_add(say, client, "hello")

        client.add_url.assert_not_called()
        text = say.call_args[1]["text"]
        assert "http://" in text or "https://" in text

    def test_too_many_arguments(self):
        client = _make_mock_client()
        say = _make_say()

        handle_add(say, client, "https://example.com webpage extra stuff")

        client.add_url.assert_not_called()
        text = say.call_args[1]["text"]
        assert "Too many arguments" in text

    def test_invalid_type(self):
        client = _make_mock_client()
        say = _make_say()

        handle_add(say, client, "https://example.com badtype")

        client.add_url.assert_not_called()
        text = say.call_args[1]["text"]
        assert "Unknown type" in text

    def test_empty_args(self):
        client = _make_mock_client()
        say = _make_say()

        handle_add(say, client, "")

        text = say.call_args[1]["text"]
        assert "Usage:" in text
        client.add_url.assert_not_called()

    def test_whitespace_only_args(self):
        client = _make_mock_client()
        say = _make_say()

        handle_add(say, client, "   ")

        text = say.call_args[1]["text"]
        assert "Usage:" in text
        client.add_url.assert_not_called()

    def test_connection_error(self):
        client = _make_mock_client()
        client.add_url.side_effect = ApiConnectionError("timeout")
        say = _make_say()

        handle_add(say, client, "https://example.com/article")

        text = say.call_args[1]["text"]
        assert "Backend unreachable" in text

    def test_response_error(self):
        client = _make_mock_client()
        client.add_url.side_effect = ApiResponseError("bad", status_code=500, response_body="error")
        say = _make_say()

        handle_add(say, client, "https://example.com/article")

        text = say.call_args[1]["text"]
        assert "Unexpected response from backend" in text
        assert "500" in text

    def test_generic_api_error(self):
        client = _make_mock_client()
        client.add_url.side_effect = ApiError("add failed")
        say = _make_say()

        handle_add(say, client, "https://example.com/article")

        text = say.call_args[1]["text"]
        assert "An error occurred" in text
        assert "add failed" in text

    def test_missing_keys(self):
        client = _make_mock_client()
        client.add_url.return_value = {"status": "success"}
        say = _make_say()

        handle_add(say, client, "https://example.com")

        text = say.call_args[1]["text"]
        assert "Unexpected response from backend" in text


# --- Test DM check handler ---


class TestDmHandleCheck:
    def test_url_found(self):
        client = _make_mock_client()
        client.check_url.return_value = {
            "id": 123,
            "url": "https://example.com/article",
            "document_type": "webpage",
            "document_state": "URL_ADDED",
            "created_at": "2026-01-15 10:30:45",
        }
        say = _make_say()

        handle_check(say, client, "https://example.com/article")

        client.check_url.assert_called_once_with("https://example.com/article")
        text = say.call_args[1]["text"]
        assert "Found in database (ID: 123)" in text
        assert "webpage" in text
        assert "URL_ADDED" in text
        assert "2026-01-15 10:30:45" in text

    def test_url_not_found(self):
        client = _make_mock_client()
        client.check_url.return_value = None
        say = _make_say()

        handle_check(say, client, "https://example.com/new")

        text = say.call_args[1]["text"]
        assert "Not found in database." in text

    def test_invalid_url_no_scheme(self):
        client = _make_mock_client()
        say = _make_say()

        handle_check(say, client, "example.com")

        client.check_url.assert_not_called()
        text = say.call_args[1]["text"]
        assert "http://" in text or "https://" in text

    def test_invalid_url_plain_text(self):
        client = _make_mock_client()
        say = _make_say()

        handle_check(say, client, "random-text")

        client.check_url.assert_not_called()
        text = say.call_args[1]["text"]
        assert "http://" in text or "https://" in text

    def test_empty_url(self):
        client = _make_mock_client()
        say = _make_say()

        handle_check(say, client, "")

        text = say.call_args[1]["text"]
        assert "Usage:" in text
        client.check_url.assert_not_called()

    def test_whitespace_only(self):
        client = _make_mock_client()
        say = _make_say()

        handle_check(say, client, "   ")

        text = say.call_args[1]["text"]
        assert "Usage:" in text
        client.check_url.assert_not_called()

    def test_connection_error(self):
        client = _make_mock_client()
        client.check_url.side_effect = ApiConnectionError("timeout")
        say = _make_say()

        handle_check(say, client, "https://example.com")

        text = say.call_args[1]["text"]
        assert "Backend unreachable" in text

    def test_response_error(self):
        client = _make_mock_client()
        client.check_url.side_effect = ApiResponseError("bad", status_code=502, response_body="error")
        say = _make_say()

        handle_check(say, client, "https://example.com")

        text = say.call_args[1]["text"]
        assert "Unexpected response from backend" in text
        assert "502" in text

    def test_generic_api_error(self):
        client = _make_mock_client()
        client.check_url.side_effect = ApiError("check failed")
        say = _make_say()

        handle_check(say, client, "https://example.com")

        text = say.call_args[1]["text"]
        assert "An error occurred" in text
        assert "check failed" in text

    def test_missing_keys(self):
        client = _make_mock_client()
        client.check_url.return_value = {"id": 123}
        say = _make_say()

        handle_check(say, client, "https://example.com")

        text = say.call_args[1]["text"]
        assert "Unexpected response from backend" in text


# --- Test DM info handler ---


class TestDmHandleInfo:
    def test_success(self):
        client = _make_mock_client()
        client.get_document.return_value = {
            "id": 123,
            "title": "Article Title",
            "document_type": "webpage",
            "document_state": "URL_ADDED",
            "created_at": "2026-01-15 10:30:45",
        }
        say = _make_say()

        handle_info(say, client, "123")

        client.get_document.assert_called_once_with(123)
        text = say.call_args[1]["text"]
        assert "Document #123" in text
        assert "Article Title" in text
        assert "webpage" in text
        assert "URL_ADDED" in text
        assert "2026-01-15 10:30:45" in text

    def test_non_numeric_id(self):
        client = _make_mock_client()
        say = _make_say()

        handle_info(say, client, "abc")

        text = say.call_args[1]["text"]
        assert "Usage:" in text
        assert "numeric ID required" in text
        client.get_document.assert_not_called()

    def test_empty_input(self):
        client = _make_mock_client()
        say = _make_say()

        handle_info(say, client, "")

        text = say.call_args[1]["text"]
        assert "Usage:" in text

    def test_unicode_digit_input(self):
        client = _make_mock_client()
        say = _make_say()

        handle_info(say, client, "\u00b2")  # superscript 2

        text = say.call_args[1]["text"]
        assert "Usage:" in text
        assert "numeric ID required" in text
        client.get_document.assert_not_called()

    def test_connection_error(self):
        client = _make_mock_client()
        client.get_document.side_effect = ApiConnectionError("timeout")
        say = _make_say()

        handle_info(say, client, "123")

        text = say.call_args[1]["text"]
        assert "Backend unreachable" in text

    def test_response_error(self):
        client = _make_mock_client()
        client.get_document.side_effect = ApiResponseError("bad", status_code=404, response_body="not found")
        say = _make_say()

        handle_info(say, client, "999")

        text = say.call_args[1]["text"]
        assert "Unexpected response from backend" in text
        assert "404" in text

    def test_generic_api_error(self):
        client = _make_mock_client()
        client.get_document.side_effect = ApiError("info failed")
        say = _make_say()

        handle_info(say, client, "123")

        text = say.call_args[1]["text"]
        assert "An error occurred" in text
        assert "info failed" in text

    def test_missing_keys(self):
        client = _make_mock_client()
        client.get_document.return_value = {"id": 123}
        say = _make_say()

        handle_info(say, client, "123")

        text = say.call_args[1]["text"]
        assert "Unexpected response from backend" in text


# --- Test DM search handler ---


class TestDmHandleSearch:
    def test_success(self):
        client = _make_mock_client()
        client.search_similar.return_value = [
            {"title": "K8s Guide", "url": "https://example.com/k8s", "document_type": "webpage", "similarity": 0.87},
        ]
        say = _make_say()

        handle_search(say, client, "Kubernetes security")

        client.search_similar.assert_called_once_with("Kubernetes security")
        text = say.call_args[1]["text"]
        assert "K8s Guide" in text
        assert "87%" in text

    def test_empty_query(self):
        client = _make_mock_client()
        say = _make_say()

        handle_search(say, client, "")

        text = say.call_args[1]["text"]
        assert "Usage:" in text
        client.search_similar.assert_not_called()

    def test_whitespace_only(self):
        client = _make_mock_client()
        say = _make_say()

        handle_search(say, client, "   ")

        text = say.call_args[1]["text"]
        assert "Usage:" in text
        client.search_similar.assert_not_called()

    def test_no_results(self):
        client = _make_mock_client()
        client.search_similar.return_value = []
        say = _make_say()

        handle_search(say, client, "obscure xyz")

        text = say.call_args[1]["text"]
        assert "No similar documents found" in text

    def test_connection_error(self):
        client = _make_mock_client()
        client.search_similar.side_effect = ApiConnectionError("timeout")
        say = _make_say()

        handle_search(say, client, "test query")

        text = say.call_args[1]["text"]
        assert "Backend unreachable" in text

    def test_response_error(self):
        client = _make_mock_client()
        client.search_similar.side_effect = ApiResponseError("bad", status_code=500, response_body="error")
        say = _make_say()

        handle_search(say, client, "test query")

        text = say.call_args[1]["text"]
        assert "Unexpected response from backend" in text
        assert "500" in text

    def test_generic_api_error(self):
        client = _make_mock_client()
        client.search_similar.side_effect = ApiError("search failed")
        say = _make_say()

        handle_search(say, client, "test query")

        text = say.call_args[1]["text"]
        assert "An error occurred" in text
        assert "search failed" in text


# --- Test DM event filtering and parsing ---


class TestDmEventFiltering:
    """Test that the message event handler properly filters non-DM messages."""

    def _register_and_get_handler(self, client=None):
        """Register DM handler and return the event handler function."""
        app = MagicMock()
        if client is None:
            client = _make_mock_client()
        register_dm_handler(app, client)
        # The handler is registered via @app.event("message")
        app.event.assert_called_once_with("message")
        # Get the decorator and the function it wraps
        return app.event.return_value

    def test_registers_message_event(self):
        app = MagicMock()
        client = _make_mock_client()

        register_dm_handler(app, client)

        app.event.assert_called_once_with("message")

    def test_non_dm_message_ignored(self):
        """Messages in channels (not DM) should be ignored."""
        app = MagicMock()
        client = _make_mock_client()
        register_dm_handler(app, client)

        # Get the actual handler function passed to the decorator
        handler_fn = app.event.return_value.call_args[0][0]
        event = _make_dm_event("version", channel_type="channel")
        say = _make_say()

        handler_fn(event=event, say=say)

        say.assert_not_called()

    def test_bot_message_ignored(self):
        """Bot's own messages should be ignored to prevent infinite loops."""
        app = MagicMock()
        client = _make_mock_client()
        register_dm_handler(app, client)

        handler_fn = app.event.return_value.call_args[0][0]
        event = _make_dm_event("version", bot_id="B123")
        say = _make_say()

        handler_fn(event=event, say=say)

        say.assert_not_called()

    def test_message_subtype_ignored(self):
        """Message subtypes (edits, deletes) should be ignored."""
        app = MagicMock()
        client = _make_mock_client()
        register_dm_handler(app, client)

        handler_fn = app.event.return_value.call_args[0][0]
        event = _make_dm_event("version", subtype="message_changed")
        say = _make_say()

        handler_fn(event=event, say=say)

        say.assert_not_called()

    def test_empty_text_shows_help(self):
        """Empty text message should show help."""
        app = MagicMock()
        client = _make_mock_client()
        register_dm_handler(app, client)

        handler_fn = app.event.return_value.call_args[0][0]
        event = _make_dm_event("")
        say = _make_say()

        handler_fn(event=event, say=say)

        text = say.call_args[1]["text"]
        assert "Available commands:" in text

    def test_none_text_shows_help(self):
        """None text (missing key) should show help."""
        app = MagicMock()
        client = _make_mock_client()
        register_dm_handler(app, client)

        handler_fn = app.event.return_value.call_args[0][0]
        event = _make_dm_event("")
        event.pop("text")  # No text key at all
        say = _make_say()

        handler_fn(event=event, say=say)

        text = say.call_args[1]["text"]
        assert "Available commands:" in text

    def test_whitespace_only_shows_help(self):
        """Whitespace-only text should show help."""
        app = MagicMock()
        client = _make_mock_client()
        register_dm_handler(app, client)

        handler_fn = app.event.return_value.call_args[0][0]
        event = _make_dm_event("   ")
        say = _make_say()

        handler_fn(event=event, say=say)

        text = say.call_args[1]["text"]
        assert "Available commands:" in text


# --- Test DM command parsing and routing ---


class TestDmCommandParsing:
    """Test text command parsing via the full event handler."""

    def _get_handler(self, client=None):
        """Register and return the message event handler."""
        app = MagicMock()
        if client is None:
            client = _make_mock_client()
            client.get_version.return_value = {"app_version": "1.0", "app_build_time": "2026-01-01"}
        register_dm_handler(app, client)
        return app.event.return_value.call_args[0][0], client

    def test_version_command(self):
        handler_fn, client = self._get_handler()
        event = _make_dm_event("version")
        say = _make_say()

        handler_fn(event=event, say=say)

        client.get_version.assert_called_once()
        text = say.call_args[1]["text"]
        assert "1.0" in text

    def test_version_case_insensitive(self):
        handler_fn, client = self._get_handler()
        event = _make_dm_event("VERSION")
        say = _make_say()

        handler_fn(event=event, say=say)

        client.get_version.assert_called_once()

    def test_version_mixed_case(self):
        handler_fn, client = self._get_handler()
        event = _make_dm_event("VeRsIoN")
        say = _make_say()

        handler_fn(event=event, say=say)

        client.get_version.assert_called_once()

    def test_count_command(self):
        client = _make_mock_client()
        client.get_all_counts.return_value = {"ALL": 5, "webpage": 5}
        handler_fn, _ = self._get_handler(client)
        event = _make_dm_event("count")
        say = _make_say()

        handler_fn(event=event, say=say)

        client.get_all_counts.assert_called_once()
        text = say.call_args[1]["text"]
        assert "5 total" in text

    def test_add_command(self):
        client = _make_mock_client()
        client.add_url.return_value = {"status": "success", "document_id": 42}
        handler_fn, _ = self._get_handler(client)
        event = _make_dm_event("add https://example.com")
        say = _make_say()

        handler_fn(event=event, say=say)

        client.add_url.assert_called_once_with("https://example.com", url_type="webpage")

    def test_add_command_with_type(self):
        client = _make_mock_client()
        client.add_url.return_value = {"status": "success", "document_id": 99}
        handler_fn, _ = self._get_handler(client)
        event = _make_dm_event("add https://example.com youtube")
        say = _make_say()

        handler_fn(event=event, say=say)

        client.add_url.assert_called_once_with("https://example.com", url_type="youtube")

    def test_add_with_invalid_type(self):
        client = _make_mock_client()
        handler_fn, _ = self._get_handler(client)
        event = _make_dm_event("add https://example.com badtype")
        say = _make_say()

        handler_fn(event=event, say=say)

        client.add_url.assert_not_called()
        text = say.call_args[1]["text"]
        assert "Unknown type" in text

    def test_check_command(self):
        client = _make_mock_client()
        client.check_url.return_value = None
        handler_fn, _ = self._get_handler(client)
        event = _make_dm_event("check https://example.com")
        say = _make_say()

        handler_fn(event=event, say=say)

        client.check_url.assert_called_once_with("https://example.com")

    def test_info_command(self):
        client = _make_mock_client()
        client.get_document.return_value = {
            "id": 123, "title": "T", "document_type": "link",
            "document_state": "URL_ADDED", "created_at": "2026-01-01",
        }
        handler_fn, _ = self._get_handler(client)
        event = _make_dm_event("info 123")
        say = _make_say()

        handler_fn(event=event, say=say)

        client.get_document.assert_called_once_with(123)

    def test_info_non_numeric(self):
        client = _make_mock_client()
        handler_fn, _ = self._get_handler(client)
        event = _make_dm_event("info abc")
        say = _make_say()

        handler_fn(event=event, say=say)

        client.get_document.assert_not_called()
        text = say.call_args[1]["text"]
        assert "numeric ID required" in text

    def test_search_command(self):
        client = _make_mock_client()
        client.search_similar.return_value = [
            {"title": "Doc A", "url": "https://a.com", "document_type": "webpage", "similarity": 0.8}
        ]
        handler_fn, _ = self._get_handler(client)
        event = _make_dm_event("search kubernetes security")
        say = _make_say()

        handler_fn(event=event, say=say)

        client.search_similar.assert_called_once_with("kubernetes security")

    def test_search_no_args(self):
        handler_fn, _ = self._get_handler()
        event = _make_dm_event("search")
        say = _make_say()

        handler_fn(event=event, say=say)

        text = say.call_args[1]["text"]
        assert "Usage:" in text

    def test_help_command(self):
        handler_fn, _ = self._get_handler()
        event = _make_dm_event("help")
        say = _make_say()

        handler_fn(event=event, say=say)

        text = say.call_args[1]["text"]
        assert "Available commands:" in text
        assert "version" in text
        assert "count" in text
        assert "search" in text
        assert "add" in text
        assert "check" in text
        assert "info" in text

    def test_unrecognized_command(self):
        handler_fn, _ = self._get_handler()
        event = _make_dm_event("hello")
        say = _make_say()

        handler_fn(event=event, say=say)

        text = say.call_args[1]["text"]
        assert "I didn't understand that" in text
        assert "Available commands:" in text

    def test_random_text(self):
        handler_fn, _ = self._get_handler()
        event = _make_dm_event("asdf")
        say = _make_say()

        handler_fn(event=event, say=say)

        text = say.call_args[1]["text"]
        assert "I didn't understand that" in text


# --- Test HELP_TEXT content ---


class TestHelpText:
    def test_contains_all_commands(self):
        assert "version" in HELP_TEXT
        assert "count" in HELP_TEXT
        assert "search" in HELP_TEXT
        assert "add" in HELP_TEXT
        assert "check" in HELP_TEXT
        assert "info" in HELP_TEXT
        assert "help" in HELP_TEXT

    def test_contains_types(self):
        assert "webpage" in HELP_TEXT
        assert "youtube" in HELP_TEXT
        assert "link" in HELP_TEXT
        assert "movie" in HELP_TEXT
        assert "text_message" in HELP_TEXT


# --- Test DM handler with intent parsing ---


class TestDmIntentParsing:
    """Test LLM intent fallback in the DM event handler."""

    def _get_handler_with_intent(self, client=None):
        """Register DM handler with intent_enabled=True and return handler."""
        app = MagicMock()
        if client is None:
            client = _make_mock_client()
        register_dm_handler(app, client, intent_enabled=True)
        return app.event.return_value.call_args[0][0], client

    def _get_handler_without_intent(self, client=None):
        """Register DM handler with intent_enabled=False and return handler."""
        app = MagicMock()
        if client is None:
            client = _make_mock_client()
        register_dm_handler(app, client, intent_enabled=False)
        return app.event.return_value.call_args[0][0], client

    def test_keyword_match_takes_priority_over_llm(self):
        """Keyword match should work even when intent parsing is enabled."""
        client = _make_mock_client()
        client.get_all_counts.return_value = {"ALL": 5, "webpage": 5}
        handler_fn, _ = self._get_handler_with_intent(client)
        event = _make_dm_event("count")
        say = _make_say()

        handler_fn(event=event, say=say)

        client.get_all_counts.assert_called_once()
        client.parse_intent.assert_not_called()

    @patch("src.dm_handler.parse_intent")
    def test_llm_fallback_count_command(self, mock_parse):
        """When keyword fails, LLM should parse intent."""
        client = _make_mock_client()
        client.get_all_counts.return_value = {"ALL": 42, "webpage": 42}
        mock_parse.return_value = ParsedIntent(command="count", args={}, confidence=0.95)
        handler_fn, _ = self._get_handler_with_intent(client)
        event = _make_dm_event("how many articles do I have?")
        say = _make_say()

        handler_fn(event=event, say=say)

        mock_parse.assert_called_once_with(client, "how many articles do I have?")
        client.get_all_counts.assert_called_once()

    @patch("src.dm_handler.parse_intent")
    def test_llm_fallback_check_command(self, mock_parse):
        client = _make_mock_client()
        client.check_url.return_value = None
        mock_parse.return_value = ParsedIntent(
            command="check", args={"url": "https://example.com"}, confidence=0.9
        )
        handler_fn, _ = self._get_handler_with_intent(client)
        event = _make_dm_event("do I have https://example.com?")
        say = _make_say()

        handler_fn(event=event, say=say)

        client.check_url.assert_called_once()

    @patch("src.dm_handler.parse_intent")
    def test_llm_unknown_shows_help(self, mock_parse):
        """When LLM returns unknown, show help text."""
        mock_parse.return_value = ParsedIntent(command="unknown", args={}, confidence=0.0)
        handler_fn, client = self._get_handler_with_intent()
        event = _make_dm_event("random gibberish that makes no sense")
        say = _make_say()

        handler_fn(event=event, say=say)

        text = say.call_args[1]["text"]
        assert "I'm not sure what you mean" in text

    @patch("src.dm_handler.parse_intent")
    def test_llm_unreachable_shows_fallback(self, mock_parse):
        """When LLM is unreachable (returns None), show default help."""
        mock_parse.return_value = None
        handler_fn, client = self._get_handler_with_intent()
        event = _make_dm_event("tell me something")
        say = _make_say()

        handler_fn(event=event, say=say)

        text = say.call_args[1]["text"]
        assert "I didn't understand that" in text

    def test_intent_disabled_no_llm_call(self):
        """When intent parsing is disabled, no LLM call should be made."""
        handler_fn, client = self._get_handler_without_intent()
        event = _make_dm_event("how many articles?")
        say = _make_say()

        handler_fn(event=event, say=say)

        client.parse_intent.assert_not_called()
        text = say.call_args[1]["text"]
        assert "I didn't understand that" in text

    @patch("src.dm_handler.parse_intent")
    def test_llm_fallback_add_command(self, mock_parse):
        client = _make_mock_client()
        client.add_url.return_value = {"document_id": 77}
        mock_parse.return_value = ParsedIntent(
            command="add", args={"url": "https://test.com", "type": "youtube"}, confidence=0.85
        )
        handler_fn, _ = self._get_handler_with_intent(client)
        event = _make_dm_event("save this youtube video https://test.com")
        say = _make_say()

        handler_fn(event=event, say=say)

        client.add_url.assert_called_once()

    @patch("src.dm_handler.parse_intent")
    def test_llm_fallback_info_command(self, mock_parse):
        client = _make_mock_client()
        client.get_document.return_value = {
            "id": 42, "title": "T", "document_type": "link",
            "document_state": "URL_ADDED", "created_at": "2026-01-01",
        }
        mock_parse.return_value = ParsedIntent(
            command="info", args={"id": 42}, confidence=0.92
        )
        handler_fn, _ = self._get_handler_with_intent(client)
        event = _make_dm_event("show me document 42")
        say = _make_say()

        handler_fn(event=event, say=say)

        client.get_document.assert_called_once_with(42)

    @patch("src.dm_handler.parse_intent")
    def test_llm_fallback_search_command(self, mock_parse):
        """When LLM returns search command, route to search handler."""
        client = _make_mock_client()
        client.search_similar.return_value = [
            {"title": "K8s Article", "url": "https://example.com/k8s", "document_type": "webpage", "similarity": 0.85}
        ]
        mock_parse.return_value = ParsedIntent(
            command="search", args={"query": "kubernetes"}, confidence=0.9
        )
        handler_fn, _ = self._get_handler_with_intent(client)
        event = _make_dm_event("find articles about kubernetes")
        say = _make_say()

        handler_fn(event=event, say=say)

        client.search_similar.assert_called_once_with("kubernetes")
        text = say.call_args[1]["text"]
        assert "K8s Article" in text
