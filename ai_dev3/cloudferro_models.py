import os
import requests
from dotenv import load_dotenv
from pprint import pprint
from datetime import datetime

load_dotenv()

# Ustawienie klucza API i niestandardowego URL dla OpenAI API
api_key = os.environ["CLOUDFERRO_SHERLOCK_KEY"]
api_base = "https://api-sherlock.cloudferro.com/openai/v1/"

# try:
#     # Zapytanie o listę modeli za pomocą requests
#     headers = {
#         "Authorization": f"Bearer {api_key}"
#     }
#     response = requests.get(f"{api_base}models", headers=headers)
#
#     # Wyświetlenie dostępnych modeli
#     if response.status_code == 200:
#         models = response.json()["data"]
#         print("Dostępne modele:")
#         for model in models:
#             print(model["id"])
#     else:
#         print(f"Błąd: {response.status_code} - {response.text}")
#
# except Exception as e:
#     print(f"Wystąpił błąd podczas komunikacji z API: {e}")


print("-----")
print("Embedding modele:")
try:
    # Zapytanie o listę modeli za pomocą requests
    headers = {
        "Authorization": f"Bearer {api_key}"
    }
    response = requests.get(f"{api_base}models", headers=headers)

    # Wyświetlenie modeli do embeddingu
    if response.status_code == 200:
        models = response.json()["data"]
        print("Modele do embeddingu:")
        for model in models:
            if model['endpoint'] != '/openai/v1/embeddings':
                continue
            print(model["id"])
            pprint(model)
            data = datetime.fromtimestamp(model["created"])
            print(f"Data utworzenia: {data.strftime('%Y-%m-%d %H:%M:%S')}")
    else:
        print(f"Błąd: {response.status_code} - {response.text}")

except Exception as e:
    print(f"Wystąpił błąd podczas komunikacji z API: {e}")
