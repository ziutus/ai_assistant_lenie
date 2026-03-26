import logging

import requests as http_requests
from openai import OpenAI

from library.models.ai_response import AiResponse
from library.api.arklabs.config import get_arklabs_config

logger = logging.getLogger(__name__)

# Stateful session — reuses GPU session via ark_session_id cookie
_stateful_session: http_requests.Session | None = None


def _get_stateful_session() -> http_requests.Session:
    """Get or create a persistent requests.Session for stateful ARK Labs calls."""
    global _stateful_session
    if _stateful_session is None:
        _stateful_session = http_requests.Session()
    return _stateful_session


def arklabs_get_completion(prompt: str, model: str = "speakleash/Bielik-11B-v3.0-Instruct",
                           max_tokens: int = 1000, temperature: float = 0.1,
                           system_prompt: str = None,
                           stateful: bool = False) -> AiResponse:
    ai_response = AiResponse(query=prompt, model=model)
    api_key, base_url = get_arklabs_config()

    if stateful:
        return _completion_stateful(ai_response, prompt, model, max_tokens,
                                    temperature, system_prompt, api_key, base_url)
    else:
        return _completion_stateless(ai_response, prompt, model, max_tokens,
                                     temperature, system_prompt, api_key, base_url)


def _completion_stateless(ai_response, prompt, model, max_tokens,
                          temperature, system_prompt, api_key, base_url):
    """Stateless mode — each request is independent (OpenAI SDK)."""
    client = OpenAI(api_key=api_key, base_url=base_url)

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    chat_response = client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )

    ai_response.id = chat_response.id
    ai_response.response_text = chat_response.choices[0].message.content
    ai_response.prompt_tokens = chat_response.usage.prompt_tokens
    ai_response.completion_tokens = chat_response.usage.completion_tokens
    ai_response.total_tokens = chat_response.usage.total_tokens

    return ai_response


def _completion_stateful(ai_response, prompt, model, max_tokens,
                         temperature, system_prompt, api_key, base_url):
    """Stateful mode — reuses GPU session via cookies (cheaper input tokens)."""
    session = _get_stateful_session()

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    url = f"{base_url}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    response = session.post(url, json=payload, headers=headers, timeout=120)
    response.raise_for_status()
    data = response.json()

    ai_response.id = data.get("id")
    ai_response.response_text = data["choices"][0]["message"]["content"]

    usage = data.get("usage", {})
    ai_response.prompt_tokens = usage.get("prompt_tokens")
    ai_response.completion_tokens = usage.get("completion_tokens")
    ai_response.total_tokens = usage.get("total_tokens")

    # Log credit usage for cost comparison
    credits_used = usage.get("credits_used")
    credit_balance = usage.get("credit_balance")
    if credits_used is not None:
        logger.info(f"ARK Labs stateful: credits_used={credits_used}, balance={credit_balance}")

    return ai_response
