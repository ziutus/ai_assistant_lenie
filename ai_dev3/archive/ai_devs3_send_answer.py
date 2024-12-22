import os
from pprint import pprint
import json

import requests
from dotenv import load_dotenv

load_dotenv()

file_for_check = '../tmp/json.json'

with open(file_for_check, 'r', encoding='utf-8') as file:
    json_for_check = json.load(file)


pprint(len(json_for_check["test-data"]))
# pprint(json_for_check["test-data"])

file_path = '../tmp/json_answer.json'

with open(file_path, 'r', encoding='utf-8') as file:
    json_answer = json.load(file)

pprint(len(json_answer["test-data"]))

# exit(0)

json_data = {
    "task": "JSON",
    "apikey": os.environ.get('AI_DEV3_API_KEY'),
    "answer": json_answer
}

# print(json_data)


response = requests.post("https://centrala.ag3nts.org/report", json=json_data)

result = response.json()
pprint(result)