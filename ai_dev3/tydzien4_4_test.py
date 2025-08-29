import requests
from pprint import pprint
import os
from dotenv import load_dotenv

load_dotenv()

lambda_url = "https://csifvk5d53ngec6rdtpub56b6u0novgc.lambda-url.us-east-1.on.aws/"


json_data = {'instruction': 'AAA Dobra. To co? zaczynamy? Odpalam silniki. Czas na kolejny lot. Jesteś moimi oczami. Lecimy w dół, albo nie! nie! czekaaaaj. Polecimy wiem jak. W prawo i dopiero teraz w dół. Tak będzie OK. Co widzisz?'}


response = requests.post(lambda_url, json=json_data)

# pprint(response)

result = response.json()
pprint(result)

