import os

from openai import OpenAI


class OpenAIClient:
    """
    A client to interact with OpenAI's API.
    Provides a method to obtain completions.
    """

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

        # :param max_tokens: Maximum tokens in the response.
        # :param temperature: Sampling temperature.

        # messages = [{"role": "user", "content": prompt}]
        # data = {
        #     # "model": model,
        #     # "messages": messages,
        #     "model": model,
        #     "max_tokens": max_tokens,
        #     # "n": 1,
        #     "temperature": temperature,
        #     "prompt": prompt
        # }

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
