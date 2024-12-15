from pprint import pprint
import os
import requests
from dotenv import load_dotenv
load_dotenv()

json_data = {
    "task": "mp3",
    "apikey": os.environ.get('AI_DEV3_API_KEY'),
    "answer": "Łojasiewicza"
}

response = requests.post("https://centrala.ag3nts.org/report", json=json_data)

result = response.json()
pprint(result)