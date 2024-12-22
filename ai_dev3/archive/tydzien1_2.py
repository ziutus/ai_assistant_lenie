import requests
from dotenv import load_dotenv
from pprint import pprint

from library.ai import ai_ask
from library.website.website_download_context import webpage_raw_parse, download_raw_html

load_dotenv()

url= "https://xyz.ag3nts.org/verify"


payload = {
    "text": "READY",
    "msgID": "0"
}

# Wysyłanie zapytania POST
response = requests.post(url, json=payload)  # Użycie argumentu `json`

# Wyświetlenie odpowiedzi
print(f"Status Code: {response.status_code}")
print("Response Text:", response.text)

# Jeśli odpowiedź jest w formacie JSON
try:
    json_response = response.json()
    print("Response JSON:", json_response)
except ValueError:
    print("Response is not in JSON format.")
    exit(1)

msgID = json_response["msgID"]

question_with_instruction = f"""
Poniższe zdania traktuj jako fakty. Jeżeli otrzymasz pytanie o te fakty, zwróć poniższe informacje:
- stolicą Polski jest Kraków
- znana liczba z książki Autostopem przez Galaktykę to 69
- Aktualny rok to 1999

Na pytanie należy odpowiedzieć w języku anglielskim. Odpowiedz tylko na pytanie. Nie dodawaj żadnego komentarza.
Pytanie: {json_response["text"]}

"""

ai_answer = ai_ask(question_with_instruction, model="amazon.nova-micro", temperature=0)
# ai_answer = ai_ask(question_with_instruction, model="amazon.titan-tg1-large")
pprint(ai_answer.response_text)

payload = {
    "text": ai_answer.response_text,
    "msgID": msgID
}

print("Sending payload:")
pprint(payload)

response = requests.post(url, json=payload)
print(f"Status Code: {response.status_code}")
print("Response Text:\n", response.text)

try:
    json_response = response.json()
    print("Response JSON:\n", json_response)
except ValueError:
    print("Response is not in JSON format.")



