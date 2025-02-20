#! /bin/bash

PROFILE="lenie-ai-admin"
FUNCTION_NAME="lenie-url-add"

zip -r lambda.zip lambda_function.py


aws lambda update-function-code --function-name ${FUNCTION_NAME}  --zip-file fileb://lambda.zip --profile ${PROFILE}

rm lambda.zip
