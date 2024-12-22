import os
from pprint import pprint
from dotenv import load_dotenv
import requests
import json

load_dotenv()

directory = "tmp/tydzien3_1/answers"

txt_files = [f for f in os.listdir(directory)]
answers = {}

# filename = f"{directory}/{txt_files[1]}"
for file_name in txt_files:
    filename = f"{directory}/{file_name}"
    # print(filename)
    answer = ""
    with open(filename, "r", encoding="utf-8") as file:
        json_data = json.loads(file.readline())
        # pprint(json_data["key_words"])
        answers[file_name] = json_data["key_words"]



json_data = {
    "task": "dokumenty",
    "apikey": os.environ.get('AI_DEV3_API_KEY'),
    "answer": answers
}

# print(json_data["answer"]['2024-11-12_report-00-sektor_C4.txt'])
# print(len(json_data["answer"]))
print(len(json_data["answer"]))
print(json_data)

# pprint(json_data["answer"]["2024-11-12_report-08-sektor_A1.txt"])

response = requests.post("https://centrala.ag3nts.org/report", json=json_data)
result = response.json()
pprint(result)