"""Unit tests for src.intent_parser module."""

from unittest.mock import MagicMock

from src.api_client import ApiConnectionError, ApiError, ApiResponseError
from src.intent_parser import ParsedIntent, parse_intent


def _make_mock_client():
    return MagicMock()


class TestParseIntent:
    """Tests for parse_intent function."""

    def test_successful_parse(self):
        client = _make_mock_client()
        client.parse_intent.return_value = {
            "status": "success",
            "command": "count",
            "args": {},
            "confidence": 0.95,
        }

        result = parse_intent(client, "how many articles?")
        assert result is not None
        assert isinstance(result, ParsedIntent)
        assert result.command == "count"
        assert result.args == {}
        assert result.confidence == 0.95
        client.parse_intent.assert_called_once_with("how many articles?")

    def test_check_command_with_url(self):
        client = _make_mock_client()
        client.parse_intent.return_value = {
            "command": "check",
            "args": {"url": "https://example.com"},
            "confidence": 0.9,
        }

        result = parse_intent(client, "do I have https://example.com?")
        assert result.command == "check"
        assert result.args["url"] == "https://example.com"

    def test_unknown_command(self):
        client = _make_mock_client()
        client.parse_intent.return_value = {
            "command": "unknown",
            "args": {},
            "confidence": 0.0,
        }

        result = parse_intent(client, "random gibberish")
        assert result.command == "unknown"
        assert result.confidence == 0.0

    def test_connection_error_returns_none(self):
        client = _make_mock_client()
        client.parse_intent.side_effect = ApiConnectionError("Backend unreachable")

        result = parse_intent(client, "how many articles?")
        assert result is None

    def test_api_response_error_returns_none(self):
        client = _make_mock_client()
        client.parse_intent.side_effect = ApiResponseError(
            "Backend returned HTTP 400", status_code=400, response_body="Intent parser disabled"
        )

        result = parse_intent(client, "how many articles?")
        assert result is None

    def test_api_error_returns_none(self):
        client = _make_mock_client()
        client.parse_intent.side_effect = ApiError("Unknown error")

        result = parse_intent(client, "how many articles?")
        assert result is None

    def test_unexpected_exception_returns_none(self):
        client = _make_mock_client()
        client.parse_intent.side_effect = RuntimeError("something broke")

        result = parse_intent(client, "count")
        assert result is None

    def test_missing_fields_in_response(self):
        client = _make_mock_client()
        client.parse_intent.return_value = {"status": "success"}

        result = parse_intent(client, "test")
        assert result.command == "unknown"
        assert result.args == {}
        assert result.confidence == 0.0
