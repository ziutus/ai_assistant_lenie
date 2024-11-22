import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv
import os

load_dotenv()

# Konfiguracja
jenkins_url = os.getenv("JENKINS_URL")
job_name = "lenie_server"
username = os.getenv("JENKINS_USER")
password = os.getenv("JENKINS_PASSWORD")

# URL API
api_url = f"{jenkins_url}/job/{job_name}/api/json"

# Wysyłanie żądania do API Jenkins
response = requests.get(api_url, auth=HTTPBasicAuth(username, password), verify=False)

# Sprawdzanie statusu odpowiedzi
if response.status_code == 200:
    # Parsowanie odpowiedzi JSON
    data = response.json()
    builds = data.get("builds", [])

    print(f"Liczba uruchomień: {len(builds)}")

    # Wyświetlanie informacji o każdym uruchomieniu
    for build in builds:
        build_number = build.get("number")
        build_url = build.get("url")
        print(f"Uruchomienie {build_number}: {build_url}")
else:
    print(f"Nie udało się pobrać danych z Jenkins. Kod statusu: {response.status_code}")