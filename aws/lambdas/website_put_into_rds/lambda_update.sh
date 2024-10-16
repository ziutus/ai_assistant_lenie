#! /bin/bash

PROFILE="lenie-ai-admin"

zip -r lambda.zip lambda_function.py


aws lambda update-function-code --function-name lenie-webpage-put-link-rds  --zip-file fileb://lambda.zip  --profile ${PROFILE}
