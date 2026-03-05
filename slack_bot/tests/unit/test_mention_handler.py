"""Unit tests for src.mention_handler module."""

from unittest.mock import MagicMock, patch

from src.intent_parser import ParsedIntent
from src.mention_handler import _strip_mention, register_mention_handler


# --- Helpers ---


def _make_mock_client() -> MagicMock:
    return MagicMock()


def _make_say() -> MagicMock:
    return MagicMock()


def _make_mention_event(text: str = "", **overrides) -> dict:
    """Create a fake app_mention event dict."""
    event = {
        "type": "app_mention",
        "channel": "C123ABC",
        "user": "U456DEF",
        "text": text,
        "ts": "1234567890.123456",
    }
    event.update(overrides)
    return event


def _get_handler(client=None):
    """Register mention handler and return the event handler function."""
    app = MagicMock()
    if client is None:
        client = _make_mock_client()
        client.get_version.return_value = {"app_version": "1.0", "app_build_time": "2026-01-01"}
    register_mention_handler(app, client)
    app.event.assert_called_once_with("app_mention")
    handler_fn = app.event.return_value.call_args[0][0]
    return handler_fn, client


# --- Test mention text stripping ---


class TestStripMention:
    def test_strips_bot_mention(self):
        assert _strip_mention("<@U123ABC> version") == "version"

    def test_strips_with_extra_spaces(self):
        assert _strip_mention("<@U123ABC>   count") == "count"

    def test_strips_no_space_after_mention(self):
        assert _strip_mention("<@U123ABC>version") == "version"

    def test_no_mention_returns_text(self):
        assert _strip_mention("version") == "version"

    def test_empty_after_mention(self):
        assert _strip_mention("<@U123ABC>") == ""

    def test_empty_string(self):
        assert _strip_mention("") == ""

    def test_mention_with_args(self):
        assert _strip_mention("<@U123ABC> add https://example.com youtube") == "add https://example.com youtube"


# --- Test thread_ts is passed ---


class TestThreadResponse:
    def test_thread_ts_passed_on_command(self):
        handler_fn, client = _get_handler()
        event = _make_mention_event("<@U123ABC> version", ts="9999.1234")
        say = _make_say()

        handler_fn(event=event, say=say)

        say.assert_called_once()
        assert say.call_args[1]["thread_ts"] == "9999.1234"

    def test_thread_ts_passed_on_help(self):
        handler_fn, _ = _get_handler()
        event = _make_mention_event("<@U123ABC>", ts="9999.1234")
        say = _make_say()

        handler_fn(event=event, say=say)

        assert say.call_args[1]["thread_ts"] == "9999.1234"

    def test_thread_ts_passed_on_unknown_command(self):
        handler_fn, _ = _get_handler()
        event = _make_mention_event("<@U123ABC> foobar", ts="9999.1234")
        say = _make_say()

        handler_fn(event=event, say=say)

        assert say.call_args[1]["thread_ts"] == "9999.1234"


# --- Test command routing ---


class TestMentionCommandRouting:
    def test_version_command(self):
        handler_fn, client = _get_handler()
        event = _make_mention_event("<@U123ABC> version")
        say = _make_say()

        handler_fn(event=event, say=say)

        client.get_version.assert_called_once()
        text = say.call_args[1]["text"]
        assert "1.0" in text

    def test_count_command(self):
        client = _make_mock_client()
        client.get_all_counts.return_value = {"ALL": 5, "webpage": 5}
        handler_fn, _ = _get_handler(client)
        event = _make_mention_event("<@U123ABC> count")
        say = _make_say()

        handler_fn(event=event, say=say)

        client.get_all_counts.assert_called_once()

    def test_add_command(self):
        client = _make_mock_client()
        client.add_url.return_value = {"status": "success", "document_id": 42}
        handler_fn, _ = _get_handler(client)
        event = _make_mention_event("<@U123ABC> add https://example.com")
        say = _make_say()

        handler_fn(event=event, say=say)

        client.add_url.assert_called_once_with("https://example.com", url_type="webpage")

    def test_check_command(self):
        client = _make_mock_client()
        client.check_url.return_value = None
        handler_fn, _ = _get_handler(client)
        event = _make_mention_event("<@U123ABC> check https://example.com")
        say = _make_say()

        handler_fn(event=event, say=say)

        client.check_url.assert_called_once_with("https://example.com")

    def test_info_command(self):
        client = _make_mock_client()
        client.get_document.return_value = {
            "id": 123, "title": "T", "document_type": "link",
            "document_state": "URL_ADDED", "created_at": "2026-01-01",
        }
        handler_fn, _ = _get_handler(client)
        event = _make_mention_event("<@U123ABC> info 123")
        say = _make_say()

        handler_fn(event=event, say=say)

        client.get_document.assert_called_once_with(123)

    def test_help_command(self):
        handler_fn, _ = _get_handler()
        event = _make_mention_event("<@U123ABC> help")
        say = _make_say()

        handler_fn(event=event, say=say)

        text = say.call_args[1]["text"]
        assert "Available commands:" in text

    def test_case_insensitive(self):
        handler_fn, client = _get_handler()
        event = _make_mention_event("<@U123ABC> VERSION")
        say = _make_say()

        handler_fn(event=event, say=say)

        client.get_version.assert_called_once()


