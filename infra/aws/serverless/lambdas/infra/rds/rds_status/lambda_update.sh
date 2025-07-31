#! /bin/bash
set -x
set -e

source ../../../../env.sh

FUNCTION_NAME="rds-status"
LAMBDA_NAME="${PROJECT_NAME}-${ENVIRONMENT}-${FUNCTION_NAME}"

zip -r lambda.zip lambda_function.py

aws lambda update-function-code --function-name $LAMBDA_NAME --zip-file fileb://lambda.zip --profile ${PROFILE} > /dev/null

rm lambda.zip
