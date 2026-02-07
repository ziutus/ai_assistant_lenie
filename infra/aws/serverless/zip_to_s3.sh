#!/usr/bin/env bash
set -e
set -x

source ./env.sh

# Check if parameter is provided
if [ $# -eq 0 ]; then
  echo "Usage: $0 <functions_type>"
  echo "functions_type: 'simple' or 'app'"
  exit 1
fi

FUNCTIONS_TYPE=${1:-"simple"}

FUNCTION_LIST_SIMPLE="./function_list_cf.txt"
FUNCTION_LIST_APP="./function_list_cf_app.txt"

if [ "$FUNCTIONS_TYPE" == "app" ]; then
  FUNCTION_LIST_FILE=$FUNCTION_LIST_APP
else
  FUNCTION_LIST_FILE=$FUNCTION_LIST_SIMPLE
fi

FUNCTION_LIST=$(cat $FUNCTION_LIST_FILE)

echo "function list: $FUNCTION_LIST"

TMP_DIR="tmp"
mkdir -p $TMP_DIR

cd $TMP_DIR || exit
#zip lambda.zip lambda_function.py

CURRENT_DIR=$(pwd)
#ls -l "$CURRENT_DIR"/../../../../


while IFS= read -r FUNCTION_NAME; do
  echo "function1 : $FUNCTION_NAME"
  # Pomiń puste linie
  if [[ -z "$FUNCTION_NAME" ]]; then
    echo "Ignoring empty line"
    continue
  fi

  FUNCTION_NAME=$(echo $FUNCTION_NAME | tr -d '\r')
  echo "function2: >$FUNCTION_NAME<"
  LAMBDA_NAME="${PROJECT_NAME}-${ENVIRONMENT}-${FUNCTION_NAME}"
  echo "function3: >$LAMBDA_NAME<"

  TEMP_FUNCTION_DIR="${LAMBDA_NAME}_temp"
  mkdir -p "${TEMP_FUNCTION_DIR}"

  # Skopiuj zawartość katalogu funkcji do tymczasowego katalogu
  cp -r "../lambdas/${FUNCTION_NAME}/"* "${TEMP_FUNCTION_DIR}/"
  if [ "$FUNCTIONS_TYPE" == "app" ]; then
    ls -l "$CURRENT_DIR"/../
    cp -r "$CURRENT_DIR"/../../../../backend/library "${TEMP_FUNCTION_DIR}/"
  fi

  # Spakuj zawartość tymczasowego katalogu
  cd ${TEMP_FUNCTION_DIR}
  pwd
  ls -l
  zip -r "${LAMBDA_NAME}.zip" "./"*

  cd ..
  ls
  mv ${TEMP_FUNCTION_DIR}/*.zip ./

  ls

  # Usuń tymczasowy katalog
  rm -rf "${TEMP_FUNCTION_DIR}"

  # Wysyłanie pliku zip na S3
  aws s3 cp "${LAMBDA_NAME}.zip" "s3://${AWS_S3_BUCKET_NAME}/${LAMBDA_NAME}.zip"
  echo "Uploaded ${LAMBDA_NAME}.zip to S3"

  aws lambda update-function-code --function-name ${LAMBDA_NAME}  --zip-file fileb://"${LAMBDA_NAME}.zip" --profile ${PROFILE}

done <<<"$FUNCTION_LIST"

echo "Exit Code: 0"
exit 0
