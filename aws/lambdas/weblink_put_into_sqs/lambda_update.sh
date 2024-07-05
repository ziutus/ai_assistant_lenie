#! /bin/bash

zip -r lambda.zip lambda_function.py


aws lambda update-function-code --function-name stalker-url-add  --zip-file fileb://lambda.zip --profile stalker-free-developer
