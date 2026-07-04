import os
import json
from typing import Optional

from openai import OpenAI
# from langfuse.decorators import observe


class OpenAIClient:
    """
    A client to interact with OpenAI's API.
    Provides a method to obtain completions.
    """

    @staticmethod
    def _call_chat(content, model: str, max_tokens: Optional[int] = None) -> str:
        """
        Common helper for calling OpenAI Chat Completions API.

        :param content: Content for the user message (str or list of content parts).
        :param model: OpenAI model to use.
        :param max_tokens: Optional max tokens for the response.
        :return: Raw response content string.
        """
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        kwargs = {
            "model": model,
            "messages": [{"role": "user", "content": content}],
        }
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens

        try:
            response = client.chat.completions.create(**kwargs)
            return response.choices[0].message.content
        except Exception as e:
            raise Exception(f"An error occurred: {e}")

    # @observe()
    @staticmethod
    def get_completion(prompt: str, model: str = "gpt-4") -> str:
        """
        Get a completion response from OpenAI for a given prompt.

        :param prompt: Text prompt for the completion.
        :param model: OpenAI model to use.
        :return: Completion response or None if request fails.
        """
        return OpenAIClient._call_chat(prompt, model=model)

    # @observe()
    @staticmethod
    def get_completion2(prompt: str, model: str = "gpt-4o-mini") -> str:
        result = OpenAIClient._call_chat(prompt, model=model, max_tokens=1000)
        return json.loads(result)

    # @observe()
    @staticmethod
    def get_completion_image(prompt: str, image_urls=None, detail: str = "auto", model: str = "gpt-4o-mini",
                             max_tokens=300) -> str:
        if image_urls is None:
            image_urls = []

        content = [{"type": "text", "text": prompt}]
        for image in image_urls:
            content.append({
                "type": "image_url",
                "image_url": {"url": image, "detail": detail},
            })

        return OpenAIClient._call_chat(content, model=model, max_tokens=max_tokens)
