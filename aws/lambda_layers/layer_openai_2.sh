#!/usr/bin/env bash
set -e
set -x

PYTHON_VERSION=3.11
PROFILE="lenie-ai-admin"

rm -rf tmp/lenie_openai
mkdir tmp/lenie_openai

cd tmp/lenie_openai
pwd

mkdir python

pip install openai  --platform manylinux2014_x86_64 --python-version $PYTHON_VERSION  --only-binary=:all: -t ./python

zip -r lenie_openai.zip python

# Teraz możemy wgrać naszą warstwę do AWS Lambda
aws lambda publish-layer-version --layer-name lenie_openai --zip-file fileb://./lenie_openai.zip --compatible-runtimes python${PYTHON_VERSION} --profile ${PROFILE}

rm -rf tmp/lenie
