#! /bin/bash

PROFILE="lenie-ai-admin"

cp -r ../../../library .

zip -r lambda.zip lambda_function.py library/

aws lambda update-function-code --function-name lenie_2_internet  --zip-file fileb://lambda.zip --profile ${PROFILE}

rm -rf library/
rm lambda.zip

exit 0