#!/bin/bash

PROFILE="lenie-ai-admin"
FUNCTION_NAME="lenie-manual-sqs-length"

cp -r ../../../library .

zip -r lambda.zip lambda_function.py library/

aws lambda update-function-code --function-name ${FUNCTION_NAME}  --zip-file fileb://lambda.zip --profile ${PROFILE}
#aws lambda update-function-code --function-name ${FUNCTION_NAME}  --zip-file fileb://lambda.zip --profile ${PROFILE}

rm -rf library/
rm lambda.zip

exit 0