"""Unit tests for ai_intent_parser module."""

import json
import sys
from unittest.mock import MagicMock, patch

from library.ai_intent_parser import CONFIDENCE_THRESHOLD, _parse_llm_response, parse_intent


class TestParseLlmResponse:
    """Tests for _parse_llm_response (JSON parsing and validation)."""

    def test_valid_response(self):
        raw = json.dumps({"command": "count", "args": {}, "confidence": 0.95})
        result = _parse_llm_response(raw)
        assert result["command"] == "count"
        assert result["args"] == {}
        assert result["confidence"] == 0.95

    def test_check_command_with_url_arg(self):
        raw = json.dumps({"command": "check", "args": {"url": "https://example.com"}, "confidence": 0.9})
        result = _parse_llm_response(raw)
        assert result["command"] == "check"
        assert result["args"]["url"] == "https://example.com"

    def test_add_command_with_type(self):
        raw = json.dumps({"command": "add", "args": {"url": "https://x.com", "type": "youtube"}, "confidence": 0.85})
        result = _parse_llm_response(raw)
        assert result["command"] == "add"
        assert result["args"]["type"] == "youtube"

    def test_info_command_with_id(self):
        raw = json.dumps({"command": "info", "args": {"id": 42}, "confidence": 0.92})
        result = _parse_llm_response(raw)
        assert result["command"] == "info"
        assert result["args"]["id"] == 42

    def test_search_command(self):
        raw = json.dumps({"command": "search", "args": {"query": "kubernetes"}, "confidence": 0.88})
        result = _parse_llm_response(raw)
        assert result["command"] == "search"
        assert result["args"]["query"] == "kubernetes"

    def test_unknown_command_returned_as_is(self):
        raw = json.dumps({"command": "unknown", "args": {}, "confidence": 0.0})
        result = _parse_llm_response(raw)
        assert result["command"] == "unknown"

    def test_low_confidence_becomes_unknown(self):
        raw = json.dumps({"command": "count", "args": {}, "confidence": 0.3})
        result = _parse_llm_response(raw)
        assert result["command"] == "unknown"
        assert result["confidence"] == 0.3

    def test_confidence_at_threshold(self):
        raw = json.dumps({"command": "count", "args": {}, "confidence": CONFIDENCE_THRESHOLD})
        result = _parse_llm_response(raw)
        assert result["command"] == "count"

    def test_confidence_just_below_threshold(self):
        raw = json.dumps({"command": "count", "args": {}, "confidence": CONFIDENCE_THRESHOLD - 0.01})
        result = _parse_llm_response(raw)
        assert result["command"] == "unknown"

    def test_malformed_json(self):
        result = _parse_llm_response("this is not json at all")
        assert result["command"] == "unknown"
        assert result["confidence"] == 0.0

    def test_empty_string(self):
        result = _parse_llm_response("")
        assert result["command"] == "unknown"

    def test_markdown_code_block(self):
        raw = '```json\n{"command": "version", "args": {}, "confidence": 0.9}\n```'
        result = _parse_llm_response(raw)
        assert result["command"] == "version"

    def test_invalid_command_name(self):
        raw = json.dumps({"command": "delete_everything", "args": {}, "confidence": 0.99})
        result = _parse_llm_response(raw)
        assert result["command"] == "unknown"

    def test_missing_command_key(self):
        raw = json.dumps({"args": {}, "confidence": 0.9})
        result = _parse_llm_response(raw)
        assert result["command"] == "unknown"

    def test_non_dict_args(self):
        raw = json.dumps({"command": "count", "args": "invalid", "confidence": 0.9})
        result = _parse_llm_response(raw)
        assert result["args"] == {}

    def test_confidence_clamped_above_1(self):
        raw = json.dumps({"command": "count", "args": {}, "confidence": 1.5})
        result = _parse_llm_response(raw)
        assert result["confidence"] == 1.0

    def test_confidence_clamped_below_0(self):
        raw = json.dumps({"command": "count", "args": {}, "confidence": -0.5})
        result = _parse_llm_response(raw)
        assert result["confidence"] == 0.0

    def test_non_numeric_confidence(self):
        raw = json.dumps({"command": "count", "args": {}, "confidence": "high"})
        result = _parse_llm_response(raw)
        assert result["confidence"] == 0.0

    def test_response_is_json_array(self):
        result = _parse_llm_response('[{"command": "count"}]')
        assert result["command"] == "unknown"


