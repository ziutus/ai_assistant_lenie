"""Tests for ai_ask() (stage 3 of the search rebuild: LLM abstraction).

Every test that reaches a provider patches the central recorder
(library.llm_usage.recorder.record_llm_usage) — a unit test must never
write a real llm_usage_logs row.
"""

from unittest.mock import patch

import pytest

pytest.importorskip("openai")

from library.ai import ai_ask  # noqa: E402
from library.models.ai_response import AiResponse  # noqa: E402


def sherlock_response(prompt_tokens=100, completion_tokens=20) -> AiResponse:
    response = AiResponse(query="q", model="Bielik-11B-v3.0-Instruct")
    response.id = "chatcmpl-123"
    response.response_text = "odpowiedź"
    response.prompt_tokens = prompt_tokens
    response.completion_tokens = completion_tokens
    response.total_tokens = prompt_tokens + completion_tokens
    return response


def patched_sherlock(return_value=None, side_effect=None):
    return patch(
        "library.api.cloudferro.sherlock.sherlock.sherlock_get_completion",
        return_value=return_value if return_value is not None else sherlock_response(),
        side_effect=side_effect,
    )


def patched_recorder(**kwargs):
    return patch("library.llm_usage.recorder.record_llm_usage", **kwargs)


class TestParameterPropagation:
    def test_forwards_generation_parameters_to_sherlock_for_bielik(self):
        with patched_sherlock() as mock_completion, patched_recorder():
            ai_ask(
                "Extract timeline events",
                model="Bielik-11B-v3.0-Instruct",
                temperature=0.1,
                max_token_count=4000,
            )

        mock_completion.assert_called_once_with(
            "Extract timeline events",
            model="Bielik-11B-v3.0-Instruct",
            temperature=0.1,
            max_tokens=4000,
            system_prompt=None,
            response_format=None,
        )

    def test_temperature_zero_is_propagated(self):
        with patched_sherlock() as mock_completion, patched_recorder():
            ai_ask("q", model="Bielik-11B-v3.0-Instruct", temperature=0.0)
        assert mock_completion.call_args.kwargs["temperature"] == 0.0


class TestSystemPrompt:
    def test_system_prompt_is_a_separate_argument_not_concatenated(self):
        with patched_sherlock() as mock_completion, patched_recorder():
            ai_ask(
                "tekst użytkownika",
                model="Bielik-11B-v3.0-Instruct",
                system_prompt="Jesteś parserem zapytań.",
            )
        args, kwargs = mock_completion.call_args
        assert args[0] == "tekst użytkownika"
        assert kwargs["system_prompt"] == "Jesteś parserem zapytań."
        assert "Jesteś parserem" not in args[0]

    def test_system_prompt_forwarded_to_arklabs(self):
        with patch(
            "library.api.arklabs.arklabs_completion.arklabs_get_completion",
            return_value=sherlock_response(),
        ) as mock_completion, patched_recorder():
            ai_ask("tekst", model="arklabs/Bielik-11B-v3.0-Instruct", system_prompt="System.")
        assert mock_completion.call_args.kwargs["system_prompt"] == "System."
        assert mock_completion.call_args.kwargs["model"] == "Bielik-11B-v3.0-Instruct"

    def test_system_prompt_rejected_for_unsupported_provider(self):
        with patched_recorder() as mock_record:
            with pytest.raises(ValueError, match="system_prompt"):
                ai_ask("tekst", model="gpt-4", system_prompt="System.")
        mock_record.assert_not_called()


class TestResponseFormat:
    def test_response_format_forwarded_to_sherlock(self):
        schema = {"type": "json_schema", "json_schema": {"name": "x", "schema": {"type": "object"}}}
        with patched_sherlock() as mock_completion, patched_recorder():
            ai_ask("q", model="Bielik-11B-v3.0-Instruct", response_format=schema)
        assert mock_completion.call_args.kwargs["response_format"] is schema

    def test_response_format_rejected_for_unsupported_provider(self):
        with pytest.raises(ValueError, match="response_format"):
            ai_ask("q", model="gpt-4o", response_format={"type": "json_object"})


