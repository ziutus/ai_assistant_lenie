"""OpenRouter chat completions (OpenAI-compatible API) — an external intermediary, off unless enabled.

The document text sent here leaves Lenie for OpenRouter and the model's own provider, so the provider
stays disabled until ``OPENROUTER_ENABLED`` is switched on in the config (see ``is_enabled``).
"""

import logging

from openai import OpenAI

from library.models.ai_response import AiResponse

logger = logging.getLogger(__name__)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
REQUEST_TIMEOUT_SECONDS = 60
_TRUE_VALUES = ("1", "true", "yes", "on")


def is_enabled() -> bool:
    """True when the ``OPENROUTER_ENABLED`` config flag is switched on."""
    from library.config_loader import load_config

    return str(load_config().get("OPENROUTER_ENABLED") or "").strip().lower() in _TRUE_VALUES


def openrouter_get_completion(prompt: str, model: str, max_tokens: int = 1000, temperature: float = 0.1,
                              system_prompt: str | None = None, response_format: dict | None = None) -> AiResponse:
    """``model`` is the OpenRouter id without the internal ``openrouter/`` prefix (e.g. ``openai/gpt-4o-mini``).

    ``response_format`` (a JSON-schema format) is forwarded as-is; only models whose catalog entry lists
    ``structured_outputs`` honour it (``openrouter_catalog``), callers check that first.
    """
    from library.config_loader import load_config

    if not is_enabled():
        raise RuntimeError("OpenRouter is disabled (OPENROUTER_ENABLED)")
    api_key = load_config().get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not configured")

    client = OpenAI(api_key=api_key, base_url=OPENROUTER_BASE_URL, timeout=REQUEST_TIMEOUT_SECONDS, max_retries=1)
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    extra_args = {"response_format": response_format} if response_format is not None else {}
    chat_response = client.chat.completions.create(
        model=model, messages=messages, max_tokens=max_tokens, temperature=temperature, **extra_args,
    )

    ai_response = AiResponse(query=prompt, model=model)
    ai_response.id = chat_response.id
    ai_response.response_text = chat_response.choices[0].message.content
    usage = getattr(chat_response, "usage", None)
    if usage is not None:
        ai_response.prompt_tokens = usage.prompt_tokens
        ai_response.completion_tokens = usage.completion_tokens
        ai_response.total_tokens = usage.total_tokens
    return ai_response
