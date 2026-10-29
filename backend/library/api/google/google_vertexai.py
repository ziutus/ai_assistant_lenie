"""Gemini on Google Vertex AI (Agent Platform) through the google-genai SDK.

Authentication is either a Vertex AI API key (``GCP_VERTEX_API_KEY``) or Application
Default Credentials with ``GCP_PROJECT_ID`` / ``GCP_LOCATION`` (a service-account key
file via ``GOOGLE_APPLICATION_CREDENTIALS`` on the NAS, ``gcloud auth
application-default login`` on a dev machine). The ``global`` endpoint is the default
location: Gemini 3.x models and the cheapest price tier are served there.
"""

import logging

from library.models.ai_response import AiResponse

logger = logging.getLogger(__name__)

DEFAULT_LOCATION = "global"


def _setting(name: str) -> str | None:
    from library.config_loader import load_config

    value = load_config().get(name)
    return str(value).strip() if value and str(value).strip() else None


def _genai():
    """Import the SDK lazily: it is a heavy import and only this provider needs it."""
    from google import genai
    from google.genai import types

    return genai, types


def _client(genai):
    api_key = _setting("GCP_VERTEX_API_KEY")
    if api_key:
        # An API key carries its own project; the SDK rejects project/location next to it.
        return genai.Client(vertexai=True, api_key=api_key)
    project = _setting("GCP_PROJECT_ID")
    if not project:
        raise ValueError("GCP_PROJECT_ID is not configured")
    return genai.Client(vertexai=True, project=project, location=_setting("GCP_LOCATION") or DEFAULT_LOCATION)


def _json_schema(response_format: dict) -> dict:
    """The JSON Schema inside an OpenAI-style ``{"type": "json_schema", "json_schema": {"schema": ...}}``."""
    schema = (response_format.get("json_schema") or {}).get("schema") if response_format.get("type") == "json_schema" else None
    if not isinstance(schema, dict):
        raise ValueError("response_format must be {'type': 'json_schema', 'json_schema': {'schema': {...}}}")
    return schema


def connect_to_google_llm_with_role(
    prompt: str,
    model_id: str,
    *,
    temperature: float | None = None,
    max_output_tokens: int | None = None,
    top_p: float | None = None,
    system_prompt: str | None = None,
    response_format: dict | None = None,
) -> AiResponse:
    if not prompt or not prompt.strip():
        raise ValueError("prompt cannot be empty")
    if not model_id or not model_id.strip():
        raise ValueError("model_id cannot be empty")

    settings = {"temperature": temperature, "max_output_tokens": max_output_tokens, "top_p": top_p}
    if system_prompt is not None:
        settings["system_instruction"] = system_prompt
    if response_format is not None:
        settings["response_mime_type"] = "application/json"
        settings["response_json_schema"] = _json_schema(response_format)

    genai, types = _genai()
    client = _client(genai)
    config = types.GenerateContentConfig(**settings)

    try:
        response = client.models.generate_content(model=model_id, contents=prompt, config=config)
    except Exception:
        logger.exception("Vertex AI request for %s failed", model_id)
        raise

    text = response.text
    if not text:
        raise ValueError("Model returned empty response")

    ai_response = AiResponse(query=prompt, model=model_id)
    ai_response.response_text = text
    ai_response.temperature = temperature
    ai_response.max_token_count = max_output_tokens
    ai_response.top_p = top_p
    usage = response.usage_metadata
    if usage is not None:
        ai_response.prompt_tokens = usage.prompt_token_count
        # Reasoning ("thoughts") tokens are billed as output tokens.
        ai_response.completion_tokens = (usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0)
        ai_response.total_tokens = usage.total_token_count
    ai_response.id = getattr(response, "response_id", None)
    return ai_response
