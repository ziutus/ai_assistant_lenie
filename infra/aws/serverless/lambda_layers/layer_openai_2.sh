#!/usr/bin/env bash
set -e
set -x

source ./env.sh

TMP_DIR="tmp/lenie_openai"

rm -rf $TMP_DIR
mkdir -p $TMP_DIR

cd $TMP_DIR
pwd

mkdir python

pip install openai  --platform $PLATFORM --python-version $PYTHON_VERSION  --only-binary=:all: -t ./python

zip -r lenie_openai.zip python

# Teraz możemy wgrać naszą warstwę do AWS Lambda
aws lambda publish-layer-version --layer-name lenie_openai --zip-file fileb://./lenie_openai.zip --compatible-runtimes python${PYTHON_VERSION} --profile ${PROFILE}

rm -rf $TMP_DIR

exit 0
