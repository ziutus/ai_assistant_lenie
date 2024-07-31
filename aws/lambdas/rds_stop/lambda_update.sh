#! /bin/bash

PROFILE="lenie-ai-admin"

zip -r lambda.zip lambda_function.py


aws lambda update-function-code --function-name lenie-rds-stop  --zip-file fileb://lambda.zip --profile ${PROFILE}

rm lambda.zip
