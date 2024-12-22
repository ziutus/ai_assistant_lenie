import os
from pprint import pprint
import json

import requests
from dotenv import load_dotenv

load_dotenv()

json_data = {
    "task": "POLIGON",
    "apikey": os.environ.get('AI_DEV3_API_KEY'),
    "answer": None
}


file_path = '../tmp/poligon_dane.txt'



url = "https://poligon.aidevs.pl/dane.txt"
response = requests.get(url)
if response.status_code == 200:
    answers = response.text
    # os.makedirs(os.path.dirname(file_path), exist_ok=True)
    # with open(file_path, 'w', encoding='utf-8') as file:
    #     file.write(response.text)
else:
    print(f"Failed to fetch data. HTTP Status Code: {response.status_code}")

# with open(file_path, 'r', encoding='utf-8') as file:
#     answers = file.readlines()

pprint(answers.split("\n"))

answers_stings = []
print(type(answers))

for answer in answers.split("\n"):
    if len(answer) > 0:
        answers_stings.append(answer)

# pprint(answers_stings)

json_data["answer"] = answers_stings

# pprint(json_data)


json_data = json.dumps(json_data)

print(json_data)

# response = requests.post("https://poligon.aidevs.pl/verify", json=json_data)
#
# result = response.json()
# pprint(result)