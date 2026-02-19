#!/usr/bin/env bash
set -e
#set -x

ENV_FILE="./env.sh"
source "$ENV_FILE"

# Validate required environment variables from sourced env file
if [ -z "$AWS_ACCOUNT_ID" ] || [ -z "$PROFILE" ] || [ -z "$AWS_S3_BUCKET_NAME" ]; then
  echo "ERROR: Required environment variables not set. Check ${ENV_FILE}" >&2
  exit 1
fi

# Parse flags (--yes/-y) before positional arguments
AUTO_CONFIRM=false
POSITIONAL_ARGS=()
for arg in "$@"; do
  case "$arg" in
    --yes|-y) AUTO_CONFIRM=true ;;
    *) POSITIONAL_ARGS+=("$arg") ;;
  esac
done
set -- "${POSITIONAL_ARGS[@]}"

# Check if parameter is provided
if [ $# -eq 0 ]; then
  echo "Usage: $0 [--yes|-y] <functions_type>"
  echo "functions_type: 'simple' or 'app'"
  echo "  --yes, -y    Skip confirmation prompt"
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

echo "================================================"
echo "  Deployment Target Information"
echo "================================================"
echo "  Env file:    ${ENV_FILE}"
echo "  AWS Account: ${AWS_ACCOUNT_ID}"
echo "  Profile:     ${PROFILE}"
echo "  Environment: ${ENVIRONMENT}"
echo "  S3 Bucket:   ${AWS_S3_BUCKET_NAME}"
echo "================================================"

if [ "$AUTO_CONFIRM" != "true" ]; then
  read -p "Continue with deployment? (y/N) " confirm
  if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
    echo "Deployment cancelled."
    exit 0
  fi
fi

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

  aws lambda update-function-code --function-name ${LAMBDA_NAME}  --zip-file fileb://"${LAMBDA_NAME}.zip" --profile ${PROFILE} || echo "Warning: Lambda ${LAMBDA_NAME} not found in AWS — skipping update (will be created by CloudFormation)"

done <<<"$FUNCTION_LIST"

echo "Exit Code: 0"
exit 0
