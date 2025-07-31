# Użyj obrazu Ubuntu jako bazy
FROM ubuntu:24.04

# Ustaw katalog roboczy
WORKDIR /workspace

# Skopiuj skrypt do kontenera
COPY script.sh .

# Ustaw uprawnienia wykonania
RUN chmod +x ./script.sh

# Domyślne polecenie kontenera: uruchom skrypt
CMD ["./script.sh"]
