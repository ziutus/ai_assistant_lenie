#!/usr/bin/env bash
set -e

# Utworzenie katalogu layers/psycopg2_2 jeżeli nie istnieje
if [ ! -d "layers/psycopg2_2" ]; then
    mkdir -p layers/psycopg2_2
fi

#mkdir layers/psycopg2_2
cd layers/psycopg2_2
pwd

# Utwórz katalog python, w którym będziemy przechowywali naszą bibliotekę
mkdir python

# Teraz skopiuj bibliotekę psycopg2-binary do katalogu python.
# Zakładam, że masz już zainstalowany psycopg2-binary w swoim środowisku. Jeśli nie, zainstaluj go używając pip install psycopg2-binary
cp -R ../../psycopg2* ./python
cp -R ../../aws_psycopg2-1.3.8.dist-info* ./python
cp -R ../../psycopg2_binary.libs* ./python

# Spakuj go do pliku zipfile.
zip -r psycopg2_layer.zip .

# Teraz możemy wgrać naszą warstwę do AWS Lambda
aws lambda publish-layer-version --layer-name psycopg2_layer --zip-file fileb://./psycopg2_layer.zip --compatible-runtimes python3.11 --profile stalker-free-developer
