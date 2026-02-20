#!/bin/bash
# Smoke test for the URL Add flow (API Gateway -> Lambda -> DynamoDB + SQS).
# Verifies that the deployed stack can accept a URL, process it through Lambda,
# and store the result in DynamoDB. Cleans up test data after verification.
#
# Usage:
#   ./smoke-test-url-add.sh -p lenie -s dev [-r us-east-1]
#
# Exit codes:
#   0 - smoke test passed
#   1 - test failed (API error, DynamoDB entry not found)
#   2 - prerequisites not met (tools missing, stack not deployed)
#
# Future: deploy.sh could call this script after deploying url-add stack.

set -euo pipefail

OPTIND=1
REGION="us-east-1"
STAGE=""
PROJECT_CODE=""

# --- Argument parsing (same pattern as deploy.sh) ---

show_help() {
  echo "Usage:
  $0 -p <PROJECT_CODE> -s <STAGE> [-r <REGION>] [-h]

  -p PROJECT_CODE  Project code (e.g. lenie)
  -s STAGE         Environment (e.g. dev)
  -r REGION        AWS region (default: $REGION)
  -h               Show this help

  Example:
    $0 -p lenie -s dev -r us-east-1
  "
  exit 2
}

while getopts "hp:s:r:" opt; do
  case "$opt" in
    h) show_help ;;
    p) PROJECT_CODE=$OPTARG ;;
    r) REGION=$OPTARG ;;
    s) STAGE=$OPTARG ;;
    *) show_help ;;
  esac
done

if [ -z "${PROJECT_CODE}" ]; then echo "ERROR: PROJECT_CODE is required (-p)"; show_help; fi
if [ -z "${STAGE}" ]; then echo "ERROR: STAGE is required (-s)"; show_help; fi

# --- Prerequisite checks ---

command -v aws > /dev/null 2>&1 || { echo >&2 "ERROR: aws cli not installed. Aborting."; exit 2; }
command -v jq  > /dev/null 2>&1 || { echo >&2 "ERROR: jq not installed. Aborting."; exit 2; }

STACK_NAME="${PROJECT_CODE}-${STAGE}-url-add"
TABLE_NAME="${PROJECT_CODE}_${STAGE}_documents"

echo "=== Smoke Test: URL Add Flow ==="
echo "Stack:  ${STACK_NAME}"
echo "Table:  ${TABLE_NAME}"
echo "Region: ${REGION}"
echo ""

# Check if the CF stack exists
if ! aws --region "${REGION}" cloudformation describe-stacks \
    --stack-name "${STACK_NAME}" > /dev/null 2>&1; then
  echo "ERROR: CloudFormation stack '${STACK_NAME}' not found. Is the stack deployed?"
  exit 2
fi

# --- Retrieve API endpoint and key from CloudFormation outputs ---

echo "Retrieving API endpoint and key from CloudFormation outputs..."

API_ENDPOINT=$(aws --region "${REGION}" cloudformation describe-stacks \
  --stack-name "${STACK_NAME}" \
  --query "Stacks[0].Outputs[?OutputKey=='ApiEndpoint'].OutputValue" \
  --output text)

API_KEY_ID=$(aws --region "${REGION}" cloudformation describe-stacks \
  --stack-name "${STACK_NAME}" \
  --query "Stacks[0].Outputs[?OutputKey=='ApiKeyID'].OutputValue" \
  --output text)

if [ -z "${API_ENDPOINT}" ] || [ "${API_ENDPOINT}" == "None" ]; then
  echo "ERROR: Could not retrieve ApiEndpoint from stack outputs."
  exit 1
fi

if [ -z "${API_KEY_ID}" ] || [ "${API_KEY_ID}" == "None" ]; then
  echo "ERROR: Could not retrieve ApiKeyID from stack outputs."
  exit 1
fi

API_KEY_VALUE=$(aws --region "${REGION}" apigateway get-api-key \
  --api-key "${API_KEY_ID}" \
  --include-value \
  --query "value" \
  --output text)

if [ -z "${API_KEY_VALUE}" ] || [ "${API_KEY_VALUE}" == "None" ]; then
  echo "ERROR: Could not retrieve API key value."
  exit 1
fi

echo "API Endpoint: ${API_ENDPOINT}"
echo "API Key ID:   ${API_KEY_ID}"
echo ""

# --- Generate test payload ---

TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%S)
TODAY=$(date -u +%Y-%m-%d)

# UUID generation: try uuidgen, fallback to python3
if command -v uuidgen > /dev/null 2>&1; then
  TEST_UUID=$(uuidgen | tr '[:upper:]' '[:lower:]')
elif command -v python3 > /dev/null 2>&1; then
  TEST_UUID=$(python3 -c "import uuid; print(uuid.uuid4())")
else
  echo "ERROR: Neither uuidgen nor python3 available for UUID generation."
  exit 2
fi

TEST_URL="https://test.lenie-ai.eu/smoke-test/${TIMESTAMP}/${TEST_UUID}"

PAYLOAD=$(jq -n \
  --arg url "${TEST_URL}" \
  --arg source "smoke-test" \
  --arg note "Automated smoke test - safe to delete" \
  '{
    url: $url,
    type: "link",
    source: $source,
    note: $note,
    title: "",
    language: "",
    text: "",
    html: "",
    paywall: false
  }')

echo "Test URL: ${TEST_URL}"
echo "Sending POST to ${API_ENDPOINT}..."

# --- Send POST request ---
# MSYS_NO_PATHCONV=1 prevents MSYS/Git Bash from mangling /v1/url_add path on Windows
HTTP_RESPONSE=$(MSYS_NO_PATHCONV=1 curl -s -w "\n%{http_code}" \
  -X POST "${API_ENDPOINT}" \
  -H "Content-Type: application/json" \
  -H "x-api-key: ${API_KEY_VALUE}" \
  -d "${PAYLOAD}")

HTTP_BODY=$(echo "${HTTP_RESPONSE}" | sed '$d')
HTTP_STATUS=$(echo "${HTTP_RESPONSE}" | tail -1)

echo "HTTP Status: ${HTTP_STATUS}"
echo "Response:    ${HTTP_BODY}"
echo ""

if [ "${HTTP_STATUS}" != "200" ]; then
  echo "FAILED: Expected HTTP 200, got ${HTTP_STATUS}"
  exit 1
fi

echo "API call succeeded. Waiting 3 seconds for DynamoDB write..."
sleep 3

# --- Verify DynamoDB entry ---

echo "Querying DynamoDB table '${TABLE_NAME}' for test entry..."

DYNAMO_RESULT=$(aws --region "${REGION}" dynamodb query \
  --table-name "${TABLE_NAME}" \
  --index-name "DateIndex" \
  --key-condition-expression "created_date = :d" \
  --filter-expression "#u = :url" \
  --expression-attribute-names '{"#u": "url"}' \
  --expression-attribute-values "{\":d\": {\"S\": \"${TODAY}\"}, \":url\": {\"S\": \"${TEST_URL}\"}}" \
  --output json)

ITEM_COUNT=$(echo "${DYNAMO_RESULT}" | jq '.Count')

if [ "${ITEM_COUNT}" -eq 0 ] 2>/dev/null; then
  echo "FAILED: Test entry not found in DynamoDB after 3 seconds."
  echo "The Lambda may not have written to DynamoDB, or the write is still in progress."
  exit 1
fi

echo "Found ${ITEM_COUNT} matching item(s) in DynamoDB."

# --- Cleanup: delete test entry ---

echo "Cleaning up test entry from DynamoDB..."

PK=$(echo "${DYNAMO_RESULT}" | jq -r '.Items[0].pk.S')
SK=$(echo "${DYNAMO_RESULT}" | jq -r '.Items[0].sk.S')

if [ -n "${PK}" ] && [ "${PK}" != "null" ] && [ -n "${SK}" ] && [ "${SK}" != "null" ]; then
  aws --region "${REGION}" dynamodb delete-item \
    --table-name "${TABLE_NAME}" \
    --key "{\"pk\": {\"S\": \"${PK}\"}, \"sk\": {\"S\": \"${SK}\"}}"
  echo "Test entry deleted (pk=${PK}, sk=${SK})."
else
  echo "WARNING: Could not extract pk/sk for cleanup. Manual cleanup may be needed."
  echo "Look for entries with source=smoke-test in table ${TABLE_NAME}."
fi

echo ""
echo "=== SMOKE TEST PASSED ==="
echo "Flow verified: API Gateway -> Lambda -> DynamoDB"
echo "Note: An SQS message was also sent (source=smoke-test). It will be processed or expire naturally."
exit 0
