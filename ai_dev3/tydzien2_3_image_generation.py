import json
import os
from pprint import pprint
import requests
from dotenv import load_dotenv

from library.ai import ai_ask

load_dotenv()

api_key = os.getenv('AI_DEV3_API_KEY')

if not api_key:
    raise EnvironmentError("Environment variable 'AI_DEV3_API_KEY' is not set.")

os.makedirs('tmp', exist_ok=True)

# Construct the URL
url = f"https://centrala.ag3nts.org/data/{api_key}/robotid.json"

# Fetch the data
response = requests.get(url)

# Ensure the request was successful
if response.status_code != 200:
    raise Exception(f"Failed to fetch data: {response.status_code} - {response.text}")

# Write the data to the file
with open('tmp/robot_description.txt', 'w', encoding='utf-8') as file:
    file.write(response.text)

robot_description_raw = response.text

robot_description = robot_description_raw.encode().decode('unicode_escape')

pprint(robot_description)

question_with_instruction = f"""
Stwórz opis robota, który podam do generatora obrazu na podstawie opisu. Nie podawaj nic poza opisem robota.
Usuń komentarze autora dotyczące tego czy je widział wcześniej czy nie.
Opis: {robot_description}

"""

ai_answer = ai_ask(question_with_instruction, model="amazon.nova-micro", temperature=0)
# ai_answer = ai_ask(question_with_instruction, model="amazon.titan-tg1-large")
pprint(ai_answer.response_text)


# URL endpointu dla generowania obrazów
url = "https://api.openai.com/v1/images/generations"


opepnai_api_key = os.getenv('OPENAI_API_KEY')

from openai import OpenAI
client = OpenAI(api_key=opepnai_api_key)

response = client.images.generate(
model="dall-e-3",
prompt=ai_answer.response_text,
size="1024x1024",
quality="standard",
n=1,
)

image_url = response.data[0].url

print(f"image url: {image_url}")

json_data = {
    "task": "robotid",
    "apikey": os.environ.get('AI_DEV3_API_KEY'),
    "answer": image_url
}

response = requests.post("https://centrala.ag3nts.org/report", json=json_data)

result = response.json()
pprint(result)