import os
import json

from openai import OpenAI
from langfuse.decorators import observe


class OpenAIClient:
    """
    A client to interact with OpenAI's API.
    Provides a method to obtain completions.
    """

    @observe()
    @staticmethod
    # model="gpt-4"
    # model="gpt-3.5-turbo"
    def get_completion(prompt: str, model: str = "gpt-4") -> str:
        """
        Get a completion response from OpenAI for a given prompt.

        :param prompt: Text prompt for the completion.
        :param model: OpenAI model to use.
        :return: Completion response or None if request fails.
        """

        messages = [{"role": "user", "content": prompt}]
        try:

            client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

            chat_completion = client.chat.completions.create(
                messages=messages,
                model=model,
            )
            return chat_completion.choices[0].message.content

        except Exception as e:
            raise Exception(f"An error occurred: {e}")

    @observe()
    def get_completion2(prompt: str, model: str = "gpt-4o-mini") -> str:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},

                    ],
                }
            ],
            max_tokens=1000,
        )

        return json.loads(response.choices[0].message.content)

    @observe()
    def get_completion_image(prompt: str, image_urls=[], detail: str="auto", model: str="gpt-4o-mini",
                             max_tokens = 300) -> str:
        client = OpenAI()

        content = [{"type": "text", "text": prompt}]

        for image in image_urls:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": image,
                        "detail": detail
                    }
                }
        )

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "user",
                    "content": content,
                }
            ],
            max_tokens= max_tokens,
        )

        return response.choices[0].message.content