class TestParseIntent:
    """Tests for parse_intent (full flow with LLM mock)."""

    @staticmethod
    def _make_ai_response(response_text):
        mock = MagicMock()
        mock.response_text = response_text
        return mock

    def test_empty_text_input(self):
        result = parse_intent("")
        assert result["command"] == "unknown"

    def test_whitespace_only_input(self):
        result = parse_intent("   ")
        assert result["command"] == "unknown"

    def test_successful_parse(self):
        mock_ai = MagicMock()
        mock_ai_module = MagicMock()
        mock_ai_module.ai_ask = mock_ai
        mock_ai.return_value = self._make_ai_response(
            json.dumps({"command": "count", "args": {}, "confidence": 0.95})
        )

        mock_cfg = MagicMock()
        mock_cfg.get.return_value = "gpt-4o-mini"
        mock_config_module = MagicMock()
        mock_config_module.load_config.return_value = mock_cfg

        with patch.dict(sys.modules, {
            "library.ai": mock_ai_module,
            "library.config_loader": mock_config_module,
        }):
            result = parse_intent("how many articles do I have?")
            assert result["command"] == "count"
            assert result["confidence"] == 0.95
            mock_ai.assert_called_once()

    def test_llm_exception_returns_unknown(self):
        mock_ai_module = MagicMock()
        mock_ai_module.ai_ask.side_effect = Exception("LLM service unavailable")

        mock_cfg = MagicMock()
        mock_cfg.get.return_value = "gpt-4o-mini"
        mock_config_module = MagicMock()
        mock_config_module.load_config.return_value = mock_cfg

        with patch.dict(sys.modules, {
            "library.ai": mock_ai_module,
            "library.config_loader": mock_config_module,
        }):
            result = parse_intent("how many articles?")
            assert result["command"] == "unknown"
            assert result["confidence"] == 0.0

    def test_empty_llm_response(self):
        mock_ai_module = MagicMock()
        mock_ai_module.ai_ask.return_value = self._make_ai_response("")

        mock_cfg = MagicMock()
        mock_cfg.get.return_value = "gpt-4o-mini"
        mock_config_module = MagicMock()
        mock_config_module.load_config.return_value = mock_cfg

        with patch.dict(sys.modules, {
            "library.ai": mock_ai_module,
            "library.config_loader": mock_config_module,
        }):
            result = parse_intent("count articles")
            assert result["command"] == "unknown"

    def test_explicit_model_parameter(self):
        mock_ai_module = MagicMock()
        mock_ai_module.ai_ask.return_value = self._make_ai_response(
            json.dumps({"command": "version", "args": {}, "confidence": 0.9})
        )

        with patch.dict(sys.modules, {"library.ai": mock_ai_module}):
            result = parse_intent("what version?", model="gpt-4o-mini")
            assert result["command"] == "version"
            mock_ai_module.ai_ask.assert_called_once()
            call_args = mock_ai_module.ai_ask.call_args
            assert call_args[1]["model"] == "gpt-4o-mini"

    def test_prompt_contains_user_text(self):
        mock_ai_module = MagicMock()
        mock_ai_module.ai_ask.return_value = self._make_ai_response(
            json.dumps({"command": "check", "args": {"url": "https://x.com"}, "confidence": 0.9})
        )

        mock_cfg = MagicMock()
        mock_cfg.get.return_value = "gpt-4o-mini"
        mock_config_module = MagicMock()
        mock_config_module.load_config.return_value = mock_cfg

        with patch.dict(sys.modules, {
            "library.ai": mock_ai_module,
            "library.config_loader": mock_config_module,
        }):
            parse_intent("do I have https://x.com?")
            call_args = mock_ai_module.ai_ask.call_args
            assert "do I have https://x.com?" in call_args[0][0]

    def test_temperature_is_low(self):
        mock_ai_module = MagicMock()
        mock_ai_module.ai_ask.return_value = self._make_ai_response(
            json.dumps({"command": "count", "args": {}, "confidence": 0.9})
        )

        mock_cfg = MagicMock()
        mock_cfg.get.return_value = "gpt-4o-mini"
        mock_config_module = MagicMock()
        mock_config_module.load_config.return_value = mock_cfg

        with patch.dict(sys.modules, {
            "library.ai": mock_ai_module,
            "library.config_loader": mock_config_module,
        }):
            parse_intent("count")
            call_args = mock_ai_module.ai_ask.call_args
            assert call_args[1]["temperature"] == 0.1
