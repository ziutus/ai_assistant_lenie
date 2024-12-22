import requests
from pprint import pprint
import os
from dotenv import load_dotenv

load_dotenv()

json_data = {
    "task": "database",
    "apikey": os.environ.get('AI_DEV3_API_KEY'),
    "answer": ["4278", "9294"]
}

response = requests.post("https://centrala.ag3nts.org/report", json=json_data)

result = response.json()
pprint(result)