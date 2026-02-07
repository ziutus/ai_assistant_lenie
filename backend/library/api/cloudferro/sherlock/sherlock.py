from openai import OpenAI
import os
from dotenv import load_dotenv
from library.models.ai_response import AiResponse


load_dotenv()


def sherlock_get_completion(prompt: str, model: str = "Bielik-11B-v2.3-Instruct", max_tokens=1000) -> AiResponse:

    ai_response = AiResponse(query=prompt, model=model)

    client = OpenAI(
        api_key=os.environ['CLOUDFERRO_SHERLOCK_KEY'],
        base_url="https://api-sherlock.cloudferro.com/openai/v1"
    )

    chat_response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "user", "content": prompt}
        ],
        max_tokens=max_tokens,
    )

    ai_response.id = chat_response.id
    ai_response.response = chat_response.choices[0].message.content
    ai_response.response_text = chat_response.choices[0].message.content
    ai_response.prompt_tokens = chat_response.usage.prompt_tokens
    ai_response.total_tokens = chat_response.usage.total_tokens
    ai_response.completion_tokens = chat_response.usage.completion_tokens

    return ai_response
