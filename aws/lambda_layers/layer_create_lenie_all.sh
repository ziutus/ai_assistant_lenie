#!/usr/bin/env bash
set -e
set -x

PYTHON_VERSION=3.11
PROFILE="lenie-ai-admin"

rm -rf tmp/lenie_3_11
mkdir tmp/lenie_3_11

cd tmp/lenie_3_11
pwd

mkdir python

pip install pytube urllib3 requests beautifulsoup4  --platform manylinux2014_x86_64 --python-version $PYTHON_VERSION --only-binary=:all: -t ./python

zip -r lenie_3_11 python

aws lambda publish-layer-version --layer-name lenie_all_layer --zip-file fileb://./lenie_3_11.zip --compatible-runtimes python${PYTHON_VERSION} --profile ${PROFILE}

rm -rf tmp/lenie_3_11
