import json

import requests
from pprint import pprint
import os
from dotenv import load_dotenv
from openai import OpenAI
from langfuse import Langfuse
from langfuse.decorators import observe
from langfuse.openai import openai
from library.ai import ai_ask, ai_describe_image

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

iteration = 0

possible_actions = {"REPAIR", "BRIGHTEN", "DARKEN"}

api_answers = []

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


def ai_question(initial_question: str, model: str,  prompt_id: str = None):
    prompt = langfuse.get_prompt(prompt_id)
    ai_task = prompt.compile(TEXT=initial_question)

    ai_answer = ai_ask(ai_task, model=model, temperature=0.5, max_token_count=20000)

    return ai_answer.response_text



txt_list_of_files = aidev3("START")
print("DEBUG: initial information: ", txt_list_of_files)
list_of_files_ai_txt = ai_question(txt_list_of_files, model="gpt-4o-mini", prompt_id="aidevs3_tydzien4_1_initial")
pprint(list_of_files_ai_txt)

images_urls = list_of_files_ai_txt.replace('"', '').split(",")
pprint(images_urls)

if len(images_urls) != 4:
    print("Wrong number of images, got {len(images_urls)}, expected: 4")
    exit(1)

# images_urls = ['IMG_1410.PNG']

files_ok = []

for image_file in images_urls:
    print(f"----- image file: {image_file} -----")
    image_file = image_file.strip()
    iteration = 1
    unsuccessful_actions = []
    force_action = None
    while iteration < 7:
        ai_image_action = None
        if len(unsuccessful_actions) == 3:
            print("ERROR: wszystkie możliwe akcje zostały na zdjęciu przeprowadzone, przechodzę do kolejnego")
            break

        if len(unsuccessful_actions) == 2:
            print("DEBUG: I'm making hack, guessing missing action from list of possible actions")
            force_action = list(possible_actions - set(unsuccessful_actions))  # Convert set to list
            pprint(force_action)


        # print(f"DEBUG: image file: {image_file}")
        image_url = f"https://centrala.ag3nts.org/dane/barbara/{image_file}"
        # print(f"DEBUG: image url: {image_url}")

        if not force_action:
            prompt = langfuse.get_prompt("aidev3_tydzien4_1_validate_image")
            ai_task = prompt.compile(LAST_UNSUCCESSFUL_ACTION=",".join(unsuccessful_actions))
            print(ai_task)
            ai_image_action = ai_describe_image(image_urls = [image_url], model_id="gpt-4o-mini", question=ai_task)
            print(f"File: {image_url}, answer from AI: {ai_image_action}")

            if ai_image_action in ["ALL_IS_OK", "NONE"]:
                files_ok.append(image_file)
                break
            last_action = ai_image_action

            if ai_image_action == "MISSING":
                raise("ERROR: missing image")

            if ai_image_action not in possible_actions:
                print("ERROR: wrong action, please correct loop")
                raise ("ERROR: wrong action, please correct loop")
        else:
            ai_image_action = force_action[0]

        aidev3_task = f"{ai_image_action} {image_file} "

        aidev3_answer = aidev3(aidev3_task)

        print("aidev3_answer: ", aidev3_answer)

        prompt = langfuse.get_prompt("aidev3_tydzien4_1_take_one_filename")
        ai_task = prompt.compile(TEXT=aidev3_answer)

        ai_answer = ai_ask(ai_task, model="gpt-4o-mini")
        new_filename = ai_answer.response_text
        pprint(new_filename)

        prompt2 = langfuse.get_prompt("aidev3_tydzien4_1_is_filename_final")
        ai_task2 = prompt2.compile(TEXT=aidev3_answer)
        ai_answer2 = ai_ask(ai_task2, model="gpt-4o-mini")
        if ai_answer2.response_text == "FINAL":
            unsuccessful_actions = []
            files_ok.append(new_filename)
            break

        if new_filename == "NONE":
            print("ERROR: can't take new filename, using old one")
            if last_action not in unsuccessful_actions:
                unsuccessful_actions.append(last_action)
            else:
                print(f"Chyba coś nie tak bo znowu chcę zrobić zrobić {last_action}")

            iteration += 1
            continue

        image_file = new_filename.strip()
        unsuccessful_actions = []
        iteration += 1


pprint(files_ok)

if len(files_ok) != 4:
    print("ERROR: wrong number of files corrected files, please correct loop")
    raise ("ERROR: wrong number of files corrected files, please correct loop")

prompt = langfuse.get_prompt("aidev3_tydzien4_1_final_review")
ai_task = prompt.compile()
print("final prompt: ", ai_task)
image_urls = []
for file in files_ok:
    image_urls.append(f"https://centrala.ag3nts.org/dane/barbara/{file}")

pprint(image_urls)
ai_answer = ai_describe_image(ai_task, model_id="gpt-4o-mini", image_urls=image_urls)

person_description = ai_answer.response_text
aidev3_answer = aidev3(person_description)
print("aidev3_answer: ", aidev3_answer)

exit(0)