import requests
from pprint import pprint
import os
from dotenv import load_dotenv

load_dotenv()

json_data = {
    "task": "connections",
    "apikey": os.environ.get('AI_DEV3_API_KEY'),
    "answer": "Rafał,Azazel,Aleksander,Barbara"
}

response = requests.post("https://centrala.ag3nts.org/report", json=json_data)

result = response.json()
pprint(result)