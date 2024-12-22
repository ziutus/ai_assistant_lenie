from pprint import pprint

import assemblyai as aai
import os

import requests
from dotenv import load_dotenv
load_dotenv()

# aai.settings.api_key = os.getenv("ASSEMBLYAI")
#
# config = aai.TranscriptionConfig(language_code="pl")
#
# transcriber = aai.Transcriber(config=config)
#
# osoba="rafal"
#
# transcript = transcriber.transcribe(f"tmp/przesluchania/{osoba}.m4a")
#
# if transcript.status == aai.TranscriptStatus.error:
#     print(transcript.error)
# else:
#     print(transcript.text)
#
#     with open(f"tmp/przesluchania/{osoba}.txt", "w", encoding="utf-8") as file:
#         file.write(transcript.text)

json_data = {
    "task": "mp3",
    "apikey": os.environ.get('AI_DEV3_API_KEY'),
    "answer": "Łojasiewicza"
}

response = requests.post("https://centrala.ag3nts.org/report", json=json_data)

result = response.json()
pprint(result)