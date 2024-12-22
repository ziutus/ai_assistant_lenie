from pprint import pprint
import boto3
import requests

import filetype
import os
import mimetypes

import assemblyai as aai

from dotenv import load_dotenv
load_dotenv()

from library.ai import ai_ask

rekognition = boto3.client('rekognition', region_name='us-east-1')  # Zmień region, jeśli wymagane

aai.settings.api_key = os.getenv("ASSEMBLYAI")

config = aai.TranscriptionConfig(language_code="pl")

transcriber = aai.Transcriber(config=config)



def get_filename_without_extension(filepath):
    """
    Zwraca nazwę pliku bez rozszerzenia.
    """
    filename_with_extension = os.path.basename(filepath)
    filename, _ = os.path.splitext(filename_with_extension)
    return filename


# Funkcja analizująca obraz i ekstrakcję tekstu
def extract_text_from_image(image_path):
    # Wczytaj obraz w formacie JPG
    with open(image_path, 'rb') as image_file:
        image_bytes = image_file.read()

    # Wywołanie API AWS Rekognition do wykrycia tekstu
    response = rekognition.detect_text(
        Image={'Bytes': image_bytes}
    )

    return response


def is_text_file(filepath):
    try:
        with open(filepath, 'r') as f:
            # Próba odczytania pierwszej linii. Jeśli plik nie jest tekstowy, prawdopodobnie wystąpi błąd.
            f.readline()
            return True
    except UnicodeDecodeError:
        return False

def get_file_type_mimetypes(filepath):
    """Zwraca typ MIME pliku na podstawie jego zawartości."""
    mime_type, _ = mimetypes.guess_type(filepath)
    return mime_type

def get_file_type_filetype(filepath):
    """Zwraca typ MIME pliku na podstawie jego zawartości."""
    kind = filetype.guess(filepath)
    if kind is None:
        return None
    return kind.mime


def get_file_type(filepath):
    filetype = get_file_type_filetype(filepath)
    if filetype:
        return filetype
    filetype = get_file_type_mimetypes(filepath)
    if filetype:
        return filetype
    if is_text_file(filepath):
        return "text/plain"

    return None

def list_files_in_directory(root_dir):
    """Zwraca listę plików w katalogu, pomijając podkatalog 'facts' oraz pliki zip."""
    files = []
    for dirpath, dirnames, filenames in os.walk(root_dir):
        if 'facts' in dirnames:
            dirnames.remove('facts')  # Ignoruj podkatalog 'facts'
        for filename in filenames:
            if not filename.endswith('.zip'):  # Pomijaj pliki .zip
                files.append(os.path.join(dirpath, filename))
    return files

files = list_files_in_directory("../tmp/dane_z_fabryki")

pprint(files)

target_dir = "../tmp/dane_z_fabryki_obrobione"

text_files = []


file_extension = {}

for filepath in files:
    file_type = get_file_type(filepath)
    rozszerzenie = os.path.splitext(filepath)[1][1:]
    path1 = target_dir + "/" + get_filename_without_extension(filepath)
    text_file =  path1 + ".txt"

    file_extension[get_filename_without_extension(filepath)] = rozszerzenie

    print("----")
    print(f"text file to: {text_file}")
    print(f"Plik: {filepath} | rozszerzenie: {rozszerzenie} ", end=" | ")

    if file_type:
        print(f"Typ: {file_type} ")
        if file_type == "text/plain":
            text_files.append(filepath)
            continue

        if file_type == "audio/mpeg":
            if os.path.exists(text_file):
                print("Text file already exists")
                text_files.append(text_file)
                continue
            else:
                print("Will make transcription")
                transcript = transcriber.transcribe(filepath)

                if transcript.status == aai.TranscriptStatus.error:
                    print(transcript.error)
                    exit(1)
                else:
                    print(transcript.text)
                    text_files.append(text_file)

                    with open(text_file, "w", encoding="utf-8") as file:
                        file.write(transcript.text)
                continue

        if file_type in ["image/png", "image/jpeg"]:
            if os.path.exists(text_file):
                print("Text file already exists")
                text_files.append(text_file)
                continue
            else:
                print("Will make recognition")
                result = extract_text_from_image(filepath)
                print(result)
                result_text = ""
                for text in result['TextDetections']:
                    result_text += text['DetectedText'] + " "
                print(result_text)
                with open(text_file, "w", encoding="utf-8") as f:
                    f.write(result_text)
                continue

        print(f"Unknown file type {file_type}...")
        exit(1)

    else:
        print(f" | Nie można określić typu pliku.")

people = []
hardware = []
others = []

pprint(text_files)

for filepath in text_files:
    print(filepath)

    # if filepath != "tmp/dane_z_fabryki_obrobione/2024-11-12_report-12-sektor_A1.txt":
    #     continue

    # Load the file content into `robo_data`
    with open(filepath, "r", encoding="utf-8") as file:
        robo_data = file.read()

    # Display the content of `robo_data`
    print("File content (robo_data):")
    print(robo_data)
    

    ai_task = f"""
    Poniższy tekst zawiera dane z pewnej gry. Opis dotyczy fabryki i ochrony tej fabryki. Przypisz go do jednej z kategorii:
     * jeżeli tekst opisuje schwytanie czyli pojmanie ludzi lub o śladach ich obecności, przypis do kategorii "people", Nie przypis tej do kategorii, gdy opisywane jest samopoczucie lub nastawienie zespołu patrolowego (brygady), zatrudnianiem do zespołu ochrony albo nie związane jest z ochroną fabryki.
     * jeżeli tekst opisuje usterki hardware, przypis do kategorii "hardware", nie przypisuj notatek związanych z software ani aktualizacją algorytmów
     * pozostałe teksty przypisuj do kategorii "others".
     zwróć jedynie nazwę kategorii. 
    
    text: {robo_data}.
    """

    ai_answer = ai_ask(ai_task, model="gpt-4o", temperature=0.0)

    print("\n\n")
    print(f"AI answer: {ai_answer.response_text}")
    if ai_answer.response_text == "people":
        people.append(get_filename_without_extension(filepath) + "." + file_extension[get_filename_without_extension(filepath)])
    elif ai_answer.response_text == "hardware":
        hardware.append(get_filename_without_extension(filepath) + "." + file_extension[get_filename_without_extension(filepath)])
    else:
        others.append(get_filename_without_extension(filepath) + "." + file_extension[get_filename_without_extension(filepath)])
        print("Unknown category, assigned to 'others'")
    print("----")

# pprint(text_files)
answer = {
    "people": people,
    "hardware": hardware
}

pprint(answer)

json_data = {
    "task": "kategorie",
    "apikey": os.environ.get('AI_DEV3_API_KEY'),
    "answer": answer
}

response = requests.post("https://centrala.ag3nts.org/report", json=json_data)

result = response.json()
pprint(result)

exit(0)