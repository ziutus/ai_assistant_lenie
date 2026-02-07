#!/usr/bin/env bash
set -e

source ./env.sh

FUNCTION_LIST=$(cat ./function_list.txt)

TMP_DIR="tmp"
mkdir -p $TMP_DIR


echo 'def lambda_handler(event, context):
    return {"statusCode": 200, "body": "Empty Lambda"}' > $TMP_DIR/lambda_function.py
cd $TMP_DIR || exit
zip lambda.zip lambda_function.py


for FUNCTION_NAME in $FUNCTION_LIST; do
  echo -n $FUNCTION_NAME
  FUNCTION_NAME=$(echo $FUNCTION_NAME | tr -d '\r')
  LAMBDA_NAME="${PROJECT_NAME}-${ENVIRONMENT}-${FUNCTION_NAME}"
  echo -n $LAMBDA_NAME
  # Check if Lambda exists
  if aws lambda get-function --function-name $LAMBDA_NAME --profile $PROFILE >/dev/null 2>/dev/null; then
      echo " Lambda exist [IGNORING]"
  else
    # Create new Lambda function if it doesn't exist
    echo "[creating...]"
    aws lambda create-function \
      --function-name $LAMBDA_NAME --runtime python$PYTHON_VERSION \
      --role $AWS_LAMBDA_DEFAULT_ROLE \
      --handler lambda_function.lambda_handler \
      --zip-file fileb://lambda.zip \
      --profile $PROFILE >/dev/null
  fi
done

echo "Exit Code: 0"
exit 0
