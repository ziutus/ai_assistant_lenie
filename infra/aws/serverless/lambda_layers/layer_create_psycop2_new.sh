#!/usr/bin/env bash
set -e
set -x

source ./env.sh

TMP_DIR="tmp/psycopg2_new"

rm -rf $TMP_DIR
mkdir -p $TMP_DIR

cd $TMP_DIR
pwd

mkdir python

pip install psycopg2-binary --platform ${PLATFORM}  --python-version $PYTHON_VERSION --only-binary=:all: -t ./python

zip -r psycopg2_new python

aws lambda publish-layer-version --layer-name psycopg2_new_layer --zip-file fileb://./psycopg2_new.zip --compatible-runtimes python${PYTHON_VERSION} --profile ${PROFILE}

rm -rf $TMP_DIR
