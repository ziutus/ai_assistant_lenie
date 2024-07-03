#!/usr/bin/env bash
set -e
set -x

PYTHON_VERSION=3.11

rm -rf tmp/psycopg2_new
mkdir tmp/psycopg2_new

cd tmp/psycopg2_new
pwd

mkdir python

pip install psycopg2-binary --platform manylinux2014_x86_64  --python-version $PYTHON_VERSION --only-binary=:all: -t ./python

zip -r psycopg2_new python

aws lambda publish-layer-version --layer-name psycopg2_new_layer --zip-file fileb://./psycopg2_new.zip --compatible-runtimes python${PYTHON_VERSION} --profile stalker-free-developer

rm -rf tmp/psycopg2_new
