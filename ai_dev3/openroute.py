from openai import OpenAI
from os import getenv

# gets API Key from environment variable OPENAI_API_KEY
client = OpenAI(
  base_url="https://openrouter.ai/api/v1",
  api_key="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",
)

completion = client.chat.completions.create(
  model="anthropic/claude-sonnet-4",
  messages=[
    {
      "role": "user",
      "content": "Say this is a test",
    },
  ],
)
print(completion.choices[0].message.content)
