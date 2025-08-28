#! /bin/bash

source ../../env.sh

FUNCTION_NAME_PART="url-add"

zip -r lambda.zip lambda_function.py

aws s3 cp lambda.zip s3://$AWS_S3_BUCKET_NAME/${PROJECT_NAME}-${ENVIRONMENT}-${FUNCTION_NAME_PART}.zip --profile ${PROFILE}

#aws lambda update-function-code --function-name ${FUNCTION_NAME}  --zip-file fileb://lambda.zip --profile ${PROFILE}

rm lambda.zip
