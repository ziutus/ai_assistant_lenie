"""LLM provider abstraction (stage 3 of docs/search-rebuild-implementation-plan.md).

``ai_ask()`` routes a prompt to the provider implied by the model name,
measures latency, and records exactly one llm_usage_logs row per call
(success or exception) through the central recorder. The resulting
``UsageRecord`` (tokens, latency, usage_log_id, cost summary with status)
is attached to the response as ``response.usage`` — cost never lives
anywhere else on the response object.

A ``system_prompt`` is passed as a real system-role message to providers
that support it (CloudFerro Sherlock, ARK Labs) and is NEVER concatenated
with the user text; for other providers passing one raises ValueError.
"""

import logging
import time

from library.models.ai_response import AiResponse

logger = logging.getLogger(__name__)

OPENAI_MODELS = ("gpt-3.5-turbo", "gpt-3.5-turbo-16k", "gpt-4", "gpt-4o", "gpt-4o-2024-05-13", "gpt-4o-mini")
BEDROCK_MODELS = ("amazon.titan-tg1-large", "amazon.nova-micro", "amazon.nova-pro", "aws")
SHERLOCK_MODELS = ("Bielik-11B-v2.3-Instruct", "Bielik-11B-v3.0-Instruct")
GOOGLE_MODELS = ("gemini-2.0-flash-lite-001",)

# Providers whose API accepts a separate system-role message.
_SYSTEM_PROMPT_PROVIDERS = ("cloudferro", "arklabs")
# Providers accepting response_format; Sherlock enforces json_schema
# (verified live 2026-07-18) but rejects json_object with HTTP 400.
_RESPONSE_FORMAT_PROVIDERS = ("cloudferro",)


def _unified_tokens(response) -> tuple[int | None, int | None, int | None]:
    """Map prompt/input and completion/output naming variants onto one view."""
    prompt = getattr(response, "prompt_tokens", None)
    if prompt is None:
        prompt = getattr(response, "input_tokens", None)
    completion = getattr(response, "completion_tokens", None)
    if completion is None:
        completion = getattr(response, "output_tokens", None)
    total = getattr(response, "total_tokens", None)
    return prompt, completion, total


def _record_usage(**kwargs):
    """Write the usage row via the central recorder; never let it break the call."""
    try:
        from library.llm_usage.recorder import record_llm_usage
    except ImportError:
        logger.warning("library.llm_usage.recorder unavailable; skipping LLM usage record")
        return None
    try:
        return record_llm_usage(**kwargs)
    except (SystemExit, Exception):
        logger.exception("Recording LLM usage failed")
        return None


def ai_ask(query: str, model: str, temperature: float = 0.7, max_token_count: int = 4096, top_p: float = 0.9,
           *, system_prompt: str | None = None, response_format: dict | None = None,
           operation: str = "ai_ask", search_interpretation_log_id: int | None = None,
           arklabs_stateful: bool = False, document_id: int | None = None,
           analysis_job_id: str | None = None, analysis_run_id: int | None = None) -> AiResponse:

    if model in OPENAI_MODELS:
        provider = "openai"
        if model in ("gpt-3.5-turbo", "gpt-3.5-turbo-16k"):
            if len(query) < 8000:
                model = "gpt-3.5-turbo"
            elif len(query) < 16000:
                model = "gpt-3.5-turbo-16k"
            else:
                raise Exception("Too long text for gpt-3.5 models")

        def call(resolved_model=model):
            import library.api.openai.openai_my

            response = library.api.openai.openai_my.OpenAIClient.get_completion(query, resolved_model)
            ai_response = AiResponse(query=query, model=resolved_model)
            if isinstance(response, bytes):
                response = response.decode('utf-8')
            ai_response.response_text = response
            return ai_response

    elif model in BEDROCK_MODELS:
        provider = "aws-bedrock"

        def call():
            import library.api.aws.bedrock_ask

            return library.api.aws.bedrock_ask.query_aws_bedrock(query, model, temperature=temperature,
                                                                 max_token_count=max_token_count, top_p=top_p)

    elif model in SHERLOCK_MODELS:
        provider = "cloudferro"

        def call():
            from library.api.cloudferro.sherlock.sherlock import sherlock_get_completion

            return sherlock_get_completion(query, model=model, temperature=temperature,
                                           max_tokens=max_token_count, system_prompt=system_prompt,
                                           response_format=response_format)

    elif model.startswith("arklabs/"):
        provider = "arklabs"
        actual_model = model.removeprefix("arklabs/")

        def call():
            from library.api.arklabs.arklabs_completion import arklabs_get_completion

            return arklabs_get_completion(query, model=actual_model, temperature=temperature,
                                          max_tokens=max_token_count, system_prompt=system_prompt,
                                          stateful=arklabs_stateful)

    elif model in GOOGLE_MODELS:
        provider = "google-vertexai"

        def call():
            import library.api.google.google_vertexai as google_vertexai

            return google_vertexai.connect_to_google_llm_with_role(query, model)

    else:
        raise Exception(f"ERROR: Unknown model {model}")

    if system_prompt is not None and provider not in _SYSTEM_PROMPT_PROVIDERS:
        raise ValueError(
            f"system_prompt is not supported for model {model}; "
            "a system prompt must never be concatenated with the user text"
        )
    if response_format is not None and provider not in _RESPONSE_FORMAT_PROVIDERS:
        raise ValueError(f"response_format is not supported for model {model}")

    started = time.monotonic()
    try:
        ai_response = call()
    except Exception as exc:
        _record_usage(
            operation=operation,
            provider=provider,
            model=model,
            success=False,
            error_code=type(exc).__name__,
            latency_ms=int((time.monotonic() - started) * 1000),
            search_interpretation_log_id=search_interpretation_log_id,
            document_id=document_id, analysis_job_id=analysis_job_id, analysis_run_id=analysis_run_id,
        )
        raise

    latency_ms = int((time.monotonic() - started) * 1000)
    prompt_tokens, completion_tokens, total_tokens = _unified_tokens(ai_response)
    ai_response.usage = _record_usage(
        operation=operation,
        provider=provider,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        request_id=getattr(ai_response, "id", None),
        latency_ms=latency_ms,
        search_interpretation_log_id=search_interpretation_log_id,
        document_id=document_id, analysis_job_id=analysis_job_id, analysis_run_id=analysis_run_id,
    )
    return ai_response
