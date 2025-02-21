#! /bin/bash

PROFILE="lenie-ai-admin"
FUNCTION_NAME_PART="url-add"
PROJECT="lenie"
STAGE="dev"

zip -r lambda.zip lambda_function.py

aws s3 cp lambda.zip s3://${PROJECT}-${STAGE}-cloudformation/${PROJECT}-${STAGE}-${FUNCTION_NAME_PART}.zip --profile ${PROFILE}

#aws lambda update-function-code --function-name ${FUNCTION_NAME}  --zip-file fileb://lambda.zip --profile ${PROFILE}

rm lambda.zip
