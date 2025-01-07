#!/bin/bash

set -e
#
# Brief description of your script
# Copyright 2025 ziutus

PROFILE="lenie-ai-admin"

zip -r lambda.zip lambda_function.py library/ package/


aws lambda update-function-code --function-name lenie_ses_excel_summary  --zip-file fileb://lambda.zip --profile ${PROFILE}

rm lambda.zip

