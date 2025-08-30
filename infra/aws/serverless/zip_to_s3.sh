#!/usr/bin/env bash
set -e

source ./env.sh

#cat ./function_list_cf.txt

FUNCTION_LIST=$(cat ./function_list_cf.txt)

echo "function list: $FUNCTION_LIST"

TMP_DIR="tmp"
mkdir -p $TMP_DIR


cd $TMP_DIR || exit
#zip lambda.zip lambda_function.py

pwd

while IFS= read -r FUNCTION_NAME; do
  echo "function1 : $FUNCTION_NAME"
  # Pomiń puste linie
  if [[ -z "$FUNCTION_NAME" ]]; then
    echo  "Ignoring empty line"
    continue
  fi

  FUNCTION_NAME=$(echo $FUNCTION_NAME | tr -d '\r')
  echo "function2: >$FUNCTION_NAME<"
  LAMBDA_NAME="${PROJECT_NAME}-${ENVIRONMENT}-${FUNCTION_NAME}"
  echo "function3: >$LAMBDA_NAME<"

  zip -r "${LAMBDA_NAME}.zip" "../lambdas/${FUNCTION_NAME}"

  # Wysyłanie pliku zip na S3
  aws s3 cp "${LAMBDA_NAME}.zip" "s3://${AWS_S3_BUCKET_NAME}/${LAMBDA_NAME}.zip"

  echo "Uploaded ${LAMBDA_NAME}.zip to S3"

done <<< "$FUNCTION_LIST"

echo "Exit Code: 0"
exit 0

