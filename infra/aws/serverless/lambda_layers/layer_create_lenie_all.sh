#!/usr/bin/env bash
set -e
set -x

source ./env.sh


TMP_DIR="tmp/lenie_${PYTHON_VERSION_NICE}"

rm -rf $TMP_DIR
mkdir $TMP_DIR

cd $TMP_DIR
pwd

mkdir python

pip install pytube urllib3 requests beautifulsoup4  --platform ${PLATFORM} --python-version $PYTHON_VERSION --only-binary=:all: -t ./python

zip -r lenie_${PYTHON_VERSION_NICE} python

aws lambda publish-layer-version --layer-name lenie_all_layer --zip-file fileb://./lenie_${PYTHON_VERSION_NICE}.zip --compatible-runtimes python${PYTHON_VERSION} --profile ${PROFILE}

rm -rf $TMP_DIR
