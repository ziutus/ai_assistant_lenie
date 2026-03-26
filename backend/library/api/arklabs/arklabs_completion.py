from openai import OpenAI

from library.models.ai_response import AiResponse
from library.api.arklabs.config import get_arklabs_config


def arklabs_get_completion(prompt: str, model: str = "speakleash/Bielik-11B-v3.0-Instruct",
                           max_tokens: int = 1000, temperature: float = 0.1,
                           system_prompt: str = None) -> AiResponse:
    ai_response = AiResponse(query=prompt, model=model)

    api_key, base_url = get_arklabs_config()
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