# --- Test filtering ---


class TestMentionFiltering:
    def test_bot_message_ignored(self):
        handler_fn, _ = _get_handler()
        event = _make_mention_event("<@U123ABC> version", bot_id="B123")
        say = _make_say()

        handler_fn(event=event, say=say)

        say.assert_not_called()

    def test_empty_mention_shows_help(self):
        handler_fn, _ = _get_handler()
        event = _make_mention_event("<@U123ABC>")
        say = _make_say()

        handler_fn(event=event, say=say)

        text = say.call_args[1]["text"]
        assert "Available commands:" in text

    def test_unknown_command_shows_help(self):
        handler_fn, _ = _get_handler()
        event = _make_mention_event("<@U123ABC> foobar")
        say = _make_say()

        handler_fn(event=event, say=say)

        text = say.call_args[1]["text"]
        assert "I didn't understand that" in text
        assert "Available commands:" in text


# --- Test mention handler with intent parsing ---


def _get_handler_with_intent(client=None):
    """Register mention handler with intent_enabled=True."""
    app = MagicMock()
    if client is None:
        client = _make_mock_client()
    register_mention_handler(app, client, intent_enabled=True)
    handler_fn = app.event.return_value.call_args[0][0]
    return handler_fn, client


class TestMentionIntentParsing:
    """Test LLM intent fallback in the mention event handler."""

    def test_keyword_match_takes_priority(self):
        client = _make_mock_client()
        client.get_all_counts.return_value = {"ALL": 5, "webpage": 5}
        handler_fn, _ = _get_handler_with_intent(client)
        event = _make_mention_event("<@U123ABC> count")
        say = _make_say()

        handler_fn(event=event, say=say)

        client.get_all_counts.assert_called_once()
        client.parse_intent.assert_not_called()

    @patch("src.mention_handler.parse_intent")
    def test_llm_fallback_count(self, mock_parse):
        client = _make_mock_client()
        client.get_all_counts.return_value = {"ALL": 42, "webpage": 42}
        mock_parse.return_value = ParsedIntent(command="count", args={}, confidence=0.95)
        handler_fn, _ = _get_handler_with_intent(client)
        event = _make_mention_event("<@U123ABC> how many articles?")
        say = _make_say()

        handler_fn(event=event, say=say)

        mock_parse.assert_called_once()
        client.get_all_counts.assert_called_once()
        assert say.call_args[1]["thread_ts"] == "1234567890.123456"

    @patch("src.mention_handler.parse_intent")
    def test_llm_unknown_shows_help_in_thread(self, mock_parse):
        mock_parse.return_value = ParsedIntent(command="unknown", args={}, confidence=0.0)
        handler_fn, _ = _get_handler_with_intent()
        event = _make_mention_event("<@U123ABC> random gibberish", ts="9999.1234")
        say = _make_say()

        handler_fn(event=event, say=say)

        text = say.call_args[1]["text"]
        assert "I'm not sure what you mean" in text
        assert say.call_args[1]["thread_ts"] == "9999.1234"

    @patch("src.mention_handler.parse_intent")
    def test_llm_unreachable_shows_fallback(self, mock_parse):
        mock_parse.return_value = None
        handler_fn, _ = _get_handler_with_intent()
        event = _make_mention_event("<@U123ABC> tell me something")
        say = _make_say()

        handler_fn(event=event, say=say)

        text = say.call_args[1]["text"]
        assert "I didn't understand that" in text

    @patch("src.mention_handler.parse_intent")
    def test_thread_response_preserved_for_llm(self, mock_parse):
        client = _make_mock_client()
        client.get_version.return_value = {"app_version": "1.0", "app_build_time": "2026-01-01"}
        mock_parse.return_value = ParsedIntent(command="version", args={}, confidence=0.9)
        handler_fn, _ = _get_handler_with_intent(client)
        event = _make_mention_event("<@U123ABC> what version is running?", ts="5555.6666")
        say = _make_say()

        handler_fn(event=event, say=say)

        assert say.call_args[1]["thread_ts"] == "5555.6666"
