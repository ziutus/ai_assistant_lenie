import requests
from dotenv import load_dotenv
import os
from pprint import pprint

from library.ai import ai_ask
from library.website.website_download_context import webpage_raw_parse, download_raw_html

# from firecrawl import FirecrawlApp

# dotenv.load_dotenv(".env", override=True)
load_dotenv()

# pprint(os.environ.get('FIRECRAWL_API_KEY'))
#
# app = FirecrawlApp(api_key=os.environ.get('FIRECRAWL_API_KEY'))
#
page="https://xyz.ag3nts.org/"
#
# # Crawl a website:
# crawl_status = app.crawl_url(
#   page,
#   params={
#     'limit': 100,
#     'scrapeOptions': {'formats': ['markdown', 'html']}
#   },
#   poll_interval=30
# )
# pprint(crawl_status)



raw_page =  download_raw_html(page)
question = webpage_raw_parse(page, raw_page).text

print(f"Pytanie uzyskane od systemu: {question}")

question_with_instruction = f"Odpowiedz tylko na pytanie, nie dodawaj żadnego komentarza. Pytanie: {question}"

ai_answer = ai_ask(question_with_instruction, model="amazon.nova-micro")
# ai_answer = ai_ask(question_with_instruction, model="amazon.titan-tg1-large")
pprint(ai_answer.response_text)

payload = {
    'username': 'tester',
    'password': 'XYZ',
    'answer': int(ai_answer.response_text),  # Zakładamy, że odpowiedź jest liczbą
}

# Wysyłanie zapytania POST
response = requests.post(page, data=payload)

# Wyświetlanie kodu statusu odpowiedzi
print(f"Status Code: {response.status_code}")

# Wyświetlanie treści odpowiedzi jako tekst
print("Response Text:\n", response.text)

# Jeśli odpowiedź jest w formacie JSON
try:
    json_response = response.json()
    print("Response JSON:\n", json_response)
except ValueError:
    print("Response is not in JSON format.")



