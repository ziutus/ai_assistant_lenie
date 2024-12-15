import json
import os
from pprint import pprint

import requests

from dotenv import load_dotenv

from library.ai import ai_ask
import re

# Load environment variables from a standard .env file
load_dotenv()
# Create directory if it doesn't exist
os.makedirs('tmp', exist_ok=True)

# Retrieve the API key from the environment variable
api_key = os.getenv('AI_DEV3_API_KEY')

# Ensure the API key is provided
if not api_key:
    raise EnvironmentError("Environment variable 'AI_DEV3_API_KEY' is not set.")

# Construct the URL
url = f"https://centrala.ag3nts.org/data/{api_key}/cenzura.txt"

# Fetch the data
response = requests.get(url)

# Ensure the request was successful
if response.status_code != 200:
    raise Exception(f"Failed to fetch data: {response.status_code} - {response.text}")

# Write the data to the file
with open('tmp/personal_data.txt', 'w', encoding='utf-8') as file:
    file.write(response.text)

data_to_protect = response.text
data_to_protect_original = response.text

print(data_to_protect)

# ai_task = f"""
# Z w poniższym zdaniu zamień Imię i nazwisko oraz miasto oraz adres oraz wiek na słowo CENZURA.
# Zasady:
# * Adres składa się z nazwy ulicy oraz numeru.
# * Nie zmieniaj szyku zdań.
# * Zwróć samo zdanie po zmienieniu.
# * Nie zmieniaj pozostałych słów np. "lata" na "lat" lub "we" na "w".
# * jeżeli w opdowiedzi znajduje się liczba, usuń ją.
# Zdanie: {data_to_protect}.
# """

ai_task = f"""
Z w poniższym zdaniu znajdz następujące dane: Imię i nazwisko, miasto, adres, wiek.
* wiek to tylko liczba 
* Adres składa się z nazwy ulicy oraz numeru, bez słowa ulica lub ulicy
Zwróć tylko Wynik w formie JSON o następujących polach, nie zmieniaj formy znalezionych wyrazów, nie dodawaj formatowania ani komentarzy:
{{
"imie_naziwsko": IMIE I NAZWISKO,
"adres": ADRES,
"miasto: MIASTO,
"wiek": WIEK
}}

Zdanie: {data_to_protect}.
"""


ai_answer = ai_ask(ai_task, model="amazon.nova-micro", temperature=0.0)

# print(ai_answer.response_text)

json_personal_data = json.loads(ai_answer.response_text)
pprint(json_personal_data)


if data_to_protect.find(str(json_personal_data["wiek"])) >= 0:
    print("Manual correction needed: wiek")
    data_to_protect = data_to_protect.replace(str(json_personal_data["wiek"]), "CENZURA")
    print(f"New target string: {data_to_protect}" )

if re.search(json_personal_data["miasto"], data_to_protect, re.IGNORECASE):
    print("Manual correction needed: miasto")
    data_to_protect = re.sub(json_personal_data["miasto"], "CENZURA", data_to_protect, flags=re.IGNORECASE)
    print(f"New target string: {data_to_protect}")

if data_to_protect.find(json_personal_data["adres"]) >= 0:
    print("Manual correction needed: adres")
    data_to_protect = data_to_protect.replace(json_personal_data["adres"], "CENZURA")
    print(f"New target string: {data_to_protect}" )

if data_to_protect.find(json_personal_data["imie_naziwsko"]) >= 0:
    print("Manual correction needed: imie_naziwsko")
    data_to_protect = data_to_protect.replace(json_personal_data["imie_naziwsko"], "CENZURA")
    print(f"New target string: {data_to_protect}" )


if data_to_protect.find("na ulicy") >= 0:
    print("Manual correction needed: doubled na ulicy")
    data_to_protect = data_to_protect.replace("na ulicy", "")
    print(f"New target string: {data_to_protect}" )

if data_to_protect.find("na ul.") >= 0:
    print("Manual correction needed: na ul.")
    data_to_protect = data_to_protect.replace("na ul.", "")
    print(f"New target string: {data_to_protect}" )

# if data_to_protect.find("na ul.") >= 0:
#     print("Manual correction needed: na ul.")
#     data_to_protect = data_to_protect.replace("na ul.", "")
#     print(f"New target string: {data_to_protect}" )

if data_to_protect.find("ulica") >= 0:
    print("Manual correction needed: ulica")
    data_to_protect = data_to_protect.replace("ulica", "")
    print(f"New target string: {data_to_protect}" )


# Replace occurrences of "CENZURA" followed by letters or digits with just "CENZURA"
if re.search(r'CENZURA\w', data_to_protect):
    print("Manual correction needed: 'CENZURA' followed by letters or digits")
    data_to_protect = re.sub(r'CENZURA\w*', 'CENZURA', data_to_protect)
    print(f"New target string: {data_to_protect}")

if data_to_protect.find("CENZURA, CENZURA") >= 0:
    print("Manual correction needed: doubled CENZURA")
    data_to_protect = data_to_protect.replace("CENZURA, CENZURA", "CENZURA")
    print(f"New target string: {data_to_protect}" )

if re.search(r'CENZURA\s+CENZURA', data_to_protect):
    print("Manual correction needed: multiple 'CENZURA'")
    data_to_protect = re.sub(r'CENZURA\s+CENZURA', 'CENZURA', data_to_protect)
    print(f"New target string: {data_to_protect}")


print(f"original string:>{data_to_protect_original}")
print(f"final string:   >{data_to_protect}<")

json_data = {
    "task": "CENZURA",
    "apikey": os.environ.get('AI_DEV3_API_KEY'),
    "answer": data_to_protect
}

response = requests.post("https://centrala.ag3nts.org/report", json=json_data)

result = response.json()
pprint(result)