import json
from pprint import pprint
from dotenv import load_dotenv
import os
import re
import requests
import csv

from library.ai import ai_ask

load_dotenv()

db_api = "https://centrala.ag3nts.org/apidb"

initial_query = "show tables"

db_query = {
    "task": "database",
    "apikey": os.environ.get('AI_DEV3_API_KEY'),
    "query": "select * from users"
}

# pprint(db_query)

response = requests.post(db_api, json=db_query)

result = response.json()
# pprint(result)

# Sprawdź, czy odpowiedź zawiera dane
if "reply" in result:
    rows = result["reply"]

    # Nazwa pliku CSV
    file_name = 'tmp/users.csv'

    # Zapis danych do pliku CSV
    with open(file_name, mode='w', newline='', encoding='utf-8') as csv_file:
        # Przygotowanie nagłówków na podstawie kluczy pierwszego wiersza
        fieldnames = rows[0].keys() if rows else []
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)

        # Zapis nagłówków
        writer.writeheader()

        # Zapis wszystkich wierszy
        writer.writerows(rows)

    print(f'Dane zapisano do pliku {file_name}.')
else:
    print("Brak danych w odpowiedzi API.")


db_query = {
    "task": "database",
    "apikey": os.environ.get('AI_DEV3_API_KEY'),
    "query": "select * from connections"
}

# pprint(db_query)

response = requests.post(db_api, json=db_query)

result = response.json()
# pprint(result)

# Sprawdź, czy odpowiedź zawiera dane
if "reply" in result:
    rows = result["reply"]

    # Nazwa pliku CSV
    file_name = 'tmp/connections.csv'

    # Zapis danych do pliku CSV
    with open(file_name, mode='w', newline='', encoding='utf-8') as csv_file:
        # Przygotowanie nagłówków na podstawie kluczy pierwszego wiersza
        fieldnames = rows[0].keys() if rows else []
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)

        # Zapis nagłówków
        writer.writeheader()

        # Zapis wszystkich wierszy
        writer.writerows(rows)

    print(f'Dane zapisano do pliku {file_name}.')
else:
    print("Brak danych w odpowiedzi API.")