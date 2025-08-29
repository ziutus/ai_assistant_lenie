import requests
from pprint import pprint
import os
from dotenv import load_dotenv

load_dotenv()

json_data = {
    "task": "softo",
    "apikey": os.environ.get('AI_DEV3_API_KEY'),
    "answer": {
        "01": "kontakt@softoai.whatever",
        "02": "https://banan.ag3nts.org",
        "03":  "ISO 9001,ISO/IEC 27001"
    }
}

response = requests.post("https://centrala.ag3nts.org/report", json=json_data)

result = response.json()
pprint(result)