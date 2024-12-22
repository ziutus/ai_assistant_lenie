import json

import requests
from pprint import pprint
import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

task = "START"

iteration = 0

api_answers = []

while iteration < 3:

    json_data = {
        "task": "photos",
        "apikey": os.environ.get('AI_DEV3_API_KEY'),
        "answer": task
    }

    response = requests.post("https://centrala.ag3nts.org/report", json=json_data)

    result = response.json()
    pprint(result)

    if result['code'] != 0:
        pprint(result)
        raise("Wrong answer from AI Dev3 API")

    aidev3_message = result['message']

    ai_task = f"""
Jesteś asystentem analizującym zdjęcia. Twoim zadaniem jest:

1. Sprawdzenie poprawności 4 zdjęć z podanego źródła
2. Wykonanie jednej z dozwolonych akcji (DARKEN/REPAIR/BRIGHTEN) jeśli któreś zdjęcie tego wymaga
3. W przypadku gdy wszystkie zdjęcia są poprawne - opisanie ich zawartości i stworzenie opisu osoby o imieniu Barbara

Format odpowiedzi:
- Dla akcji naprawczej:
{{"task": "AKCJA NAZWA_PLIKU", "photos": [LISTA_4_ZDJEC]}}

- Dla opisu (tylko gdy wszystkie zdjęcia są poprawne):
{{"answer": "Opis Barbary"}}

Zasady:
- Zawsze analizuj dokładnie jakość każdego zdjęcia
- Dozwolone akcje to tylko: DARKEN, REPAIR, BRIGHTEN
- Jeśli zdjęcie wymaga poprawy, zwróć odpowiednią akcję
- Pracuj sekwencyjnie - zwracaj tylko jeden następny krok
- Wszystkie zdjęcia nie muszą przedstawiać Barbary
- W opisie Barbary bazuj na dostępnych zdjęciach

Przykład odpowiedzi z akcją:
    {{"task": "BRIGHTEN IMG_111.PNG", "photos": ["IMG_111.PNG", "IMG_222.PNG", "IMG_333.PNG", "IMG_444.PNG"]}}    

    Informacje z zewnętrznego systemu:
    {aidev3_message}
    
    Poprzednie informacje: {" ".join(api_answers)}
"""

    print(ai_task)

    api_answers.append(f"<iteration: {iteration}>{aidev3_message}</iteration>\n")

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": ai_task},


                ],
            }
        ],
        max_tokens=1000,
    )

    ai_answer = json.loads(response.choices[0].message.content)

    if 'answer' in ai_answer:
        print("Znalazłem odpowiedz!")
        print(ai_answer)
        exit(0)

    pprint(ai_answer)

    task = ai_answer['task']
    iteration += 1

