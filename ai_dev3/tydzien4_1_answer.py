from pprint import pprint
import os

import langfuse
import requests

from library.ai import ai_ask, ai_describe_image
from dotenv import load_dotenv
from langfuse import Langfuse
from langfuse.decorators import observe
from langfuse.openai import openai

load_dotenv()

langfuse = Langfuse()

def aidev3(task: str):

    json_data = {
            "task": "photos",
            "apikey": os.environ.get('AI_DEV3_API_KEY'),
            "answer": task
    }

    result = requests.post("https://centrala.ag3nts.org/report", json=json_data).json()
    pprint(result)

    if result['code'] != 0:
        pprint(result)
        raise("Wrong answer from AI Dev3 API")

    return result['message']

images = ['https://centrala.ag3nts.org/dane/barbara/IMG_559_FGR4.PNG',
 'https://centrala.ag3nts.org/dane/barbara/IMG_1410_FXER.PNG',
 'https://centrala.ag3nts.org/dane/barbara/IMG_1443_FT12.PNG',
 'https://centrala.ag3nts.org/dane/barbara/IMG_1444.PNG']

prompt = langfuse.get_prompt("aidev3_tydzien4_1_final_review")
ai_task = prompt.compile()
person_description = ai_describe_image(question=ai_task, model_id="gpt-4o-mini", image_urls=images, max_tokens=1000)

pprint(person_description)

aidev3_answer = aidev3(person_description)
print("aidev3_answer: ", aidev3_answer)