#!/bin/bash

# Załaduj zmienne środowiskowe
set -a
source ../../.env
set +a
#set -x

# Konfiguracja
jenkins_url="$JENKINS_URL"
job_name="lenie_server"
username="$JENKINS_USER"
password="$JENKINS_PASSWORD"

# URL API
api_url="${jenkins_url}/job/${job_name}/api/json"

# Wysyłanie żądania do API Jenkins
response=$(curl --insecure -s -u "$username:$password" "$api_url")

# Sprawdzanie statusu odpowiedzi
http_status=$(echo "$response" | jq -r '.status // empty')

if [[ -z "$http_status" ]]; then
    # Odpowiedź prawidłowa jeśli powyższy warunek jest spełniony
    builds=$(echo "$response" | jq '.builds')

    echo "Liczba uruchomień: $(echo "$builds" | jq 'length')"

    # Wyświetlanie informacji o każdym uruchomieniu
    for build in $(echo "$builds" | jq -c '.[]'); do
        build_number=$(echo "$build" | jq '.number')
        build_url=$(echo "$build" | jq -r '.url')
        echo "Uruchomienie $build_number: $build_url"
    done
else
    echo "Nie udało się pobrać danych z Jenkins. Kod statusu: $http_status"
fi