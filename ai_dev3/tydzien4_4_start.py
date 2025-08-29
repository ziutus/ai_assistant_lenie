import requests
from pprint import pprint
import os
from dotenv import load_dotenv

load_dotenv()

lambda_url = "https://csifvk5d53ngec6rdtpub56b6u0novgc.lambda-url.us-east-1.on.aws/"

json_data = {
    "task": "webhook",
    "apikey": os.environ.get('AI_DEV3_API_KEY'),
    "answer": lambda_url
}

response = requests.post("https://centrala.ag3nts.org/report", json=json_data)

result = response.json()
pprint(result)