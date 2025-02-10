#! /bin/bash

PROFILE="lenie-ai-admin"

mkdir -p lambda_package
cd lambda_package
pip install requests -t .
cp ../lambda_function.py .
zip -r lambda_function.zip .

aws lambda update-function-code --function-name jenkins-start-job  --zip-file fileb://lambda_function.zip  --profile ${PROFILE}

cd ..
rm -rf lambda_package

exit 0