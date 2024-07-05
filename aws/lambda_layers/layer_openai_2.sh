#!/usr/bin/env bash
set -e
set -x

rm -rf tmp/lenie_openai
mkdir tmp/lenie_openai

cd tmp/lenie_openai
pwd

mkdir python

pip install openai  --platform manylinux2014_x86_64 --python-version 3.10  --only-binary=:all: -t ./python

zip -r lenie_openai.zip python

# Teraz możemy wgrać naszą warstwę do AWS Lambda
aws lambda publish-layer-version --layer-name lenie_openai --zip-file fileb://./lenie_openai.zip --compatible-runtimes python3.10 --profile stalker-free-developer

rm -rf tmp/lenie
