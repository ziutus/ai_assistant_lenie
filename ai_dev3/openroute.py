from openai import OpenAI
import os
from os import getenv
from dotenv import load_dotenv
load_dotenv("../.env")

api_key = getenv("OPEN_ROUTER_KEY")

if not api_key:
    print("Błąd: Zmienna środowiskowa 'OPEN_ROUTER_KEY' nie jest ustawiona w pliku .env")
    print("Sprawdź czy plik ../.env zawiera linię: OPEN_ROUTER_KEY=twój_klucz_api")
    exit(1)


# gets API Key from environment variable OPENAI_API_KEY
client = OpenAI(
  base_url="https://openrouter.ai/api/v1",
  api_key= os.environ["OPEN_ROUTER_KEY"],
)

load_dotenv("../.env")


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
