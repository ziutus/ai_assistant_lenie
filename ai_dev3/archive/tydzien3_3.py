import json
from pprint import pprint
from dotenv import load_dotenv
import os
import re
import requests

from library.ai import ai_ask

load_dotenv()

db_api = "https://centrala.ag3nts.org/apidb"
# model="gpt-4o-2024-05-13"
model="amazon.nova-pro"

initial_query = "show tables"

db_facts = []

answer = None

for i in range(1, 15):

    ai_task = f"""
    Jesteś programistą SQL i masz dostęp do bazy danych.
    
    Informacje o bazie bazie danych masz zapisane w faktach. 
    Do wylistowania tabel w bazie danych możesz użyć polecenia: "show tables"
    Do sprawdzenia jak jest zbudowana tabela, możesz użyć polecenia: "show create table NAZWA_TABELI"
    
    Twoim zadaniem jest zwrócenie numerów ID czynnych datacenter, które zarządzane są przez menadżerów, którzy aktualnie przebywają na urlopie (są nieaktywni)
    
    * Jeżeli znasz odpowiedz, zwróć listę ID czynnych datacenter. odpowiedz zwróć w formacie JSON:{{"answer": "Lista ID czynnych datacenter"}}
    Jeżeli nie znasz odpowiedzi, zwróć zapytanie SQL, odpowiedz zwróć w formacie JSON:{{"sql": "zapytanie SQL"}}
    
    Rozumowanie będzie prowadzone w krokach. Podaj tylko następny krok.
    
    dotychczas dostępne informacje o bazie danych:
    {db_facts}
    """

    print(ai_task)

    ai_answer = ai_ask(ai_task, model="gpt-4o-2024-05-13", temperature=0.5, max_token_count=20000)

    print(ai_answer.response_text)

    pattern = r"```json(.+?)```"

    match = re.search(pattern, ai_answer.response_text, re.DOTALL)

    if match:
        result = match.group(1).strip()
        print(result)

        result_json = json.loads(result)
        if "answer" in result_json:
            answer = result_json["answer"]
            print(answer)
            break

        elif  "sql" in result_json:
            query = result_json["sql"]
            print(query)


            db_query = {
                "task": "database",
                "apikey": os.environ.get('AI_DEV3_API_KEY'),
                "query": query
            }

            pprint(db_query)

            response = requests.post(db_api, json=db_query)

            result = response.json()
            pprint(result)
            db_facts.append(f"<fact><query>{query}</query><error>{result['error']}</error><answer>{result['reply']}</answer></fact>" )
            continue
        else:
            raise Exception("Wrong type of answer from LLM model")


    else:
        print("Nie znaleziono dopasowania.")


print(f"The answer is: {answer}")
