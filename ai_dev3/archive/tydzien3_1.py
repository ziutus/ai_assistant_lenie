import json
import os
from pprint import pprint
from dotenv import load_dotenv
import requests
import re
from library.ai import ai_ask

load_dotenv()


def extract_sector(filename):
    """
    Funkcja pobiera nazwę sektora z podanego ciągu znaków i zwraca bez podkreślnika.

    Args:
    filename (str): Pełna nazwa pliku z sektorem.

    Returns:
    str: Wyodrębniona wartość sektora z zamienionym podkreślnikiem na spację,
         lub None, jeśli sektor nie został znaleziony.
    """
    match = re.search(r'sektor_[A-Za-z0-9]+', filename)
    if match:
        return match.group(0).replace("_", " ")
    return None


def list_files_in_directory(root_dir, ignore_dirs=[], ignore_extensions=[], only_extensions=[]):
    files = []
    for dirpath, dirnames, filenames in os.walk(root_dir):
        dirnames[:] = [d for d in dirnames if d not in ignore_dirs]  # Ignoruj katalogi z ignore_dirs
        for filename in filenames:
            if (not any(filename.endswith(ext) for ext in ignore_extensions) and  # Ignoruj pliki o rozszerzeniach z ignore_extensions
                (not only_extensions or any(filename.endswith(ext) for ext in only_extensions))):  # Uwzględnij tylko pliki z only_extensions (jeśli podano)
                files.append(os.path.join(dirpath, filename))
    return files

def list_txt_files(directory):
    try:
        txt_files = [f for f in os.listdir(directory) if
                     f.endswith('.txt') and os.path.isfile(os.path.join(directory, f))]
        return txt_files
    except FileNotFoundError:
        print(f"Katalog {directory} nie został znaleziony.")
        return []
    except Exception as e:
        print(f"Wystąpił błąd: {e}")
        return []

files = list_files_in_directory("../tmp/tydzien3_1/facts", only_extensions=[".txt"])

reports_files = {
    "2024-11-12_report-00-sektor_C4.txt": ["tmp/tydzien3_1/facts/f04.txt"],
    "2024-11-12_report-01-sektor_A1.txt": ["tmp/tydzien3_1/facts/f01.txt", "tmp/tydzien3_1/facts/f02.txt"],
    "2024-11-12_report-02-sektor_A3.txt": ["tmp/tydzien3_1/facts/f01.txt", "tmp/tydzien3_1/facts/f02.txt"],
    "2024-11-12_report-03-sektor_A3.txt": ["tmp/tydzien3_1/facts/f01.txt", "tmp/tydzien3_1/facts/f02.txt"],
    "2024-11-12_report-04-sektor_B2.txt": ["tmp/tydzien3_1/facts/f03.txt"],
    "2024-11-12_report-05-sektor_C1.txt": ["tmp/tydzien3_1/facts/f01.txt", "tmp/tydzien3_1/facts/f02.txt", "tmp/tydzien3_1/facts/f03.txt"],
    "2024-11-12_report-06-sektor_C2.txt": ["tmp/tydzien3_1/facts/f01.txt"],
    "2024-11-12_report-07-sektor_C4.txt": ["tmp/tydzien3_1/facts/f01.txt", "tmp/tydzien3_1/facts/f05.txt"],
    "2024-11-12_report-08-sektor_A1.txt": ["tmp/tydzien3_1/facts/f02.txt"],
    "2024-11-12_report-09-sektor_C2.txt": ["tmp/tydzien3_1/facts/f01.txt", "tmp/tydzien3_1/facts/f02.txt", "tmp/tydzien3_1/facts/f03.txt", "tmp/tydzien3_1/facts/f09.txt"],
}

fakty = ""

for file in files:
    with open(file, "r", encoding="utf-8") as f:
        fakty += f"<FAKT><NAZWA>{file}</NAZWA><TRESC>" + f.read() + "</TRESC></FAKT>\n"

raporty = list_txt_files("tmp/tydzien3_1/")

answers = {}

raporty2 = raporty.copy()
# raporty2 = ["2024-11-12_report-00-sektor_C4.txt"]



for raport in raporty2:
    raport_text = ""
    sektor = extract_sector(raport)

    if raport in reports_files:
        fakty = ""
        for file in reports_files[raport]:
            with open(file, "r", encoding="utf-8") as f:
                fakty += f"<FAKT><NAZWA>{file}</NAZWA><TRESC>" + f.read() + "</TRESC></FAKT>\n"

    with open("tmp/tydzien3_1/"+ raport, "r", encoding="utf-8") as f:
        raport_text += f"<PLIK>{raport}</PLIK><TRESC>" + f.read() + "</TRESC>"

    ai_task = f"""
    znając FAKTY (podane poniżej), wygeneruj słowa kluczowe w formie mianownika do TEKST. Minimum 20 słów.

    jeżeli TEKST opisuje osobę, odpowiedz powinna zawierać informacje o osobie jak wiek, zawód, zainteresowania, miejsca pracy, miejsce zatrzymania, powód zatrzymania
    Odpowiedź zwróć w postaci json: 
    {{
        "human": "True",
        "person": "Imię i Nazwisko",
        "key_words":"słowo1, słowo2, słowo3",
        "source": ["FAKT NAZWA", "FAKT NAZWA"]
    }}

    Jeżeli Tekst opisuje coś innego, zwróc w postaci json: 
    {{
        "human": "False",
        "person": "",
        "key_words":"słowo1, słowo2, słowo3",
        "source": ["FAKT NAZWA", "FAKT NAZWA"]
    }}
    
    Wskaż FAKT nazwę, która została użyta do wygenerowania listy słów
    <TEKST>{raport_text}</TEKST>
    <FAKTY>{fakty}</FAKTY>

    """

    print(ai_task)

    # ai_answer = ai_ask(ai_task, model="amazon.nova-pro", temperature=0.0)
    ai_answer = ai_ask(ai_task, model="gpt-4o-2024-05-13", temperature=0.5, max_token_count=20000)

    print(ai_answer.response_text)

    print(f"sektor: {sektor}")

    response_text = ai_answer.response_text.strip("```json").strip("```")

    response_json = json.loads(response_text)

    print(json.dumps(response_json, indent=4))

    response_json["key_words"] = f"{sektor}," + response_json["key_words"]

    print(json.dumps(response_json, indent=4))

    # print("\n\n")
    # print(f"AI answer: {response_text}")
    # answers[raport] = response_text
    with open("tmp/tydzien3_1/answers/"+ raport, "w", encoding="utf-8") as f:
        f.write(json.dumps(response_json))
        # f.write(json.dumps(ai_answer.response_text))


# json_data = {
#     "task": "arxiv",
#     "apikey": os.environ.get('AI_DEV3_API_KEY'),
#     "answer": json.dumps(answers)
# }
#
# pprint(json_data)

# response = requests.post("https://centrala.ag3nts.org/report", json=json_data)
#
# result = response.json()
# pprint(result)