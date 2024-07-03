#! /bin/bash

cp -r ../../library .

zip -r lambda.zip lambda_function.py library/

aws lambda update-function-code --function-name lenie_2_db  --zip-file fileb://lambda.zip --profile stalker-free-developer

rm -rf package/

exit 0
