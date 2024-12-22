import json
from pprint import pprint
import os
import requests
from dotenv import load_dotenv
from library.ai import ai_ask

load_dotenv()


with open('../tmp/tydzien2_5/arxiv.txt', 'r', encoding='utf-8') as file:
    questions = file.readlines()

with open('../tmp/tydzien2_5/arxiv-draft.md', 'r', encoding='utf-8') as file:
    md_data = file.read()

questions_text = ""

for question in questions:
    # print(f"question: {question}")
    question_id, question_text = question.replace("\n", "").split('=')
    print(f"{question_id}:{question_text} ")
    questions_text += f"{question_id}: {question_text} "



ai_task = f"""
Znając dane poniżej, odpowiedz na poniższe pytania:
{questions_text}

Odpowiedz w formacie:
{{
    "ID-pytania-01": "krótka odpowiedź w 1 zdaniu",
    "ID-pytania-02": "krótka odpowiedź w 1 zdaniu",
    "ID-pytania-03": "krótka odpowiedź w 1 zdaniu",
    "ID-pytania-NN": "krótka odpowiedź w 1 zdaniu"
}}

Dane: {md_data}
"""

print(ai_task)

# ai_answer = ai_ask(ai_task, model="amazon.nova-pro", max_token_count = 60000, temperature=0.1)
# print(ai_answer.response_text)

json_data = {
    "task": "arxiv",
    "apikey": os.environ.get('AI_DEV3_API_KEY'),
    "answer": {
        "01": "Do pierwszej próby transmisji materii w czasie użyto truskawki.",
        "02": "Testową fotografię wykonano na rynku w Krakowie.",
        "03": "Bomba chciał znaleźć hotel w Grudziądzu.",
        "04": "Rafał pozostawił resztki pizzy z ananasem, czyli pizzy hawajskiej.",
        "05": "Litery BNW w nazwie modelu pochodzą od 'Brave New World' (Nowy Wspaniały Świat)."
    }
}

response = requests.post("https://centrala.ag3nts.org/report", json=json_data)

result = response.json()
pprint(result)