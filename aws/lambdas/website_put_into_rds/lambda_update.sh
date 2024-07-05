#! /bin/bash

zip -r lambda.zip lambda_function.py


aws lambda update-function-code --function-name WebpagePutLink  --zip-file fileb://lambda.zip --profile stalker-free-developer
