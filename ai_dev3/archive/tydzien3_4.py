import json
from pprint import pprint
from dotenv import load_dotenv
import os
import re
import requests
from unidecode import unidecode



from library.ai import ai_ask

load_dotenv()

model="gpt-4o-2024-05-13"

start_information="""
Podczas pobytu w Krakowie w 2019 roku, Barbara Zawadzka poznała swojego ówczesnego narzeczonego, a obecnie męża, 
Aleksandra Ragowskiego. Tam też poznali osobę prawdopodobnie powiązaną z ruchem oporu, której dane nie są nam znane. 
Istnieje podejrzenie, że już wtedy pracowali oni nad planami ograniczenia rozwoju sztucznej inteligencji, tłumacząc
to względami bezpieczeństwa. Tajemniczy osobnik zajmował się także organizacją spotkań mających na celu podnoszenie
wiedzy na temat wykorzystania sztucznej inteligencji przez programistów. Na spotkania te uczęszczała także Barbara.

W okolicach 2021 roku Ragowski udał się do Warszawy celem spotkania z profesorem Andrzejem Majem. Prawdopodobnie nie 
zabrał ze sobą żony, a cel ich spotkania nie jest do końca jasny.

Podczas pobytu w Warszawie, w instytucie profesora doszło do incydentu, w wyniku którego, jeden z laborantów - 
Rafał Bomba - zaginął. Niepotwierdzone źródła informacji podają jednak, że Rafał spędził około 2 lata, wynajmując 
pokój w pewnym hotelu. Dlaczego zniknął?  Przed kim się ukrywał? Z kim kontaktował się przez ten czas i dlaczego 
ujawnił się po tym czasie? Na te pytania nie znamy odpowiedzi, ale agenci starają się uzupełnić brakujące informacje.

Istnieje podejrzenie, że Rafał mógł być powiązany z ruchem oporu. Prawdopodobnie przekazał on notatki profesora Maja
w ręce Ragowskiego, a ten po powrocie do Krakowa mógł przekazać je swojej żonie. Z tego powodu uwaga naszej jednostki 
skupia się na odnalezieniu Barbary.

Aktualne miejsce pobytu Barbary Zawadzkiej nie jest znane. Przypuszczamy jednak, że nie opuściła ona kraju.
"""

answer_api = "https://centrala.ag3nts.org/report"
places_api = "https://centrala.ag3nts.org/places"
people_api = "https://centrala.ag3nts.org/people"

ai_task = f"""
Z tekstu poniżej wybierz informacje o osobach i miejscach przebywania. 
Odpowiedz zwróć w postaci tablicy json, gdzie każda osoba ma swój rekord w postaci:
{{
"imie_nazwisko": "imie nazwisko", 
"imie": "imie",
"miejsce_przebywania": ["miasto1", "miasto2", "miasto3"]
}} 

TEKST: {start_information}

"""

# ai_answer = ai_ask(ai_task, model=model, temperature=0.5, max_token_count=20000)
#
# print(ai_answer.response_text)

inital_json_text = """
[
    {
        "imie_nazwisko": "Barbara Zawadzka",
        "imie": "Barbara",
        "miejsce_przebywania": ["Kraków"]
    },
    {
        "imie_nazwisko": "Aleksander Ragowski",
        "imie": "Aleksander",
        "miejsce_przebywania": ["Kraków", "Warszawa"]
    },
    {
        "imie_nazwisko": "Andrzej Maj",
        "imie": "Andrzej",
        "miejsce_przebywania": ["Warszawa"]
    },
    {
        "imie_nazwisko": "Rafał Bomba",
        "imie": "Rafal",
        "miejsce_przebywania": ["Warszawa", "hotel"]
    }
]
"""
json_data = json.loads(inital_json_text)
# pprint(json_data)


places_checked = []
places_to_check = []
persons_checked = []
persons_to_check = []

for person in json_data:
    # pprint(person)
    if person["imie"] not in persons_to_check:
        persons_to_check.append(person["imie"].upper())
    for place in person["miejsce_przebywania"]:
        place = place.upper()
        if place == 'HOTEL':
            continue

        if place == 'KRAKÓW':
            place = 'KRAKOW'
        if place not in places_to_check:
            places_to_check.append(place)


city_to_find = None
barbara_found = False

iteration = 0
while len(places_to_check) > 0 and len(persons_to_check) > 0 and not barbara_found:
    print(f"---- iteration: {iteration} ----")
    print(f"places to check: {places_to_check}")
    print(f"persons to check: {persons_to_check}")

    if len(places_to_check) == 0 and len(persons_to_check) == 0:
        print("ERROR: No places or persons to check")
        exit(0)

    for place in places_to_check:
        place = place.upper()
        print("Checking city ", place)
        api_city_query = {
            "apikey": os.environ.get('AI_DEV3_API_KEY'),
            "query":  place
        }
        response = requests.post(places_api, json=api_city_query)
        result = response.json()
        pprint(result)

        if result["code"] != 0:
            raise Exception("wrong answer from places api")

        if result['message'] == "[**RESTRICTED DATA**]":
            print("Ignoring restricted data as API will not aswer :)")
            continue


        print(f"Found in >{place}< persons >{result['message']}<")

        for person in result["message"].split(" "):
            person = unidecode(person.upper())
            if person == "BARBARA" and place != "KRAKOW":
                barbara_found = True
                city_to_find = place
                print(f"SUCCESS: Found Barbary in {place}")

                db_query = {
                    "task": "loop",
                    "apikey": os.environ.get('AI_DEV3_API_KEY'),
                    "answer": city_to_find
                }

                pprint(db_query)

                response = requests.post(answer_api, json=db_query)

                result = response.json()
                pprint(result)

                exit()

            if person not in persons_checked and person not in persons_to_check:
                print(f"Found new person to check {person} in {place}")
                persons_to_check.append(person)

        places_checked.append(place)
        places_to_check.remove(place)

    for person in persons_to_check:
        person = unidecode(person.upper())
        print("Checking person ", person)

        if person == 'BARBARA':
            print("Ignoring Barbara as API will not aswer :)")
            continue

        api_person_query = {
            "apikey": os.environ.get('AI_DEV3_API_KEY'),
            "query":  person
        }
        response = requests.post(people_api, json=api_person_query)
        result = response.json()

        pprint(result)
        if result["code"] != 0:
            raise Exception("wrong answer from people api")

        if result['message'] == "[**RESTRICTED DATA**]":
            print("Ignoring restricted data as API will not aswer :)")
            continue


        for place in result["message"].split(" "):
            place = place.upper()
            if place not in places_checked:
                print(f"Found new place to check {place} for {person}")
                places_to_check.append(place)

    iteration += 1