class TestUsageRecording:
    def test_success_records_exactly_one_usage_row(self):
        with patched_sherlock(), patched_recorder(return_value="usage-record") as mock_record:
            response = ai_ask(
                "q",
                model="Bielik-11B-v3.0-Instruct",
                operation="search_query_parse",
                search_interpretation_log_id=7,
            )
        mock_record.assert_called_once()
        kwargs = mock_record.call_args.kwargs
        assert kwargs["operation"] == "search_query_parse"
        assert kwargs["provider"] == "cloudferro"
        assert kwargs["model"] == "Bielik-11B-v3.0-Instruct"
        assert kwargs["prompt_tokens"] == 100
        assert kwargs["completion_tokens"] == 20
        assert kwargs["total_tokens"] == 120
        assert kwargs["request_id"] == "chatcmpl-123"
        assert kwargs["search_interpretation_log_id"] == 7
        assert isinstance(kwargs["latency_ms"], int) and kwargs["latency_ms"] >= 0
        assert response.usage == "usage-record"

    def test_default_operation_is_ai_ask(self):
        with patched_sherlock(), patched_recorder() as mock_record:
            ai_ask("q", model="Bielik-11B-v3.0-Instruct")
        assert mock_record.call_args.kwargs["operation"] == "ai_ask"

    def test_exception_records_failed_usage_and_reraises(self):
        with patched_sherlock(side_effect=RuntimeError("timeout")), patched_recorder() as mock_record:
            with pytest.raises(RuntimeError, match="timeout"):
                ai_ask("q", model="Bielik-11B-v3.0-Instruct", operation="search_query_parse")
        mock_record.assert_called_once()
        kwargs = mock_record.call_args.kwargs
        assert kwargs["success"] is False
        assert kwargs["error_code"] == "RuntimeError"
        assert kwargs["provider"] == "cloudferro"
        assert isinstance(kwargs["latency_ms"], int)

    def test_bedrock_input_output_tokens_unified(self):
        bedrock_response = AiResponse(query="q", model="amazon.nova-micro")
        bedrock_response.response_text = "ok"
        bedrock_response.input_tokens = 300
        bedrock_response.output_tokens = 40
        with patch(
            "library.api.aws.bedrock_ask.query_aws_bedrock", return_value=bedrock_response
        ), patched_recorder() as mock_record:
            ai_ask("q", model="amazon.nova-micro")
        kwargs = mock_record.call_args.kwargs
        assert kwargs["provider"] == "aws-bedrock"
        assert kwargs["prompt_tokens"] == 300
        assert kwargs["completion_tokens"] == 40

    def test_recorder_failure_does_not_break_the_call(self):
        with patched_sherlock(), patched_recorder(side_effect=RuntimeError("db down")):
            response = ai_ask("q", model="Bielik-11B-v3.0-Instruct")
        assert response.response_text == "odpowiedź"
        assert response.usage is None

    def test_recorder_systemexit_does_not_kill_the_call(self):
        with patched_sherlock(), patched_recorder(side_effect=SystemExit(1)):
            response = ai_ask("q", model="Bielik-11B-v3.0-Instruct")
        assert response.usage is None


class TestRegressions:
    def test_unknown_model_raises_without_usage_record(self):
        with patched_recorder() as mock_record:
            with pytest.raises(Exception, match="Unknown model"):
                ai_ask("q", model="no-such-model")
        mock_record.assert_not_called()

    def test_ai_response_has_no_cost_attributes(self):
        # Stage 3 rule: cost lives only in response.usage — adding cost_usd/
        # cost/credits_used would revive the dead probe in timeline_events.py.
        response = AiResponse(query="q")
        for name in ("cost_usd", "cost", "credits_used"):
            assert not hasattr(response, name)
        assert response.usage is None
