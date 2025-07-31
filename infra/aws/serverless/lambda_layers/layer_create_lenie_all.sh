#!/usr/bin/env bash
set -e
set -x

source ./env.sh

rm -rf tmp/lenie_${PYTHON_VERSION_NICE}
mkdir tmp/lenie_${PYTHON_VERSION_NICE}

cd tmp/lenie_${PYTHON_VERSION_NICE}
pwd

mkdir python

pip install pytube urllib3 requests beautifulsoup4  --platform ${PLATFORM} --python-version $PYTHON_VERSION --only-binary=:all: -t ./python

zip -r lenie_${PYTHON_VERSION_NICE} python

aws lambda publish-layer-version --layer-name lenie_all_layer --zip-file fileb://./lenie_${PYTHON_VERSION_NICE}.zip --compatible-runtimes python${PYTHON_VERSION} --profile ${PROFILE}

rm -rf tmp/lenie_${PYTHON_VERSION_NICE}
